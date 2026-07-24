from __future__ import annotations

import hashlib
from dataclasses import dataclass
from typing import Any

from .eligibility import filter_to_eligible_customers
from .knowledge_adapter import customers_from_knowledge_insight
from .local_knowledge_data import LocalKnowledgeData
from .models import CampaignRequest, Customer
from .offer_catalog import OfferCatalog, ProductOffer, offer_eligibility_reasons
from .orchestrator import MarketingDecisionEngine
from .persona import PersonaProfile, cluster_priority_candidates
from .storage import PlanRepository


@dataclass(frozen=True)
class AudienceContext:
    customers: dict[str, Customer]
    profiles: dict[str, dict[str, Any]]
    persona_assignments: dict[str, PersonaProfile]


class PersonalizedStrategyService:
    """Serve online recommendations without exposing raw customer data to the client."""

    def __init__(
        self,
        local_data: LocalKnowledgeData,
        engine: MarketingDecisionEngine,
        repo: PlanRepository | None = None,
    ) -> None:
        self.local_data = local_data
        self.engine = engine
        self.catalog = OfferCatalog()
        self.repo = repo
        self._audience_context: AudienceContext | None = None

    def recommendations(self, oneid: str, *, scene: str = "agent_home", limit: int = 5) -> dict[str, Any]:
        try:
            customer_id, customer, profile, persona = self._customer_context(oneid)
        except PermissionError:
            return self._empty_response(oneid, scene, "marketing_eligibility_failed", personalization_consent=True)
        if not profile.get("personalization_consent", False):
            return self._empty_response(oneid, scene, "personalization_consent_required")

        maximum = max(1, min(limit, 10))
        published_contexts = self._published_contexts(customer_id, oneid=oneid)
        recommendations = _published_campaign_recommendations(published_contexts, persona, limit=maximum)
        catalog_recommendations = self._rank_offers(
            customer,
            profile,
            persona,
            oneid=oneid,
            limit=maximum,
            published_contexts=published_contexts,
        )
        recommendations = _merge_unique_recommendations(
            published=recommendations,
            catalogue=catalog_recommendations,
            limit=maximum,
        )
        for rank, recommendation in enumerate(recommendations, start=1):
            recommendation["rank"] = rank
        return {
            "oneid": oneid,
            "scene": scene,
            "strategy_version": "online_personalization_v1",
            "status": "success" if recommendations else "no_recommendation",
            "eligible_for_personalization": True,
            "eligible_for_marketing": True,
            "reason_code": None if recommendations else "no_matching_recommendation",
            # Keep `reason` during the transition so existing C-side code does not break.
            "reason": None if recommendations else "no_matching_recommendation",
            "recommendations": recommendations,
            "customer_reference": _reference(customer_id),
            # The HTTP layer conditionally fills this only for a displayable card.
            "published_strategy_context": [],
            "published_strategy": None,
        }

    def decision(
        self,
        oneid: str,
        *,
        scene: str,
        user_intent: str = "",
        product_id: str = "",
        conversation_summary: str = "",
        touchpoint: str = "in_app",
    ) -> dict[str, Any]:
        customer_id, customer, profile, persona = self._customer_context(oneid)
        if not profile.get("personalization_consent", False):
            return {
                "oneid": oneid,
                "scene": scene,
                "should_recommend": False,
                "reason": "personalization_consent_required",
            }

        if _is_installment_request(product_id, user_intent, conversation_summary):
            return self._installment_decision(oneid, customer_id, customer, persona, scene, touchpoint)

        offer = self.catalog.get(product_id) if product_id else None
        published_contexts = self._published_contexts(customer_id, oneid=oneid)
        if offer is None and not product_id:
            recommendations = _published_campaign_recommendations(published_contexts, persona, limit=1)
            if not recommendations:
                recommendations = self._rank_offers(
                    customer,
                    profile,
                    persona,
                    limit=1,
                    oneid=oneid,
                    published_contexts=published_contexts,
                )
        else:
            recommendations = self._rank_offers(
                customer,
                profile,
                persona,
                limit=1,
                only_product=offer,
                oneid=oneid,
                published_contexts=published_contexts,
            )
        if not recommendations:
            return {
                "oneid": oneid,
                "scene": scene,
                "should_recommend": False,
                "reason": "no_eligible_offer",
            }
        recommendation = recommendations[0]
        return {
            "oneid": oneid,
            "scene": scene,
            "should_recommend": True,
            "persona_name": recommendation["persona_name"],
            "segment_id": recommendation["segment_id"],
            "next_best_action": f"\u5c55\u793a{recommendation['title']}\u7684\u65b9\u6848\u4e0e\u9002\u7528\u6761\u4ef6",
            "recommended_product_id": recommendation["product_id"],
            "recommended_benefit_id": recommendation["benefit_id"],
            "offer_direction": recommendation["strategy"]["offer_direction"],
            "content_direction": recommendation["strategy"]["content_direction"],
            "allowed_channels": [touchpoint],
            "compliance_notes": _compliance_notes(),
            "recommendation": recommendation,
        }

    def _customer_context(self, oneid: str) -> tuple[str, Customer, dict[str, Any], PersonaProfile | None]:
        customer_id = self.local_data.customer_id_for_oneid(oneid)
        if customer_id is None:
            raise KeyError("unknown_oneid")
        context = self._load_audience_context()
        customer = context.customers.get(customer_id)
        profile = context.profiles.get(customer_id)
        if customer is None or profile is None:
            raise PermissionError("customer_not_eligible_for_marketing")
        return customer_id, customer, profile, context.persona_assignments.get(customer_id)

    def _load_audience_context(self) -> AudienceContext:
        if self._audience_context is not None:
            return self._audience_context
        insight = self.local_data.build_customer_insight(target_product="installment")
        eligibility = self.engine.assess_knowledge_insight(insight)
        eligible_payload = filter_to_eligible_customers(insight, eligibility)
        eligible_customers = customers_from_knowledge_insight(eligible_payload)
        # The home page must not reuse the narrow installment-campaign threshold.
        # It serves all compliant, consented customers and lets product-level rules
        # decide which cards can be ranked for each individual.
        request = CampaignRequest(goal="online personalization", product="coupon", budget_wan=20)
        personas = cluster_priority_candidates(eligible_customers, request)
        self._audience_context = AudienceContext(
            customers={customer.customer_id: customer for customer in eligible_customers},
            profiles={
                item["customer_id"]: item.get("customer_profile", {})
                for item in eligible_payload.get("customers", [])
            },
            persona_assignments=personas.assignments if personas else {},
        )
        return self._audience_context

    def _published_contexts(self, customer_id: str, *, oneid: str = "") -> list[dict[str, Any]]:
        if self.repo is None:
            return []
        suppressed_campaigns = self.repo.get_suppressed_campaigns(oneid) if oneid else frozenset()
        return [
            context
            for context in self.repo.published_context_for_customer(customer_id=customer_id)
            if str(context.get("campaign_id", "")) not in suppressed_campaigns
        ]

    def _rank_offers(
        self,
        customer: Customer,
        profile: dict[str, Any],
        persona: PersonaProfile | None,
        *,
        limit: int,
        only_product: ProductOffer | None = None,
        oneid: str = "",
        published_contexts: list[dict[str, Any]] | None = None,
    ) -> list[dict[str, Any]]:
        offers = [only_product] if only_product else self.catalog.offers()

        # -- layer 1: suppression -------------------------------------------------
        suppressed: frozenset[str] = frozenset()
        persona_affinity: dict[str, float] = {}
        if self.repo and oneid:
            suppressed = self.repo.get_suppressed_campaigns(oneid)
            persona_name = persona.name if persona else ""
            persona_affinity = self.repo.get_benefit_affinity(persona_name) if persona_name else {}

        ranked: list[tuple[float, ProductOffer, str, list[str]]] = []
        for offer in offers:
            if offer is None or offer_eligibility_reasons(offer, profile):
                continue

            # -- layer 1: skip suppressed campaigns for this oneid ----------------
            if self.repo and oneid:
                rejection_key = _rejection_key_for_offer(offer)
                if rejection_key and _matches_suppressed(rejection_key, suppressed):
                    continue

            base_score, theme, evidence = _offer_score(
                customer,
                profile,
                offer,
                persona,
                published_contexts=published_contexts or [],
            )

            # persona affinity: same-persona click-through rate bonus
            benefit_cat = _benefit_category_for_offer(offer)
            affinity = persona_affinity.get(benefit_cat, 0.0) if benefit_cat else 0.0

            score = round(base_score + affinity, 4)
            ranked.append((score, offer, theme, evidence))

        ranked.sort(key=lambda item: item[0], reverse=True)

        theme_counts: dict[str, int] = {}
        result: list[dict[str, Any]] = []
        remaining = list(ranked)
        while remaining and len(result) < limit:
            # Apply diversity only after individual relevance has been calculated.
            score, offer, theme, evidence = max(
                remaining,
                key=lambda item: item[0] - 0.08 * theme_counts.get(item[2], 0),
            )
            remaining.remove((score, offer, theme, evidence))
            theme_counts[theme] = theme_counts.get(theme, 0) + 1
            recommendation = _recommendation(customer, profile, offer, persona, score, theme, evidence=evidence)
            recommendation["rank"] = len(result) + 1
            result.append(recommendation)
        return result

    def _installment_decision(
        self,
        oneid: str,
        customer_id: str,
        customer: Customer,
        persona: PersonaProfile | None,
        scene: str,
        touchpoint: str,
    ) -> dict[str, Any]:
        intent_score = customer.intent_scores.get("\u5206\u671f/\u501f\u8d37\u9700\u6c42", 0.0)
        strategy = _strategy(persona)
        return {
            "oneid": oneid,
            "scene": scene,
            "should_recommend": intent_score >= 0.25 or customer.installment_history > 0,
            "persona_name": _persona_name(persona),
            "segment_id": _segment_id(persona),
            "next_best_action": "\u63d0\u4f9b\u8d26\u5355\u5206\u671f\u6d4b\u7b97\u4e0e\u53ef\u529e\u7406\u65b9\u6848",
            "recommended_product_id": "INSTALLMENT",
            "recommended_benefit_id": "INSTALLMENT_FEE_COUPON",
            "offer_direction": strategy["offer_direction"],
            "content_direction": "\u5148\u8bf4\u660e\u671f\u6570\u3001\u8d39\u7528\u548c\u9002\u7528\u6761\u4ef6\uff0c\u518d\u5f15\u5bfc\u7528\u6237\u6d4b\u7b97\u3002",
            "allowed_channels": [touchpoint],
            "compliance_notes": _compliance_notes(),
            "customer_reference": _reference(customer_id),
        }

    @staticmethod
    def _empty_response(
        oneid: str,
        scene: str,
        reason: str,
        *,
        personalization_consent: bool = False,
    ) -> dict[str, Any]:
        return {
            "oneid": oneid,
            "scene": scene,
            "strategy_version": "online_personalization_v1",
            "status": "not_eligible",
            "eligible_for_personalization": personalization_consent,
            "eligible_for_marketing": False,
            "reason_code": reason,
            # Keep `reason` during the transition so existing C-side code does not break.
            "reason": reason,
            "recommendations": [],
            "published_strategy_context": [],
            "published_strategy": None,
        }


