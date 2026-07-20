from __future__ import annotations

import csv
from bisect import bisect_left
from collections import defaultdict
from dataclasses import dataclass
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any

try:
    from joblib import load
except ImportError:  # pragma: no cover - handled by availability metadata.
    load = None


SERVICE_DIR = Path(__file__).resolve().parents[1]
REPOSITORY_ROOT = Path(__file__).resolve().parents[3]
STRUCTURED_DIR = REPOSITORY_ROOT / "mock_data" / "structured"
MAPPING_PATH = SERVICE_DIR / "config" / "campaign_offer_mapping.csv"
DEFAULT_ARTIFACT_DIR = SERVICE_DIR / "artifacts" / "historical_modeling_v2"

MODEL_FILES = {
    "open": "open_model.joblib",
    "click": "click_model.joblib",
    "conversion": "conversion_model.joblib",
    "unsubscribe": "unsubscribe_model.joblib",
}
CHANNEL_SOURCE_NAMES = {
    "app_push": "APP Push",
    "sms": "\u77ed\u4fe1",
    "wechat": "\u5fae\u4fe1\u516c\u4f17\u53f7",
}


@dataclass
class TimeSeries:
    times: list[datetime]
    sums: list[float]

    def window_sum(self, as_of: datetime, days: int) -> float:
        left = bisect_left(self.times, as_of - timedelta(days=days))
        right = bisect_left(self.times, as_of)
        return self.sums[right] - self.sums[left]


