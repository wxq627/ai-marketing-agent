from __future__ import annotations

from collections import defaultdict

from .models import CampaignRequest, Customer, CustomerScore, SegmentRecommendation
from .predictor import expected_customer_value, predict_conversion, predict_response


def score_customers(customers: list[Customer], request: CampaignRequest) -> list[CustomerScore]:
    scored: list[CustomerScore] = []
    risk_ceiling = {1: 0.08, 2: 0.14, 3: 0.22}.get(request.risk_level, 0.14)
    contact_ceiling = {1: 1, 2: 2, 3: 3, 4: 4}.get(request.frequency_level, 2)

    for customer in customers:
        if not customer.has_marketing_consent:
            continue
        if customer.complaint_risk > risk_ceiling:
            continue
        if customer.recent_contacts > contact_ceiling:
            continue

        response, reasons, segment = predict_response(customer, request.product)
        conversion = predict_conversion(response, request.channel_mode)
        value = expected_customer_value(customer, request.product, conversion)
        scored.append(
            CustomerScore(
                customer=customer,
                response_prob=round(response, 4),
                conversion_prob=round(conversion, 4),
                expected_value=round(value, 4),
                risk_penalty=round(customer.complaint_risk, 4),
                segment=segment,
                reasons=reasons,
            )
        )

    scored.sort(key=lambda item: item.expected_value, reverse=True)
    max_size = min(len(scored), int(320 + request.budget_wan * 9))
    return scored[:max_size]


def summarize_segments(scored: list[CustomerScore]) -> list[SegmentRecommendation]:
    grouped: dict[str, list[CustomerScore]] = defaultdict(list)
    for item in scored:
        grouped[item.segment].append(item)

    result: list[SegmentRecommendation] = []
    for segment, rows in grouped.items():
        size = len(rows)
        avg_score = sum(row.response_prob for row in rows) / size
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
                avg_score=round(avg_score * 100, 1),
                conversion_rate=round(conversion * 100, 2),
                expected_value_wan=round(value_wan, 2),
                reasons=top_reasons,
            )
        )
    result.sort(key=lambda item: item.expected_value_wan, reverse=True)
    return result[:3]