def _offer_score(
    customer: Customer,
    profile: dict[str, Any],
    offer: ProductOffer,
    persona: PersonaProfile | None,
    *,
    published_contexts: list[dict[str, Any]],
) -> tuple[float, str, list[str]]:
    text = " ".join([offer.product_name, *offer.selling_points, *offer.benefit_names])
    theme = _theme(text)
    intent_key = {
        "installment": "\u5206\u671f/\u501f\u8d37\u9700\u6c42",
        "travel": "\u8de8\u5883/\u51fa\u884c\u9700\u6c42",
        "benefit": "\u6743\u76ca/\u4f18\u60e0\u9700\u6c42",
    }.get(theme)
    intent_match = customer.intent_scores.get(intent_key, 0.25) if intent_key else max(customer.intent_scores.values(), default=0.25)
    value_score = min(customer.monthly_spend / 20000, 1.0)
    activity_score = min(customer.app_active_days / 30, 1.0)
    persona_bonus = persona.allocation_weight if persona else 0.1
    behavior_affinity, evidence = _behavior_affinity(customer, profile, offer)
    published_bonus = _published_campaign_bonus(offer, theme, published_contexts)
    score = (
        0.36 * intent_match
        + 0.26 * behavior_affinity
        + 0.16 * value_score
        + 0.12 * activity_score
        + 0.06 * persona_bonus
        + published_bonus
    )
    return round(score, 4), theme, evidence


