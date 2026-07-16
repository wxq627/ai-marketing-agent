from __future__ import annotations

import hashlib
import json

from .compliance import run_compliance_checks
from .content import generate_content
from .data import load_demo_customers
from .knowledge_adapter import customers_from_knowledge_insight
from .intent import parse_intent
from .models import CampaignRequest, MarketingPlan
from .optimizer import build_channel_plan, forecast_effect
from .recommender import score_customers, summarize_segments


class MarketingDecisionEngine:
    def __init__(self) -> None:
        self.customers = load_demo_customers()

    def generate_plan(self, request: CampaignRequest) -> MarketingPlan:
        return self._generate_plan_with_customers(request, self.customers)

    def generate_plan_from_knowledge_insight(self, request: CampaignRequest, payload: dict) -> MarketingPlan:
        customers = customers_from_knowledge_insight(payload)
        if not customers:
            customers = self.customers
        return self._generate_plan_with_customers(request, customers)

    def _generate_plan_with_customers(self, request: CampaignRequest, customers) -> MarketingPlan:
        intent = parse_intent(request)
        normalized = CampaignRequest(
            goal=request.goal,
            product=intent.product,
            channel_mode=request.channel_mode,
            budget_wan=request.budget_wan,
            risk_level=request.risk_level,
            frequency_level=request.frequency_level,
        )
        scored = score_customers(customers, normalized)
        segments = summarize_segments(scored)
        channels = build_channel_plan(normalized, len(scored))
        content = generate_content(normalized, intent, segments)
        compliance = run_compliance_checks(normalized, scored, content)
        uplift, roi, effect, experiment = forecast_effect(normalized, scored, segments)
        campaign_id = self._campaign_id(normalized)

        return MarketingPlan(
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
            next_actions=[
                "运营确认活动目标、权益成本和投放窗口",
                "灰度投放后回收响应、转化、投诉与核销数据",
                "用真实活动结果更新响应模型与策略约束",
            ],
        )

    @staticmethod
    def _campaign_id(request: CampaignRequest) -> str:
        payload = json.dumps(request.__dict__, ensure_ascii=False, sort_keys=True)
        return "MKT-" + hashlib.sha1(payload.encode("utf-8")).hexdigest()[:8].upper()
