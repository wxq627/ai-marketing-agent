from ai_marketing.models import CampaignRequest
from ai_marketing.orchestrator import MarketingDecisionEngine


def test_generate_installment_plan():
    engine = MarketingDecisionEngine()
    plan = engine.generate_plan(
        CampaignRequest(
            goal="提升信用卡分期转化，控制投诉风险和触达频次",
            product="installment",
            channel_mode="omni",
            budget_wan=80,
            risk_level=2,
            frequency_level=2,
        )
    )
    assert plan.audience_size > 0
    assert plan.predicted_roi > 0
    assert plan.segments
    assert plan.channels
    assert plan.content["sms"]
    assert all(check.status in {"通过", "需复核", "拦截"} for check in plan.compliance)
