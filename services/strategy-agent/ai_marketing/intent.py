from __future__ import annotations

from .models import CampaignRequest, ParsedIntent


PRODUCT_KEYWORDS = {
    "installment": ["分期", "账单", "费率", "还款"],
    "coupon": ["消费券", "券", "餐饮", "商超", "满减"],
    "travel": ["商旅", "出行", "暑期", "夏季", "酒店", "机票", "贵宾厅", "里程"],
}


def parse_intent(request: CampaignRequest) -> ParsedIntent:
    text = request.goal.lower()
    product = request.product
    if not request.product_locked:
        for candidate, keywords in PRODUCT_KEYWORDS.items():
            if any(keyword in text for keyword in keywords):
                product = candidate
                break

    signals: list[str] = []
    if any(word in text for word in ["餐饮", "商超", "消费券", "线上支付"]):
        signals.append("高频消费/权益敏感")
    if any(word in text for word in ["商旅", "出行", "暑期", "夏季", "酒店", "机票"]):
        signals.append("商旅出行偏好")
    if any(word in text for word in ["分期", "资金", "账单", "还款"]):
        signals.append("分期接受度/资金周转")
    if any(word in text for word in ["沉睡", "召回", "低活"]):
        signals.append("沉睡唤醒")
    if not signals:
        signals.append("综合活跃与响应倾向")

    constraints = ["营销授权校验", "频控校验", "投诉风险过滤", "内容合规校验"]
    if "预算" in text or request.budget_wan:
        constraints.append(f"预算上限 {request.budget_wan} 万")
    if "合规" in text or "风险" in text:
        constraints.append("高风险策略需人工确认")

    objective = "提升转化与ROI"
    if "召回" in text or "唤醒" in text:
        objective = "提升沉睡客户召回"
    elif "分期" in text:
        objective = "提升分期活动转化"
    elif "权益" in text or "券" in text:
        objective = "提升权益领取与核销"

    return ParsedIntent(
        product=product,
        objective=objective,
        target_signals=signals,
        constraints=constraints,
        risk_level=request.risk_level,
        frequency_level=request.frequency_level,
    )
