from __future__ import annotations

from .models import CampaignRequest, MarketingPlan


PRODUCT_CODES = {
    "installment": "credit_card_installment",
    "coupon": "coupon_package",
    "travel": "travel_benefit",
}

BENEFIT_RULES = {
    "installment": {
        "benefit_type": "installment_fee_coupon",
        "benefit_name": "分期手续费折扣券",
        "eligibility": ["marketing_consent=true", "risk_level != high"],
        "limit": "每客户最多领取1次",
    },
    "coupon": {
        "benefit_type": "scenario_coupon",
        "benefit_name": "餐饮/商超/线上支付消费券包",
        "eligibility": ["marketing_consent=true", "recent_contact_count <= frequency_limit"],
        "limit": "每客户每活动周期最多领取1次",
    },
    "travel": {
        "benefit_type": "travel_benefit_package",
        "benefit_name": "商旅权益组合包",
        "eligibility": ["marketing_consent=true", "travel_intent_score >= threshold"],
        "limit": "权益数量有限，按活动页规则生效",
    },
}

FREQUENCY_LIMITS = {
    1: "7天最多触达1次",
    2: "7天最多触达2次",
    3: "7天最多触达3次",
    4: "3天最多触达2次",
}


def build_strategy_package(plan: MarketingPlan) -> dict:
    request = plan.request
    product_code = PRODUCT_CODES.get(request.product, request.product)
    return {
        "campaign_metadata": {
            "campaign_id": plan.campaign_id,
            "objective": plan.intent.objective,
            "product": product_code,
            "budget": request.budget_wan * 10000,
        },
        "audience_segments": [
            {
                "segment_id": f"SEG{index:03d}",
                "segment_name": segment.name,
                "size": segment.size,
                "priority": round(segment.avg_score / 100, 3),
                "features": segment.reasons,
                "expected_conversion_rate": round(segment.conversion_rate / 100, 4),
                "expected_roi": plan.predicted_roi,
            }
            for index, segment in enumerate(plan.segments, start=1)
        ],
        "audience_persona": {
            "method": plan.persona_method,
            "feature_names": plan.persona_feature_names,
            "cluster_count": len(plan.segments),
        },
        "benefit_rule": BENEFIT_RULES.get(request.product, BENEFIT_RULES["installment"]),
        "channel_routing": [
            {
                "channel": normalize_channel_name(channel.channel),
                "budget_ratio": channel.budget_share,
                "contact_order": index,
                "retry_rule": build_retry_rule(channel.channel),
            }
            for index, channel in enumerate(plan.channels, start=1)
        ],
        "audience_delivery_constraints": {
            "channel_coverage": plan.eligibility_summary.get("channel_coverage", {}),
            "channel_block_by_layer": plan.eligibility_summary.get("channel_block_by_layer", {}),
            "data_quality_warning_summary": plan.eligibility_summary.get("data_quality_warning_summary", {}),
            "customer_channel_constraints": plan.customer_channel_constraints,
        },
        "budget_allocation": {
            "total_budget": request.budget_wan * 10000,
            "unit": "CNY",
            "allocation_method": "按渠道转化效率、成本和风险约束分配",
        },
        "content_brief": {
            "core_message": plan.content.get("explain", ""),
            "tone": "专业、克制、合规",
            "channel_copy": plan.content,
            "personalization_fields": ["customer_name", "available_benefit", "valid_period"],
            "required_disclosure": ["活动规则以页面展示为准", "短信需包含退订方式"],
        },
        "compliance_guard": {
            "blocked_words": ["稳赚", "保证", "无条件通过", "最高收益"],
            "must_not_claim": ["承诺一定省钱", "承诺审批通过", "夸大权益价值"],
            "frequency_limit": FREQUENCY_LIMITS.get(request.frequency_level, "7天最多触达2次"),
            "checks": [check.__dict__ for check in plan.compliance],
            "eligibility_summary": plan.eligibility_summary,
        },
        "experiment_plan": {
            "control_group_ratio": 0.1,
            "test_group_ratio": 0.9,
            "success_metrics": ["conversion_rate", "roi", "complaint_rate"],
            "sample_hint": plan.experiment.get("sample_hint", ""),
        },
        "callback_config": {
            "feedback_url": "/api/strategy/feedback",
            "report_interval": "hourly",
        },
    }


def normalize_channel_name(name: str) -> str:
    mapping = {
        "App Push": "app_push",
        "App Home": "app_push",
        "SMS": "sms",
        "WeChat": "wechat",
        "App弹窗": "app_popup",
        "App首页": "app_home",
        "Push": "app_push",
        "短信": "sms",
        "企微": "wechat",
    }
    return mapping.get(name, name)


def build_retry_rule(channel_name: str) -> str:
    if channel_name in {"App Push", "App Home"}:
        return "Use an allowed fallback channel only after the frequency check passes."
    if channel_name == "SMS":
        return "Skip when SMS is blocked by customer-level channel eligibility."
    if channel_name == "WeChat":
        return "Send only when the customer is eligible for the WeChat channel."
    if channel_name in {"App弹窗", "App首页", "Push"}:
        return "24小时未点击后可切换短信或企微，命中频控则跳过"
    if channel_name == "短信":
        return "命中频控或投诉风险阈值则跳过"
    if channel_name == "企微":
        return "仅高价值且授权客户触达，客户拒绝后停止营销"
    return "按活动频控规则执行"


def summarize_feedback(feedback: dict) -> dict:
    metrics = feedback.get("feedback_metrics", {})
    exposure = max(int(metrics.get("exposure_count", 0)), 1)
    click = int(metrics.get("click_count", 0))
    conversion = int(metrics.get("conversion_count", 0))
    complaint = int(metrics.get("complaint_count", 0))
    ctr = click / exposure
    conversion_rate = conversion / exposure
    complaint_rate = complaint / exposure
    suggestions: list[str] = []
    if complaint_rate > 0.001:
        suggestions.append("投诉率偏高，建议降低高风险客群触达频次并减少短信渠道占比")
    if ctr < 0.08:
        suggestions.append("点击率偏低，建议优化权益表达和首触达文案")
    if conversion_rate < 0.01:
        suggestions.append("转化率偏低，建议收紧客群圈选并提高权益匹配度")
    if not suggestions:
        suggestions.append("当前反馈表现稳定，可保留主策略并扩大高 ROI 客群")

    return {
        "campaign_id": feedback.get("campaign_id", ""),
        "metrics": {
            "ctr": round(ctr, 4),
            "conversion_rate": round(conversion_rate, 4),
            "complaint_rate": round(complaint_rate, 6),
            "roi": metrics.get("roi", 0),
        },
        "suggestions": suggestions,
    }