class HistoricalModelScoreProvider:
    """Score an eligible customer x campaign x channel touch with the V2 artifacts.

    Features are rebuilt from Project A's raw records using only events before the
    requested touch time. This keeps online inference aligned with model training.
    """

    def __init__(
        self,
        *,
        artifact_dir: Path | None = None,
        structured_dir: Path | None = None,
        mapping_path: Path | None = None,
    ) -> None:
        self.artifact_dir = artifact_dir or DEFAULT_ARTIFACT_DIR
        self.structured_dir = structured_dir or STRUCTURED_DIR
        self.mapping_path = mapping_path or MAPPING_PATH
        self._models: dict[str, dict[str, Any]] | None = None
        self._availability_error: str | None = None
        self._customers: dict[str, dict[str, str | float]] | None = None
        self._mappings: dict[str, dict[str, str]] | None = None
        self._channel_costs: dict[str, float] | None = None
        self._series: dict[str, dict[str, TimeSeries]] | None = None

    @property
    def available(self) -> bool:
        self._load_models()
        return self._models is not None

    def score(
        self,
        *,
        customer_id: str,
        campaign_id: str,
        channel: str,
        touch_time: str | datetime | None = None,
    ) -> dict[str, Any]:
        source_channel = _source_channel(channel)
        as_of = _parse_time(touch_time) if touch_time else datetime.now().replace(microsecond=0)
        base = {
            "model_version": "historical_response_v2",
            "customer_id": customer_id,
            "campaign_id": campaign_id,
            "channel": _canonical_channel(channel),
            "touch_time": as_of.isoformat(sep=" "),
        }
        if not self.available:
            return {
                **base,
                "model_available": False,
                "reason": self._availability_error or "model_artifacts_unavailable",
            }

        customer = self._load_customers().get(customer_id)
        if customer is None:
            raise KeyError(f"Unknown customer_id: {customer_id}")
        mapping = self._load_mappings().get(campaign_id)
        if mapping is None:
            raise ValueError(f"Unknown campaign_id: {campaign_id}")

        features = self._make_feature_row(
            customer_id=customer_id,
            customer=customer,
            campaign_id=campaign_id,
            channel=source_channel,
            mapping=mapping,
            touch_time=as_of,
        )
        probabilities = {
            f"p_{name}": round(self._predict(name, features), 6)
            for name in MODEL_FILES
        }
        return {
            **base,
            "model_available": True,
            "feature_source": "project1_pre_touch_raw_data",
            "probabilities": probabilities,
        }

    def _load_models(self) -> None:
        if self._models is not None or self._availability_error is not None:
            return
        if load is None:
            self._availability_error = "joblib_not_installed"
            return
        missing = [name for name, filename in MODEL_FILES.items() if not (self.artifact_dir / filename).exists()]
        if missing:
            self._availability_error = "missing_artifacts:" + ",".join(missing)
            return
        try:
            self._models = {
                name: load(self.artifact_dir / filename)
                for name, filename in MODEL_FILES.items()
            }
        except Exception as exc:  # pragma: no cover - depends on local artifact compatibility.
            self._availability_error = f"artifact_load_failed:{exc.__class__.__name__}"

    def _predict(self, model_name: str, features: dict[str, str | float]) -> float:
        assert self._models is not None
        artifact = self._models[model_name]
        vectorizer = artifact["vectorizer"]
        scaler = artifact["scaler"]
        model = artifact["model"]
        matrix = scaler.transform(vectorizer.transform([features]))
        return float(model.predict_proba(matrix)[0][1])

    def _load_customers(self) -> dict[str, dict[str, str | float]]:
        if self._customers is not None:
            return self._customers
        basic = {row["cust_id"]: row for row in _read_csv(self.structured_dir / "customer_basic.csv")}
        cards_by_customer: dict[str, list[dict[str, str]]] = defaultdict(list)
        for card in _read_csv(self.structured_dir / "credit_card.csv"):
            cards_by_customer[card["cust_id"]].append(card)
        self._customers = {}
        for customer_id, row in basic.items():
            active_cards = [card for card in cards_by_customer[customer_id] if card["card_status"] == "\u6b63\u5e38"]
            self._customers[customer_id] = {
                "age": _as_float(row.get("age")),
                "city": row.get("city", "unknown"),
                "occupation": row.get("occupation", "unknown"),
                "income_level": row.get("income_level", "unknown"),
                "education": row.get("education", "unknown"),
                "active_card_count": float(len(active_cards)),
                "max_credit_amount": max((_as_float(card.get("credit_amount")) for card in active_cards), default=0.0),
            }
        return self._customers

    def _load_mappings(self) -> dict[str, dict[str, str]]:
        if self._mappings is None:
            self._mappings = {row["campaign_id"]: row for row in _read_csv(self.mapping_path)}
        return self._mappings

    def _load_channel_costs(self) -> dict[str, float]:
        if self._channel_costs is None:
            self._channel_costs = {
                row["channel_name"]: _as_float(row.get("cost_per_send"))
                for row in _read_csv(self.structured_dir / "channel_config.csv")
            }
        return self._channel_costs

    def _load_series(self) -> dict[str, dict[str, TimeSeries]]:
        if self._series is not None:
            return self._series

        card_to_customer = {
            row["card_no"]: row["cust_id"] for row in _read_csv(self.structured_dir / "credit_card.csv")
        }
        spend: dict[str, list[tuple[datetime, float]]] = defaultdict(list)
        transactions: dict[str, list[tuple[datetime, float]]] = defaultdict(list)
        for row in _read_csv(self.structured_dir / "transaction_log.csv"):
            if row.get("txn_type") != "\u6d88\u8d39" or _as_float(row.get("amount")) <= 0:
                continue
            customer_id = card_to_customer.get(row.get("card_no", ""))
            if customer_id:
                event_time = _parse_time(row["timestamp"])
                spend[customer_id].append((event_time, _as_float(row.get("amount"))))
                transactions[customer_id].append((event_time, 1.0))

        open_to_oneid = {
            row["id_value"]: row["oneid"]
            for row in _read_csv(self.structured_dir / "id_mapping.csv")
            if row.get("id_type") == "open_id"
        }
        oneid_to_customer = {
            row["oneid"]: row["id_value"]
            for row in _read_csv(self.structured_dir / "id_mapping.csv")
            if row.get("id_type") == "cust_id"
        }
        app_events: dict[str, list[tuple[datetime, float]]] = defaultdict(list)
        app_searches: dict[str, list[tuple[datetime, float]]] = defaultdict(list)
        for row in _read_csv(self.structured_dir / "app_events.csv"):
            customer_id = oneid_to_customer.get(open_to_oneid.get(row.get("open_id", ""), ""))
            if customer_id:
                event_time = _parse_time(row["timestamp"])
                app_events[customer_id].append((event_time, 1.0))
                if row.get("event_type") == "\u641c\u7d22" or row.get("search_keyword", "").strip():
                    app_searches[customer_id].append((event_time, 1.0))

        overdue: dict[str, list[tuple[datetime, float]]] = defaultdict(list)
        min_payment: dict[str, list[tuple[datetime, float]]] = defaultdict(list)
        for row in _read_csv(self.structured_dir / "bill_record.csv"):
            customer_id = card_to_customer.get(row.get("card_no", ""))
            if not customer_id:
                continue
            due_time = _parse_time(row["due_date"])
            if row.get("payment_status") == "\u903e\u671f":
                overdue[customer_id].append((due_time, 1.0))
            if row.get("is_min_payment") == "True":
                min_payment[customer_id].append((due_time, 1.0))

        contacts: dict[str, list[tuple[datetime, float]]] = defaultdict(list)
        clicks: dict[str, list[tuple[datetime, float]]] = defaultdict(list)
        unsubscribes: dict[str, list[tuple[datetime, float]]] = defaultdict(list)
        for row in _read_csv(self.structured_dir / "contact_history.csv"):
            if row.get("contact_type") != "marketing" or not row.get("campaign_id"):
                continue
            event_time = _parse_time(row["contact_time"])
            customer_id = row["cust_id"]
            contacts[customer_id].append((event_time, 1.0))
            if row.get("status") == "clicked":
                clicks[customer_id].append((event_time, 1.0))
            if row.get("status") == "unsubscribed":
                unsubscribes[customer_id].append((event_time, 1.0))

        self._series = {
            "spend": _build_series(spend),
            "transactions": _build_series(transactions),
            "app_events": _build_series(app_events),
            "app_searches": _build_series(app_searches),
            "overdue": _build_series(overdue),
            "min_payment": _build_series(min_payment),
            "contacts": _build_series(contacts),
            "clicks": _build_series(clicks),
            "unsubscribes": _build_series(unsubscribes),
        }
        return self._series

    def _make_feature_row(
        self,
        *,
        customer_id: str,
        customer: dict[str, str | float],
        campaign_id: str,
        channel: str,
        mapping: dict[str, str],
        touch_time: datetime,
    ) -> dict[str, str | float]:
        series = self._load_series()
        contacts_90d = _series_value(series["contacts"], customer_id, touch_time, 90)
        clicks_90d = _series_value(series["clicks"], customer_id, touch_time, 90)
        return {
            "age": customer["age"],
            "city": str(customer["city"]),
            "occupation": str(customer["occupation"]),
            "income_level": str(customer["income_level"]),
            "education": str(customer["education"]),
            "active_card_count": customer["active_card_count"],
            "max_credit_amount": customer["max_credit_amount"],
            "campaign_id": campaign_id,
            "channel": channel,
            "strategy_object_type": mapping["strategy_object_type"],
            "product_scope": mapping["product_scope"],
            "benefit_category": mapping["benefit_category"],
            "objective": mapping["objective"],
            "benefit_unit_cost_proxy": _as_float(mapping.get("benefit_unit_cost_proxy")),
            "touch_cost": self._load_channel_costs().get(channel, 0.0),
            "touch_hour": float(touch_time.hour),
            "touch_weekday": float(touch_time.weekday()),
            "touch_month": float(touch_time.month),
            "spend_7d": _series_value(series["spend"], customer_id, touch_time, 7),
            "spend_30d": _series_value(series["spend"], customer_id, touch_time, 30),
            "spend_90d": _series_value(series["spend"], customer_id, touch_time, 90),
            "txn_count_30d": _series_value(series["transactions"], customer_id, touch_time, 30),
            "txn_count_90d": _series_value(series["transactions"], customer_id, touch_time, 90),
            "app_events_7d": _series_value(series["app_events"], customer_id, touch_time, 7),
            "app_events_30d": _series_value(series["app_events"], customer_id, touch_time, 30),
            "app_searches_30d": _series_value(series["app_searches"], customer_id, touch_time, 30),
            "marketing_contacts_7d": _series_value(series["contacts"], customer_id, touch_time, 7),
            "marketing_contacts_30d": _series_value(series["contacts"], customer_id, touch_time, 30),
            "marketing_clicks_90d": clicks_90d,
            "historical_click_rate_90d": clicks_90d / contacts_90d if contacts_90d else 0.0,
            "historical_unsubscribes_90d": _series_value(series["unsubscribes"], customer_id, touch_time, 90),
            "overdue_bills_180d": _series_value(series["overdue"], customer_id, touch_time, 180),
            "min_payment_bills_180d": _series_value(series["min_payment"], customer_id, touch_time, 180),
        }


