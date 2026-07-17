from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass

from .models import CampaignRequest, CustomerScore, SegmentRecommendation
from .recommender import PRODUCT_EVENT_KEYWORDS, PRODUCT_INTENTS

try:
    from sklearn.cluster import KMeans
    from sklearn.preprocessing import StandardScaler
except ImportError:  # Keeps the demo usable before the optional dependency is installed.
    KMeans = None
    StandardScaler = None


FEATURE_NAMES = [
    "\u5339\u914d\u610f\u56fe",
    "\u6708\u5747\u6d88\u8d39",
    "\u989d\u5ea6\u4f7f\u7528\u7387",
    "App \u6d3b\u8dc3\u5929\u6570",
    "\u8fd1\u671f\u76f8\u5173\u884c\u4e3a",
    "\u6295\u8bc9\u98ce\u9669",
]


@dataclass(frozen=True)
class PersonaClusteringResult:
    segments: list[SegmentRecommendation]
    feature_names: list[str]


def kmeans_available() -> bool:
    return KMeans is not None and StandardScaler is not None


def build_kmeans_personas(
    scored: list[CustomerScore], request: CampaignRequest, n_clusters: int = 4
) -> PersonaClusteringResult | None:
    """Cluster the already eligible and prioritized audience for operator interpretation."""
    if not kmeans_available() or len(scored) < n_clusters:
        return None

    feature_rows = [_feature_row(item, request.product) for item in scored]
    scaled_rows = StandardScaler().fit_transform(feature_rows)
    labels = KMeans(n_clusters=n_clusters, n_init=20, random_state=42).fit_predict(scaled_rows)

    grouped: dict[int, list[CustomerScore]] = defaultdict(list)
    features_by_group: dict[int, list[list[float]]] = defaultdict(list)
    for label, item, features in zip(labels, scored, feature_rows):
        grouped[int(label)].append(item)
        features_by_group[int(label)].append(features)

    segments: list[SegmentRecommendation] = []
    for cluster_id, rows in grouped.items():
        averages = [sum(column) / len(column) for column in zip(*features_by_group[cluster_id])]
        avg_score = sum(row.priority_score for row in rows) / len(rows)
        avg_conversion = sum(row.conversion_prob for row in rows) / len(rows)
        value_wan = sum(row.expected_value for row in rows) / 10000
        segments.append(
            SegmentRecommendation(
                name=f"{_persona_name(averages)}-{cluster_id + 1}",
                size=len(rows),
                avg_score=round(avg_score, 1),
                conversion_rate=round(avg_conversion * 100, 2),
                expected_value_wan=round(value_wan, 2),
                reasons=_persona_reasons(averages),
            )
        )

    segments.sort(key=lambda item: item.expected_value_wan, reverse=True)
    return PersonaClusteringResult(segments=segments, feature_names=FEATURE_NAMES)


def _feature_row(item: CustomerScore, product: str) -> list[float]:
    customer = item.customer
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


def _persona_name(averages: list[float]) -> str:
    intent, monthly_spend, credit_usage, app_days, behavior, _risk = averages
    if monthly_spend >= 50000:
        return "\u6838\u5fc3\u4ef7\u503c\u6df1\u8015\u5ba2\u7fa4"
    if intent >= 0.75 and app_days >= 18:
        return "\u9ad8\u610f\u56fe\u6d3b\u8dc3\u8f6c\u5316\u5ba2\u7fa4"
    if behavior >= 0.30:
        return "\u8fd1\u671f\u884c\u4e3a\u54cd\u5e94\u5ba2\u7fa4"
    return "\u7a33\u5065\u8f6c\u5316\u5ba2\u7fa4"


def _persona_reasons(averages: list[float]) -> list[str]:
    intent, monthly_spend, credit_usage, app_days, behavior, risk = averages
    return [
        f"\u5339\u914d\u610f\u56fe\u5747\u503c {intent * 100:.0f}\u5206",
        f"\u6708\u5747\u6d88\u8d39 {monthly_spend:,.0f}\u5143\uff0c\u989d\u5ea6\u4f7f\u7528\u7387 {credit_usage * 100:.0f}%",
        f"App \u6d3b\u8dc3 {app_days:.0f}\u5929\uff0c\u76f8\u5173\u884c\u4e3a {behavior * 100:.0f}\u5206\uff0c\u6295\u8bc9\u98ce\u9669 {risk * 100:.1f}%",
    ]
