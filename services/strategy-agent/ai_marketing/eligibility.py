from __future__ import annotations

import json
from collections import Counter
from dataclasses import asdict, dataclass
from datetime import datetime
from pathlib import Path
from typing import Any


CONFIG_DIR = Path(__file__).resolve().parent.parent / "config"
RULE_FILES = {
    "compliance": "compliance_rules.json",
    "product_eligibility": "product_eligibility_rules.json",
    "business_policy": "business_policy_rules.json",
}


@dataclass(frozen=True)
class RuleTrace:
    rule_id: str
    layer: str
    action: str
    scope: str
    reason_code: str
    owner: str
    configurable: bool


@dataclass(frozen=True)
class EligibilityDecision:
    customer_id: str
    final_decision: str
    eligible: bool
    eligible_channels: list[str]
    channel_eligibility: dict[str, dict[str, Any]]
    blocked_channels: dict[str, list[str]]
    hard_blocks: list[str]
    policy_actions: list[str]
    channel_compliance_blocks: dict[str, list[str]]
    channel_policy_blocks: dict[str, list[str]]
    data_quality_warnings: list[str]
    exclusion_reasons: list[str]
    rule_trace: list[RuleTrace]
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
    final_decision_summary: dict[str, int]
    exclusion_summary: dict[str, int]
    global_exclusion_by_layer: dict[str, dict[str, int]]
    channel_block_by_layer: dict[str, dict[str, int]]
    blocked_channel_summary: dict[str, int]
    channel_coverage: dict[str, int]
    data_quality_warning_summary: dict[str, int]
    decisions: list[EligibilityDecision]
    rule_version: str

    def to_dict(self) -> dict[str, Any]:
        return {
            **asdict(self),
            "decisions": [decision.to_dict() for decision in self.decisions],
        }


def load_eligibility_rules(config_dir: Path | None = None) -> dict[str, Any]:
    """Load separately owned compliance, product, and business rule catalogs."""
    config_dir = config_dir or CONFIG_DIR
    catalogs: dict[str, Any] = {}
    versions: set[str] = set()
    for layer, filename in RULE_FILES.items():
        with (config_dir / filename).open(encoding="utf-8") as file:
            catalog = json.load(file)
        catalogs[layer] = catalog.get("rules", [])
        versions.add(str(catalog["rule_version"]))
        if layer == "business_policy":
            catalogs["default_channels"] = catalog["default_channels"]
    if len(versions) != 1:
        raise ValueError("Rule catalogs must use the same rule_version")
    catalogs["rule_version"] = versions.pop()
    return catalogs


