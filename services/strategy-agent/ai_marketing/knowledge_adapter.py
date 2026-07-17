from __future__ import annotations

from .models import Customer


def customers_from_knowledge_insight(payload: dict) -> list[Customer]:
    """Convert Knowledge Agent customer insight JSON into Strategy Agent features."""
    customers: list[Customer] = []
    for index, item in enumerate(payload.get("customers", []), start=1):
        profile = item.get("customer_profile", {})
        tags = set(profile.get("tags", []))
        intent_names = {
            intent.get("name", "")
            for intent in item.get("intent_vector", {}).get("top_intents", [])
            if isinstance(intent, dict)
        }
        event_names = {
            event.get("event_name", "")
            for event in item.get("event_sequence", [])
            if isinstance(event, dict)
        }
        customers.append(
            Customer(
                customer_id=str(item.get("customer_id") or f"KC{index:06d}"),
                age=int(profile.get("age", 35)),
                city_tier=int(profile.get("city_tier", 2)),
                monthly_spend=float(profile.get("monthly_spend", 5000)),
                dining_txn=int(profile.get("dining_txn", estimate_dining_txn(tags, event_names))),
                travel_txn=int(profile.get("travel_txn", estimate_travel_txn(tags, intent_names, event_names))),
                online_txn=int(profile.get("online_txn", estimate_online_txn(tags, event_names))),
                credit_limit_usage=float(profile.get("credit_limit_usage", 0.45)),
                coupon_response=float(profile.get("coupon_response", estimate_coupon_response(tags, intent_names))),
                installment_history=int(
                    profile.get("installment_history", estimate_installment_history(tags, intent_names, event_names))
                ),
                app_active_days=int(profile.get("app_active_days", estimate_app_active_days(tags, profile))),
                recent_contacts=int(profile.get("recent_contact_count", 0)),
                complaint_risk=float(profile.get("complaint_risk", 0.05)),
                has_marketing_consent=bool(profile.get("marketing_consent", False)),
            )
        )
    return customers


def estimate_dining_txn(tags: set[str], event_names: set[str]) -> int:
    score = 6
    if "餐饮高频" in tags or any("餐饮" in event for event in event_names):
        score += 8
    if "高消费" in tags:
        score += 3
    return score


def estimate_travel_txn(tags: set[str], intent_names: set[str], event_names: set[str]) -> int:
    score = 1
    if "商旅活跃" in tags or any("商旅" in value or "出行" in value for value in intent_names | event_names):
        score += 4
    return score


def estimate_online_txn(tags: set[str], event_names: set[str]) -> int:
    score = 12
    if "App活跃" in tags:
        score += 8
    if any("线上" in event or "App" in event for event in event_names):
        score += 4
    return score


def estimate_coupon_response(tags: set[str], intent_names: set[str]) -> float:
    score = 0.28
    if "权益敏感" in tags:
        score += 0.28
    if any("权益" in intent or "券" in intent for intent in intent_names):
        score += 0.18
    return min(score, 0.9)


def estimate_installment_history(tags: set[str], intent_names: set[str], event_names: set[str]) -> int:
    score = 0
    if "分期敏感" in tags:
        score += 2
    if any("分期" in value or "账单" in value for value in intent_names | event_names):
        score += 1
    return min(score, 3)


def estimate_app_active_days(tags: set[str], profile: dict) -> int:
    if "app_active_days" in profile:
        return int(profile["app_active_days"])
    if "App活跃" in tags:
        return 24
    return 12
