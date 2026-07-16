from __future__ import annotations

from .models import CampaignRequest, ChannelPlan, CustomerScore, SegmentRecommendation


# The canonical code is used for eligibility; the display name is for the B-side console.
CHANNELS = {
    "omni": [
        ("app_push", "App Push", 0.46, "primary reach"),
        ("sms", "SMS", 0.18, "timely recall"),
        ("wechat", "WeChat", 0.36, "high-value follow-up"),
    ],
    "app": [
        ("app_push", "App Home", 0.62, "primary reach"),
        ("app_push", "App Push", 0.38, "scenario reminder"),
    ],
    "sms": [("sms", "SMS", 1.0, "low-cost recall")],
}


def build_channel_plan(
    request: CampaignRequest, audience_size: int, allowed_channels: set[str] | None = None
) -> list[ChannelPlan]:
    rows = CHANNELS.get(request.channel_mode, CHANNELS["omni"])
    if allowed_channels is not None:
        rows = [row for row in rows if row[0] in allowed_channels]
    if not rows:
        return []

    total_share = sum(row[2] for row in rows)
    return [
        ChannelPlan(
            channel=display_name,
            budget_share=round(share / total_share, 2),
            expected_reach=max(1, int(audience_size * (0.72 + share * 0.22))),
            role=role,
        )
        for _, display_name, share, role in rows
    ]


def forecast_effect(
    request: CampaignRequest,
    scored: list[CustomerScore],
    segments: list[SegmentRecommendation],
) -> tuple[float, float, dict[str, float], dict[str, object]]:
    if not scored:
        return 0.0, 0.0, {"ctr": 0.0, "conversion": 0.0, "complaint": 0.0, "net_value_wan": 0.0}, {}

    conversion_rate = sum(row.conversion_prob for row in scored) / len(scored)
    avg_response = sum(row.response_prob for row in scored) / len(scored)
    avg_risk = sum(row.risk_penalty for row in scored) / len(scored)
    net_value_wan = sum(row.expected_value for row in scored) / 10000
    cost_wan = request.budget_wan * 0.72
    roi = net_value_wan / max(cost_wan, 1)
    baseline_conversion = max(0.01, conversion_rate * 0.78)
    uplift = (conversion_rate - baseline_conversion) / baseline_conversion
    experiment = {
        "method": "A/B Test",
        "control_group": "10%",
        "success_metrics": ["conversion_rate", "ROI", "complaint_rate", "contact_cost"],
        "sample_hint": f"Recommend a pilot with {max(200, int(len(scored) * 0.18))} customers before full rollout.",
        "top_segment": segments[0].name if segments else "none",
    }
    effect = {
        "ctr": round(avg_response * 28, 2),
        "conversion": round(conversion_rate * 100, 2),
        "complaint": round(avg_risk * 100, 3),
        "net_value_wan": round(net_value_wan, 2),
    }
    return round(uplift * 100, 1), round(roi, 2), effect, experiment
