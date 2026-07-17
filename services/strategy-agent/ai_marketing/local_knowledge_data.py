from __future__ import annotations

import csv
from collections import defaultdict
from datetime import datetime
from pathlib import Path
from typing import Any


REPOSITORY_ROOT = Path(__file__).resolve().parents[3]
STRUCTURED_DATA_DIR = REPOSITORY_ROOT / "mock_data" / "structured"

CHANNELS = {
    "app_push": {"consent_field": "push_consent", "source_name": "APP Push"},
    "sms": {"consent_field": "sms_consent", "source_name": "\u77ed\u4fe1"},
    "wechat": {"consent_field": "wechat_consent", "source_name": "\u5fae\u4fe1\u516c\u4f17\u53f7"},
}
CITY_TIERS = {
    "\u5317\u4eac": 1,
    "\u4e0a\u6d77": 1,
    "\u5e7f\u5dde": 1,
    "\u6df1\u5733": 1,
    "\u676d\u5dde": 2,
    "\u6210\u90fd": 2,
    "\u5357\u4eac": 2,
    "\u6b66\u6c49": 2,
    "\u897f\u5b89": 2,
    "\u91cd\u5e86": 2,
}


class LocalKnowledgeData:
    """Adapt Project A's local CSV files to the Strategy Agent insight contract."""

    def __init__(self, structured_dir: Path | None = None) -> None:
        self.structured_dir = structured_dir or STRUCTURED_DATA_DIR
        self._profiles: dict[str, dict[str, str]] | None = None
        self._consents: dict[str, dict[str, str]] | None = None
        self._contacts: dict[str, list[dict[str, str]]] | None = None
        self._channel_context: dict[str, Any] | None = None

    def build_customer_insight(
        self,
        *,
        campaign_id: str = "LOCAL_REAL_DATA",
        target_product: str = "installment",
        evaluation_time: str | None = None,
        limit: int | None = None,
    ) -> dict[str, Any]:
        profiles = self._load_profiles()
        consents = self._load_consents()
        contacts = self._load_contacts()
        customer_ids = sorted(profiles)
        if limit is not None:
            customer_ids = customer_ids[: max(0, limit)]

        return {
            "campaign_id": campaign_id,
            "target_product": target_product,
            "evaluation_time": evaluation_time or datetime.now().astimezone().isoformat(),
            "source": "project1_local_csv",
            "data_version": "2026-07-16-project1",
            "channel_context": self._load_channel_context(),
            "customers": [
                self._to_insight_customer(
                    profile=profiles[customer_id],
                    consent=consents.get(customer_id, {}),
                    contacts=contacts.get(customer_id, []),
                )
                for customer_id in customer_ids
            ],
        }

    def _load_profiles(self) -> dict[str, dict[str, str]]:
        if self._profiles is None:
            self._profiles = _read_csv_indexed(self.structured_dir / "customer_profile.csv", "cust_id")
        return self._profiles

    def _load_consents(self) -> dict[str, dict[str, str]]:
        if self._consents is None:
            self._consents = _read_csv_indexed(self.structured_dir / "customer_consent.csv", "cust_id")
        return self._consents

    def _load_contacts(self) -> dict[str, list[dict[str, str]]]:
        if self._contacts is None:
            grouped: dict[str, list[dict[str, str]]] = defaultdict(list)
            for row in _read_csv(self.structured_dir / "contact_history.csv"):
                grouped[row["cust_id"]].append(row)
            self._contacts = dict(grouped)
        return self._contacts

    def _load_channel_context(self) -> dict[str, Any]:
        if self._channel_context is not None:
            return self._channel_context
        config_by_name = {
            row["channel_name"].strip(): row for row in _read_csv(self.structured_dir / "channel_config.csv")
        }
        statuses: dict[str, str] = {}
        available_channels: list[str] = []
        for canonical, definition in CHANNELS.items():
            source = config_by_name.get(definition["source_name"])
            available = bool(source) and source.get("status") == "active"
            statuses[canonical] = "available" if available else "unavailable"
            if available:
                available_channels.append(canonical)
        self._channel_context = {
            "available_channels": available_channels,
            "channel_status": statuses,
        }
        return self._channel_context

    def _to_insight_customer(
        self,
        *,
        profile: dict[str, str],
        consent: dict[str, str],
        contacts: list[dict[str, str]],
    ) -> dict[str, Any]:
        unsubscribed = _split_csv_values(consent.get("unsubscribe_channels", ""))
        channel_consents = {
            canonical: _as_bool(consent.get(definition["consent_field"]))
            and definition["source_name"] not in unsubscribed
            for canonical, definition in CHANNELS.items()
        }
        consent_risk = consent.get("risk_level") or profile.get("risk_risk_level", "low")
        blacklist = _as_bool(consent.get("blacklist_flag")) or _as_bool(profile.get("risk_blacklist_flag"))
        if blacklist:
            consent_risk = "blacklist"
        contact_history = [
            {
                "channel": _canonical_channel(event.get("channel", "")),
                "contact_type": event.get("contact_type", ""),
                "contacted_at": event.get("contact_time", ""),
                "status": event.get("status", ""),
            }
            for event in contacts
            if _canonical_channel(event.get("channel", "")) in CHANNELS
        ]
        recent_counts = {
            channel: sum(
                event["channel"] == channel and event["contact_type"] == "marketing"
                for event in contact_history
            )
            for channel in CHANNELS
        }
        complaint_count = _as_int(consent.get("complaint_count_90d"))
        credit_amount = _as_float(profile.get("account_total_credit_amount"))
        monthly_spend = _as_float(profile.get("value_monthly_avg_consumption"))

        customer_profile = {
            "oneid": profile.get("oneid", ""),
            "age": _as_int(profile.get("demographics_age"), default=35),
            "city_tier": CITY_TIERS.get(profile.get("demographics_city", ""), 3),
            "monthly_spend": monthly_spend,
            "credit_limit_usage": min(1.0, monthly_spend / credit_amount) if credit_amount else 0.0,
            "marketing_consent": _as_bool(consent.get("marketing_consent")),
            "personalization_consent": _as_bool(consent.get("personalization_consent")),
            "dnc_list": _as_bool(consent.get("dnc_list")),
            "do_not_contact_signal": _as_bool(consent.get("do_not_contact_signal")),
            "blacklist_flag": blacklist,
            "risk_level": consent_risk,
            "complaint_count_90d": complaint_count,
            "complaint_risk": min(1.0, complaint_count / 3),
            "value_level": consent.get("value_level") or profile.get("value_value_level", ""),
            "lifecycle_stage": profile.get("lifecycle_stage", ""),
            "churn_risk_score": _as_int(profile.get("risk_churn_risk_score")),
            "owned_products": [profile["account_product_name"]] if profile.get("account_product_name") else [],
            "channel_consents": channel_consents,
            "recent_contact_count": len(contact_history),
            "recent_contact_count_by_channel": recent_counts,
            "tags": _build_tags(profile, consent),
        }
        return {
            "customer_id": profile["cust_id"],
            "customer_profile": customer_profile,
            "contact_history": contact_history,
            "intent_vector": {"top_intents": []},
            "event_sequence": [],
        }