def _recommendation(
    customer: Customer,
    profile: dict[str, Any],
    offer: ProductOffer,
    persona: PersonaProfile | None,
    score: float,
    theme: str,
    *,
    evidence: list[str],
) -> dict[str, Any]:
    benefit_id, benefit_name = _best_benefit(customer, profile, offer)
    subtitle_items = offer.selling_points[:1] or offer.benefit_names[:1]
    return {
        "rank": 0,
        "recommendation_id": _reference(f"{customer.customer_id}:{offer.product_id}"),
        "product_id": offer.product_id,
        "benefit_id": benefit_id,
        "title": benefit_name or offer.product_name,
        "subtitle": "\u3001".join(subtitle_items),
        "reason": _reason(theme, evidence),
        "persona_name": _persona_name(persona),
        "segment_id": _segment_id(persona),
        "score": score,
        "action": "\u67e5\u770b\u65b9\u6848",
        "allowed_channels": ["in_app"],
        "strategy": _strategy(persona),
        "source": "catalog_personalized",
    }


def _best_benefit(customer: Customer, profile: dict[str, Any], offer: ProductOffer) -> tuple[str, str]:
    """Choose a behavior-matched benefit while retaining the eligible product ID."""
    pairs = list(zip(offer.benefit_ids, offer.benefit_names))
    if not pairs:
        return "", ""
    customer_text = " ".join(
        [
            *[str(name) for name in customer.intent_scores],
            *[str(event.get("event_name", "")) for event in customer.recent_events],
            *[str(value) for value in profile.get("recent_behavior_signals", [])],
            *[str(value) for value in profile.get("tags", [])],
        ]
    )
    rules = (
        (("娱乐", "观影", "电影", "视频", "演出", "音乐"), ("电影", "观影", "视频", "文娱", "会员")),
        (("餐饮", "餐厅", "美食", "咖啡", "外卖"), ("餐", "咖啡", "饮品", "美食")),
        (("购物", "商超", "电商", "商城", "京东", "支付"), ("购物", "京东", "商超", "返现", "支付", "商城")),
        (("出行", "旅行", "旅游", "机票", "酒店", "境外"), ("出行", "旅行", "酒店", "机场", "机票", "境外", "里程")),
        (("分期", "账单", "还款", "借贷"), ("分期", "账单")),
    )
    scored: list[tuple[int, str, str]] = []
    for benefit_id, benefit_name in pairs:
        score = 0
        for customer_words, benefit_words in rules:
            if any(word in customer_text for word in customer_words) and any(word in benefit_name for word in benefit_words):
                score += 10
        scored.append((score, benefit_id, benefit_name))
    _, benefit_id, benefit_name = max(scored, key=lambda item: (item[0], item[2]))
    return benefit_id, benefit_name


