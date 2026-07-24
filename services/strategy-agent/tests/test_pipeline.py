import json

from ai_marketing.models import CampaignRequest
from ai_marketing.orchestrator import MarketingDecisionEngine
from ai_marketing.strategy_package import build_optimized_strategy_package, build_strategy_package, summarize_feedback
from ai_marketing.eligibility import evaluate_customer_insight
from ai_marketing.llm_adapter import parse_campaign_goal
from ai_marketing.local_knowledge_data import LocalKnowledgeData
from ai_marketing.persona import DEFAULT_CLUSTER_COUNT, kmeans_available
from ai_marketing.personalization import PersonalizedStrategyService, _merge_unique_recommendations
from ai_marketing.candidates import StrategyCandidateService
from ai_marketing.historical_model_scoring import HistoricalModelScoreProvider
from ai_marketing.storage import PlanRepository
from ai_marketing.selection import BudgetConstrainedSelector
from ai_marketing.strategy_value import StrategyValueCalculator
from ai_marketing.strategy_copilot import _content_context, _fallback_content
from app import _normalize_c_feedback_event, _published_strategy_delivery_status


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


def test_goal_parser_fallback_extracts_budget_and_channel():
    result = parse_campaign_goal(
        "面向高价值客户，用短信投放分期优惠，预算20万",
        CampaignRequest(goal="", product="installment", channel_mode="omni", budget_wan=80),
        api_key="",
    )

    assert result.campaign_request.budget_wan == 20
    assert result.campaign_request.channel_mode == "sms"


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
    assert len(plan.segments) == DEFAULT_CLUSTER_COUNT
    assert sum(segment.size for segment in plan.segments) == plan.audience_size
    assert plan.persona_feature_names
    assert all(segment.strategy["content_direction"] for segment in plan.segments)
    assert all(segment.strategy["cluster_feature_priorities"] for segment in plan.segments)
    assert all("数据驱动群像" in segment.name for segment in plan.segments)
    package = build_strategy_package(plan)
    assert len(package["content_brief"]["persona_content_briefs"]) == DEFAULT_CLUSTER_COUNT


def test_online_personalization_returns_recommendations_and_chat_strategy():
    service = PersonalizedStrategyService(LocalKnowledgeData(), MarketingDecisionEngine())
    recommendations = service.recommendations("UID000001", limit=5)
    decision = service.decision(
        "UID000001",
        scene="chat",
        user_intent="\u60f3\u4e86\u89e3\u8d26\u5355\u5206\u671f\u8d39\u7528",
    )

    assert recommendations["recommendations"]
    assert recommendations["status"] == "success"
    assert recommendations["eligible_for_personalization"] is True
    assert recommendations["eligible_for_marketing"] is True
    assert recommendations["reason_code"] is None
    assert recommendations["published_strategy_context"] == []
    assert recommendations["published_strategy"] is None
    assert recommendations["recommendations"][0]["rank"] == 1
    assert all(item["allowed_channels"] == ["in_app"] for item in recommendations["recommendations"])
    assert decision["should_recommend"] is True
    assert decision["recommended_product_id"] == "INSTALLMENT"


def test_online_personalization_returns_a_fixed_empty_envelope_without_consent():
    service = PersonalizedStrategyService(LocalKnowledgeData(), MarketingDecisionEngine())

    result = service.recommendations("UID000020", limit=5)

    assert result["status"] == "not_eligible"
    assert result["eligible_for_personalization"] is False
    assert result["eligible_for_marketing"] is False
    assert result["reason_code"] == "personalization_consent_required"
    assert result["recommendations"] == []
    assert result["published_strategy_context"] == []
    assert result["published_strategy"] is None


def test_published_strategy_delivery_status_keeps_auditable_membership_but_blocks_missing_consent():
    status = _published_strategy_delivery_status(
        {
            "status": "not_eligible",
            "eligible_for_personalization": False,
            "eligible_for_marketing": False,
            "reason_code": "personalization_consent_required",
            "recommendations": [],
        },
        in_published_strategy=True,
    )

    assert status == {
        "in_published_strategy": True,
        "deliverable_now": False,
        "block_reason": "personalization_consent_required",
    }


def test_personalization_deduplicates_published_and_catalogue_cards():
    published = [
        {
            "product_id": "CAMPAIGN:SUMMER_FILM",
            "benefit_id": "campaign_benefit",
            "title": "观影活动权益",
            "source": "published_strategy",
        }
    ]
    catalogue = [
        {
            "product_id": "PROD_FILM_CARD",
            "benefit_id": "BEN_FILM_001",
            "title": "观影活动权益",
            "source": "catalogue",
        },
        {
            "product_id": "PROD_TRAVEL_CARD",
            "benefit_id": "BEN_TRAVEL_001",
            "title": "出行礼遇",
            "source": "catalogue",
        },
    ]

    result = _merge_unique_recommendations(published=published, catalogue=catalogue, limit=3)

    assert [item["title"] for item in result] == ["观影活动权益", "出行礼遇"]


