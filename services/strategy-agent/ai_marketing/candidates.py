from __future__ import annotations

import hashlib
from collections import Counter
from typing import Any

from .eligibility import EligibilityReport
from .historical_model_scoring import HistoricalModelScoreProvider
from .local_knowledge_data import LocalKnowledgeData
from .offer_catalog import OfferCatalog, ProductOffer, offer_eligibility_reasons
from .orchestrator import MarketingDecisionEngine


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

            for offer in self.catalog.offers():
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
            for candidate in candidate_sample:
                candidate["model_scores"] = self.model_scores.score(
                    customer_id=candidate["customer_id"],
                    campaign_id=campaign_id,
                    channel=candidate["channel"],
                    touch_time=evaluation_time,
                )
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


def _candidate_record(
    *,
    customer_id: str,
    oneid: str,
    offer: ProductOffer,
    channel: str,
    channel_metrics: dict[str, Any],
) -> dict[str, Any]:
    key = f"{customer_id}|{offer.product_id}|{channel}"
    return {
        "candidate_id": hashlib.sha1(key.encode("utf-8")).hexdigest()[:16].upper(),
        "candidate_status": "ELIGIBLE",
        "customer_id": customer_id,
        "oneid": oneid,
        "product_id": offer.product_id,
        "product_name": offer.product_name,
        "benefit_ids": offer.benefit_ids,
        "benefit_names": offer.benefit_names,
        "channel": channel,
        "contact_cost": float(channel_metrics.get("cost_per_send", 0.0)),
        "channel_avg_open_rate": float(channel_metrics.get("avg_open_rate", 0.0)),
        "channel_avg_click_rate": float(channel_metrics.get("avg_click_rate", 0.0)),
        "channel_daily_capacity": int(channel_metrics.get("daily_capacity", 0)),
        "reason_codes": [],
    }


def _top_counts(counter: Counter[str], limit: int = 10) -> list[dict[str, Any]]:
    return [{"reason_code": key, "count": value} for key, value in counter.most_common(limit)]