def _theme(text: str) -> str:
    if any(word in text for word in ["\u5206\u671f", "\u8d26\u5355"]):
        return "installment"
    if any(word in text for word in ["\u51fa\u884c", "\u673a\u573a", "\u9152\u5e97", "\u5883\u5916"]):
        return "travel"
    if any(word in text for word in ["\u4f18\u60e0", "\u6743\u76ca", "\u8fd4\u73b0", "\u79ef\u5206"]):
        return "benefit"
    return "general"


def _behavior_affinity(customer: Customer, profile: dict[str, Any], offer: ProductOffer) -> tuple[float, list[str]]:
    """Score product-specific fit from recent behavior instead of only overall customer value."""
    customer_text = " ".join(
        [
            *[str(name) for name in customer.intent_scores],
            *[str(event.get("event_name", "")) for event in customer.recent_events],
            *[str(value) for value in profile.get("recent_behavior_signals", [])],
            *[str(value) for value in profile.get("tags", [])],
        ]
    )
    offer_text = " ".join([offer.product_name, *offer.selling_points, *offer.benefit_names])
    scenarios = {
        "娱乐观影行为": {
            "customer": ("娱乐", "观影", "电影", "视频", "演出", "音乐"),
            "offer": ("电影", "观影", "视频", "文娱", "会员"),
        },
        "餐饮消费行为": {
            "customer": ("餐饮", "餐厅", "美食", "咖啡", "外卖"),
            "offer": ("餐", "咖啡", "饮品", "美食"),
        },
        "购物消费行为": {
            "customer": ("购物", "商超", "电商", "商城", "京东", "支付"),
            "offer": ("购物", "京东", "商超", "返现", "支付", "商城"),
        },
        "出行行为": {
            "customer": ("出行", "旅行", "旅游", "机票", "酒店", "境外"),
            "offer": ("出行", "旅行", "酒店", "机场", "机票", "境外", "里程"),
        },
        "分期需求": {
            "customer": ("分期", "账单", "还款", "借贷"),
            "offer": ("分期", "账单"),
        },
    }
    evidence: list[str] = []
    affinity = 0.0
    for label, rules in scenarios.items():
        if any(word in customer_text for word in rules["customer"]) and any(
            word in offer_text for word in rules["offer"]
        ):
            evidence.append(label)
            affinity += 0.24
    return min(1.0, affinity), evidence