def test_c_feedback_normalizes_to_detail_ignore_and_unsubscribe():
    assert _normalize_c_feedback_event("详情") == "view_detail"
    assert _normalize_c_feedback_event("ignore") == "ignored"
    assert _normalize_c_feedback_event("not_interested") == "ignored"
    assert _normalize_c_feedback_event("退订") == "unsubscribed"


def test_real_data_candidate_generation_outputs_only_eligible_product_channel_pairs():
    result = StrategyCandidateService(LocalKnowledgeData(), MarketingDecisionEngine()).generate(
        customer_limit=30,
        sample_limit=500,
        include_blocked=True,
    )

    assert result["source"] == "project1_local_csv"
    assert result["summary"]["input_customer_count"] == 30
    assert result["summary"]["eligible_candidate_count"] > 0
    assert result["candidate_sample"]
    assert all(item["candidate_status"] == "ELIGIBLE" for item in result["candidate_sample"])
    assert all(item["channel"] in {"app_push", "sms", "wechat"} for item in result["candidate_sample"])
    assert all(item["contact_cost"] > 0 for item in result["candidate_sample"])
    assert result["blocked_sample"]


def test_historical_model_score_provider_handles_missing_artifacts(tmp_path):
    provider = HistoricalModelScoreProvider(artifact_dir=tmp_path / "missing")

    result = provider.score(
        customer_id="C000001",
        campaign_id="CAMP_2026_DOUBLE11",
        channel="app_push",
        touch_time="2026-07-17 12:00:00",
    )

    assert result["model_available"] is False
    assert result["reason"].startswith("missing_artifacts:")


def test_historical_model_score_provider_uses_v2_artifacts_when_available():
    provider = HistoricalModelScoreProvider()
    if not provider.available:
        return

    result = provider.score(
        customer_id="C000001",
        campaign_id="CAMP_2026_DOUBLE11",
        channel="app_push",
        touch_time="2026-07-17 12:00:00",
    )

    assert result["model_available"] is True
    assert result["feature_source"] == "project1_pre_touch_raw_data"
    assert set(result["probabilities"]) == {"p_open", "p_click", "p_conversion", "p_unsubscribe"}
    assert all(0 <= value <= 1 for value in result["probabilities"].values())


def test_published_strategy_context_is_versioned_and_customer_scoped(tmp_path):
    insight = LocalKnowledgeData().build_customer_insight(
        campaign_id="PUBLISHED_CONTEXT_TEST",
        target_product="installment",
        limit=100,
    )
    plan = MarketingDecisionEngine().generate_plan_from_knowledge_insight(
        CampaignRequest(goal="installment conversion", product="installment", budget_wan=20),
        insight,
    )
    package = build_strategy_package(plan)
    customer_id = package["audience_delivery_constraints"]["customer_channel_constraints"][0]["customer_id"]
    repository = PlanRepository(tmp_path / "strategy.sqlite3")
    repository.save(plan, package)

    publication = repository.publish(plan.campaign_id, effective_from="2026-07-20 09:00:00")
    contexts = repository.published_context_for_customer(
        customer_id=customer_id,
        product="installment",
        as_of="2026-07-20 10:00:00",
    )

    assert publication["status"] == "published"
    assert publication["strategy_version"].startswith("STR_")
    downloaded = repository.get_published_package(publication["strategy_version"])
    assert downloaded is not None
    assert downloaded["campaign_metadata"]["campaign_id"] == plan.campaign_id
    assert len(contexts) == 1
    assert contexts[0]["strategy_version"] == publication["strategy_version"]
    assert contexts[0]["benefit_rule"]

    repository.archive(publication["strategy_version"])
    assert repository.published_context_for_customer(
        customer_id=customer_id,
        product="installment",
        as_of="2026-07-20 10:00:00",
    ) == []


def test_strategy_value_uses_click_trigger_for_benefit_costs():
    candidate = {
        "candidate_id": "CANDIDATE_1",
        "campaign_id": "CAMP_2026_618",
        "annual_fee": 300,
        "contact_cost": 0.02,
        "economic_profile": {
            "monthly_spend": 10000,
            "value_level": "medium",
            "risk_level": "low",
            "complaint_risk": 0.0,
        },
        "model_scores": {
            "probabilities": {
                "p_open": 0.8,
                "p_click": 0.5,
                "p_conversion": 0.2,
                "p_unsubscribe": 0.01,
            }
        },
    }

    value = StrategyValueCalculator().score(candidate)

    assert value.breakdown["benefit_expected_cost"] == 40.0
    assert value.breakdown["contact_cost"] == 0.02
    assert value.p_long_term > 0


