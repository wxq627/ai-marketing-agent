from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass
from typing import Any

from .models import CampaignRequest, Customer, CustomerScore, SegmentRecommendation

try:
    from sklearn.cluster import KMeans
    from sklearn.preprocessing import StandardScaler
except ImportError:  # Keeps the demo usable before the optional dependency is installed.
    KMeans = None
    StandardScaler = None


PRODUCT_INTENTS = {
    "installment": "\u5206\u671f/\u501f\u8d37\u9700\u6c42",
    "coupon": "\u6743\u76ca/\u4f18\u60e0\u9700\u6c42",
    "travel": "\u8de8\u5883/\u51fa\u884c\u9700\u6c42",
}
PRODUCT_EVENT_KEYWORDS = {
    "installment": ["\u5206\u671f", "\u8d26\u5355"],
    "coupon": ["\u4f18\u60e0", "\u79ef\u5206", "\u6743\u76ca"],
    "travel": ["\u51fa\u884c", "\u5883\u5916", "\u9152\u5e97", "\u673a\u7968"],
}
FEATURE_NAMES = [
    "\u5339\u914d\u610f\u56fe",
    "\u6708\u5747\u6d88\u8d39",
    "\u989d\u5ea6\u4f7f\u7528\u7387",
    "App \u6d3b\u8dc3\u5929\u6570",
    "\u8fd1\u671f\u76f8\u5173\u884c\u4e3a",
    "\u6295\u8bc9\u98ce\u9669",
]


@dataclass(frozen=True)
class PersonaProfile:
    cluster_id: int
    name: str
    feature_averages: list[float]
    score_weights: dict[str, float]
    allocation_weight: float
    strategy: dict[str, Any]


@dataclass(frozen=True)
class PersonaClusteringResult:
    assignments: dict[str, PersonaProfile]
    profiles: dict[int, PersonaProfile]
    feature_names: list[str]


def kmeans_available() -> bool:
    return KMeans is not None and StandardScaler is not None


def cluster_priority_candidates(
    customers: list[Customer], request: CampaignRequest, n_clusters: int = 4
) -> PersonaClusteringResult | None:
    """Cluster compliant candidates before score-based selection and budget allocation."""
    if not kmeans_available() or len(customers) < n_clusters:
        return None

    feature_rows = [_feature_row(customer, request.product) for customer in customers]
    scaled_rows = StandardScaler().fit_transform(feature_rows)
    labels = KMeans(n_clusters=n_clusters, n_init=20, random_state=42).fit_predict(scaled_rows)

    grouped_features: dict[int, list[list[float]]] = defaultdict(list)
    grouped_customers: dict[int, list[Customer]] = defaultdict(list)
    for label, customer, features in zip(labels, customers, feature_rows):
        cluster_id = int(label)
        grouped_customers[cluster_id].append(customer)
        grouped_features[cluster_id].append(features)

    assignments: dict[str, PersonaProfile] = {}
    profiles: dict[int, PersonaProfile] = {}
    for cluster_id, cluster_customers in grouped_customers.items():
        averages = [sum(column) / len(column) for column in zip(*grouped_features[cluster_id])]
        profile = _build_profile(cluster_id, averages)
        profiles[cluster_id] = profile
        assignments.update({customer.customer_id: profile for customer in cluster_customers})

    return PersonaClusteringResult(assignments=assignments, profiles=profiles, feature_names=FEATURE_NAMES)


def summarize_selected_personas(
    scored: list[CustomerScore], assignments: dict[str, PersonaProfile]
) -> list[SegmentRecommendation]:
    grouped: dict[str, list[CustomerScore]] = defaultdict(list)
    profiles_by_name: dict[str, PersonaProfile] = {}
    for item in scored:
        profile = assignments.get(item.customer.customer_id)
        if profile is None:
            continue
        grouped[profile.name].append(item)
        profiles_by_name[profile.name] = profile

    segments: list[SegmentRecommendation] = []
    for name, rows in grouped.items():
        profile = profiles_by_name[name]
        avg_score = sum(row.priority_score for row in rows) / len(rows)
        conversion = sum(row.conversion_prob for row in rows) / len(rows)
        value_wan = sum(row.expected_value for row in rows) / 10000
        segments.append(
            SegmentRecommendation(
                name=name,
                size=len(rows),
                avg_score=round(avg_score, 1),
                conversion_rate=round(conversion * 100, 2),
                expected_value_wan=round(value_wan, 2),
                reasons=_persona_reasons(profile.feature_averages),
                strategy=profile.strategy,
            )
        )
    segments.sort(key=lambda item: item.expected_value_wan, reverse=True)
    return segments


