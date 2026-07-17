from ai_marketing.models import CampaignRequest
from ai_marketing.orchestrator import MarketingDecisionEngine
from ai_marketing.strategy_package import build_strategy_package, summarize_feedback
from ai_marketing.eligibility import evaluate_customer_insight
from ai_marketing.llm_adapter import parse_campaign_goal
from ai_marketing.local_knowledge_data import LocalKnowledgeData
from ai_marketing.persona import kmeans_available
from ai_marketing.personalization import PersonalizedStrategyService


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


def test_goal_parser_falls_back_without_api_key():
    result = parse_campaign_goal(
        "Improve installment conversion with a low-risk campaign",
        CampaignRequest(
            goal="ignored",
            product="coupon",
            channel_mode="app",
            budget_wan=20,
            risk_level=1,
            frequency_level=1,
        ),
        api_key="",
    )
    assert result.source == "fallback"
    assert result.fallback_reason == "api_key_not_configured"
    assert result.campaign_request.goal == "Improve installment conversion with a low-risk campaign"
    assert result.campaign_request.budget_wan == 20


def test_goal_parser_uses_deepseek_json_response():
    def sender(payload, api_key):
        assert payload["response_format"] == {"type": "json_object"}
        assert payload["thinking"] == {"type": "disabled"}
        assert "json" in payload["messages"][0]["content"].lower()
        assert api_key == "test-key"
        return {
            "choices": [
                {
                    "message": {
                        "content": (
                            '{"product":"installment","channel_mode":"app","budget_wan":30,'
                            '"risk_level":1,"frequency_level":2,'
                            '"audience_hints":["high_spend"],"constraints":["frequency_cap"]}'
                        )
                    },
                }
            ]
        }

    result = parse_campaign_goal(
        "Target installment users with low risk",
        CampaignRequest(goal="ignored"),
        api_key="test-key",
        sender=sender,
    )
    assert result.source == "deepseek"
    assert result.campaign_request.product == "installment"
    assert result.campaign_request.channel_mode == "app"
    assert result.campaign_request.budget_wan == 30
    assert result.audience_hints == ["high_spend"]


def test_real_project_one_csv_data_can_run_through_eligibility():
    payload = LocalKnowledgeData().build_customer_insight(
        campaign_id="REAL_DATA_TEST",
        target_product="installment",
        evaluation_time="2026-07-17T12:00:00+08:00",
    )
    report = evaluate_customer_insight(payload)

    assert payload["source"] == "project1_local_csv"
    assert len(payload["customers"]) == 8000
    assert report.candidate_count == 8000
    assert 0 < report.eligible_count < report.candidate_count
    assert report.exclusion_summary
    customer = next(item for item in payload["customers"] if item["customer_id"] == "C000001")
    assert customer["intent_vector"]["top_intents"][0] == {
        "name": "\u5206\u671f/\u501f\u8d37\u9700\u6c42",
        "score": 90.0,
    }


def test_real_project_one_data_generates_a_selected_strategy_package():
    payload = LocalKnowledgeData().build_customer_insight(
        campaign_id="REAL_STRATEGY_TEST",
        target_product="installment",
        evaluation_time="2026-07-17T12:00:00+08:00",
        limit=500,
    )
    plan = MarketingDecisionEngine().generate_plan_from_knowledge_insight(
        CampaignRequest(goal="installment conversion", product="installment", budget_wan=20),
        payload,
    )
    package = build_strategy_package(plan)

    assert plan.audience_size > 0
    assert plan.audience_size <= plan.eligibility_summary["eligible_count"]
    assert plan.channels[0].unit_cost > 0
    assert len(plan.customer_channel_constraints) == plan.audience_size
    assert package["channel_routing"]
    customer_mapping = package["audience_delivery_constraints"]["customer_channel_constraints"]
    assert all(item["persona_name"] and item["segment_id"] for item in customer_mapping)


def test_kmeans_personas_cover_the_selected_audience_when_dependency_is_available():
    if not kmeans_available():
        return

    plan = MarketingDecisionEngine().generate_plan(
        CampaignRequest(goal="installment conversion", product="installment", budget_wan=20)
    )

    assert plan.persona_method == "kmeans"
    assert len(plan.segments) == 4
    assert sum(segment.size for segment in plan.segments) == plan.audience_size
    assert plan.persona_feature_names
    assert all(segment.strategy["content_direction"] for segment in plan.segments)
    package = build_strategy_package(plan)
    assert len(package["content_brief"]["persona_content_briefs"]) == 4


def test_online_personalization_returns_recommendations_and_chat_strategy():
    service = PersonalizedStrategyService(LocalKnowledgeData(), MarketingDecisionEngine())
    recommendations = service.recommendations("UID000001", limit=5)
    decision = service.decision(
        "UID000001",
        scene="chat",
        user_intent="\u60f3\u4e86\u89e3\u8d26\u5355\u5206\u671f\u8d39\u7528",
    )

    assert recommendations["recommendations"]
    assert recommendations["recommendations"][0]["rank"] == 1
    assert all(item["allowed_channels"] == ["in_app"] for item in recommendations["recommendations"])
    assert decision["should_recommend"] is True
    assert decision["recommended_product_id"] == "INSTALLMENT"


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
