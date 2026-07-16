from __future__ import annotations

import json
from collections import Counter
from dataclasses import asdict, dataclass
from datetime import datetime
from pathlib import Path
from typing import Any


RULES_PATH = Path(__file__).resolve().parent.parent / "config" / "eligibility_rules.json"


@dataclass(frozen=True)
class EligibilityDecision:
    customer_id: str
    eligible: bool
    eligible_channels: list[str]
    blocked_channels: dict[str, list[str]]
    exclusion_reasons: list[str]
    rule_version: str

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class EligibilityReport:
    campaign_id: str
    target_product: str
    candidate_count: int
    eligible_count: int
    excluded_count: int
    exclusion_summary: dict[str, int]
    blocked_channel_summary: dict[str, int]
    decisions: list[EligibilityDecision]
    rule_version: str

    def to_dict(self) -> dict[str, Any]:
        return {
            **asdict(self),
            "decisions": [decision.to_dict() for decision in self.decisions],
        }


def load_eligibility_rules(path: Path | None = None) -> dict[str, Any]:
    with (path or RULES_PATH).open(encoding="utf-8") as file:
        return json.load(file)


def evaluate_customer_insight(
    payload: dict[str, Any],
    *,
    rules: dict[str, Any] | None = None,
    evaluated_at: datetime | None = None,
) -> EligibilityReport:
    """Apply deterministic marketing eligibility rules to A -> B customer insight."""
    rules = rules or load_eligibility_rules()
    reference_time = evaluated_at or _parse_time(payload.get("evaluation_time")) or datetime.now().astimezone()
    channel_context = payload.get("channel_context", {})
    available_channels = channel_context.get("available_channels") or rules["default_channels"]
    channel_status = channel_context.get("channel_status", {})
    product = str(payload.get("target_product", "installment"))

    decisions = [
        evaluate_customer(
            customer,
            product=product,
            available_channels=available_channels,
            channel_status=channel_status,
            rules=rules,
            evaluated_at=reference_time,
        )
        for customer in payload.get("customers", [])
    ]
    exclusion_summary = Counter(
        reason for decision in decisions if not decision.eligible for reason in decision.exclusion_reasons
    )
    blocked_channel_summary = Counter(
        reason
        for decision in decisions
        for reasons in decision.blocked_channels.values()
        for reason in reasons
    )

    return EligibilityReport(
        campaign_id=str(payload.get("campaign_id", "")),
        target_product=product,
        candidate_count=len(decisions),
        eligible_count=sum(decision.eligible for decision in decisions),
        excluded_count=sum(not decision.eligible for decision in decisions),
        exclusion_summary=dict(sorted(exclusion_summary.items())),
        blocked_channel_summary=dict(sorted(blocked_channel_summary.items())),
        decisions=decisions,
        rule_version=str(rules["rule_version"]),
    )


def evaluate_customer(
    customer: dict[str, Any],
    *,
    product: str,
    available_channels: list[str],
    channel_status: dict[str, str],
    rules: dict[str, Any],
    evaluated_at: datetime,
) -> EligibilityDecision:
    profile = customer.get("customer_profile", {})
    customer_id = str(customer.get("customer_id", ""))
    global_reasons = _global_exclusion_reasons(profile, product, rules)
    blocked_channels: dict[str, list[str]] = {}

    for channel in available_channels:
        reasons = list(global_reasons)
        if channel_status.get(channel, "available") != "available":
            reasons.append("channel_unavailable")
        if profile.get("marketing_consent") and not _channel_has_consent(profile, channel):
            reasons.append("channel_consent_revoked")
        if not reasons and _frequency_cap_reached(customer, channel, rules, evaluated_at):
            reasons.append("frequency_cap_reached")
        if reasons:
            blocked_channels[channel] = sorted(set(reasons))

    eligible_channels = [channel for channel in available_channels if channel not in blocked_channels]
    if not eligible_channels and not global_reasons:
        global_reasons.append("no_eligible_channel")

    return EligibilityDecision(
        customer_id=customer_id,
        eligible=bool(eligible_channels),
        eligible_channels=eligible_channels,
        blocked_channels=blocked_channels,
        exclusion_reasons=sorted(set(global_reasons)),
        rule_version=str(rules["rule_version"]),
    )


def filter_to_eligible_customers(payload: dict[str, Any], report: EligibilityReport) -> dict[str, Any]:
    """Return a copy of A's payload containing only customers with at least one usable channel."""
    decision_by_customer = {decision.customer_id: decision for decision in report.decisions}
    customers: list[dict[str, Any]] = []
    for customer in payload.get("customers", []):
        decision = decision_by_customer.get(str(customer.get("customer_id", "")))
        if not decision or not decision.eligible:
            continue
        enriched = dict(customer)
        enriched["strategy_eligibility"] = {
            "eligible_channels": decision.eligible_channels,
            "blocked_channels": decision.blocked_channels,
        }
        customers.append(enriched)

    filtered = dict(payload)
    filtered["customers"] = customers
    return filtered


def _global_exclusion_reasons(profile: dict[str, Any], product: str, rules: dict[str, Any]) -> list[str]:
    reasons: list[str] = []
    if not profile.get("marketing_consent", False):
        reasons.append("no_marketing_consent")
    if str(profile.get("risk_level", "low")).lower() in set(rules["risk"]["blocked_risk_levels"]):
        reasons.append("blocked_risk_level")
    if float(profile.get("complaint_risk", 0)) >= float(rules["risk"]["complaint_risk_threshold"]):
        reasons.append("high_complaint_risk")
    if _already_owns_target_product(profile, product, rules):
        reasons.append("product_already_owned")
    return reasons


def _channel_has_consent(profile: dict[str, Any], channel: str) -> bool:
    channel_consents = profile.get("channel_consents")
    if not isinstance(channel_consents, dict):
        return True
    return bool(channel_consents.get(channel, True))


def _frequency_cap_reached(
    customer: dict[str, Any], channel: str, rules: dict[str, Any], evaluated_at: datetime
) -> bool:
    cap = rules["channel_frequency_caps"].get(channel)
    if not cap:
        return False
    recent_count = _recent_marketing_contacts(customer, channel, int(cap["window_days"]), evaluated_at)
    if recent_count is None:
        recent_count = int(customer.get("customer_profile", {}).get("recent_contact_count", 0))
    return recent_count >= int(cap["max_contacts"])


def _recent_marketing_contacts(
    customer: dict[str, Any], channel: str, window_days: int, evaluated_at: datetime
) -> int | None:
    history = customer.get("contact_history")
    if not isinstance(history, list):
        return None
    lower_bound = evaluated_at.timestamp() - window_days * 24 * 60 * 60
    count = 0
    for event in history:
        if not isinstance(event, dict) or event.get("channel") != channel:
            continue
        if event.get("contact_type", "marketing") != "marketing":
            continue
        event_time = _parse_time(event.get("contacted_at"))
        if event_time and event_time.timestamp() >= lower_bound:
            count += 1
    return count


def _already_owns_target_product(profile: dict[str, Any], product: str, rules: dict[str, Any]) -> bool:
    owned_products = set(profile.get("owned_products", []))
    for config in rules["product_eligibility"].values():
        if product in config.get("aliases", []):
            return bool(owned_products.intersection(config.get("blocked_owned_products", [])))
    return False


def _parse_time(value: Any) -> datetime | None:
    if not value or not isinstance(value, str):
        return None
    try:
        return datetime.fromisoformat(value)
    except ValueError:
        return None