def evaluate_customer_insight(
    payload: dict[str, Any],
    *,
    rules: dict[str, Any] | None = None,
    evaluated_at: datetime | None = None,
) -> EligibilityReport:
    """Evaluate customer and channel eligibility before strategy optimization."""
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
    channel_coverage = Counter(channel for decision in decisions for channel in decision.eligible_channels)
    final_decision_summary = Counter(decision.final_decision for decision in decisions)
    global_exclusion_by_layer = _global_exclusion_by_layer(decisions)
    channel_block_by_layer = _channel_block_by_layer(decisions)
    warning_summary = Counter(
        warning for decision in decisions for warning in decision.data_quality_warnings
    )

    return EligibilityReport(
        campaign_id=str(payload.get("campaign_id", "")),
        target_product=product,
        candidate_count=len(decisions),
        eligible_count=sum(decision.eligible for decision in decisions),
        excluded_count=sum(not decision.eligible for decision in decisions),
        final_decision_summary=dict(sorted(final_decision_summary.items())),
        exclusion_summary=dict(sorted(exclusion_summary.items())),
        global_exclusion_by_layer=global_exclusion_by_layer,
        channel_block_by_layer=channel_block_by_layer,
        blocked_channel_summary=dict(sorted(blocked_channel_summary.items())),
        channel_coverage={channel: channel_coverage.get(channel, 0) for channel in available_channels},
        data_quality_warning_summary=dict(sorted(warning_summary.items())),
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
    hard_blocks: list[str] = []
    policy_actions: list[str] = []
    traces: list[RuleTrace] = []

    for rule in rules["compliance"]:
        if rule["scope"] == "customer" and _matches_profile_rule(profile, rule):
            hard_blocks.append(rule["reason_code"])
            traces.append(_trace(rule))
    for rule in rules["product_eligibility"]:
        if _matches_product_rule(profile, product, rule):
            hard_blocks.append(rule["reason_code"])
            traces.append(_trace(rule))
    for rule in rules["business_policy"]:
        if rule["scope"] == "customer" and _matches_profile_rule(profile, rule):
            policy_actions.append(rule["reason_code"])
            traces.append(_trace(rule))

    global_reasons = sorted(set(hard_blocks + policy_actions))
    channel_eligibility: dict[str, dict[str, Any]] = {}
    blocked_channels: dict[str, list[str]] = {}
    channel_compliance_blocks: dict[str, list[str]] = {}
    channel_policy_blocks: dict[str, list[str]] = {}
    data_quality_warnings: list[str] = []

    for channel in available_channels:
        channel_traces: list[RuleTrace] = []
        compliance_reasons: list[str] = []
        policy_reasons: list[str] = []
        channel_warnings: list[str] = []
        if global_reasons:
            reason_codes = global_reasons
        else:
            for rule in rules["compliance"] + rules["business_policy"]:
                if rule["scope"] != "channel":
                    continue
                if rule["layer"] == "business_policy" and compliance_reasons:
                    continue
                if rule.get("rule_type") == "frequency_cap" and policy_reasons:
                    continue
                matched, warning, missing_data_reason = _evaluate_channel_rule(
                    customer, channel, channel_status, rule, evaluated_at
                )
                if warning:
                    channel_warnings.append(warning)
                    data_quality_warnings.append(warning)
                if matched:
                    if rule["layer"] == "compliance":
                        compliance_reasons.append(rule["reason_code"])
                    else:
                        policy_reasons.append(rule["reason_code"])
                    trace = _trace(rule)
                    channel_traces.append(trace)
                    traces.append(trace)
                elif missing_data_reason:
                    policy_reasons.append(missing_data_reason)
                    trace = _trace(rule)
                    channel_traces.append(trace)
                    traces.append(trace)
            if compliance_reasons:
                channel_compliance_blocks[channel] = sorted(set(compliance_reasons))
            if policy_reasons:
                channel_policy_blocks[channel] = sorted(set(policy_reasons))
            reason_codes = sorted(set(compliance_reasons + policy_reasons))

        if reason_codes:
            blocked_channels[channel] = reason_codes
            channel_eligibility[channel] = {
                "decision": "BLOCKED",
                "reason_codes": reason_codes,
                "compliance_reason_codes": sorted(set(compliance_reasons)),
                "policy_reason_codes": sorted(set(policy_reasons)),
                "data_quality_warnings": sorted(set(channel_warnings)),
                "rule_ids": sorted({trace.rule_id for trace in channel_traces}),
            }
        else:
            channel_eligibility[channel] = {
                "decision": "ELIGIBLE",
                "reason_codes": [],
                "compliance_reason_codes": [],
                "policy_reason_codes": [],
                "data_quality_warnings": sorted(set(channel_warnings)),
                "rule_ids": [],
            }

    eligible_channels = [channel for channel in available_channels if channel not in blocked_channels]
    if hard_blocks:
        final_decision = "BLOCK"
    elif policy_actions:
        final_decision = "SUPPRESS"
    elif eligible_channels:
        final_decision = "ALLOW" if len(eligible_channels) == len(available_channels) else "ALLOW_WITH_LIMITS"
    elif _all_channels_blocked_by_compliance(available_channels, channel_compliance_blocks, channel_policy_blocks):
        final_decision = "BLOCK_ALL_CHANNELS"
    else:
        final_decision = "SUPPRESS"
        policy_actions.append("no_eligible_channel")

    exclusion_reasons = sorted(
        set(
            hard_blocks
            + policy_actions
            + [reason for reasons in channel_compliance_blocks.values() for reason in reasons]
            + [reason for reasons in channel_policy_blocks.values() for reason in reasons]
        )
    )
    return EligibilityDecision(
        customer_id=customer_id,
        final_decision=final_decision,
        eligible=final_decision in {"ALLOW", "ALLOW_WITH_LIMITS"},
        eligible_channels=eligible_channels,
        channel_eligibility=channel_eligibility,
        blocked_channels=blocked_channels,
        hard_blocks=sorted(set(hard_blocks)),
        policy_actions=sorted(set(policy_actions)),
        channel_compliance_blocks=channel_compliance_blocks,
        channel_policy_blocks=channel_policy_blocks,
        data_quality_warnings=sorted(set(data_quality_warnings)),
        exclusion_reasons=exclusion_reasons,
        rule_trace=_unique_traces(traces),
        rule_version=str(rules["rule_version"]),
    )


def filter_to_eligible_customers(payload: dict[str, Any], report: EligibilityReport) -> dict[str, Any]:
    """Pass only allowed customers and their channel constraints to strategy scoring."""
    decision_by_customer = {decision.customer_id: decision for decision in report.decisions}
    customers: list[dict[str, Any]] = []
    for customer in payload.get("customers", []):
        decision = decision_by_customer.get(str(customer.get("customer_id", "")))
        if not decision or not decision.eligible:
            continue
        enriched = dict(customer)
        enriched["strategy_eligibility"] = {
            "final_decision": decision.final_decision,
            "eligible_channels": decision.eligible_channels,
            "blocked_channels": decision.blocked_channels,
            "channel_compliance_blocks": decision.channel_compliance_blocks,
            "channel_policy_blocks": decision.channel_policy_blocks,
            "data_quality_warnings": decision.data_quality_warnings,
            "rule_trace": [trace.rule_id for trace in decision.rule_trace],
        }
        customers.append(enriched)
    filtered = dict(payload)
    filtered["customers"] = customers
    return filtered


def _matches_profile_rule(profile: dict[str, Any], rule: dict[str, Any]) -> bool:
    if rule.get("rule_type") != "profile":
        return False
    value = profile.get(rule["field"])
    operator = rule["operator"]
    if operator == "not_true":
        return value is not True
    if operator == "is_true":
        return value is True
    if operator == "in":
        return str(value).lower() in {str(item).lower() for item in rule["values"]}
    if operator == "gte":
        return float(value or 0) >= float(rule["value"])
    raise ValueError(f"Unsupported profile rule operator: {operator}")


def _matches_product_rule(profile: dict[str, Any], product: str, rule: dict[str, Any]) -> bool:
    if rule.get("rule_type") != "product_ownership" or product not in rule["product_aliases"]:
        return False
    owned_products = set(profile.get("owned_products", []))
    return bool(owned_products.intersection(rule["blocked_owned_products"]))


def _evaluate_channel_rule(
    customer: dict[str, Any],
    channel: str,
    channel_status: dict[str, str],
    rule: dict[str, Any],
    evaluated_at: datetime,
) -> tuple[bool, str | None, str | None]:
    """Return matched, data warning, and a fail-closed missing-data reason."""
    profile = customer.get("customer_profile", {})
    rule_type = rule.get("rule_type")
    if rule_type == "channel_consent":
        consents = profile.get("channel_consents")
        return isinstance(consents, dict) and consents.get(channel) is False, None, None
    if rule_type == "channel_status":
        return channel_status.get(channel, rule.get("available_value", "available")) != rule.get("available_value", "available"), None, None
    if rule_type == "channel_capability":
        capabilities = profile.get("channel_capabilities")
        return isinstance(capabilities, dict) and capabilities.get(channel) is False, None, None
    if rule_type == "frequency_cap":
        cap = rule.get("caps", {}).get(channel)
        if not cap:
            return False, None, None
        count = _recent_marketing_contacts(customer, channel, int(cap["window_days"]), evaluated_at)
        if count is None:
            count = _recent_channel_contact_count(profile, channel)
        if count is None:
            warning = f"frequency_data_missing:{channel}"
            reason = rule.get("missing_data_reason_code") if rule.get("missing_data_action") == "LIMIT_CHANNEL" else None
            return False, warning, reason
        return count >= int(cap["max_contacts"]), None, None
    return False, None, None


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


def _recent_channel_contact_count(profile: dict[str, Any], channel: str) -> int | None:
    counts = profile.get("recent_contact_count_by_channel")
    if not isinstance(counts, dict) or channel not in counts:
        return None
    try:
        return int(counts[channel])
    except (TypeError, ValueError):
        return None


def _all_channels_blocked_by_compliance(
    available_channels: list[str],
    channel_compliance_blocks: dict[str, list[str]],
    channel_policy_blocks: dict[str, list[str]],
) -> bool:
    return bool(available_channels) and all(
        channel_compliance_blocks.get(channel) and not channel_policy_blocks.get(channel)
        for channel in available_channels
    )


def _global_exclusion_by_layer(decisions: list[EligibilityDecision]) -> dict[str, dict[str, int]]:
    counters = {layer: Counter() for layer in RULE_FILES}
    for decision in decisions:
        if decision.eligible:
            continue
        for trace in decision.rule_trace:
            if trace.scope == "customer":
                counters[trace.layer][trace.reason_code] += 1
    return {layer: dict(sorted(counter.items())) for layer, counter in counters.items()}


def _channel_block_by_layer(decisions: list[EligibilityDecision]) -> dict[str, dict[str, int]]:
    counters = {"compliance": Counter(), "business_policy": Counter()}
    for decision in decisions:
        for reasons in decision.channel_compliance_blocks.values():
            counters["compliance"].update(reasons)
        for reasons in decision.channel_policy_blocks.values():
            counters["business_policy"].update(reasons)
    return {layer: dict(sorted(counter.items())) for layer, counter in counters.items()}


def _trace(rule: dict[str, Any]) -> RuleTrace:
    return RuleTrace(
        rule_id=rule["rule_id"],
        layer=rule["layer"],
        action=rule["action"],
        scope=rule["scope"],
        reason_code=rule["reason_code"],
        owner=rule["owner"],
        configurable=bool(rule["configurable"]),
    )


def _unique_traces(traces: list[RuleTrace]) -> list[RuleTrace]:
    by_id = {trace.rule_id: trace for trace in traces}
    return [by_id[rule_id] for rule_id in sorted(by_id)]


def _parse_time(value: Any) -> datetime | None:
    if not value or not isinstance(value, str):
        return None
    try:
        return datetime.fromisoformat(value)
    except ValueError:
        return None
