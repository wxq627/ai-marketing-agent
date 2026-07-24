from __future__ import annotations

import csv
import hashlib
from collections import Counter
from typing import Any

from .eligibility import EligibilityReport
from .historical_model_scoring import HistoricalModelScoreProvider
from .pd_risk_scoring import PDRiskScoreProvider
from .local_knowledge_data import LocalKnowledgeData
from .models import CampaignRequest, Customer
from .offer_catalog import OfferCatalog, ProductOffer, offer_eligibility_reasons
from .orchestrator import MarketingDecisionEngine
from .persona import DEFAULT_CLUSTER_COUNT, cluster_priority_candidates
from .selection import BudgetConstrainedSelector
from .strategy_value import StrategyValueCalculator


class StrategyCandidateService:
    """Build explainable customer x product x channel candidates before scoring."""

    def __init__(
        self,
        local_data: LocalKnowledgeData,
        engine: MarketingDecisionEngine,
        model_scores: HistoricalModelScoreProvider | None = None,
        pd_risk_scores: PDRiskScoreProvider | None = None,
    ) -> None:
        self.local_data = local_data
        self.engine = engine
        self.catalog = OfferCatalog()
        self.model_scores = model_scores or HistoricalModelScoreProvider()
        self.pd_risk_scores = pd_risk_scores or PDRiskScoreProvider()

    def generate(
        self,
        *,
        customer_limit: int | None = None,
        sample_limit: int = 100,
        include_blocked: bool = False,
        campaign_id: str | None = None,
        include_model_scores: bool = False,
        evaluation_time: str | None = None,
        target_segment: str = "auto",
        target_segments: list[str] | None = None,
        operator_filters: dict[str, Any] | None = None,
        channel_mode: str = "omni",
    ) -> dict[str, Any]:
        if customer_limit is not None and customer_limit <= 0:
            raise ValueError("customer_limit must be positive or null")
        if sample_limit <= 0:
            raise ValueError("sample_limit must be positive")
        if include_model_scores and not campaign_id:
            raise ValueError("campaign_id is required when include_model_scores is true")
        selected_target_segments = _normalize_target_segments(target_segments or [target_segment])
        normalized_operator_filters = _normalize_operator_filters(operator_filters)
        valid_channels = {"app", "sms", "wechat", "email", "phone"}
        if channel_mode != "omni" and not all(
            part in valid_channels for part in channel_mode.split("_")
        ):
            raise ValueError("unsupported channel_mode")

        insight = self.local_data.build_customer_insight(
            campaign_id="STRATEGY_CANDIDATES",
            target_product="all_products",
            limit=customer_limit,
        )
        report = self.engine.assess_knowledge_insight(insight)
        decisions = {item.customer_id: item for item in report.decisions}
        channel_metrics = insight.get("channel_context", {}).get("channel_metrics", {})
        available_channels = insight.get("channel_context", {}).get("available_channels", [])
        offers = self._offers_for_campaign(campaign_id)
        insight_customers = {
            str(customer.get("customer_id", "")): customer for customer in insight.get("customers", [])
        }

        eligible_candidates: list[dict[str, Any]] = []
        blocked_sample: list[dict[str, Any]] = []
        eligible_by_channel: Counter[str] = Counter()
        eligible_by_product: Counter[str] = Counter()
        blocked_reasons: Counter[str] = Counter()
        product_filtered_count = 0
        channel_filtered_count = 0

        for customer in insight.get("customers", []):
            customer_id = str(customer.get("customer_id", ""))
            profile = customer.get("customer_profile", {})
            decision = decisions.get(customer_id)
            if decision is None:
                continue
            if not decision.eligible:
                for reason in decision.exclusion_reasons:
                    blocked_reasons[reason] += 1
                self._append_blocked(
                    blocked_sample,
                    customer_id=customer_id,
                    oneid=str(profile.get("oneid", "")),
                    reason_codes=decision.exclusion_reasons or ["customer_not_marketable"],
                    sample_limit=sample_limit,
                    include_blocked=include_blocked,
                )
                continue
            if not _matches_operator_filters(customer, normalized_operator_filters):
                blocked_reasons["operator_filter_mismatch"] += 1
                continue
            if not _matches_target_segments(customer, selected_target_segments):
                blocked_reasons["operator_target_segment_mismatch"] += 1
                continue

            for offer in offers:
                product_reasons = offer_eligibility_reasons(offer, profile)
                if product_reasons:
                    product_filtered_count += 1
                    for reason in product_reasons:
                        blocked_reasons[reason] += 1
                    self._append_blocked(
                        blocked_sample,
                        customer_id=customer_id,
                        oneid=str(profile.get("oneid", "")),
                        offer=offer,
                        reason_codes=product_reasons,
                        sample_limit=sample_limit,
                        include_blocked=include_blocked,
                    )
                    continue

                for channel in decision.eligible_channels:
                    if not _channel_matches_mode(channel, channel_mode):
                        channel_filtered_count += 1
                        continue
                    eligible_candidates.append(
                        _candidate_record(
                            customer_id=customer_id,
                            oneid=str(profile.get("oneid", "")),
                            offer=offer,
                            channel=channel,
                            channel_metrics=channel_metrics.get(channel, {}),
                            campaign_id=campaign_id or "",
                            economic_profile=_economic_profile(profile),
                        )
                    )
                    eligible_by_channel[channel] += 1
                    eligible_by_product[offer.product_id] += 1

                for channel in available_channels:
                    reasons = decision.blocked_channels.get(channel, [])
                    if not reasons:
                        continue
                    channel_filtered_count += 1
                    for reason in reasons:
                        blocked_reasons[reason] += 1
                    self._append_blocked(
                        blocked_sample,
                        customer_id=customer_id,
                        oneid=str(profile.get("oneid", "")),
                        offer=offer,
                        channel=channel,
                        reason_codes=reasons,
                        sample_limit=sample_limit,
                        include_blocked=include_blocked,
                    )

        persona_clustering = _attach_kmeans_personas(
            eligible_candidates,
            insight_customers,
            product=_persona_product_for_campaign(campaign_id),
        )
        candidate_sample = eligible_candidates[:sample_limit]
        model_scoring: dict[str, Any] = {
            "requested": include_model_scores,
            "model_version": "historical_response_v2",
            "campaign_id": campaign_id,
            "scored_candidate_count": 0,
        }
        if include_model_scores:
            score_cache: dict[tuple[str, str, str, str], dict[str, Any]] = {}
            pd_cache: dict[tuple[str, str], dict[str, Any]] = {}
            for candidate in candidate_sample:
                cache_key = (
                    candidate["customer_id"],
                    candidate["channel"],
                    campaign_id or "",
                    evaluation_time or "",
                )
                if cache_key not in score_cache:
                    score_cache[cache_key] = self.model_scores.score(
                        customer_id=candidate["customer_id"],
                        campaign_id=campaign_id,
                        channel=candidate["channel"],
                        touch_time=evaluation_time,
                    )
                candidate["model_scores"] = score_cache[cache_key]
                pd_key = (candidate["customer_id"], evaluation_time or "")
                if pd_key not in pd_cache:
                    pd_cache[pd_key] = self.pd_risk_scores.score(
                        customer_id=candidate["customer_id"],
                        as_of=evaluation_time,
                    )
                candidate["pd_risk_score"] = pd_cache[pd_key]
            model_scoring["model_available"] = self.model_scores.available
            model_scoring["pd_model_available"] = self.pd_risk_scores.available
            model_scoring["scored_candidate_count"] = len(candidate_sample)

        return {
            "source": insight.get("source"),
            "data_version": insight.get("data_version"),
            "candidate_definition": "eligible customer x eligible product x eligible channel",
            "generation_parameters": {
                "customer_limit": customer_limit,
                "sample_limit": sample_limit,
                "include_blocked": include_blocked,
                "campaign_id": campaign_id,
                "include_model_scores": include_model_scores,
                "evaluation_time": evaluation_time,
                "operator_filters": normalized_operator_filters,
            },
            "summary": {
                "input_customer_count": len(insight.get("customers", [])),
                "marketing_eligible_customer_count": report.eligible_count,
                "operator_filter_matched_customer_count": len({item["customer_id"] for item in eligible_candidates}),
                "eligible_candidate_count": len(eligible_candidates),
                "product_filtered_customer_offer_count": product_filtered_count,
                "channel_filtered_customer_offer_count": channel_filtered_count,
                "eligible_candidate_by_channel": dict(eligible_by_channel),
                "eligible_candidate_by_product": dict(eligible_by_product),
                "top_blocked_reason_codes": _top_counts(blocked_reasons),
            },
            "candidate_sample": candidate_sample,
            "blocked_sample": blocked_sample,
            "model_scoring": model_scoring,
            "persona_clustering": persona_clustering,
            "next_step": "calculate strategy value from p_conversion, p_unsubscribe, product economics, and constraints",
        }

    def campaign_options(self) -> list[dict[str, str]]:
        """Return activities that have both catalog metadata and value-model mappings."""
        with (self.local_data.structured_dir / "campaign_catalog.csv").open(
            encoding="utf-8-sig", newline=""
        ) as handle:
            catalog = {row["campaign_id"]: row for row in csv.DictReader(handle)}
        mappings = StrategyValueCalculator().campaign_mapping
        options: list[dict[str, str]] = []
        for campaign_id, row in catalog.items():
            mapping = mappings.get(campaign_id)
            if mapping is None:
                continue
            campaign_name = row.get("campaign_name", campaign_id)
            object_type = mapping.get("strategy_object_type", "benefit")
            type_label = {
                "installment": "分期优惠",
                "benefit": "消费权益",
                "card_upgrade": "卡升级",
                "activation": "新客激活",
            }.get(object_type, "权益")
            options.append(
                {
                    "campaign_id": campaign_id,
                    "campaign_name": campaign_name,
                    "benefit_category": mapping.get("benefit_category", "权益"),
                    "strategy_object_type": object_type,
                    "label": f"{campaign_name} · {type_label}",
                }
            )
        return options

    def optimize(
        self,
        *,
        campaign_id: str,
        budget: float,
        customer_limit: int | None = None,
        selected_sample_limit: int = 100,
        evaluation_time: str | None = None,
        target_segment: str = "auto",
        target_segments: list[str] | None = None,
        operator_filters: dict[str, Any] | None = None,
        channel_mode: str = "omni",
        channel_coverage_trial: bool = False,
    ) -> dict[str, Any]:
        """Score all eligible candidates, then select a budget-feasible delivery list."""
        if selected_sample_limit <= 0:
            raise ValueError("selected_sample_limit must be positive")
        generated = self.generate(
            customer_limit=customer_limit,
            sample_limit=100_000,
            campaign_id=campaign_id,
            include_model_scores=True,
            evaluation_time=evaluation_time,
            target_segment=target_segment,
            target_segments=target_segments,
            operator_filters=operator_filters,
            channel_mode=channel_mode,
        )
        candidates = generated["candidate_sample"]
        unavailable = [
            item for item in candidates if not item.get("model_scores", {}).get("model_available", False)
        ]
        if unavailable:
            reason = unavailable[0]["model_scores"].get("reason", "model_artifacts_unavailable")
            raise RuntimeError(f"historical response model is unavailable: {reason}")

        calculator = StrategyValueCalculator()
        for candidate in candidates:
            candidate["strategy_value"] = _apply_persona_allocation_weight(
                calculator.score(candidate).to_dict(),
                candidate.get("kmeans_persona", {}),
            )
        selector = BudgetConstrainedSelector()
        policy = calculator.policy["selection"]
        requested_channels = _channels_for_mode(channel_mode)
        coverage_channels = (
            requested_channels if channel_coverage_trial and len(requested_channels) > 1 else []
        )
        result = selector.select(
            candidates,
            budget=budget,
            minimum_net_value=float(policy["minimum_net_value"]),
            one_candidate_per_customer=bool(policy["one_candidate_per_customer"]),
            coverage_channels=coverage_channels,
            minimum_channel_trial_count=50 if coverage_channels else 0,
        )
        selected = result.selected
        # Read campaign display name for human-readable output.
        campaign_name = campaign_id
        catalog_path = self.local_data.structured_dir / "campaign_catalog.csv"
        if catalog_path.exists():
            with catalog_path.open(encoding="utf-8-sig", newline="") as handle:
                for row in csv.DictReader(handle):
                    if row["campaign_id"] == campaign_id:
                        campaign_name = row.get("campaign_name", campaign_id)
                        break

        mapping_entry = dict(calculator.campaign_mapping[campaign_id])
        strategy_type_name = {
            "installment": "分期优惠方案",
            "benefit": "消费权益活动",
            "card_upgrade": "卡升级活动",
            "activation": "客户激活活动",
        }.get(
            mapping_entry.get("strategy_object_type", ""),
            mapping_entry.get("strategy_object_type", "权益活动"),
        )
        campaign_context = {
            **mapping_entry,
            "campaign_name": campaign_name,
            "strategy_display_name": f"{campaign_name} · {strategy_type_name}",
            "benefit_cost_trigger": calculator.policy["strategy_object_economics"].get(
                mapping_entry.get("strategy_object_type", "benefit"),
                calculator.policy["strategy_object_economics"]["benefit"],
            )["benefit_cost_trigger"],
        }
        selected_target_segments = _normalize_target_segments(target_segments or [target_segment])
        normalized_operator_filters = _normalize_operator_filters(operator_filters)
        strategy_view = _build_strategy_view(
            selected,
            result,
            campaign_context,
            budget=budget,
            target_segments=selected_target_segments,
            persona_clustering=generated.get("persona_clustering", {}),
        )

        return {
            "source": generated["source"],
            "data_version": generated["data_version"],
            "campaign_id": campaign_id,
            "evaluation_time": evaluation_time,
            "candidate_definition": generated["candidate_definition"],
            "value_policy_version": calculator.policy["policy_version"],
            "campaign_context": campaign_context,
            "persona_clustering": generated.get("persona_clustering", {}),
            "budget": budget,
            "operator_constraints": {
                "target_segment": target_segment,
                "target_segments": selected_target_segments,
                "operator_filters": normalized_operator_filters,
                "channel_mode": channel_mode,
                "channel_coverage_trial": bool(coverage_channels),
            },
            "selection_summary": {
                **result.to_dict(),
                "household_deduplication": policy["household_deduplication"],
                "scored_candidate_count": len(candidates),
            },
            "strategy_view": strategy_view,
            "selected_candidate_sample": selected[:selected_sample_limit],
            "selected_candidate_total": len(selected),
            "_selected_candidates": selected,
            "top_rejected_reason_codes": generated["summary"]["top_blocked_reason_codes"],
        }

    @staticmethod
    def _append_blocked(
        target: list[dict[str, Any]],
        *,
        customer_id: str,
        oneid: str,
        reason_codes: list[str],
        sample_limit: int,
        include_blocked: bool,
        offer: ProductOffer | None = None,
        channel: str = "",
    ) -> None:
        if not include_blocked or len(target) >= sample_limit:
            return
        target.append(
            {
                "candidate_status": "BLOCKED",
                "customer_id": customer_id,
                "oneid": oneid,
                "product_id": offer.product_id if offer else "",
                "product_name": offer.product_name if offer else "",
                "channel": channel,
                "reason_codes": sorted(set(reason_codes)),
            }
        )

    def _offers_for_campaign(self, campaign_id: str | None) -> list[ProductOffer]:
        if not campaign_id:
            return self.catalog.offers()
        mapping = StrategyValueCalculator().campaign_mapping.get(campaign_id)
        if mapping is None:
            raise ValueError(f"unknown campaign_id: {campaign_id}")
        object_type = mapping.get("strategy_object_type", "benefit")
        if object_type == "card_upgrade":
            return self.catalog.offers()
        # Read campaign display name from catalog
        campaign_display = campaign_id
        catalog_path = self.local_data.structured_dir / "campaign_catalog.csv"
        if catalog_path.exists():
            with catalog_path.open(encoding="utf-8-sig", newline="") as handle:
                for row in csv.DictReader(handle):
                    if row["campaign_id"] == campaign_id:
                        campaign_display = row.get("campaign_name", campaign_id)
                        break
        strategy_label = {
            "installment": "分期优惠",
            "benefit": "权益活动",
            "activation": "激活活动",
        }.get(object_type, "活动")
        product_id, product_name = {
            "installment": ("INSTALLMENT", f"{campaign_display} · {strategy_label}"),
            "benefit": ("CAMPAIGN_BENEFIT", f"{campaign_display} · {strategy_label}"),
            "activation": ("CUSTOMER_ACTIVATION", f"{campaign_display} · {strategy_label}"),
        }.get(object_type, ("CAMPAIGN_OFFER", f"{campaign_display} · 活动"))
        benefit_ids = [
            item for item in mapping.get("primary_benefit_ids", "").split("|") if item
        ]
        return [
            ProductOffer(
                product_id=product_id,
                product_name=product_name,
                annual_fee=0.0,
                target_income="",
                selling_points=[str(mapping.get("objective", "conversion"))],
                benefit_ids=benefit_ids,
                benefit_names=benefit_ids,
                required_income="",
                min_age=0,
                max_age=120,
                required_card_level="",
                min_credit=0.0,
                special_conditions="",
            )
        ]


