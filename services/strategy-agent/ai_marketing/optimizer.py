from __future__ import annotations

from .models import CampaignRequest, ChannelPlan, CustomerScore, SegmentRecommendation


CHANNELS = {
    "omni": [("App弹窗", 0.46, "主触达"), ("短信", 0.18, "限时召回"), ("企微", 0.36, "高价值跟进")],
    "app": [("App首页", 0.62, "主触达"), ("Push", 0.38, "场景提醒")],
    "sms": [("短信", 1.0, "低成本召回")],
}


def build_channel_plan(request: CampaignRequest, audience_size: int) -> list[ChannelPlan]:
    rows = CHANNELS.get(request.channel_mode, CHANNELS["omni"])
    return [
        ChannelPlan(
            channel=name,
            budget_share=round(share, 2),
            expected_reach=max(1, int(audience_size * (0.72 + share * 0.22))),
            role=role,
        )
        for name, share, role in rows
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
        "success_metrics": ["转化率", "ROI", "投诉率", "触达成本"],
        "sample_hint": f"建议灰度 {max(200, int(len(scored) * 0.18))} 人后再全量",
        "top_segment": segments[0].name if segments else "暂无",
    }
    effect = {
        "ctr": round(avg_response * 28, 2),
        "conversion": round(conversion_rate * 100, 2),
        "complaint": round(avg_risk * 100, 3),
        "net_value_wan": round(net_value_wan, 2),
    }
    return round(uplift * 100, 1), round(roi, 2), effect, experiment
