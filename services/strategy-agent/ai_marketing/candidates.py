from __future__ import annotations

import hashlib
from collections import Counter
from typing import Any

from .eligibility import EligibilityReport
from .historical_model_scoring import HistoricalModelScoreProvider
from .local_knowledge_data import LocalKnowledgeData
from .offer_catalog import OfferCatalog, ProductOffer, offer_eligibility_reasons
from .orchestrator import MarketingDecisionEngine
from .selection import BudgetConstrainedSelector
from .strategy_value import StrategyValueCalculator


class StrategyCandidateService:
    """Build explainable customer x product x channel candidates before scoring."""

    def __init__(
        self,
        local_data: LocalKnowledgeData,
        engine: MarketingDecisionEngine,
        model_scores: HistoricalModelScoreProvider | None = None,
    ) -> None:
        self.local_data = local_data
        self.engine = engine
        self.catalog = OfferCatalog()
        self.model_scores = model_scores or HistoricalModelScoreProvider()

    def generate(
        self,
        *,
        customer_limit: int | None = 200,
        sample_limit: int = 100,
        include_blocked: bool = False,
        campaign_id: str | None = None,
        include_model_scores: bool = False,
        evaluation_time: str | None = None,
    ) -> dict[str, Any]:
        if customer_limit is not None and customer_limit <= 0:
            raise ValueError("customer_limit must be positive or null")
        if sample_limit <= 0:
            raise ValueError("sample_limit must be positive")
        if include_model_scores and not campaign_id:
            raise ValueError("campaign_id is required when include_model_scores is true")

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

        candidate_sample = eligible_candidates[:sample_limit]
        model_scoring: dict[str, Any] = {
            "requested": include_model_scores,
            "model_version": "historical_response_v2",
            "campaign_id": campaign_id,
            "scored_candidate_count": 0,
        }
        if include_model_scores:
            score_cache: dict[tuple[str, str, str, str], dict[str, Any]] = {}
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
            model_scoring["model_available"] = self.model_scores.available
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
            },
            "summary": {
                "input_customer_count": len(insight.get("customers", [])),
                "marketing_eligible_customer_count": report.eligible_count,
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
            "next_step": "calculate strategy value from p_conversion, p_unsubscribe, product economics, and constraints",
        }

    def optimize(
        self,
        *,
        campaign_id: str,
        budget: float,
        customer_limit: int | None = 200,
        selected_sample_limit: int = 100,
        evaluation_time: str | None = None,
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
            candidate["strategy_value"] = calculator.score(candidate).to_dict()
        selector = BudgetConstrainedSelector()
        policy = calculator.policy["selection"]
        result = selector.select(
            candidates,
            budget=budget,
            minimum_net_value=float(policy["minimum_net_value"]),
            one_candidate_per_customer=bool(policy["one_candidate_per_customer"]),
        )
        selected = result.selected
        return {
            "source": generated["source"],
            "data_version": generated["data_version"],
            "campaign_id": campaign_id,
            "evaluation_time": evaluation_time,
            "candidate_definition": generated["candidate_definition"],
            "value_policy_version": calculator.policy["policy_version"],
            "campaign_context": {
                **calculator.campaign_mapping[campaign_id],
                "benefit_cost_trigger": calculator.policy["strategy_object_economics"].get(
                    calculator.campaign_mapping[campaign_id].get("strategy_object_type", "benefit"),
                    calculator.policy["strategy_object_economics"]["benefit"],
                )["benefit_cost_trigger"],
            },
            "budget": budget,
            "selection_summary": {
                **result.to_dict(),
                "household_deduplication": policy["household_deduplication"],
                "scored_candidate_count": len(candidates),
            },
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
        product_id, product_name = {
            "installment": ("INSTALLMENT", "Installment plan"),
            "benefit": ("CAMPAIGN_BENEFIT", "Campaign benefit"),
            "activation": ("CUSTOMER_ACTIVATION", "Customer activation"),
        }.get(object_type, ("CAMPAIGN_OFFER", "Campaign offer"))
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
