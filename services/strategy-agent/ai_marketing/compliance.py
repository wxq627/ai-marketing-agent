from __future__ import annotations

from .models import CampaignRequest, ComplianceCheck, CustomerScore


def run_compliance_checks(request: CampaignRequest, scored: list[CustomerScore], content: dict[str, str]) -> list[ComplianceCheck]:
    risky_terms = ["稳赚", "保证", "无条件", "最高收益"]
    joined_content = " ".join(content.values())
    found_terms = [term for term in risky_terms if term in joined_content]
    avg_risk = sum(row.risk_penalty for row in scored) / len(scored) if scored else 0
    max_contact = {1: "7天1次", 2: "7天2次", 3: "7天3次", 4: "3天2次"}.get(request.frequency_level, "7天2次")

    return [
        ComplianceCheck("营销授权", "通过", "已过滤未授权客户"),
        ComplianceCheck("频控策略", "通过", f"当前频控约束：{max_contact}"),
        ComplianceCheck("投诉风险", "通过" if avg_risk <= 0.12 else "需复核", f"入选客群平均投诉风险 {avg_risk * 100:.3f}%"),
        ComplianceCheck("内容合规", "通过" if not found_terms else "拦截", "未发现高风险承诺词" if not found_terms else f"命中：{','.join(found_terms)}"),
    ]