def _published_campaign_bonus(
    offer: ProductOffer,
    theme: str,
    contexts: list[dict[str, Any]],
) -> float:
    """Keep the catalog aligned with the benefit category of active B-side campaigns."""
    if not contexts:
        return 0.0
    benefit_text = " ".join(
        str(context.get("benefit_rule", {}).get(key, ""))
        for context in contexts
        for key in ("benefit_name", "benefit_category", "benefit_type")
    )
    offer_text = " ".join([offer.product_name, *offer.selling_points, *offer.benefit_names])
    if any(word in benefit_text and word in offer_text for word in ("出行", "分期", "餐饮", "观影", "购物")):
        return 0.10
    if "权益" in benefit_text and theme == "benefit":
        return 0.06
    return 0.0


def _published_campaign_recommendations(
    contexts: list[dict[str, Any]],
    persona: PersonaProfile | None,
    *,
    limit: int,
) -> list[dict[str, Any]]:
    """Convert published B-side strategy membership into the first C-side card."""
    result: list[dict[str, Any]] = []
    for context in contexts[:limit]:
        benefit = context.get("benefit_rule", {})
        campaign_id = str(context.get("campaign_id", ""))
        benefit_name = str(benefit.get("benefit_name") or context.get("product") or campaign_id)
        allowed_channels = list(context.get("allowed_channels", []))
        result.append(
            {
                "rank": 0,
                "recommendation_id": _reference(f"published:{context.get('strategy_version', '')}:{campaign_id}"),
                "product_id": f"CAMPAIGN:{campaign_id}",
                "benefit_id": str(benefit.get("benefit_type", "campaign_benefit")),
                "title": benefit_name,
                "subtitle": "你已进入本期活动的合规投放名单，可查看适用条件与有效期。",
                "reason": "匹配当前已发布策略、你的客群准入与触达约束",
                "persona_name": _persona_name(persona),
                "segment_id": str(context.get("segment_id", _segment_id(persona))),
                "score": 1.0,
                "action": "查看活动",
                "allowed_channels": ["in_app"],
                "delivery_channels": allowed_channels,
                "strategy": context.get("strategy", _strategy(persona)),
                "source": "published_strategy",
                "campaign_id": campaign_id,
                "strategy_version": str(context.get("strategy_version", "")),
            }
        )
    return result


def _merge_unique_recommendations(
    *,
    published: list[dict[str, Any]],
    catalogue: list[dict[str, Any]],
    limit: int,
) -> list[dict[str, Any]]:
    """Keep campaign cards first while removing duplicate product or benefit displays."""
    result: list[dict[str, Any]] = []
    seen_product_ids: set[str] = set()
    seen_benefit_ids: set[str] = set()
    seen_titles: set[str] = set()

    for recommendation in [*published, *catalogue]:
        product_id = _recommendation_identity(recommendation.get("product_id"))
        benefit_id = _recommendation_identity(recommendation.get("benefit_id"))
        title = _recommendation_identity(recommendation.get("title"))
        if (
            product_id in seen_product_ids
            or benefit_id in seen_benefit_ids
            or title in seen_titles
        ):
            continue

        result.append(recommendation)
        seen_product_ids.add(product_id)
        seen_benefit_ids.add(benefit_id)
        seen_titles.add(title)
        if len(result) >= limit:
            break
    return result


