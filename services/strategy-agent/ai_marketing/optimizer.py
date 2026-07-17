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


def build_channel_plan_from_context(
    request: CampaignRequest,
    audience_size: int,
    channel_context: dict[str, object],
    allowed_channels: set[str] | None = None,
) -> list[ChannelPlan]:
    """Allocate the selected audience with Project A channel cost and performance data."""
    metrics = channel_context.get("channel_metrics", {})
    if not isinstance(metrics, dict):
        return build_channel_plan(request, audience_size, allowed_channels=allowed_channels)

    preferred = {
        "omni": ["app_push", "sms", "wechat"],
        "app": ["app_push"],
        "sms": ["sms"],
    }.get(request.channel_mode, ["app_push", "sms", "wechat"])
    display = {"app_push": "App Push", "sms": "SMS", "wechat": "WeChat"}
    roles = {
        "app_push": "primary reach",
        "sms": "timely recall",
        "wechat": "high-value follow-up",
    }
    rows: list[tuple[str, dict[str, object], float]] = []
    for channel in preferred:
        if allowed_channels is not None and channel not in allowed_channels:
            continue
        metric = metrics.get(channel)
        if not isinstance(metric, dict):
            continue
        cost = float(metric.get("cost_per_send", 0) or 0)
        click_rate = float(metric.get("avg_click_rate", 0) or 0)
        utility = click_rate / max(cost, 0.01)
        rows.append((channel, metric, utility))
    if not rows:
        return build_channel_plan(request, audience_size, allowed_channels=allowed_channels)

    utility_total = sum(row[2] for row in rows)
    return [
        ChannelPlan(
            channel=display[channel],
            budget_share=round(utility / utility_total, 2),
            expected_reach=min(
                int(metric.get("daily_capacity", audience_size) or audience_size),
                max(1, int(audience_size * (0.65 + utility / utility_total * 0.3))),
            ),
            role=roles[channel],
            unit_cost=round(float(metric.get("cost_per_send", 0) or 0), 4),
        )
        for channel, metric, utility in rows
    ]


def forecast_effect(
    request: CampaignRequest,
    scored: list[CustomerScore],
    segments: list[SegmentRecommendation],
    channels: list[ChannelPlan] | None = None,
) -> tuple[float, float, dict[str, float], dict[str, object]]:
    if not scored:
        return 0.0, 0.0, {"ctr": 0.0, "conversion": 0.0, "complaint": 0.0, "net_value_wan": 0.0}, {}

    conversion_rate = sum(row.conversion_prob for row in scored) / len(scored)
    avg_response = sum(row.response_prob for row in scored) / len(scored)
    avg_risk = sum(row.risk_penalty for row in scored) / len(scored)
    net_value_wan = sum(row.expected_value for row in scored) / 10000
    channel_cost_wan = sum(channel.expected_reach * channel.unit_cost for channel in channels or []) / 10000
    cost_wan = channel_cost_wan or request.budget_wan * 0.72
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
