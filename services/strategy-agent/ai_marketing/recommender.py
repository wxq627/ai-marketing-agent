from __future__ import annotations

from collections import defaultdict
from typing import Any

from .models import CampaignRequest, Customer, CustomerScore, SegmentRecommendation
from .predictor import expected_customer_value, predict_conversion, predict_response


PRODUCT_INTENTS = {
    "installment": "\u5206\u671f/\u501f\u8d37\u9700\u6c42",
    "coupon": "\u6743\u76ca/\u4f18\u60e0\u9700\u6c42",
    "travel": "\u8de8\u5883/\u51fa\u884c\u9700\u6c42",
}
PRODUCT_EVENT_KEYWORDS = {
    "installment": ["\u5206\u671f", "\u8d26\u5355"],
    "coupon": ["\u4f18\u60e0", "\u79ef\u5206", "\u6743\u76ca"],
    "travel": ["\u51fa\u884c", "\u5883\u5916", "\u9152\u5e97", "\u673a\u7968"],
}

DEFAULT_SCORE_WEIGHTS = {
    "intent": 0.35,
    "behavior": 0.20,
    "value": 0.15,
    "activity": 0.10,
    "response": 0.10,
    "limit_usage": 0.00,
    "risk": 0.10,
}

# Different products need different evidence and have different affordable contact volumes.
PRODUCT_MATCH_THRESHOLDS = {"installment": 0.26, "coupon": 0.30, "travel": 0.22}
PRODUCT_AUDIENCE_CAP = {
    "installment": (220, 9),
    "coupon": (280, 11),
    "travel": (140, 7),
}


def filter_priority_candidates(customers: list[Customer], request: CampaignRequest) -> list[Customer]:
    risk_ceiling = {1: 0.08, 2: 0.14, 3: 0.22}.get(request.risk_level, 0.14)
    return [
        customer
        for customer in customers
        if customer.has_marketing_consent and customer.complaint_risk <= risk_ceiling
        and _product_match_score(customer, request.product) >= PRODUCT_MATCH_THRESHOLDS.get(request.product, 0.26)
    ]


def score_customers(
    customers: list[Customer],
    request: CampaignRequest,
    persona_assignments: dict[str, Any] | None = None,
    candidates_pre_filtered: bool = False,
) -> list[CustomerScore]:
    scored: list[CustomerScore] = []
    eligible_customers = customers if candidates_pre_filtered else filter_priority_candidates(customers, request)
    for customer in eligible_customers:
        persona = (persona_assignments or {}).get(customer.customer_id)

        response, reasons, segment = predict_response(customer, request.product)
        conversion = predict_conversion(response, request.channel_mode)
        value = expected_customer_value(customer, request.product, conversion)
        weights = getattr(persona, "score_weights", None)
        priority_score, priority_reason = calculate_priority(customer, request.product, response, weights)
        if persona is not None:
            segment = persona.name
            reasons = [f"\u7fa4\u50cf\u8bc4\u5206\u4fa7\u91cd\uff1a{persona.strategy['scoring_focus']}", *reasons]
        reasons = [priority_reason, *reasons]
        scored.append(
            CustomerScore(
                customer=customer,
                response_prob=round(response, 4),
                conversion_prob=round(conversion, 4),
                expected_value=round(value, 4),
                risk_penalty=round(customer.complaint_risk, 4),
                priority_score=round(priority_score, 2),
                segment=segment,
                reasons=reasons,
            )
        )

    scored.sort(key=lambda item: (item.priority_score, item.expected_value), reverse=True)
    base, per_budget_wan = PRODUCT_AUDIENCE_CAP.get(request.product, PRODUCT_AUDIENCE_CAP["installment"])
    max_size = min(len(scored), int(base + request.budget_wan * per_budget_wan))
    return _select_with_persona_allocation(scored, max_size, persona_assignments)


def summarize_segments(scored: list[CustomerScore]) -> list[SegmentRecommendation]:
    grouped: dict[str, list[CustomerScore]] = defaultdict(list)
    for item in scored:
        grouped[item.segment].append(item)

    result: list[SegmentRecommendation] = []
    for segment, rows in grouped.items():
        size = len(rows)
        avg_score = sum(row.priority_score for row in rows) / size
        conversion = sum(row.conversion_prob for row in rows) / size
        value_wan = sum(row.expected_value for row in rows) / 10000
        reason_counts: dict[str, int] = defaultdict(int)
        for row in rows:
            for reason in row.reasons:
                reason_counts[reason] += 1
        top_reasons = [reason for reason, _ in sorted(reason_counts.items(), key=lambda x: x[1], reverse=True)[:3]]
        result.append(
            SegmentRecommendation(
                name=segment,
                size=size,
            avg_score=round(avg_score, 1),
                conversion_rate=round(conversion * 100, 2),
                expected_value_wan=round(value_wan, 2),
                reasons=top_reasons,
            )
        )
    result.sort(key=lambda item: item.expected_value_wan, reverse=True)
    return result[:3]


