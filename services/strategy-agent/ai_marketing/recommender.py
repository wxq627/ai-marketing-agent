from __future__ import annotations

from collections import defaultdict

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


def score_customers(customers: list[Customer], request: CampaignRequest) -> list[CustomerScore]:
    scored: list[CustomerScore] = []
    risk_ceiling = {1: 0.08, 2: 0.14, 3: 0.22}.get(request.risk_level, 0.14)
    for customer in customers:
        if not customer.has_marketing_consent:
            continue
        if customer.complaint_risk > risk_ceiling:
            continue

        response, reasons, segment = predict_response(customer, request.product)
        conversion = predict_conversion(response, request.channel_mode)
        value = expected_customer_value(customer, request.product, conversion)
        priority_score, priority_reason = calculate_priority(customer, request.product, response)
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
    max_size = min(len(scored), int(320 + request.budget_wan * 9))
    return scored[:max_size]


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


def calculate_priority(customer: Customer, product: str, response_prob: float) -> tuple[float, str]:
    """Score intent, recent behavior, value, activity, response and risk on a 0-100 scale."""
    intent_name = PRODUCT_INTENTS.get(product, PRODUCT_INTENTS["installment"])
    intent_score = customer.intent_scores.get(intent_name, 0.0)
    behavior_score = _behavior_score(customer.recent_events, product)
    value_score = min(customer.monthly_spend / 15000, 1.0)
    activity_score = min(customer.app_active_days / 30, 1.0)
    raw = (
        0.35 * intent_score
        + 0.20 * behavior_score
        + 0.15 * value_score
        + 0.10 * activity_score
        + 0.10 * response_prob
        - 0.10 * customer.complaint_risk
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