def test_strategy_value_prefers_available_pd_score_over_risk_level_fallback():
    candidate = {
        "candidate_id": "CANDIDATE_PD_1",
        "campaign_id": "CAMP_2026_618",
        "contact_cost": 0.02,
        "economic_profile": {"monthly_spend": 10000, "value_level": "medium", "risk_level": "low", "complaint_risk": 0.0},
        "model_scores": {"probabilities": {"p_click": 0.5, "p_conversion": 0.2, "p_unsubscribe": 0.01}},
        "pd_risk_score": {"model_available": True, "pd_6m": 0.12},
    }

    value = StrategyValueCalculator().score(candidate)

    assert value.breakdown["pd_source"] == "pd_risk_model"
    assert value.breakdown["pd_6m"] == 0.12
    assert value.breakdown["credit_expected_loss"] == 60.0


def test_budget_selector_enforces_budget_and_customer_deduplication():
    candidates = [
        {
            "candidate_id": "A1",
            "customer_id": "C001",
            "channel": "app_push",
            "channel_daily_capacity": 10,
            "model_scores": {"probabilities": {"p_conversion": 0.5}},
            "strategy_value": {"expected_net_value": 100, "budget_cost": 40, "value_density": 2.5},
        },
        {
            "candidate_id": "A2",
            "customer_id": "C001",
            "channel": "sms",
            "channel_daily_capacity": 10,
            "model_scores": {"probabilities": {"p_conversion": 0.8}},
            "strategy_value": {"expected_net_value": 90, "budget_cost": 20, "value_density": 4.5},
        },
        {
            "candidate_id": "B1",
            "customer_id": "C002",
            "channel": "app_push",
            "channel_daily_capacity": 10,
            "model_scores": {"probabilities": {"p_conversion": 0.4}},
            "strategy_value": {"expected_net_value": 80, "budget_cost": 70, "value_density": 1.14},
        },
    ]

    result = BudgetConstrainedSelector().select(candidates, budget=70)

    assert result.budget_used <= 70
    assert len({item["customer_id"] for item in result.selected}) == len(result.selected)
    assert result.excluded["budget_exhausted"] == 1
    assert result.excluded["customer_deduplicated"] == 1


def test_feedback_is_persisted(tmp_path):
    repository = PlanRepository(tmp_path / "strategy.sqlite3")
    stored = repository.save_feedback(
        {
            "strategy_version": "STR_TEST_001",
            "campaign_id": "MKT_TEST",
            "oneid": "UID000001",
            "channel": "in_app",
            "event_type": "clicked",
            "event_time": "2026-07-20 10:00:00",
            "feedback_metrics": {"exposure_count": 1, "click_count": 1},
        }
    )

    rows = repository.list_feedback(strategy_version="STR_TEST_001")

    assert stored["stored"] is True
    assert rows[0]["event_type"] == "clicked"
    assert rows[0]["payload"]["oneid"] == "UID000001"


def test_ignore_frequency_and_channel_unsubscribe_are_scoped_correctly(tmp_path):
    repository = PlanRepository(tmp_path / "strategy.sqlite3")
    base = {
        "strategy_version": "STR_TEST_001",
        "campaign_id": "CAMP_TEST",
        "oneid": "UID000001",
        "channel": "app_push",
        "event_type": "ignored",
    }
    for day in (18, 20, 22):
        repository.save_feedback({**base, "event_time": f"2026-07-{day} 10:00:00"})

    frequency_block = repository.channel_delivery_state(
        "UID000001", "CAMP_TEST", "app_push", as_of="2026-07-22 12:00:00"
    )

    assert frequency_block["allowed"] is False
    assert frequency_block["reason"] == "unresponsive_frequency_cap_reached"
    assert frequency_block["unresponsive_touches_7d"] == 3

    repository.save_feedback({**base, "event_type": "view_detail", "event_time": "2026-07-23 10:00:00"})
    responded = repository.channel_delivery_state(
        "UID000001", "CAMP_TEST", "app_push", as_of="2026-07-23 12:00:00"
    )
    assert responded["allowed"] is True
    assert responded["unresponsive_touches_7d"] == 0

    repository.suppress_campaign_channel("UID000001", "CAMP_TEST", "app_push", "unsubscribed")
    app_state = repository.channel_delivery_state("UID000001", "CAMP_TEST", "app_push")
    sms_state = repository.channel_delivery_state("UID000001", "CAMP_TEST", "sms")

    assert app_state["allowed"] is False
    assert app_state["reason"] == "campaign_channel_unsubscribed"
    assert sms_state["allowed"] is True


