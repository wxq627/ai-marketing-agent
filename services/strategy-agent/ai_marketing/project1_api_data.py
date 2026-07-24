from __future__ import annotations

import json
import os
from datetime import datetime
from pathlib import Path
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from .local_knowledge_data import CHANNELS, CITY_TIERS, LocalKnowledgeData


PROJECT1_CHANNEL_CODES = {
    "CH_PUSH": "app_push",
    "CH_SMS": "sms",
    "CH_WECHAT": "wechat",
    "CH_EMAIL": "email",
    "CH_PHONE": "phone",
}
LOCAL_ENV_FILE = Path(__file__).resolve().parents[1] / ".env"


class Project1ApiKnowledgeData(LocalKnowledgeData):
    """Use Project A's API for strategy inputs, with a local demo fallback.

    The superclass remains the fallback because the historical response models
    are trained with the local raw-event feature schema. Strategy customer
    selection and channel context, however, are read from Project A whenever
    its FastAPI service is available.
    """

    def __init__(
        self,
        *,
        base_url: str | None = None,
        timeout_seconds: float | None = None,
        page_size: int = 500,
    ) -> None:
        super().__init__()
        _load_local_project1_env()
        self.base_url = (base_url or os.getenv("PROJECT1_API_BASE_URL", "http://127.0.0.1:8000")).rstrip("/")
        self.timeout_seconds = timeout_seconds or float(os.getenv("PROJECT1_API_TIMEOUT_SECONDS", "8"))
        self.page_size = max(1, min(page_size, 1000))
        self._remote_oneid_to_customer_id: dict[str, str] = {}
        self._last_remote_error = ""

    @property
    def integration_status(self) -> dict[str, Any]:
        """Expose the configured upstream without leaking any customer records."""
        return {
            "provider": "project1_api_with_local_fallback",
            "project1_api_base_url": self.base_url,
            "last_remote_error": self._last_remote_error or None,
        }

    def check_upstream(self) -> dict[str, Any]:
        """Return a small health summary for the B-side integration check."""
        try:
            health = self._get_json("/api/v1/health")
            self._last_remote_error = ""
            return {
                **self.integration_status,
                "connected": True,
                "upstream_health": health,
            }
        except Project1ApiUnavailable as exc:
            self._last_remote_error = str(exc)
            return {**self.integration_status, "connected": False, "upstream_health": None}

    def build_customer_insight(
        self,
        *,
        campaign_id: str = "LOCAL_REAL_DATA",
        target_product: str = "installment",
        evaluation_time: str | None = None,
        limit: int | None = None,
    ) -> dict[str, Any]:
        try:
            return self._build_remote_customer_insight(
                campaign_id=campaign_id,
                target_product=target_product,
                evaluation_time=evaluation_time,
                limit=limit,
            )
        except Project1ApiUnavailable as exc:
            self._last_remote_error = str(exc)
            payload = super().build_customer_insight(
                campaign_id=campaign_id,
                target_product=target_product,
                evaluation_time=evaluation_time,
                limit=limit,
            )
            payload["source"] = "project1_local_csv_fallback"
            payload["upstream"] = {
                "provider": "project1_api",
                "base_url": self.base_url,
                "status": "unavailable_fallback_used",
                "reason": self._last_remote_error,
            }
            return payload

    def build_customer_insight_for_oneid(
        self,
        oneid: str,
        *,
        target_product: str = "installment",
        evaluation_time: str | None = None,
    ) -> dict[str, Any] | None:
        normalized_oneid = oneid.strip()
        if not normalized_oneid:
            return None
        try:
            customers = self._search_customers({"oneids": [normalized_oneid], "page": 1, "page_size": 1})
            if not customers:
                return None
            channel_context = self._remote_channel_context()
            customer = self._to_api_insight_customer(customers[0])
            self._remote_oneid_to_customer_id[normalized_oneid] = customer["customer_id"]
            return {
                "campaign_id": "ONLINE_PERSONALIZATION",
                "target_product": target_product,
                "evaluation_time": evaluation_time or datetime.now().astimezone().isoformat(),
                "source": "project1_api",
                "data_version": "project1_api_v1",
                "channel_context": channel_context,
                "customers": [customer],
            }
        except Project1ApiUnavailable as exc:
            self._last_remote_error = str(exc)
            return super().build_customer_insight_for_oneid(
                normalized_oneid,
                target_product=target_product,
                evaluation_time=evaluation_time,
            )

    def customer_id_for_oneid(self, oneid: str) -> str | None:
        normalized_oneid = oneid.strip()
        if normalized_oneid in self._remote_oneid_to_customer_id:
            return self._remote_oneid_to_customer_id[normalized_oneid]
        try:
            customers = self._search_customers({"oneids": [normalized_oneid], "page": 1, "page_size": 1})
            if customers:
                customer_id = str(customers[0].get("cust_id", ""))
                if customer_id:
                    self._remote_oneid_to_customer_id[normalized_oneid] = customer_id
                    return customer_id
        except Project1ApiUnavailable as exc:
            self._last_remote_error = str(exc)
        return super().customer_id_for_oneid(normalized_oneid)

    def _build_remote_customer_insight(
        self,
        *,
        campaign_id: str,
        target_product: str,
        evaluation_time: str | None,
        limit: int | None,
    ) -> dict[str, Any]:
        channel_context = self._remote_channel_context()
        customers: list[dict[str, Any]] = []
        page = 1
        total = None
        maximum = limit if limit is not None else None

        while total is None or len(customers) < total:
            if maximum is not None and len(customers) >= maximum:
                break
            response = self._post_json(
                "/api/v1/customer/search",
                {"page": page, "page_size": self.page_size, "exclude_dnc": True, "exclude_blacklist": True},
            )
            raw_customers = response.get("customers", [])
            if not isinstance(raw_customers, list):
                raise Project1ApiUnavailable("invalid_customer_search_response")
            total = int(response.get("total", len(raw_customers)))
            customers.extend(self._to_api_insight_customer(item) for item in raw_customers if isinstance(item, dict))
            if not raw_customers:
                break
            page += 1

        if maximum is not None:
            customers = customers[: max(0, maximum)]
        for customer in customers:
            profile = customer["customer_profile"]
            if profile.get("oneid"):
                self._remote_oneid_to_customer_id[str(profile["oneid"])] = customer["customer_id"]
        return {
            "campaign_id": campaign_id,
            "target_product": target_product,
            "evaluation_time": evaluation_time or datetime.now().astimezone().isoformat(),
            "source": "project1_api",
            "data_version": "project1_api_v1",
            "channel_context": channel_context,
            "customers": customers,
            "upstream": {
                "provider": "project1_api",
                "base_url": self.base_url,
                "customer_endpoint": "/api/v1/customer/search",
                "channel_endpoint": "/api/v1/channels/context",
                "frequency_control_endpoint": "/api/v1/customer/frequency-check",
                "frequency_control_status": "available_for_pre_delivery_check",
            },
        }

    def _remote_channel_context(self) -> dict[str, Any]:
        payload = self._get_json("/api/v1/channels/context")
        rows = payload.get("channels", [])
        if not isinstance(rows, list):
            raise Project1ApiUnavailable("invalid_channel_context_response")
        by_name = {str(row.get("name", "")).strip(): row for row in rows if isinstance(row, dict)}
        by_canonical = {
            PROJECT1_CHANNEL_CODES.get(str(row.get("code", "")).strip()): row
            for row in rows
            if isinstance(row, dict) and PROJECT1_CHANNEL_CODES.get(str(row.get("code", "")).strip())
        }
        available_channels: list[str] = []
        statuses: dict[str, str] = {}
        metrics: dict[str, dict[str, float]] = {}
        for canonical, definition in CHANNELS.items():
            row = by_canonical.get(canonical) or by_name.get(definition["source_name"])
            available = bool(row) and str(row.get("status", "")).lower() == "active"
            statuses[canonical] = "available" if available else "unavailable"
            if not available or row is None:
                continue
            available_channels.append(canonical)
            metrics[canonical] = {
                "cost_per_send": _number(row.get("cost_per_send")),
                "daily_capacity": int(_number(row.get("daily_capacity"))),
                "avg_open_rate": _number(row.get("avg_open_rate")),
                "avg_click_rate": _number(row.get("avg_click_rate")),
            }
        if not available_channels:
            raise Project1ApiUnavailable("project1_returned_no_active_channels")
        return {
            "available_channels": available_channels,
            "channel_status": statuses,
            "channel_metrics": metrics,
        }

    def _to_api_insight_customer(self, item: dict[str, Any]) -> dict[str, Any]:
        profile = _mapping(item.get("profile"))
        account = _mapping(item.get("account"))
        consumption = _mapping(item.get("consumption"))
        risk = _mapping(item.get("risk"))
        tags = _mapping(item.get("tags"))
        consent = _mapping(item.get("consent"))
        intent = _mapping(item.get("intent"))
        raw_intents = intent.get("intents")
        top_intents = _top_intents(raw_intents, str(intent.get("primary_intent", "")))
        activity_score = _number(consumption.get("activity_score"))
        monthly_spend = _number(consumption.get("monthly_avg"))
        credit_amount = _number(account.get("total_credit_amount"))
        complaint_count = int(_number(consent.get("complaint_count_90d")))
        marketing_consent = bool(consent.get("marketing_consent", False))
        channel_consents = {
            canonical: bool(consent.get(definition["consent_field"], False))
            for canonical, definition in CHANNELS.items()
        }
        primary_intent = str(intent.get("primary_intent", ""))
        customer_id = str(item.get("cust_id", ""))
        recent_behavior_signals = [
            *self._load_recent_behavior_signals().get(customer_id, []),
            *[
                str(value)
                for value in (tags.get("significant_signals"), tags.get("search_keywords_7d"))
                if value
            ],
        ]
        customer_profile = {
            "oneid": str(item.get("oneid", "")),
            "city": str(profile.get("city", "")),
            "city_tier": CITY_TIERS.get(str(profile.get("city", "")), 3),
            "age": int(_number(profile.get("age"), default=35)),
            "income_level": str(profile.get("income_level", "")),
            "card_level": str(account.get("card_level", "")),
            "total_credit_amount": credit_amount,
            "monthly_spend": monthly_spend,
            "credit_limit_usage": _ratio(account.get("usage_rate"), monthly_spend, credit_amount),
            "app_active_days": min(30, max(0, int(_number(consumption.get("active_days_90d")) / 3))),
            "dining_txn": 0,
            "travel_txn": int("出行" in primary_intent or "旅游" in primary_intent),
            "online_txn": 0,
            "coupon_response": min(0.9, max(0.05, activity_score / 100)),
            "installment_history": 2 if "分期" in primary_intent else 0,
            "marketing_consent": marketing_consent,
            # Project A currently returns marketing consent but not a separate
            # personalization-consent field. This keeps demo behavior stable;
            # production integration must request that explicit field from A.
            "personalization_consent": marketing_consent,
            "dnc_list": bool(consent.get("dnc_list", False)),
            "do_not_contact_signal": bool(consent.get("do_not_contact", False)),
            "blacklist_flag": bool(consent.get("blacklist_flag", False)),
            "risk_level": str(risk.get("risk_level", "low")),
            "complaint_count_90d": complaint_count,
            "complaint_risk": min(1.0, complaint_count / 3),
            "value_level": str(tags.get("value_level", "")),
            "lifecycle_stage": str(profile.get("lifecycle_stage", "")),
            "consumption_trend": str(consumption.get("trend", "")),
            "churn_risk_score": int(_number(risk.get("churn_risk_score"))),
            "owned_products": [str(account["product_name"])] if account.get("product_name") else [],
            "channel_consents": channel_consents,
            # Project A exposes exact frequency through a dedicated endpoint.
            # Its current search response has no per-customer contact counters,
            # so batch candidate generation records the gap explicitly instead
            # of pretending this zero is a real historical count.
            "recent_contact_count": 0,
            "recent_contact_count_by_channel": {channel: 0 for channel in CHANNELS},
            "recent_behavior_signals": list(dict.fromkeys(recent_behavior_signals)),
            "frequency_data_status": "requires_project1_pre_delivery_check",
            "tags": [value for value in [profile.get("lifecycle_stage"), tags.get("value_level"), *top_intents_names(top_intents)] if value],
        }
        return {
            "customer_id": customer_id,
            "customer_profile": customer_profile,
            "contact_history": [],
            "intent_vector": {"top_intents": top_intents},
            "event_sequence": [],
        }

    def _search_customers(self, payload: dict[str, Any]) -> list[dict[str, Any]]:
        response = self._post_json("/api/v1/customer/search", payload)
        customers = response.get("customers", [])
        if not isinstance(customers, list):
            raise Project1ApiUnavailable("invalid_customer_search_response")
        return [customer for customer in customers if isinstance(customer, dict)]

    def _get_json(self, path: str) -> dict[str, Any]:
        return self._request_json(path, method="GET")

    def _post_json(self, path: str, payload: dict[str, Any]) -> dict[str, Any]:
        return self._request_json(path, method="POST", payload=payload)

    def _request_json(self, path: str, *, method: str, payload: dict[str, Any] | None = None) -> dict[str, Any]:
        body = json.dumps(payload, ensure_ascii=False).encode("utf-8") if payload is not None else None
        request = Request(
            f"{self.base_url}{path}",
            data=body,
            method=method,
            headers={"Content-Type": "application/json"} if body is not None else {},
        )
        try:
            with urlopen(request, timeout=self.timeout_seconds) as response:
                data = json.loads(response.read().decode("utf-8"))
        except (HTTPError, URLError, TimeoutError, json.JSONDecodeError, OSError) as exc:
            raise Project1ApiUnavailable(f"{exc.__class__.__name__}:{path}") from exc
        if not isinstance(data, dict):
            raise Project1ApiUnavailable(f"invalid_json_object:{path}")
        return data


