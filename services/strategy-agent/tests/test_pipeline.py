from ai_marketing.models import CampaignRequest
from ai_marketing.orchestrator import MarketingDecisionEngine
from ai_marketing.strategy_package import build_strategy_package, summarize_feedback
from ai_marketing.eligibility import evaluate_customer_insight


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
                    "recent_contact_count_by_channel": {"app_push": 0, "sms": 0, "wechat": 0},
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


def test_eligibility_evaluates_global_and_channel_rules():
    payload = {
        "campaign_id": "CMP001",
        "target_product": "credit_card_installment",
        "evaluation_time": "2026-07-16T12:00:00+08:00",
        "channel_context": {"available_channels": ["app_push", "sms"]},
        "customers": [
            {
                "customer_id": "C001",
                "customer_profile": {
                    "marketing_consent": True,
                    "channel_consents": {"app_push": True, "sms": False},
                    "risk_level": "low",
                    "complaint_risk": 0.1,
                    "owned_products": [],
                },
                "contact_history": [],
            },
            {
                "customer_id": "C002",
                "customer_profile": {
                    "marketing_consent": False,
                    "risk_level": "low",
                    "complaint_risk": 0.1,
                    "owned_products": [],
                },
                "contact_history": [],
            },
            {
                "customer_id": "C003",
                "customer_profile": {
                    "marketing_consent": True,
                    "risk_level": "low",
                    "complaint_risk": 0.1,
                    "owned_products": [],
                },
                "contact_history": [
                    {"channel": "sms", "contact_type": "marketing", "contacted_at": "2026-07-15T10:00:00+08:00"},
                    {"channel": "sms", "contact_type": "marketing", "contacted_at": "2026-07-14T10:00:00+08:00"},
                ],
            },
        ],
    }
    report = evaluate_customer_insight(payload)
    decisions = {decision.customer_id: decision for decision in report.decisions}

    assert report.candidate_count == 3
    assert report.eligible_count == 2
    assert decisions["C001"].eligible_channels == ["app_push"]
    assert decisions["C001"].blocked_channels["sms"] == ["channel_consent_revoked"]
    assert decisions["C001"].final_decision == "ALLOW_WITH_LIMITS"
    assert {trace.layer for trace in decisions["C001"].rule_trace} == {"compliance"}
    assert decisions["C002"].eligible is False
    assert decisions["C002"].final_decision == "BLOCK"
    assert decisions["C002"].hard_blocks == ["no_marketing_consent"]
    assert "no_marketing_consent" in decisions["C002"].exclusion_reasons
    assert decisions["C003"].eligible_channels == ["app_push"]
    assert decisions["C003"].blocked_channels["sms"] == ["frequency_cap_reached"]
    assert decisions["C003"].final_decision == "ALLOW_WITH_LIMITS"
    assert any(trace.rule_id == "FREQ_CHANNEL_7D_001" for trace in decisions["C003"].rule_trace)
    assert report.global_exclusion_by_layer["compliance"] == {"no_marketing_consent": 1}
    assert report.channel_block_by_layer["compliance"] == {"channel_consent_revoked": 1}


def test_knowledge_insight_plan_uses_only_eligible_customers():
    payload = {
        "campaign_id": "CMP001",
        "target_product": "installment",
        "customers": [
            {
                "customer_id": "C001",
                "customer_profile": {
                    "marketing_consent": True,
                    "risk_level": "low",
                    "complaint_risk": 0.05,
                    "recent_contact_count": 0,
                    "recent_contact_count_by_channel": {"app_push": 0, "sms": 0, "wechat": 0},
                    "owned_products": [],
                    "tags": [],
                },
            },
            {
                "customer_id": "C002",
                "customer_profile": {
                    "marketing_consent": False,
                    "risk_level": "low",
                    "complaint_risk": 0.05,
                    "recent_contact_count": 0,
                    "recent_contact_count_by_channel": {"app_push": 0, "sms": 0, "wechat": 0},
                    "owned_products": [],
                    "tags": [],
                },
            },
        ],
    }
    plan = MarketingDecisionEngine().generate_plan_from_knowledge_insight(
        CampaignRequest(goal="installment conversion", product="installment"), payload
    )
    assert plan.audience_size == 1
    assert plan.eligibility_summary["eligible_count"] == 1
    assert plan.eligibility_summary["exclusion_summary"] == {"no_marketing_consent": 1}


