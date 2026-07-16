from ai_marketing.models import CampaignRequest
from ai_marketing.orchestrator import MarketingDecisionEngine
from ai_marketing.strategy_package import build_strategy_package, summarize_feedback


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


def test_build_strategy_package_matches_contract_shape():
    engine = MarketingDecisionEngine()
    plan = engine.generate_plan(CampaignRequest(goal="提升信用卡分期转化", product="installment"))
    package = build_strategy_package(plan)
    assert package["campaign_metadata"]["campaign_id"] == plan.campaign_id
    assert package["campaign_metadata"]["product"] == "credit_card_installment"
    assert package["audience_segments"]
    assert package["channel_routing"]
    assert package["content_brief"]["channel_copy"]["sms"]
    assert package["compliance_guard"]["frequency_limit"]


def test_summarize_feedback_generates_suggestions():
    summary = summarize_feedback(
        {
            "campaign_id": "CMP001",
            "feedback_metrics": {
                "exposure_count": 1000,
                "click_count": 50,
                "conversion_count": 5,
                "complaint_count": 2,
                "roi": 1.2,
            },
        }
    )
    assert summary["campaign_id"] == "CMP001"
    assert summary["suggestions"]


def test_generate_plan_from_knowledge_insight():
    engine = MarketingDecisionEngine()
    payload = {
        "target_product": "installment",
        "customers": [
            {
                "customer_id": "C001",
                "customer_profile": {
                    "age": 29,
                    "city_tier": 1,
                    "monthly_spend": 12000,
                    "credit_limit_usage": 0.68,
                    "tags": ["高消费", "App活跃", "分期敏感"],
                    "marketing_consent": True,
                    "risk_level": "low",
                    "complaint_risk": 0.03,
                    "recent_contact_count": 1,
                    "preferred_channel": "app_push",
                },
                "intent_vector": {"top_intents": [{"name": "分期咨询", "score": 0.76}]},
                "event_sequence": [{"event_name": "搜索分期费率"}],
            }
        ],
    }
    plan = engine.generate_plan_from_knowledge_insight(
        CampaignRequest(goal="提升分期转化", product="installment"),
        payload,
    )
    assert plan.audience_size == 1
    assert plan.segments[0].size == 1