def test_optimized_delivery_list_can_be_published_for_c_side(tmp_path):
    optimization = {
        "campaign_id": "CAMP_2026_DOUBLE11",
        "budget": 500,
        "value_policy_version": "demo-2026-07-v1",
        "campaign_context": {
            "strategy_object_type": "installment",
            "benefit_category": "installment",
            "objective": "conversion",
            "benefit_cost_trigger": "conversion",
        },
        "selection_summary": {
            "selected_candidate_count": 1,
            "budget_used": 45,
            "expected_net_value": 150,
            "expected_conversion_count": 0.4,
        },
        "_selected_candidates": [
            {
                "candidate_id": "CANDIDATE_001",
                "customer_id": "C001",
                "oneid": "UID001",
                "channel": "app_push",
                "strategy_value": {"expected_net_value": 150},
                "model_scores": {"probabilities": {"p_conversion": 0.4}},
            }
        ],
    }
    package = build_optimized_strategy_package(optimization)
    repository = PlanRepository(tmp_path / "strategy.sqlite3")
    repository.save_optimized_draft(
        campaign_id="CAMP_2026_DOUBLE11",
        strategy_package=package,
        selection_summary=optimization["selection_summary"],
    )

    publication = repository.publish("CAMP_2026_DOUBLE11", effective_from="2026-07-20 09:00:00")
    context = repository.published_context_for_customer(
        customer_id="C001",
        product="installment",
        as_of="2026-07-20 10:00:00",
    )

    assert publication["product"] == "credit_card_installment"
    downloaded = repository.get_published_package(publication["strategy_version"])
    assert downloaded is not None
    assert downloaded["benefit_rule"]["benefit_type"] == "installment_fee_coupon"
    assert downloaded["benefit_rule"]["benefit_name"] == "分期手续费优惠"
    assert context[0]["strategy_version"] == publication["strategy_version"]
    assert context[0]["allowed_channels"] == ["app_push"]


def test_downloaded_legacy_package_has_c_side_benefit_fields(tmp_path):
    repository = PlanRepository(tmp_path / "strategy.sqlite3")
    package = {
        "campaign_metadata": {"campaign_id": "LEGACY", "product": "coupon_package", "budget": 100},
        "benefit_rule": {"benefit_category": "消费券"},
    }
    with repository._connection() as conn:
        conn.execute(
            """
            insert into strategy_publication
            (strategy_version, campaign_id, product, status, effective_from, effective_to,
             strategy_package, created_at, published_at)
            values (?, ?, ?, 'published', ?, null, ?, ?, ?)
            """,
            (
                "STR_LEGACY_001",
                "LEGACY",
                "coupon_package",
                "2026-07-20 09:00:00",
                json.dumps(package, ensure_ascii=False),
                "2026-07-20 09:00:00",
                "2026-07-20 09:00:00",
            ),
        )

    downloaded = repository.get_published_package("STR_LEGACY_001")
    assert downloaded is not None
    assert downloaded["benefit_rule"]["benefit_type"] == "campaign_benefit"
    assert downloaded["benefit_rule"]["benefit_name"] == "消费券活动权益"


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


def test_copy_uses_campaign_brief_not_recent_behavior_filter():
    configuration = {
        "campaign_id": "CAMP_2026_SUMMER",
        "campaign_name": "暑期出行季 · 消费权益",
        "channel_mode": "app_sms",
        "target_segments": ["high_intent"],
        "operator_filters": {"recent_behaviors": ["entertainment", "movie"]},
    }

    content = _fallback_content(configuration, ["app", "sms"])

    assert any(keyword in content["app"] for keyword in ("机票", "酒店", "WiFi"))
    assert "观影" not in content["app"]
    assert "电影" not in content["sms"]
    assert len(content["sms"]) <= 70


def test_campaign_brief_reads_project_one_activity_details():
    configuration = {
        "campaign_id": "CAMP_2026_618",
        "campaign_name": "618购物节返现 · 消费权益",
        "channel_mode": "app",
    }

    brief = _content_context(configuration)["campaign_brief"]

    assert brief["campaign_name"] == "618购物节返现"
    assert any("天猫/京东" in item or "6期免息" in item for item in brief["benefit_highlights"])
    assert brief["validity"] == "2026-06-01至2026-06-18"