def test_business_suppression_is_distinct_from_compliance_block():
    payload = {
        "campaign_id": "CMP001",
        "target_product": "installment",
        "customers": [
            {
                "customer_id": "C001",
                "customer_profile": {
                    "marketing_consent": True,
                    "risk_level": "low",
                    "complaint_risk": 0.8,
                    "owned_products": [],
                },
            }
        ],
    }
    decision = evaluate_customer_insight(payload).decisions[0]

    assert decision.final_decision == "SUPPRESS"
    assert decision.hard_blocks == []
    assert decision.policy_actions == ["high_complaint_risk"]
    assert decision.eligible is False


def test_strategy_uses_only_channels_allowed_by_stage_two():
    payload = {
        "campaign_id": "CMP001",
        "target_product": "installment",
        "channel_context": {"available_channels": ["app_push", "sms", "wechat"]},
        "customers": [
            {
                "customer_id": "C001",
                "customer_profile": {
                    "marketing_consent": True,
                    "channel_consents": {"app_push": True, "sms": False, "wechat": True},
                    "channel_capabilities": {"app_push": True, "sms": True, "wechat": False},
                    "risk_level": "low",
                    "complaint_risk": 0.05,
                    "recent_contact_count": 0,
                    "recent_contact_count_by_channel": {"app_push": 0, "sms": 0, "wechat": 0},
                    "owned_products": [],
                    "tags": [],
                },
            }
        ],
    }
    plan = MarketingDecisionEngine().generate_plan_from_knowledge_insight(
        CampaignRequest(goal="installment conversion", product="installment", channel_mode="omni"), payload
    )
    package = build_strategy_package(plan)

    assert [channel.channel for channel in plan.channels] == ["App Push"]
    assert [route["channel"] for route in package["channel_routing"]] == ["app_push"]
    assert package["audience_delivery_constraints"]["customer_channel_constraints"][0]["allowed_channels"] == [
        "app_push"
    ]


def test_all_channel_compliance_blocks_are_not_suppressed_as_policy():
    payload = {
        "campaign_id": "CMP001",
        "target_product": "installment",
        "channel_context": {"available_channels": ["app_push", "sms", "wechat"]},
        "customers": [
            {
                "customer_id": "C001",
                "customer_profile": {
                    "marketing_consent": True,
                    "channel_consents": {"app_push": False, "sms": False, "wechat": False},
                    "risk_level": "low",
                    "complaint_risk": 0.05,
                    "owned_products": [],
                },
                "contact_history": [],
            }
        ],
    }
    decision = evaluate_customer_insight(payload).decisions[0]

    assert decision.final_decision == "BLOCK_ALL_CHANNELS"
    assert decision.hard_blocks == []
    assert decision.channel_compliance_blocks == {
        "app_push": ["channel_consent_revoked"],
        "sms": ["channel_consent_revoked"],
        "wechat": ["channel_consent_revoked"],
    }
    assert decision.policy_actions == []


def test_frequency_requires_channel_level_data_not_global_total():
    payload = {
        "campaign_id": "CMP001",
        "target_product": "installment",
        "channel_context": {"available_channels": ["app_push"]},
        "customers": [
            {
                "customer_id": "C001",
                "customer_profile": {
                    "marketing_consent": True,
                    "risk_level": "low",
                    "complaint_risk": 0.05,
                    "recent_contact_count": 5,
                    "owned_products": [],
                },
            }
        ],
    }
    decision = evaluate_customer_insight(payload).decisions[0]

    assert decision.final_decision == "SUPPRESS"
    assert decision.channel_policy_blocks == {"app_push": ["frequency_data_missing"]}
    assert "frequency_cap_reached" not in decision.blocked_channels["app_push"]
    assert decision.data_quality_warnings == ["frequency_data_missing:app_push"]
