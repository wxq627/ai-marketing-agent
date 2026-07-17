from __future__ import annotations

import hashlib
import json
from dataclasses import replace

from .compliance import run_compliance_checks
from .content import generate_content
from .data import load_demo_customers
from .eligibility import EligibilityReport, evaluate_customer_insight, filter_to_eligible_customers
from .knowledge_adapter import customers_from_knowledge_insight
from .intent import parse_intent
from .models import CampaignRequest, MarketingPlan
from .optimizer import build_channel_plan, build_channel_plan_from_context, forecast_effect
from .persona import cluster_priority_candidates, summarize_selected_personas
from .recommender import filter_priority_candidates, score_customers, summarize_segments


class MarketingDecisionEngine:
    def __init__(self) -> None:
        self.customers = load_demo_customers()

    def generate_plan(self, request: CampaignRequest) -> MarketingPlan:
        return self._generate_plan_with_customers(request, self.customers)

    def assess_knowledge_insight(self, payload: dict) -> EligibilityReport:
        return evaluate_customer_insight(payload)

    def generate_plan_from_knowledge_insight(self, request: CampaignRequest, payload: dict) -> MarketingPlan:
        eligibility = self.assess_knowledge_insight(payload)
        eligible_payload = filter_to_eligible_customers(payload, eligibility)
        customers = customers_from_knowledge_insight(eligible_payload)
        allowed_channels = {channel for channel, count in eligibility.channel_coverage.items() if count}
        plan, selected_customer_ids = self._generate_plan_with_customers(
            request,
            customers,
            allowed_channels=allowed_channels,
            channel_context=payload.get("channel_context"),
            return_selected_customer_ids=True,
        )
        return replace(
            plan,
            eligibility_summary=_eligibility_summary(eligibility),
            customer_channel_constraints=_customer_channel_constraints(eligibility, selected_customer_ids),
        )

    def _generate_plan_with_customers(
        self,
        request: CampaignRequest,
        customers,
        allowed_channels: set[str] | None = None,
        channel_context: dict | None = None,
        return_selected_customer_ids: bool = False,
    ) -> MarketingPlan | tuple[MarketingPlan, set[str]]:
        intent = parse_intent(request)
        normalized = CampaignRequest(
            goal=request.goal,
            product=intent.product,
            channel_mode=request.channel_mode,
            budget_wan=request.budget_wan,
            risk_level=request.risk_level,
            frequency_level=request.frequency_level,
        )
        priority_candidates = filter_priority_candidates(customers, normalized)
        persona_result = cluster_priority_candidates(priority_candidates, normalized)
        scored = score_customers(
            customers,
            normalized,
            persona_assignments=persona_result.assignments if persona_result else None,
        )
        segments = (
            summarize_selected_personas(scored, persona_result.assignments) if persona_result else summarize_segments(scored)
        )
        if channel_context:
            channels = build_channel_plan_from_context(
                normalized, len(scored), channel_context, allowed_channels=allowed_channels
            )
        else:
            channels = build_channel_plan(normalized, len(scored), allowed_channels=allowed_channels)
        content = generate_content(normalized, intent, segments)
        compliance = run_compliance_checks(normalized, scored, content)
        uplift, roi, effect, experiment = forecast_effect(normalized, scored, segments, channels)
        campaign_id = self._campaign_id(normalized)

        plan = MarketingPlan(
            campaign_id=campaign_id,
            request=normalized,
            intent=intent,
            audience_size=len(scored),
            predicted_uplift=uplift,
            predicted_roi=roi,
            segments=segments,
            channels=channels,
            content=content,
            compliance=compliance,
            experiment=experiment,
            effect_forecast=effect,
            customer_persona_assignments=[
                {"customer_id": row.customer.customer_id, "persona_name": row.segment}
                for row in scored
            ],
            persona_method="kmeans" if persona_result else "rule_based",
            persona_feature_names=persona_result.feature_names if persona_result else [],
            next_actions=[
                "运营确认活动目标、权益成本和投放窗口",
                "灰度投放后回收响应、转化、投诉与核销数据",
                "用真实活动结果更新响应模型与策略约束",
            ],
        )
        if return_selected_customer_ids:
            return plan, {row.customer.customer_id for row in scored}
        return plan

    @staticmethod
    def _campaign_id(request: CampaignRequest) -> str:
        payload = json.dumps(request.__dict__, ensure_ascii=False, sort_keys=True)
        return "MKT-" + hashlib.sha1(payload.encode("utf-8")).hexdigest()[:8].upper()


def _eligibility_summary(report: EligibilityReport) -> dict:
    return {
        "candidate_count": report.candidate_count,
        "eligible_count": report.eligible_count,
        "excluded_count": report.excluded_count,
        "exclusion_summary": report.exclusion_summary,
        "global_exclusion_by_layer": report.global_exclusion_by_layer,
        "channel_block_by_layer": report.channel_block_by_layer,
        "blocked_channel_summary": report.blocked_channel_summary,
        "channel_coverage": report.channel_coverage,
        "final_decision_summary": report.final_decision_summary,
        "data_quality_warning_summary": report.data_quality_warning_summary,
        "rule_version": report.rule_version,
    }


def _customer_channel_constraints(
    report: EligibilityReport, selected_customer_ids: set[str] | None = None
) -> list[dict]:
    return [
        {
            "customer_id": decision.customer_id,
            "final_decision": decision.final_decision,
            "allowed_channels": decision.eligible_channels,
            "blocked_channels": decision.blocked_channels,
            "channel_compliance_blocks": decision.channel_compliance_blocks,
            "channel_policy_blocks": decision.channel_policy_blocks,
            "data_quality_warnings": decision.data_quality_warnings,
            "rule_trace": [trace.rule_id for trace in decision.rule_trace],
        }
        for decision in report.decisions
        if decision.eligible and (selected_customer_ids is None or decision.customer_id in selected_customer_ids)
    ]
