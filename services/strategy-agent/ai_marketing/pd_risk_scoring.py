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
except ImportError:  # pragma: no cover - represented in availability metadata.
    load = None


SERVICE_DIR = Path(__file__).resolve().parents[1]
REPOSITORY_ROOT = Path(__file__).resolve().parents[3]
STRUCTURED_DIR = REPOSITORY_ROOT / "mock_data" / "structured"
DEFAULT_ARTIFACT_DIR = SERVICE_DIR / "artifacts" / "pd_risk_model"
MODEL_FILE = "pd_6m_model.joblib"


@dataclass
class TimeSeries:
    times: list[datetime]
    sums: list[float]

    def window_sum(self, as_of: datetime, days: int) -> float:
        left = bisect_left(self.times, as_of - timedelta(days=days))
        right = bisect_left(self.times, as_of)
        return self.sums[right] - self.sums[left]


class PDRiskScoreProvider:
    """Predict a customer's six-month overdue probability from pre-score bill history."""

    def __init__(self, *, artifact_dir: Path | None = None, structured_dir: Path | None = None) -> None:
        self.artifact_dir = artifact_dir or DEFAULT_ARTIFACT_DIR
        self.structured_dir = structured_dir or STRUCTURED_DIR
        self._artifact: dict[str, Any] | None = None
        self._availability_error: str | None = None
        self._customers: dict[str, dict[str, str | float]] | None = None
        self._series: dict[str, dict[str, TimeSeries]] | None = None

    @property
    def available(self) -> bool:
        self._load_artifact()
        return self._artifact is not None

    def warm_up(self) -> bool:
        if not self.available:
            return False
        self._load_customers()
        self._load_series()
        return True

    def score(self, *, customer_id: str, as_of: str | datetime | None = None) -> dict[str, Any]:
        score_time = _parse_time(as_of) if as_of else datetime.now().replace(microsecond=0)
        base = {
            "model_version": "pd_risk_v1",
            "customer_id": customer_id,
            "as_of": score_time.isoformat(sep=" "),
        }
        if not self.available:
            return {**base, "model_available": False, "reason": self._availability_error or "model_artifacts_unavailable"}
        customer = self._load_customers().get(customer_id)
        if customer is None:
            raise KeyError(f"Unknown customer_id: {customer_id}")
        features = self._make_feature_row(customer_id=customer_id, customer=customer, as_of=score_time)
        assert self._artifact is not None
        vectorizer = self._artifact["vectorizer"]
        scaler = self._artifact["scaler"]
        matrix = scaler.transform(vectorizer.transform([features]))
        probability = float(self._artifact["model"].predict_proba(matrix)[0][1])
        return {
            **base,
            "model_available": True,
            "feature_source": "project1_bill_record_pre_score_history",
            "horizon_days": int(self._artifact.get("horizon_days", 180)),
            "pd_6m": round(max(0.0, min(probability, 1.0)), 6),
        }

    def _load_artifact(self) -> None:
        if self._artifact is not None or self._availability_error is not None:
            return
        if load is None:
            self._availability_error = "joblib_not_installed"
            return
        path = self.artifact_dir / MODEL_FILE
        if not path.exists():
            self._availability_error = f"missing_artifact:{MODEL_FILE}"
            return
        try:
            self._artifact = load(path)
        except Exception as exc:  # pragma: no cover - depends on local artifact compatibility.
            self._availability_error = f"artifact_load_failed:{exc.__class__.__name__}"

    def _load_customers(self) -> dict[str, dict[str, str | float]]:
        if self._customers is not None:
            return self._customers
        basic = {row["cust_id"]: row for row in _read_csv(self.structured_dir / "customer_basic.csv")}
        cards_by_customer: dict[str, list[dict[str, str]]] = defaultdict(list)
        for row in _read_csv(self.structured_dir / "credit_card.csv"):
            cards_by_customer[row["cust_id"]].append(row)
        self._customers = {}
        for customer_id, row in basic.items():
            active_cards = [card for card in cards_by_customer[customer_id] if card.get("card_status") == "正常"]
            primary = next((card for card in active_cards if card.get("is_primary") == "True"), active_cards[0] if active_cards else {})
            self._customers[customer_id] = {
                "age": _as_float(row.get("age")),
                "income_level": row.get("income_level", "unknown"),
                "active_card_count": float(len(active_cards)),
                "max_credit_amount": max((_as_float(card.get("credit_amount")) for card in active_cards), default=0.0),
                "primary_card_level": primary.get("card_level", "unknown"),
            }
        return self._customers

    def _load_series(self) -> dict[str, dict[str, TimeSeries]]:
        if self._series is not None:
            return self._series
        card_to_customer = {row["card_no"]: row["cust_id"] for row in _read_csv(self.structured_dir / "credit_card.csv")}
        amount: dict[str, list[tuple[datetime, float]]] = defaultdict(list)
        count: dict[str, list[tuple[datetime, float]]] = defaultdict(list)
        overdue: dict[str, list[tuple[datetime, float]]] = defaultdict(list)
        min_payment: dict[str, list[tuple[datetime, float]]] = defaultdict(list)
        for row in _read_csv(self.structured_dir / "bill_record.csv"):
            customer_id = card_to_customer.get(row.get("card_no", ""))
            if not customer_id:
                continue
            due_date = _parse_time(row["due_date"])
            amount[customer_id].append((due_date, max(0.0, _as_float(row.get("bill_amount")))))
            count[customer_id].append((due_date, 1.0))
            if row.get("payment_status") == "逾期":
                overdue[customer_id].append((due_date, 1.0))
            if row.get("is_min_payment") == "True":
                min_payment[customer_id].append((due_date, 1.0))
        self._series = {
            "amount": _build_series(amount),
            "count": _build_series(count),
            "overdue": _build_series(overdue),
            "min_payment": _build_series(min_payment),
        }
        return self._series

    def _make_feature_row(self, *, customer_id: str, customer: dict[str, str | float], as_of: datetime) -> dict[str, str | float]:
        series = self._load_series()
        amount_90d = _series_value(series["amount"], customer_id, as_of, 90)
        amount_180d = _series_value(series["amount"], customer_id, as_of, 180)
        count_180d = _series_value(series["count"], customer_id, as_of, 180)
        max_credit = max(float(customer["max_credit_amount"]), 1.0)
        return {
            "age": float(customer["age"]),
            "income_level": str(customer["income_level"]),
            "active_card_count": float(customer["active_card_count"]),
            "max_credit_amount": float(customer["max_credit_amount"]),
            "primary_card_level": str(customer["primary_card_level"]),
            "bill_amount_90d": amount_90d,
            "bill_amount_180d": amount_180d,
            "bill_count_180d": count_180d,
            "average_bill_amount_180d": amount_180d / count_180d if count_180d else 0.0,
            "utilization_proxy_90d": amount_90d / max_credit,
            "overdue_bills_180d": _series_value(series["overdue"], customer_id, as_of, 180),
            "overdue_bills_365d": _series_value(series["overdue"], customer_id, as_of, 365),
            "min_payment_bills_180d": _series_value(series["min_payment"], customer_id, as_of, 180),
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


def _series_value(series: dict[str, TimeSeries], customer_id: str, as_of: datetime, days: int) -> float:
    item = series.get(customer_id)
    return item.window_sum(as_of, days) if item else 0.0


def _parse_time(value: str | datetime) -> datetime:
    if isinstance(value, datetime):
        return value.replace(tzinfo=None)
    return datetime.fromisoformat(value.replace("Z", "+00:00")).replace(tzinfo=None)


def _as_float(value: object) -> float:
    try:
        return float(value or 0.0)
    except (TypeError, ValueError):
        return 0.0
