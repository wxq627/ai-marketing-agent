from __future__ import annotations

from .models import CampaignRequest, ParsedIntent, SegmentRecommendation


PRODUCT_NAMES = {
    "installment": "信用卡分期",
    "coupon": "消费券包",
    "travel": "商旅权益",
}


def generate_content(
    request: CampaignRequest,
    intent: ParsedIntent,
    segments: list[SegmentRecommendation],
) -> dict[str, str]:
    product_name = PRODUCT_NAMES.get(intent.product, "信用卡活动")
    segment_name = segments[0].name if segments else "目标客群"
    value_point = {
        "installment": "期数和手续费优惠已为您智能匹配",
        "coupon": "餐饮、商超与线上支付权益已为您优先匹配",
        "travel": "机场、酒店和里程权益已为您组合推荐",
    }.get(intent.product, "专属权益已为您匹配")

    return {
        "app_popup": f"{product_name}专属方案：{value_point}。进入 App 查看详情，领取后可按页面规则使用。",
<<<<<<< HEAD
        "sms": f"【招商银行】您有一份{product_name}活动提醒，{value_point}。请登录招商银行App查看，退订回复TD。",
=======
        "sms": f"【XX银行】您有一份{product_name}活动提醒，{value_point}。请登录XX银行App查看，退订回复TD。",
>>>>>>> origin/feature/project1-knowledge-agent
        "wechat": f"建议对{segment_name}采用权益价值解释 + 使用路径引导，重点说明适用条件、成本和有效期。",
        "explain": f"文案依据：{intent.objective}；重点客群：{segment_name}；合规处理：避免收益承诺、夸大优惠和过度打扰。",
    }