def _build_strategy_view(
    selected: list[dict[str, Any]], result: Any, campaign_context: dict[str, Any], *, budget: float,
    target_segments: list[str] | None = None,
    persona_clustering: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Build aggregate presentation data from the value-selected customer list."""
    selected_count = len(selected)
    budget_used = float(result.budget_used)
    total_value = float(result.expected_net_value)
    total_conversion = float(result.expected_conversion_count)
    by_channel: dict[str, list[dict[str, Any]]] = {}
    for candidate in selected:
        by_channel.setdefault(str(candidate.get("channel", "unknown")), []).append(candidate)

    segments = _build_kmeans_segments(selected, persona_clustering or {})

    channels = [
        {
            "channel": channel,
            "expected_reach": len(rows),
            "budget_share": round(_total_budget_cost(rows) / max(budget_used, 0.01), 4),
            "role": f"平均转化概率 {_average_probability(rows, 'p_conversion') * 100:.1f}%",
        }
        for channel, rows in by_channel.items()
    ]
    channels.sort(key=lambda item: item["expected_reach"], reverse=True)

    campaign_display = str(campaign_context.get("strategy_display_name", campaign_context.get("campaign_name", "专属权益活动")))
    category = str(campaign_context.get("benefit_category", "专属权益"))
    objective = _objective_text(str(campaign_context.get("objective", "conversion")))
    content = {
        "app_popup": f"{campaign_display}：请在 App 查看适用条件与有效期。",
        "sms": f"【信用卡服务】{campaign_display}活动提醒，请登录 App 查看详情；退订回复 TD。",
        "wechat": f"围绕{campaign_display}说明使用路径，并明确活动条件、费用与有效期。",
        "explain": f"依据{objective}目标、预测转化概率和预期净价值生成；不承诺收益或审批结果。",
    }
    average_unsubscribe = _average_probability(selected, "p_unsubscribe")
    capacity_limited = int(result.excluded.get("channel_capacity_reached", 0))
    compliance = [
        {"item": "营销授权", "status": "通过", "detail": "候选生成阶段已过滤未授权客户。"},
        {"item": "客户去重", "status": "通过", "detail": "同一客户最多保留一条投放策略。"},
        {
            "item": "渠道容量",
            "status": "通过",
            "detail": "已按各渠道日容量校验。" if not capacity_limited else "超出容量的候选已被过滤。",
        },
        {
            "item": "退订风险",
            "status": "通过" if average_unsubscribe <= 0.03 else "复核",
            "detail": f"入选客群平均退订概率 {average_unsubscribe * 100:.2f}% 。",
        },
    ]
    return {
        "metrics": {
            "audience_size": selected_count,
            "conversion_rate": round(total_conversion / max(selected_count, 1) * 100, 2),
            "expected_net_value_wan": round(total_value / 10000, 2),
            "budget_utilization": round(budget_used / max(budget, 0.01) * 100, 2),
        },
        "segments": segments,
        "channels": channels,
        "content": content,
        "compliance": compliance,
        "effect_forecast": {
            "ctr": round(_average_probability(selected, "p_click") * 100, 2),
            "conversion": round(total_conversion / max(selected_count, 1) * 100, 2),
            "unsubscribe": round(average_unsubscribe * 100, 3),
        },
    }


def _average_probability(rows: list[dict[str, Any]], name: str) -> float:
    if not rows:
        return 0.0
    return sum(float(row["model_scores"]["probabilities"].get(name, 0.0)) for row in rows) / len(rows)


def _total_net_value(rows: list[dict[str, Any]]) -> float:
    return sum(float(row["strategy_value"]["expected_net_value"]) for row in rows)


def _total_budget_cost(rows: list[dict[str, Any]]) -> float:
    return sum(float(row["strategy_value"]["budget_cost"]) for row in rows)


def _objective_text(objective: str) -> str:
    return {
        "conversion": "提升转化",
        "spend": "提升消费",
        "activation": "客户激活",
        "retention": "客户留存",
    }.get(objective, "营销转化")


def _attach_kmeans_personas(
    candidates: list[dict[str, Any]],
    insight_customers: dict[str, dict[str, Any]],
    *,
    product: str,
) -> dict[str, Any]:
    customer_ids = list(dict.fromkeys(str(item.get("customer_id", "")) for item in candidates))
    customers = [
        _to_persona_customer(insight_customers[customer_id])
        for customer_id in customer_ids
        if customer_id in insight_customers
    ]
    request = CampaignRequest(goal="value optimized strategy", product=product, product_locked=True)
    result = cluster_priority_candidates(customers, request, n_clusters=DEFAULT_CLUSTER_COUNT)
    if result is None:
        return {
            "method": "unavailable",
            "cluster_count": 0,
            "feature_names": [],
            "profiles": [],
            "assignment_count": 0,
        }

    profiles = []
    for cluster_id, profile in sorted(result.profiles.items()):
        cluster_code = f"C{cluster_id + 1}"
        profiles.append(
            {
                "cluster_id": cluster_id + 1,
                "cluster_code": cluster_code,
                "name": profile.name,
                "top_features": [item["label"] for item in profile.strategy["cluster_feature_priorities"][:2]],
                "allocation_weight": profile.allocation_weight,
                "strategy": profile.strategy,
            }
        )
    profile_by_customer = result.assignments
    for candidate in candidates:
        profile = profile_by_customer.get(str(candidate.get("customer_id", "")))
        if profile is None:
            continue
        candidate["kmeans_persona"] = {
            "cluster_id": profile.cluster_id + 1,
            "cluster_code": f"C{profile.cluster_id + 1}",
            "name": profile.name,
            "top_features": [item["label"] for item in profile.strategy["cluster_feature_priorities"][:2]],
            "allocation_weight": profile.allocation_weight,
            "strategy": profile.strategy,
        }
    return {
        "method": "kmeans",
        "cluster_count": len(profiles),
        "feature_names": result.feature_names,
        "profiles": profiles,
        "assignment_count": len(profile_by_customer),
    }


def _to_persona_customer(customer: dict[str, Any]) -> Customer:
    profile = customer.get("customer_profile", {})
    top_intents = customer.get("intent_vector", {}).get("top_intents", [])
    return Customer(
        customer_id=str(customer.get("customer_id", "")),
        age=_as_int(profile.get("age"), 35),
        city_tier=_as_int(profile.get("city_tier"), 3),
        monthly_spend=_as_float(profile.get("monthly_spend")),
        dining_txn=_as_int(profile.get("dining_txn")),
        travel_txn=_as_int(profile.get("travel_txn")),
        online_txn=_as_int(profile.get("online_txn")),
        credit_limit_usage=_as_float(profile.get("credit_limit_usage")),
        coupon_response=_as_float(profile.get("coupon_response")),
        installment_history=_as_int(profile.get("installment_history")),
        app_active_days=_as_int(profile.get("app_active_days")),
        recent_contacts=_as_int(profile.get("recent_contact_count")),
        complaint_risk=_as_float(profile.get("complaint_risk")),
        has_marketing_consent=bool(profile.get("marketing_consent")),
        intent_scores={
            "分期/借贷需求": _intent_score(top_intents, ("分期", "借贷")),
            "权益/优惠需求": _intent_score(top_intents, ("权益", "优惠", "观影", "消费")),
            "跨境/出行需求": _intent_score(top_intents, ("出行", "旅行", "酒店", "机票")),
        },
        recent_events=list(customer.get("event_sequence", [])),
    )


def _intent_score(rows: list[dict[str, Any]], keywords: tuple[str, ...]) -> float:
    matched = [
        _as_float(item.get("score"))
        for item in rows
        if any(keyword in str(item.get("name", "")) for keyword in keywords)
    ]
    return max(matched, default=0.0)


def _persona_product_for_campaign(campaign_id: str | None) -> str:
    mapping = StrategyValueCalculator().campaign_mapping.get(str(campaign_id or ""), {})
    return "installment" if mapping.get("strategy_object_type") == "installment" else "coupon"


def _apply_persona_allocation_weight(value: dict[str, Any], persona: dict[str, Any]) -> dict[str, Any]:
    if not persona:
        return value
    allocation_weight = _as_float(persona.get("allocation_weight")) or 1.0
    multiplier = min(1.15, max(0.85, allocation_weight))
    original_value = float(value["expected_net_value"])
    adjusted_value = original_value * multiplier
    adjusted = dict(value)
    adjusted["expected_net_value"] = round(adjusted_value, 4)
    adjusted["value_density"] = round(adjusted_value / max(float(value["budget_cost"]), 0.01), 4)
    adjusted["breakdown"] = {
        **dict(value.get("breakdown", {})),
        "kmeans_persona_allocation_adjustment": round(adjusted_value - original_value, 4),
        "kmeans_persona_allocation_multiplier": round(multiplier, 4),
    }
    return adjusted


def _build_kmeans_segments(selected: list[dict[str, Any]], persona_clustering: dict[str, Any]) -> list[dict[str, Any]]:
    profiles = list(persona_clustering.get("profiles", []))
    if not profiles:
        return [
            {
                "name": "待生成 KMeans 群像",
                "size": len(selected),
                "conversion_rate": round(_average_probability(selected, "p_conversion") * 100, 2),
                "expected_value_wan": round(_total_net_value(selected) / 10000, 2),
                "reasons": ["当前环境未加载 KMeans", "仍按价值模型完成策略排序"],
            }
        ]
    by_cluster: dict[str, list[dict[str, Any]]] = {}
    for candidate in selected:
        code = str(candidate.get("kmeans_persona", {}).get("cluster_code", ""))
        by_cluster.setdefault(code, []).append(candidate)
    segments = []
    for profile in profiles:
        code = str(profile["cluster_code"])
        rows = by_cluster.get(code, [])
        top_features = profile.get("top_features", [])
        segments.append(
            {
                "cluster_code": code,
                "name": profile["name"],
                "size": len(rows),
                "conversion_rate": round(_average_probability(rows, "p_conversion") * 100, 2),
                "expected_value_wan": round(_total_net_value(rows) / 10000, 2),
                "reasons": [
                    f"KMeans {code}",
                    f"突出特征：{'、'.join(top_features)}" if top_features else "由簇中心特征生成",
                    f"簇分配权重 {float(profile.get('allocation_weight', 1.0)):.2f}",
                ],
                "strategy": profile.get("strategy", {}),
            }
        )
    return segments


def _as_float(value: Any) -> float:
    try:
        return float(value or 0.0)
    except (TypeError, ValueError):
        return 0.0


def _as_int(value: Any, default: int = 0) -> int:
    try:
        return int(float(value if value is not None else default))
    except (TypeError, ValueError):
        return default
def _candidate_record(
    *,
    customer_id: str,
    oneid: str,
    offer: ProductOffer,
    channel: str,
    channel_metrics: dict[str, Any],
    campaign_id: str,
    economic_profile: dict[str, Any],
) -> dict[str, Any]:
    key = f"{customer_id}|{offer.product_id}|{channel}"
    return {
        "candidate_id": hashlib.sha1(key.encode("utf-8")).hexdigest()[:16].upper(),
        "candidate_status": "ELIGIBLE",
        "customer_id": customer_id,
        "oneid": oneid,
        "customer_unique_id": oneid or customer_id,
        "product_id": offer.product_id,
        "product_name": offer.product_name,
        "annual_fee": offer.annual_fee,
        "benefit_ids": offer.benefit_ids,
        "benefit_names": offer.benefit_names,
        "channel": channel,
        "campaign_id": campaign_id,
        "contact_cost": float(channel_metrics.get("cost_per_send", 0.0)),
        "channel_avg_open_rate": float(channel_metrics.get("avg_open_rate", 0.0)),
        "channel_avg_click_rate": float(channel_metrics.get("avg_click_rate", 0.0)),
        "channel_daily_capacity": int(channel_metrics.get("daily_capacity", 0)),
        "economic_profile": economic_profile,
        "reason_codes": [],
    }


def _top_counts(counter: Counter[str], limit: int = 10) -> list[dict[str, Any]]:
    return [{"reason_code": key, "count": value} for key, value in counter.most_common(limit)]


def _economic_profile(profile: dict[str, Any]) -> dict[str, Any]:
    """Keep only aggregate value and risk signals required by the value formula."""
    return {
        "monthly_spend": float(profile.get("monthly_spend", 0.0) or 0.0),
        "value_level": str(profile.get("value_level", "medium") or "medium"),
        "risk_level": str(profile.get("risk_level", "low") or "low"),
        "complaint_risk": float(profile.get("complaint_risk", 0.0) or 0.0),
    }


def _channel_matches_mode(channel: str, channel_mode: str) -> bool:
    if channel_mode == "omni":
        return True
    return channel in set(_channels_for_mode(channel_mode))


def _channels_for_mode(channel_mode: str) -> list[str]:
    if channel_mode == "omni":
        return []
    channel_mapping = {
        "app": "app_push",
        "sms": "sms",
        "wechat": "wechat",
        "email": "email",
        "phone": "phone",
    }
    return [channel_mapping[item] for item in channel_mode.split("_")]


def _matches_target_segments(customer: dict[str, Any], target_segments: list[str]) -> bool:
    if "auto" in target_segments:
        return True

    return any(_matches_target_segment(customer, target_segment) for target_segment in target_segments)


def _normalize_operator_filters(filters: dict[str, Any] | None) -> dict[str, Any]:
    if not isinstance(filters, dict):
        return {}

    cities = [str(city).strip() for city in filters.get("cities", []) if str(city).strip()]
    gender = str(filters.get("gender", "")).strip().lower()
    if gender not in {"", "female", "male"}:
        raise ValueError("unsupported operator filter gender")
    behaviors = [
        str(behavior).strip().lower()
        for behavior in filters.get("recent_behaviors", [])
        if str(behavior).strip()
    ]
    allowed_behaviors = {
        "dining", "entertainment", "shopping", "benefit", "travel", "installment", "credit_upgrade"
    }
    if not set(behaviors).issubset(allowed_behaviors):
        raise ValueError("unsupported recent behavior filter")

    value_levels = [str(value).strip().lower() for value in filters.get("value_levels", []) if str(value).strip()]
    if not set(value_levels).issubset({"high", "medium", "low"}):
        raise ValueError("unsupported value level filter")
    lifecycle_stages = [str(value).strip() for value in filters.get("lifecycle_stages", []) if str(value).strip()]
    if not set(lifecycle_stages).issubset({"新户", "成长期", "成熟期", "沉睡期"}):
        raise ValueError("unsupported lifecycle stage filter")
    risk_levels = [str(value).strip().lower() for value in filters.get("risk_levels", []) if str(value).strip()]
    if not set(risk_levels).issubset({"low", "medium"}):
        raise ValueError("unsupported risk level filter")

    age_min = _optional_filter_int(filters.get("age_min"), "age_min")
    age_max = _optional_filter_int(filters.get("age_max"), "age_max")
    if age_min is not None and age_max is not None and age_min > age_max:
        raise ValueError("age_min cannot be greater than age_max")
    monthly_spend_min = _optional_filter_float(filters.get("monthly_spend_min"), "monthly_spend_min")
    return {
        "cities": list(dict.fromkeys(cities)),
        "gender": gender,
        "age_min": age_min,
        "age_max": age_max,
        "monthly_spend_min": monthly_spend_min,
        "value_levels": list(dict.fromkeys(value_levels)),
        "lifecycle_stages": list(dict.fromkeys(lifecycle_stages)),
        "risk_levels": list(dict.fromkeys(risk_levels)),
        "recent_behaviors": list(dict.fromkeys(behaviors)),
    }


def _optional_filter_int(value: Any, name: str) -> int | None:
    if value in (None, ""):
        return None
    try:
        parsed = int(value)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"{name} must be an integer") from exc
    if parsed < 0 or parsed > 120:
        raise ValueError(f"{name} must be between 0 and 120")
    return parsed


def _optional_filter_float(value: Any, name: str) -> float | None:
    if value in (None, ""):
        return None
    try:
        parsed = float(value)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"{name} must be numeric") from exc
    if parsed < 0 or parsed > 10_000_000:
        raise ValueError(f"{name} must be between 0 and 10000000")
    return parsed


def _matches_operator_filters(customer: dict[str, Any], filters: dict[str, Any]) -> bool:
    if not filters:
        return True
    profile = customer.get("customer_profile", {})
    cities = filters.get("cities", [])
    if cities and str(profile.get("city", "")).strip() not in cities:
        return False

    expected_gender = filters.get("gender", "")
    actual_gender = str(profile.get("gender", "")).strip().lower()
    gender_aliases = {
        "female": {"f", "female", "女"},
        "male": {"m", "male", "男"},
    }
    if expected_gender and actual_gender not in gender_aliases[expected_gender]:
        return False

    age = _as_int(profile.get("age"), 0)
    if filters.get("age_min") is not None and age < filters["age_min"]:
        return False
    if filters.get("age_max") is not None and age > filters["age_max"]:
        return False
    if filters.get("monthly_spend_min") is not None and _as_float(profile.get("monthly_spend")) < filters["monthly_spend_min"]:
        return False
    if filters.get("value_levels") and str(profile.get("value_level", "")).strip().lower() not in filters["value_levels"]:
        return False
    if filters.get("lifecycle_stages") and str(profile.get("lifecycle_stage", "")).strip() not in filters["lifecycle_stages"]:
        return False
    if filters.get("risk_levels") and str(profile.get("risk_level", "")).strip().lower() not in filters["risk_levels"]:
        return False

    behavior_aliases = {
        "dining": ("餐饮", "餐厅", "美食", "外卖", "咖啡"),
        "entertainment": ("娱乐", "观影", "电影", "影院", "演出", "音乐会", "游戏"),
        "shopping": ("购物", "商超", "电商", "商城", "百货"),
        "benefit": ("权益", "优惠", "双十一", "返现"),
        "travel": ("旅行", "出行", "机票", "酒店", "旅游"),
        "installment": ("分期", "借贷", "还款"),
        "credit_upgrade": ("提额", "额度", "升级"),
    }
    behavior_text = " ".join(
        [
            str(item.get("name", "")) if isinstance(item, dict) else str(item)
            for item in customer.get("intent_vector", {}).get("top_intents", [])
        ]
        + [
            " ".join(str(event.get(key, "")) for key in ("event_name", "event_type"))
            for event in customer.get("event_sequence", [])
            if isinstance(event, dict)
        ]
        + [str(value) for value in profile.get("tags", [])]
        + [str(value) for value in profile.get("recent_behavior_signals", [])]
    )
    return all(
        any(alias in behavior_text for alias in behavior_aliases[behavior])
        for behavior in filters.get("recent_behaviors", [])
    )


def _matches_target_segment(customer: dict[str, Any], target_segment: str) -> bool:

    profile = customer.get("customer_profile", {})
    top_intents = " ".join(
        str(item.get("name", "")) if isinstance(item, dict) else str(item)
        for item in customer.get("intent_vector", {}).get("top_intents", [])
    )
    if target_segment == "high_value":
        return str(profile.get("value_level", "")).lower() == "high" or float(
            profile.get("monthly_spend", 0) or 0
        ) >= 12000
    if target_segment == "high_intent":
        return any(keyword in top_intents for keyword in ("分期", "权益", "出行", "升级"))
    if target_segment == "dormant":
        return int(profile.get("churn_risk_score", 0) or 0) >= 60 or "沉睡" in str(
            profile.get("lifecycle_stage", "")
        )
    if target_segment == "young_new":
        return int(profile.get("age", 99) or 99) <= 30 or "新户" in str(profile.get("lifecycle_stage", ""))
    if target_segment == "high_activity":
        return int(profile.get("app_active_days", 0) or 0) >= 15
    if target_segment == "spend_growth":
        tags = {str(tag).strip().lower() for tag in profile.get("tags", [])}
        return str(profile.get("consumption_trend", "")).lower() in {"up", "增长"} or "consumption_growth" in tags
    if target_segment == "benefit_sensitive":
        return (
            any(keyword in top_intents for keyword in ("权益", "优惠", "返现", "券"))
            or float(profile.get("coupon_response", 0) or 0) >= 0.55
        )
    if target_segment == "low_risk":
        return (
            str(profile.get("risk_level", "")).lower() == "low"
            and float(profile.get("complaint_risk", 0) or 0) < 0.4
        )
    return False


def _normalize_target_segments(target_segments: list[str]) -> list[str]:
    allowed = {
        "auto",
        "high_value",
        "high_intent",
        "dormant",
        "young_new",
        "high_activity",
        "spend_growth",
        "benefit_sensitive",
        "low_risk",
    }
    normalized = list(dict.fromkeys(str(segment) for segment in target_segments if str(segment)))
    if not normalized or "auto" in normalized:
        return ["auto"]
    if not all(segment in allowed for segment in normalized):
        raise ValueError("unsupported target_segment")
    return normalized
