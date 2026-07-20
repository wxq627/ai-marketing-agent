"""
content_engine\templates.py
功能描述: 文案模板定义，支持Push/SMS/微信等渠道的模板
"""

from typing import Dict, List, Optional


class ContentTemplate:
    def __init__(self, template_id: str, channel: str, template_type: str,
                 subject: str, body: str, personalization_fields: Optional[List[str]] = None):
        self.template_id = template_id
        self.channel = channel
        self.template_type = template_type
        self.subject = subject
        self.body = body
        self.personalization_fields = personalization_fields or []

    def render(self, **kwargs) -> Dict[str, str]:
        try:
            rendered_subject = self.subject.format(**kwargs)
            rendered_body = self.body.format(**kwargs)
            return {
                "subject": rendered_subject,
                "body": rendered_body
            }
        except KeyError as e:
            return {
                "subject": self.subject,
                "body": self.body,
                "error": f"缺少字段: {e}"
            }


INSTALLMENT_TEMPLATES = {
    "push": {
        "A": ContentTemplate(
            template_id="PUSH_INSTALLMENT_A",
            channel="app_push",
            template_type="installment",
            subject="账单分期优惠",
            body="【账单压力缓释与分期费率优惠】\n{customer_name}您好！{benefit_name}已为您准备好！\n活动规则以页面展示为准。",
            personalization_fields=["customer_name", "benefit_name"]
        ),
        "B": ContentTemplate(
            template_id="PUSH_INSTALLMENT_B",
            channel="app_push",
            template_type="installment",
            subject="分期手续费折扣",
            body="【分期费率低至0.45%】\n{customer_name}，账单分期手续费限时8折！\n立即办理享受优惠。",
            personalization_fields=["customer_name"]
        )
    },
    "sms": {
        "A": ContentTemplate(
            template_id="SMS_INSTALLMENT_A",
            channel="sms",
            template_type="installment",
            subject="",
            body="【XX银行】{customer_name}您好！您本期账单应还{bill_amount}元，办理账单分期享手续费优惠。回复TD退订。",
            personalization_fields=["customer_name", "bill_amount"]
        ),
        "B": ContentTemplate(
            template_id="SMS_INSTALLMENT_B",
            channel="sms",
            template_type="installment",
            subject="",
            body="【XX银行】账单分期手续费低至0.45%/期，{customer_name}专属优惠已送达。回复TD退订。",
            personalization_fields=["customer_name"]
        )
    },
    "wechat": {
        "A": ContentTemplate(
            template_id="WECHAT_INSTALLMENT_A",
            channel="wechat",
            template_type="installment",
            subject="账单分期提醒",
            body="您好{customer_name}，您的账单分期专属优惠已到账，点击查看详情。",
            personalization_fields=["customer_name"]
        ),
        "B": ContentTemplate(
            template_id="WECHAT_INSTALLMENT_B",
            channel="wechat",
            template_type="installment",
            subject="分期费率优惠",
            body="{customer_name}，账单分期手续费限时8折，立即办理享优惠！",
            personalization_fields=["customer_name"]
        )
    }
}


BENEFIT_TEMPLATES = {
    "push": {
        "A": ContentTemplate(
            template_id="PUSH_BENEFIT_A",
            channel="app_push",
            template_type="benefit",
            subject="专属权益领取",
            body="【{benefit_name}】\n{customer_name}您好！您有一项专属权益待领取。\n{benefit_description}",
            personalization_fields=["customer_name", "benefit_name", "benefit_description"]
        ),
        "B": ContentTemplate(
            template_id="PUSH_BENEFIT_B",
            channel="app_push",
            template_type="benefit",
            subject="新权益到账",
            body="【惊喜】{customer_name}，您的{benefit_name}已为您准备好！\n点击立即使用。",
            personalization_fields=["customer_name", "benefit_name"]
        )
    },
    "sms": {
        "A": ContentTemplate(
            template_id="SMS_BENEFIT_A",
            channel="sms",
            template_type="benefit",
            subject="",
            body="【XX银行】{customer_name}您好！{benefit_name}已到账，请及时领取。回复TD退订。",
            personalization_fields=["customer_name", "benefit_name"]
        )
    },
    "wechat": {
        "A": ContentTemplate(
            template_id="WECHAT_BENEFIT_A",
            channel="wechat",
            template_type="benefit",
            subject="权益提醒",
            body="{customer_name}，您的{benefit_name}已发放，请点击领取。",
            personalization_fields=["customer_name", "benefit_name"]
        )
    }
}


ACTIVITY_TEMPLATES = {
    "push": {
        "A": ContentTemplate(
            template_id="PUSH_ACTIVITY_A",
            channel="app_push",
            template_type="activity",
            subject="限时活动",
            body="【{activity_name}】\n{customer_name}您好！活动期间{activity_description}。\n有效期至{valid_period}。",
            personalization_fields=["customer_name", "activity_name", "activity_description", "valid_period"]
        )
    }
}


def get_template(channel: str, template_type: str, variant: str = "A") -> Optional[ContentTemplate]:
    template_groups = {
        "installment": INSTALLMENT_TEMPLATES,
        "benefit": BENEFIT_TEMPLATES,
        "activity": ACTIVITY_TEMPLATES
    }
    
    group = template_groups.get(template_type)
    if not group:
        return None
    
    channel_templates = group.get(channel)
    if not channel_templates:
        return None
    
    return channel_templates.get(variant)