def _feature_row(customer: Customer, product: str) -> list[float]:
    intent_name = PRODUCT_INTENTS.get(product, PRODUCT_INTENTS["installment"])
    return [
        customer.intent_scores.get(intent_name, 0.0),
        customer.monthly_spend,
        customer.credit_limit_usage,
        float(customer.app_active_days),
        _related_behavior_score(customer.recent_events, product),
        customer.complaint_risk,
    ]


def _related_behavior_score(events: list[dict[str, str]], product: str) -> float:
    keywords = PRODUCT_EVENT_KEYWORDS.get(product, [])
    matched_events = 0
    for event in events[-20:]:
        event_name = str(event.get("event_name", ""))
        if any(keyword in event_name for keyword in keywords):
            matched_events += 1
    return min(1.0, matched_events * 0.25)


def _build_profile(cluster_id: int, averages: list[float]) -> PersonaProfile:
    persona_type = _persona_type(averages)
    definitions = {
        "core_value": {
            "name": "\u6838\u5fc3\u4ef7\u503c\u6df1\u8015\u5ba2\u7fa4",
            "weights": {"intent": 0.15, "behavior": 0.05, "value": 0.32, "activity": 0.05, "response": 0.12, "limit_usage": 0.21, "risk": 0.10},
            "allocation": 0.30,
            "focus": "\u9884\u671f\u6536\u76ca\u3001\u989d\u5ea6\u4f7f\u7528\u4e0e\u4f4e\u98ce\u9669",
            "channel": "App \u4e3b\u89e6\u8fbe\uff0c\u5bf9\u9ad8\u610f\u613f\u5ba2\u6237\u518d\u8f85\u4ee5\u4f01\u5fae\u670d\u52a1",
            "offer": "\u4e13\u5c5e\u6743\u76ca\u6216\u9ad8\u989d\u4f18\u5148\u65b9\u6848",
            "content": "\u5f3a\u8c03\u4e13\u5c5e\u5339\u914d\u3001\u4f7f\u7528\u6761\u4ef6\u4e0e\u900f\u660e\u6210\u672c\uff0c\u4e0d\u505a\u4fdd\u8bc1\u6027\u627f\u8bfa",
        },
        "high_intent": {
            "name": "\u9ad8\u610f\u56fe\u6d3b\u8dc3\u8f6c\u5316\u5ba2\u7fa4",
            "weights": {"intent": 0.40, "behavior": 0.20, "value": 0.05, "activity": 0.10, "response": 0.08, "limit_usage": 0.07, "risk": 0.10},
            "allocation": 0.40,
            "focus": "\u5339\u914d\u610f\u56fe\u3001\u8fd1\u671f\u884c\u4e3a\u4e0e\u5373\u65f6\u8f6c\u5316\u6982\u7387",
            "channel": "App Push / App \u5185\u6d88\u606f\u4f18\u5148\uff0c\u672a\u54cd\u5e94\u518d\u6309\u6388\u6743\u72b6\u6001\u8f6c\u5165\u5907\u7528\u6e20\u9053",
            "offer": "\u4e0e\u5f53\u524d\u610f\u56fe\u76f4\u63a5\u5339\u914d\u7684\u77ed\u7a97\u53e3\u6743\u76ca",
            "content": "\u70b9\u51fa\u5ba2\u6237\u521a\u5173\u6ce8\u7684\u670d\u52a1\u6216\u573a\u666f\uff0c\u6e05\u695a\u8bf4\u660e\u53ef\u9009\u65b9\u6848\u4e0e\u529e\u7406\u8def\u5f84",
        },
        "recent_response": {
            "name": "\u8fd1\u671f\u884c\u4e3a\u54cd\u5e94\u5ba2\u7fa4",
            "weights": {"intent": 0.22, "behavior": 0.32, "value": 0.08, "activity": 0.10, "response": 0.10, "limit_usage": 0.08, "risk": 0.10},
            "allocation": 0.20,
            "focus": "\u6700\u8fd1\u6d4f\u89c8\u3001\u70b9\u51fb\u548c\u6d3b\u52a8\u54cd\u5e94\u4fe1\u53f7",
            "channel": "\u5728\u5141\u8bb8\u7684\u9996\u9009\u6e20\u9053\u8fdb\u884c\u77ed\u7a97\u53e3\u8ddf\u8fdb\uff0c\u6ca1\u6709\u6388\u6743\u4e0d\u8f6c\u5176\u4ed6\u6e20\u9053",
            "offer": "\u4e0e\u6700\u8fd1\u884c\u4e3a\u5173\u8054\u7684\u4f4e\u95e8\u69db\u6743\u76ca",
            "content": "\u7528\u201c\u60a8\u521a\u67e5\u770b/\u5173\u6ce8\u201d\u8fdb\u884c\u5f31\u63d0\u793a\uff0c\u5e76\u63d0\u4f9b\u6e05\u6670\u7684\u4e0b\u4e00\u6b65\u64cd\u4f5c",
        },
        "nurture": {
            "name": "\u6d3b\u8dc3\u6f5c\u529b\u57f9\u80b2\u5ba2\u7fa4",
            "weights": {"intent": 0.20, "behavior": 0.08, "value": 0.15, "activity": 0.22, "response": 0.15, "limit_usage": 0.10, "risk": 0.10},
            "allocation": 0.10,
            "focus": "\u957f\u671f\u4ef7\u503c\u3001\u6d3b\u8dc3\u5ea6\u548c\u4f4e\u6253\u6270\u57f9\u80b2",
            "channel": "App \u5185\u5c55\u793a\u6216\u670d\u52a1\u8fdb\u7a0b\u4e2d\u63d0\u793a\uff0c\u4e0d\u4e3b\u52a8\u63d0\u9ad8\u89e6\u8fbe\u5f3a\u5ea6",
            "offer": "\u53ef\u9009\u7684\u8f7b\u91cf\u6743\u76ca\u4e0e\u670d\u52a1\u6559\u80b2",
            "content": "\u5148\u8bf4\u660e\u4ea7\u54c1\u4ef7\u503c\u548c\u89c4\u5219\uff0c\u907f\u514d\u50ac\u4fc3\u548c\u9ad8\u538b\u8bed\u6c14",
        },
        "credit_potential": {
            "name": "\u989d\u5ea6\u4f7f\u7528\u6f5c\u529b\u5ba2\u7fa4",
            "weights": {"intent": 0.18, "behavior": 0.08, "value": 0.18, "activity": 0.08, "response": 0.10, "limit_usage": 0.28, "risk": 0.10},
            "allocation": 0.20,
            "focus": "\u989d\u5ea6\u4f7f\u7528\u7387\u3001\u6d88\u8d39\u5bb9\u91cf\u4e0e\u529e\u7406\u53ef\u80fd\u6027",
            "channel": "App \u5185\u8d26\u5355\u3001\u989d\u5ea6\u9875\u6216\u5206\u671f\u6d4b\u7b97\u573a\u666f\u4f18\u5148\u89e6\u8fbe",
            "offer": "\u4e0e\u989d\u5ea6\u4f7f\u7528\u573a\u666f\u5339\u914d\u7684\u5206\u671f\u3001\u8fd8\u6b3e\u6216\u989d\u5ea6\u670d\u52a1",
            "content": "\u56f4\u7ed5\u201c\u989d\u5ea6\u4f7f\u7528\u66f4\u7075\u6d3b\u201d\u8fdb\u884c\u89e3\u91ca\uff0c\u9700\u660e\u793a\u8d39\u7528\u3001\u671f\u6570\u4e0e\u9002\u7528\u6761\u4ef6",
        },
    }
    definition = definitions[persona_type]
    return PersonaProfile(
        cluster_id=cluster_id,
        name=f"{definition['name']}-C{cluster_id + 1}",
        feature_averages=averages,
        score_weights=definition["weights"],
        allocation_weight=definition["allocation"],
        strategy={
            "scoring_focus": definition["focus"],
            "channel_strategy": definition["channel"],
            "offer_direction": definition["offer"],
            "content_direction": definition["content"],
            "allocation_weight": definition["allocation"],
        },
    )


def _persona_type(averages: list[float]) -> str:
    intent, monthly_spend, _credit_usage, _app_days, behavior, _risk = averages
    if monthly_spend >= 20000:
        return "core_value"
    if intent >= 0.70:
        return "high_intent"
    if _credit_usage >= 0.30:
        return "credit_potential"
    if behavior >= 0.30:
        return "recent_response"
    return "nurture"


def _persona_reasons(averages: list[float]) -> list[str]:
    intent, monthly_spend, credit_usage, app_days, behavior, risk = averages
    return [
        f"\u5339\u914d\u610f\u56fe\u5747\u503c {intent * 100:.0f}\u5206",
        f"\u6708\u5747\u6d88\u8d39 {monthly_spend:,.0f}\u5143\uff0c\u989d\u5ea6\u4f7f\u7528\u7387 {credit_usage * 100:.0f}%",
        f"App \u6d3b\u8dc3 {app_days:.0f}\u5929\uff0c\u76f8\u5173\u884c\u4e3a {behavior * 100:.0f}\u5206\uff0c\u6295\u8bc9\u98ce\u9669 {risk * 100:.1f}%",
    ]
