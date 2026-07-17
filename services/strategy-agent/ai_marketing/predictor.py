from __future__ import annotations

import math

from .models import Customer


def sigmoid(value: float) -> float:
    return 1 / (1 + math.exp(-value))


def predict_response(customer: Customer, product: str) -> tuple[float, list[str], str]:
    spend_score = min(customer.monthly_spend / 10000, 1.8)
    active_score = customer.app_active_days / 30
    contact_penalty = customer.recent_contacts * 0.11
    risk_penalty = customer.complaint_risk * 1.7

    if product == "installment":
        raw = (
            -1.35
            + 0.92 * customer.credit_limit_usage
            + 0.45 * customer.installment_history
            + 0.34 * spend_score
            + 0.28 * active_score
            - contact_penalty
            - risk_penalty
        )
        segment = (
            "高额消费潜力客群"
            if customer.monthly_spend >= 7000
            else "商旅资金周转客群"
            if customer.travel_txn >= 3
            else "权益敏感活跃客群"
        )
    elif product == "coupon":
        raw = (
            -1.05
            + 1.25 * customer.coupon_response
            + 0.055 * customer.dining_txn
            + 0.025 * customer.online_txn
            + 0.3 * active_score
            - contact_penalty
            - risk_penalty
        )
        segment = (
            "餐饮高频客群"
            if customer.dining_txn >= 10
            else "线上支付活跃客群"
            if customer.online_txn >= 18
            else "沉睡唤醒客群"
        )
    else:
        raw = (
            -1.45
            + 0.16 * customer.travel_txn
            + 0.36 * spend_score
            + 0.22 * (4 - customer.city_tier)
            + 0.24 * active_score
            - contact_penalty
            - risk_penalty
        )
        segment = (
            "高频商旅客群"
            if customer.travel_txn >= 4
            else "跨城通勤客群"
            if customer.travel_txn >= 2
            else "高净值潜力客群"
        )

    response = sigmoid(raw)
    reasons = explain_customer(customer, product)
    return response, reasons, segment


def predict_conversion(response_prob: float, channel_mode: str) -> float:
    channel_factor = {"omni": 1.18, "app": 1.06, "sms": 0.86}.get(channel_mode, 1.0)
    return min(0.82, response_prob * channel_factor * 0.42)


def expected_customer_value(customer: Customer, product: str, conversion_prob: float) -> float:
    product_value = {"installment": 5200, "coupon": 2600, "travel": 5600}.get(product, 2800)
    spend_factor = 0.75 + min(customer.monthly_spend / 12000, 0.9)
    return conversion_prob * product_value * spend_factor


def explain_customer(customer: Customer, product: str) -> list[str]:
    reasons: list[str] = []
    if customer.app_active_days >= 18:
        reasons.append("App活跃度高")
    if customer.monthly_spend >= 7000:
        reasons.append("近月消费金额高")
    if product == "installment" and customer.credit_limit_usage >= 0.55:
        reasons.append("额度使用率较高")
    if product == "coupon" and customer.coupon_response >= 0.42:
        reasons.append("历史权益响应较好")
    if product == "travel" and customer.travel_txn >= 2:
        reasons.append("商旅交易活跃")
    if not reasons:
        reasons.append("综合响应概率高")
    return reasons[:3]