def _read_csv(path: Path) -> list[dict[str, str]]:
    with path.open(encoding="utf-8-sig", newline="") as handle:
        return list(csv.DictReader(handle))


def _build_series(events: dict[str, list[tuple[datetime, float]]]) -> dict[str, TimeSeries]:
    result: dict[str, TimeSeries] = {}
    for customer_id, rows in events.items():
        rows.sort(key=lambda item: item[0])
        times: list[datetime] = []
        sums = [0.0]
        for event_time, value in rows:
            times.append(event_time)
            sums.append(sums[-1] + value)
        result[customer_id] = TimeSeries(times=times, sums=sums)
    return result


def _series_value(series_by_customer: dict[str, TimeSeries], customer_id: str, as_of: datetime, days: int) -> float:
    series = series_by_customer.get(customer_id)
    return series.window_sum(as_of, days) if series else 0.0


def _source_channel(value: str) -> str:
    normalized = value.strip()
    return CHANNEL_SOURCE_NAMES.get(normalized, normalized)


def _canonical_channel(value: str) -> str:
    normalized = value.strip()
    for canonical, source in CHANNEL_SOURCE_NAMES.items():
        if normalized in {canonical, source}:
            return canonical
    return normalized


def _parse_time(value: str | datetime) -> datetime:
    if isinstance(value, datetime):
        return value.replace(tzinfo=None)
    return datetime.fromisoformat(value.replace("Z", "+00:00")).replace(tzinfo=None)


def _as_float(value: object) -> float:
    try:
        return float(value or 0)
    except (TypeError, ValueError):
        return 0.0
