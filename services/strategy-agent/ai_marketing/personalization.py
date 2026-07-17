from __future__ import annotations

import hashlib
from dataclasses import dataclass
from typing import Any

from .eligibility import filter_to_eligible_customers
from .knowledge_adapter import customers_from_knowledge_insight
from .local_knowledge_data import LocalKnowledgeData
from .models import CampaignRequest, Customer
from .offer_catalog import OfferCatalog, ProductOffer
from .orchestrator import MarketingDecisionEngine
from .persona import PersonaProfile, cluster_priority_candidates
from .recommender import filter_priority_candidates


@dataclass(frozen=True)
class AudienceContext:
    customers: dict[str, Customer]
    profiles: dict[str, dict[str, Any]]
    persona_assignments: dict[str, PersonaProfile]


class PersonalizedStrategyService:
    """Serve online recommendations without exposing raw customer data to the client."""

    def __init__(self, local_data: LocalKnowledgeData, engine: MarketingDecisionEngine) -> None:
        self.local_data = local_data
        self.engine = engine
        self.catalog = OfferCatalog()
        self._audience_context: AudienceContext | None = None

    def recommendations(self, oneid: str, *, scene: str = "agent_home", limit: int = 5) -> dict[str, Any]:
        customer_id, customer, profile, persona = self._customer_context(oneid)
        if not profile.get("personalization_consent", False):
            return self._empty_response(oneid, scene, "personalization_consent_required")

        recommendations = self._rank_offers(customer, profile, persona, limit=max(1, min(limit, 10)))
        return {
            "oneid": oneid,
            "scene": scene,
            "strategy_version": "online_personalization_v1",
            "recommendations": recommendations,
            "customer_reference": _reference(customer_id),
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
        recommendations = self._rank_offers(customer, profile, persona, limit=1, only_product=offer)
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
        request = CampaignRequest(goal="online personalization", product="installment", budget_wan=20)
        priority_candidates = filter_priority_candidates(eligible_customers, request)
        personas = cluster_priority_candidates(priority_candidates, request)
        self._audience_context = AudienceContext(
            customers={customer.customer_id: customer for customer in priority_candidates},
            profiles={
                item["customer_id"]: item.get("customer_profile", {})
                for item in eligible_payload.get("customers", [])
            },
            persona_assignments=personas.assignments if personas else {},
        )
        return self._audience_context

    def _rank_offers(
        self,
        customer: Customer,
        profile: dict[str, Any],
        persona: PersonaProfile | None,
        *,
        limit: int,
        only_product: ProductOffer | None = None,
    ) -> list[dict[str, Any]]:
        offers = [only_product] if only_product else self.catalog.offers()
        ranked: list[tuple[float, ProductOffer, str]] = []
        for offer in offers:
            if offer is None or not _product_eligible(offer, profile):
                continue
            score, theme = _offer_score(customer, offer, persona)
            ranked.append((score, offer, theme))
        ranked.sort(key=lambda item: item[0], reverse=True)

        theme_counts: dict[str, int] = {}
        result: list[dict[str, Any]] = []
        deferred: list[tuple[float, ProductOffer, str]] = []
        for score, offer, theme in ranked:
            if theme_counts.get(theme, 0) >= 2:
                deferred.append((score, offer, theme))
                continue
            theme_counts[theme] = theme_counts.get(theme, 0) + 1
            recommendation = _recommendation(customer, offer, persona, score, theme)
            recommendation["rank"] = len(result) + 1
            result.append(recommendation)
            if len(result) >= limit:
                break
        for score, offer, theme in deferred:
            if len(result) >= limit:
                break
            recommendation = _recommendation(customer, offer, persona, score, theme)
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
    def _empty_response(oneid: str, scene: str, reason: str) -> dict[str, Any]:
        return {"oneid": oneid, "scene": scene, "strategy_version": "online_personalization_v1", "recommendations": [], "reason": reason}


def _product_eligible(offer: ProductOffer, profile: dict[str, Any]) -> bool:
    age = int(profile.get("age", 0))
    income = str(profile.get("income_level", ""))
    credit = float(profile.get("total_credit_amount", 0))
    card_level = str(profile.get("card_level", ""))
    gender = str(profile.get("gender", ""))
    conditions = offer.special_conditions
    if age < offer.min_age or age > offer.max_age or credit < offer.min_credit:
        return False
    if offer.required_income and income not in _split_levels(offer.required_income):
        return False
    if not _card_level_eligible(card_level, offer.required_card_level):
        return False
    if "\u6682\u505c" in conditions or "\u9080\u8bf7" in conditions:
        return False
    if "\u5973\u6027" in conditions and gender != "\u5973":
        return False
    if "\u5b66\u751f" in conditions:
        return False
    return True


def _offer_score(customer: Customer, offer: ProductOffer, persona: PersonaProfile | None) -> tuple[float, str]:
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
    return round(0.55 * intent_match + 0.20 * value_score + 0.15 * activity_score + 0.10 * persona_bonus, 4), theme


def _recommendation(
    customer: Customer, offer: ProductOffer, persona: PersonaProfile | None, score: float, theme: str
) -> dict[str, Any]:
    benefit_id = offer.benefit_ids[0] if offer.benefit_ids else ""
    subtitle_items = offer.benefit_names[:2] or offer.selling_points[:2]
    return {
        "rank": 0,
        "recommendation_id": _reference(f"{customer.customer_id}:{offer.product_id}"),
        "product_id": offer.product_id,
        "benefit_id": benefit_id,
        "title": offer.product_name,
        "subtitle": "\u3001".join(subtitle_items),
        "reason": _reason(theme),
        "persona_name": _persona_name(persona),
        "segment_id": _segment_id(persona),
        "score": score,
        "action": "\u67e5\u770b\u65b9\u6848",
        "allowed_channels": ["in_app"],
        "strategy": _strategy(persona),
    }


def _theme(text: str) -> str:
    if any(word in text for word in ["\u5206\u671f", "\u8d26\u5355"]):
        return "installment"
    if any(word in text for word in ["\u51fa\u884c", "\u673a\u573a", "\u9152\u5e97", "\u5883\u5916"]):
        return "travel"
    if any(word in text for word in ["\u4f18\u60e0", "\u6743\u76ca", "\u8fd4\u73b0", "\u79ef\u5206"]):
        return "benefit"
    return "general"


def _reason(theme: str) -> str:
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


def _split_levels(value: str) -> set[str]:
    return {item.strip() for item in value.split(",") if item.strip()}


def _card_level_eligible(current: str, required: str) -> bool:
    if not required or required == "-":
        return True
    ranks = {"\u666e\u5361": 1, "\u91d1\u5361": 2, "\u767d\u91d1\u5361": 3, "\u94bb\u77f3\u5361": 4, "\u65e0\u9650\u5361": 5}
    required_level = next((rank for name, rank in ranks.items() if name in required), 0)
    current_level = next((rank for name, rank in ranks.items() if name in current), 0)
    return current_level >= required_level


def _is_installment_request(product_id: str, user_intent: str, summary: str) -> bool:
    return product_id.upper() == "INSTALLMENT" or "\u5206\u671f" in f"{user_intent}{summary}"


def _compliance_notes() -> list[str]:
    return ["\u8d39\u7528\u4ee5\u9875\u9762\u5c55\u793a\u4e3a\u51c6", "\u4e0d\u5f97\u627f\u8bfa\u5ba1\u6279\u901a\u8fc7", "\u9700\u6309\u5ba2\u6237\u6388\u6743\u4e0e\u9891\u63a7\u89c4\u5219\u6267\u884c"]


def _reference(value: str) -> str:
    return hashlib.sha1(value.encode("utf-8")).hexdigest()[:12].upper()