def _recommendation_identity(value: Any) -> str:
    return "".join(str(value or "").casefold().split())


def _reason(theme: str, evidence: list[str] | None = None) -> str:
    if evidence:
        return f"结合你的{evidence[0]}与产品权益匹配"
    reasons = {
        "installment": "\u5339\u914d\u4f60\u7684\u5206\u671f\u9700\u6c42\u4e0e\u6700\u8fd1\u76f8\u5173\u884c\u4e3a",
        "travel": "\u5339\u914d\u4f60\u7684\u51fa\u884c\u9700\u6c42\u4e0e\u6d88\u8d39\u80fd\u529b",
        "benefit": "\u5339\u914d\u4f60\u7684\u6743\u76ca\u5173\u6ce8\u4e0e\u6d3b\u8dc3\u5ea6",
        "general": "\u7ed3\u5408\u4f60\u7684\u5ba2\u7fa4\u7b56\u7565\u548c\u4ea7\u54c1\u51c6\u5165\u6761\u4ef6\u5339\u914d",
    }
    return reasons[theme]


def _strategy(persona: PersonaProfile | None) -> dict[str, Any]:
    if persona is not None:
        return persona.strategy
    return {
        "offer_direction": "\u53ef\u9009\u6743\u76ca\u4e0e\u4ea7\u54c1\u8bf4\u660e",
        "content_direction": "\u6e05\u695a\u8bf4\u660e\u89c4\u5219\u3001\u8d39\u7528\u548c\u9002\u7528\u6761\u4ef6",
    }


def _persona_name(persona: PersonaProfile | None) -> str:
    return persona.name if persona else "\u9ed8\u8ba4\u7a33\u5065\u5ba2\u7fa4"


def _segment_id(persona: PersonaProfile | None) -> str:
    return f"SEG{persona.cluster_id + 1:03d}" if persona else "SEG000"


def _is_installment_request(product_id: str, user_intent: str, summary: str) -> bool:
    return product_id.upper() == "INSTALLMENT" or "\u5206\u671f" in f"{user_intent}{summary}"


def _compliance_notes() -> list[str]:
    return ["\u8d39\u7528\u4ee5\u9875\u9762\u5c55\u793a\u4e3a\u51c6", "\u4e0d\u5f97\u627f\u8bfa\u5ba1\u6279\u901a\u8fc7", "\u9700\u6309\u5ba2\u6237\u6388\u6743\u4e0e\u9891\u63a7\u89c4\u5219\u6267\u884c"]


def _reference(value: str) -> str:
    return hashlib.sha1(value.encode("utf-8")).hexdigest()[:12].upper()


def _rejection_key_for_offer(offer: ProductOffer) -> str:
    """Build a campaign-level rejection key from the offer's benefit category.

    Maps benefit_ids like 'BEN_LIF_001|BEN_LIF_003' to 'LIF', then to 'CAMP_2026_WEDDING5'.
    This is a best-effort heuristic; precise campaign-level suppression uses the
    campaign_id reported by C in the feedback event.
    """
    benefit_cat = _benefit_category_for_offer(offer)
    if not benefit_cat:
        return ""
    # Use the benefit category as the rejection lookup key (e.g., "消费", "生活")
    return f"CATEGORY_{benefit_cat}"


def _benefit_category_for_offer(offer: ProductOffer) -> str:
    """Derive a human-readable category from the offer's benefit metadata."""
    text = " ".join([offer.product_name, *offer.selling_points, *offer.benefit_names])
    theme = _theme(text)
    category_map = {"installment": "分期", "travel": "出行", "benefit": "权益", "general": "权益"}
    return category_map.get(theme, "权益")


def _matches_suppressed(key: str, suppressed: frozenset[str]) -> bool:
    """Check if an offer's rejection key hits any entry in the suppressed set."""
    if not key:
        return False
    # Direct match (category key)
    if key in suppressed:
        return True
    # Campaign-level match: suppressed set entries like "CAMP_2026_BACK_SCHOOL"
    # and category keys like "CATEGORY_分期"
    for entry in suppressed:
        if entry in key or key in entry:
            return True
    return False