class Project1ApiUnavailable(RuntimeError):
    """Raised when Project A cannot provide a valid API response."""


def _mapping(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _number(value: Any, *, default: float = 0.0) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def _ratio(usage_rate: Any, monthly_spend: float, credit_amount: float) -> float:
    explicit = _number(usage_rate, default=-1)
    if explicit >= 0:
        return min(1.0, explicit / 100 if explicit > 1 else explicit)
    return min(1.0, monthly_spend / credit_amount) if credit_amount else 0.0


def _top_intents(value: Any, primary_intent: str) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    if isinstance(value, dict):
        for name, score in value.items():
            if isinstance(score, dict):
                score = score.get("score", 0)
            rows.append({"name": str(name), "score": _number(score)})
    elif isinstance(value, list):
        for item in value:
            if isinstance(item, dict):
                rows.append({"name": str(item.get("name") or item.get("intent") or ""), "score": _number(item.get("score"))})
    if primary_intent and not any(row["name"] == primary_intent for row in rows):
        rows.append({"name": primary_intent, "score": 1.0})
    return sorted((row for row in rows if row["name"]), key=lambda row: float(row["score"]), reverse=True)[:3]


def top_intents_names(rows: list[dict[str, Any]]) -> list[str]:
    return [str(row.get("name", "")) for row in rows if row.get("name")]


def _load_local_project1_env() -> None:
    """Load only Project A connection settings from the untracked local env file."""
    if not LOCAL_ENV_FILE.is_file():
        return
    try:
        lines = LOCAL_ENV_FILE.read_text(encoding="utf-8").splitlines()
    except OSError:
        return
    for line in lines:
        candidate = line.strip()
        if not candidate or candidate.startswith("#") or "=" not in candidate:
            continue
        name, value = candidate.split("=", 1)
        name = name.strip()
        if name in {"PROJECT1_API_BASE_URL", "PROJECT1_API_TIMEOUT_SECONDS"} and name not in os.environ:
            os.environ[name] = value.strip().strip('"').strip("'")