def calculate_priority(
    customer: Customer,
    product: str,
    response_prob: float,
    weights: dict[str, float] | None = None,
) -> tuple[float, str]:
    """Score intent, recent behavior, value, activity, response and risk on a 0-100 scale."""
    intent_name = PRODUCT_INTENTS.get(product, PRODUCT_INTENTS["installment"])
    intent_score = customer.intent_scores.get(intent_name, 0.0)
    behavior_score = _behavior_score(customer.recent_events, product)
    value_score = min(customer.monthly_spend / 15000, 1.0)
    activity_score = min(customer.app_active_days / 30, 1.0)
    limit_usage_score = customer.credit_limit_usage
    score_weights = weights or DEFAULT_SCORE_WEIGHTS
    raw = (
        score_weights["intent"] * intent_score
        + score_weights["behavior"] * behavior_score
        + score_weights["value"] * value_score
        + score_weights["activity"] * activity_score
        + score_weights["response"] * response_prob
        + score_weights["limit_usage"] * limit_usage_score
        - score_weights["risk"] * customer.complaint_risk
    )
    score = max(0.0, min(100.0, raw * 100))
    return score, f"intent_priority:{round(intent_score * 100)}"


def _behavior_score(events: list[dict[str, str]], product: str) -> float:
    keywords = PRODUCT_EVENT_KEYWORDS.get(product, [])
    matches = 0
    campaign_clicks = 0
    for event in events[-20:]:
        name = str(event.get("event_name", ""))
        if any(keyword in name for keyword in keywords):
            matches += 1
        if "campaign_click" in name or "\u70b9\u51fb" in name:
            campaign_clicks += 1
    return min(1.0, matches * 0.25 + campaign_clicks * 0.3)


def _product_match_score(customer: Customer, product: str) -> float:
    """Return a transparent 0-1 product affinity score before final ranking."""
    intent_name = PRODUCT_INTENTS.get(product, PRODUCT_INTENTS["installment"])
    intent_score = customer.intent_scores.get(intent_name, 0.0)
    behavior_score = _behavior_score(customer.recent_events, product)
    if product == "installment":
        product_signal = min(1.0, customer.credit_limit_usage * 0.55 + customer.installment_history * 0.15)
    elif product == "coupon":
        spending_frequency = min(1.0, (customer.dining_txn + customer.online_txn) / 28)
        product_signal = min(1.0, customer.coupon_response * 0.7 + spending_frequency * 0.3)
    else:
        travel_frequency = min(1.0, customer.travel_txn / 4)
        product_signal = min(1.0, travel_frequency * 0.6 + customer.monthly_spend / 30000 * 0.4)
    return 0.5 * intent_score + 0.25 * behavior_score + 0.25 * product_signal


def _select_with_persona_allocation(
    scored: list[CustomerScore], max_size: int, persona_assignments: dict[str, Any] | None
) -> list[CustomerScore]:
    """Reserve campaign capacity by persona, then rank within each persona."""
    if not persona_assignments:
        return scored[:max_size]

    grouped: dict[str, list[CustomerScore]] = defaultdict(list)
    profiles: dict[str, Any] = {}
    for item in scored:
        profile = persona_assignments.get(item.customer.customer_id)
        if profile is None:
            continue
        grouped[profile.name].append(item)
        profiles[profile.name] = profile
    if not grouped:
        return scored[:max_size]

    total_weight = sum(profile.allocation_weight for profile in profiles.values())
    quotas: dict[str, int] = {}
    fractions: list[tuple[float, str]] = []
    for name, rows in grouped.items():
        desired = max_size * profiles[name].allocation_weight / total_weight
        quotas[name] = min(len(rows), int(desired))
        fractions.append((desired - int(desired), name))

    remaining = max_size - sum(quotas.values())
    for _fraction, name in sorted(fractions, reverse=True):
        if remaining <= 0:
            break
        if quotas[name] < len(grouped[name]):
            quotas[name] += 1
            remaining -= 1

    selected = [item for name, rows in grouped.items() for item in rows[: quotas[name]]]
    if remaining > 0:
        selected_ids = {item.customer.customer_id for item in selected}
        selected.extend(item for item in scored if item.customer.customer_id not in selected_ids)
    selected.sort(key=lambda item: (item.priority_score, item.expected_value), reverse=True)
    return selected[:max_size]
