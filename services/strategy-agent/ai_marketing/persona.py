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
DEFAULT_CLUSTER_COUNT = 5


@dataclass(frozen=True)
class PersonaProfile:
    cluster_id: int
    name: str
    feature_averages: list[float]
    standardized_feature_averages: list[float]
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
    customers: list[Customer], request: CampaignRequest, n_clusters: int = DEFAULT_CLUSTER_COUNT
) -> PersonaClusteringResult | None:
    """Cluster compliant candidates before score-based selection and budget allocation."""
    if not kmeans_available() or len(customers) < n_clusters:
        return None

    feature_rows = build_persona_feature_rows(customers, request.product)
    scaled_rows = StandardScaler().fit_transform(feature_rows)
    labels = KMeans(n_clusters=n_clusters, n_init=20, random_state=42).fit_predict(scaled_rows)

    grouped_features: dict[int, list[list[float]]] = defaultdict(list)
    grouped_scaled_features: dict[int, list[list[float]]] = defaultdict(list)
    grouped_customers: dict[int, list[Customer]] = defaultdict(list)
    for label, customer, features, scaled_features in zip(labels, customers, feature_rows, scaled_rows):
        cluster_id = int(label)
        grouped_customers[cluster_id].append(customer)
        grouped_features[cluster_id].append(features)
        grouped_scaled_features[cluster_id].append(list(scaled_features))

    assignments: dict[str, PersonaProfile] = {}
    profiles: dict[int, PersonaProfile] = {}
    for cluster_id, cluster_customers in grouped_customers.items():
        averages = [sum(column) / len(column) for column in zip(*grouped_features[cluster_id])]
        standardized_averages = [
            sum(column) / len(column) for column in zip(*grouped_scaled_features[cluster_id])
        ]
        profile = _build_profile(cluster_id, averages, standardized_averages)
        profiles[cluster_id] = profile
        assignments.update({customer.customer_id: profile for customer in cluster_customers})

    return PersonaClusteringResult(assignments=assignments, profiles=profiles, feature_names=FEATURE_NAMES)


def build_persona_feature_rows(customers: list[Customer], product: str) -> list[list[float]]:
    """Return the exact feature matrix used by online and batch KMeans clustering."""
    return [_feature_row(customer, product) for customer in customers]


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


def _build_profile(
    cluster_id: int, averages: list[float], standardized_averages: list[float]
) -> PersonaProfile:
    """Make KMeans centroids, rather than business thresholds, drive persona behavior."""
    feature_priorities = _cluster_feature_priorities(standardized_averages)
    score_weights = _data_driven_score_weights(standardized_averages)
    allocation_weight = _data_driven_allocation_weight(standardized_averages)
    top_features = feature_priorities[:2]
    feature_summary = "、".join(item["label"] for item in top_features)
    name = f"数据驱动群像-C{cluster_id + 1}（{feature_summary}突出）"

    return PersonaProfile(
        cluster_id=cluster_id,
        name=name,
        feature_averages=averages,
        standardized_feature_averages=standardized_averages,
        score_weights=score_weights,
        allocation_weight=allocation_weight,
        strategy={
            "scoring_focus": f"簇中心特征排序：{feature_summary}；评分权重由簇中心动态生成",
            "channel_strategy": "仅在已授权渠道中，结合渠道单位成本、历史效果和容量选择触达方式",
            "offer_direction": f"优先匹配与{feature_summary}相关、且满足产品准入的产品与权益",
            "content_direction": f"围绕{feature_summary}提供场景化说明，并透明展示费用、条件与办理路径",
            "allocation_weight": allocation_weight,
            "cluster_feature_priorities": feature_priorities,
            "score_weights": score_weights,
        },
    )


def _cluster_feature_priorities(standardized_averages: list[float]) -> list[dict[str, float | str]]:
    descriptors = [
        ("intent", "意图强度", standardized_averages[0]),
        ("value", "消费价值", standardized_averages[1]),
        ("limit_usage", "额度使用", standardized_averages[2]),
        ("activity", "App 活跃", standardized_averages[3]),
        ("behavior", "近期相关行为", standardized_averages[4]),
    ]
    return [
        {"feature": key, "label": label, "z_score": round(float(score), 3)}
        for key, label, score in sorted(descriptors, key=lambda item: item[2], reverse=True)
    ]


def _data_driven_score_weights(standardized_averages: list[float]) -> dict[str, float]:
    intent, spend, limit_usage, activity, behavior, _risk = standardized_averages
    signals = {
        "intent": intent,
        "behavior": behavior,
        "value": 0.7 * spend + 0.3 * limit_usage,
        "activity": activity,
        "response": (intent + behavior + activity) / 3,
        "limit_usage": limit_usage,
    }
    base_weights = {
        "intent": 0.20,
        "behavior": 0.16,
        "value": 0.20,
        "activity": 0.10,
        "response": 0.16,
        "limit_usage": 0.08,
    }
    adjusted = {
        key: base * max(0.35, 1.0 + 0.35 * signals[key]) for key, base in base_weights.items()
    }
    positive_total = sum(adjusted.values())
    return {
        **{key: float(round(value / positive_total * 0.90, 4)) for key, value in adjusted.items()},
        "risk": 0.10,
    }


def _data_driven_allocation_weight(standardized_averages: list[float]) -> float:
    intent, spend, limit_usage, activity, behavior, _risk = standardized_averages
    opportunity = 0.28 * intent + 0.22 * behavior + 0.20 * spend + 0.15 * limit_usage + 0.15 * activity
    return float(round(max(0.10, 1.0 + opportunity), 4))


def _persona_reasons(averages: list[float]) -> list[str]:
    intent, monthly_spend, credit_usage, app_days, behavior, risk = averages
    return [
        f"\u5339\u914d\u610f\u56fe\u5747\u503c {intent * 100:.0f}\u5206",
        f"\u6708\u5747\u6d88\u8d39 {monthly_spend:,.0f}\u5143\uff0c\u989d\u5ea6\u4f7f\u7528\u7387 {credit_usage * 100:.0f}%",
        f"App \u6d3b\u8dc3 {app_days:.0f}\u5929\uff0c\u76f8\u5173\u884c\u4e3a {behavior * 100:.0f}\u5206\uff0c\u6295\u8bc9\u98ce\u9669 {risk * 100:.1f}%",
    ]