def _read_csv(path: Path) -> list[dict[str, str]]:
    with path.open(encoding="utf-8-sig", newline="") as file:
        return list(csv.DictReader(file))


def _read_csv_indexed(path: Path, key: str) -> dict[str, dict[str, str]]:
    return {row[key]: row for row in _read_csv(path) if row.get(key)}


def _as_bool(value: str | None) -> bool:
    return str(value).strip().lower() in {"true", "1", "yes"}


def _as_int(value: str | None, *, default: int = 0) -> int:
    try:
        return int(float(value or default))
    except (TypeError, ValueError):
        return default


def _as_float(value: str | None) -> float:
    try:
        return float(value or 0)
    except (TypeError, ValueError):
        return 0.0


def _split_csv_values(value: str) -> set[str]:
    return {item.strip() for item in value.split(",") if item.strip()}


def _canonical_channel(value: str) -> str:
    normalized = value.strip()
    for canonical, definition in CHANNELS.items():
        if normalized == definition["source_name"]:
            return canonical
    return normalized


def _build_tags(profile: dict[str, str], consent: dict[str, str]) -> list[str]:
    tags = [profile.get("lifecycle_stage", ""), consent.get("value_level", "")]
    if profile.get("mid_term_30d_consumption_trend") == "up":
        tags.append("consumption_growth")
    if profile.get("long_term_90d_dormancy_risk") == "high":
        tags.append("dormant_risk")
    return [tag for tag in tags if tag]
