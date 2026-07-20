"""
content_engine\generator.py
功能描述: 文案内容生成器，支持A/B测试模拟和个性化字段注入
"""

import random
import uuid
from typing import Dict, Any, List, Optional
from datetime import datetime

from common import logger, ContentGenerationError, llm_client
from agents.adapters import profile_adapter
from agent_orchestrator.strategy_parser import strategy_loader, compliance_checker
from .templates import get_template, ContentTemplate


class GeneratedContent:
    def __init__(self, content_id: str, channel: str, variant: str,
                 subject: str, body: str, personalization_fields: Dict[str, Any],
                 template_id: str, trace_id: str):
        self.content_id = content_id
        self.channel = channel
        self.variant = variant
        self.subject = subject
        self.body = body
        self.personalization_fields = personalization_fields
        self.template_id = template_id
        self.trace_id = trace_id
        self.created_at = datetime.now()

    def to_dict(self) -> Dict[str, Any]:
        return {
            "content_id": self.content_id,
            "channel": self.channel,
            "variant": self.variant,
            "subject": self.subject,
            "body": self.body,
            "personalization_fields": self.personalization_fields,
            "template_id": self.template_id,
            "trace_id": self.trace_id,
            "created_at": self.created_at.isoformat()
        }


class ContentGenerator:
    def __init__(self):
        self._ab_test_enabled = True
        self._default_variant = "A"
        self._variant_weights = {"A": 0.5, "B": 0.5}

    def generate(self, oneid: str, channel: str, template_type: str = "installment",
                 trace_id: Optional[str] = None) -> GeneratedContent:
        content_id = str(uuid.uuid4())[:12]
        trace_id = trace_id or str(uuid.uuid4())

        variant = self._select_variant(channel, template_type)
        template = get_template(channel, template_type, variant)

        if not template:
            logger.warning(f"未找到模板: channel={channel}, type={template_type}, variant={variant}")
            return self._generate_fallback_content(oneid, channel, content_id, trace_id)

        personalization_data = self._collect_personalization_data(oneid)

        try:
            rendered = template.render(**personalization_data)
            
            if "error" in rendered:
                logger.warning(f"模板渲染失败: {rendered['error']}")
                return self._generate_fallback_content(oneid, channel, content_id, trace_id)

            content = GeneratedContent(
                content_id=content_id,
                channel=channel,
                variant=variant,
                subject=rendered["subject"],
                body=rendered["body"],
                personalization_fields=personalization_data,
                template_id=template.template_id,
                trace_id=trace_id
            )

            if not self._check_compliance(content.body):
                logger.warning(f"文案合规校验失败，使用备选方案")
                return self._generate_compliant_content(oneid, channel, content_id, trace_id)

            logger.info(f"文案生成成功: content_id={content_id}, channel={channel}, variant={variant}")
            return content

        except Exception as e:
            logger.error(f"文案生成失败: {e}")
            raise ContentGenerationError(f"文案生成失败: {e}")

    def generate_ab_variants(self, oneid: str, channel: str,
                             template_type: str = "installment") -> List[GeneratedContent]:
        results = []
        
        for variant in ["A", "B"]:
            try:
                content = self.generate(oneid, channel, template_type)
                results.append(content)
            except Exception as e:
                logger.error(f"生成变体{variant}失败: {e}")

        return results

    def _select_variant(self, channel: str, template_type: str) -> str:
        if not self._ab_test_enabled:
            return self._default_variant

        rand = random.random()
        cumulative = 0
        for variant, weight in self._variant_weights.items():
            cumulative += weight
            if rand <= cumulative:
                return variant

        return self._default_variant

    def _collect_personalization_data(self, oneid: str) -> Dict[str, Any]:
        data = {}

        profile = profile_adapter.get_profile(oneid)
        if profile:
            demographics = profile.get("demographics", {})
            billing = profile.get("billing", {})
            benefit = profile.get("benefit", {})

            data["customer_name"] = demographics.get("name", "客户")
            data["customer_city"] = demographics.get("city", "")
            data["customer_age"] = demographics.get("age", "")

            data["bill_amount"] = f"￥{billing.get('bill_amount', 0):,.2f}"
            data["bill_date"] = billing.get("bill_date", "")
            data["due_date"] = billing.get("due_date", "")

        strategy = strategy_loader.load_from_file()
        if strategy:
            if strategy.benefit_rule:
                data["benefit_name"] = strategy.benefit_rule.benefit_name
                data["benefit_type"] = strategy.benefit_rule.benefit_type

            if strategy.content_brief:
                data["core_message"] = strategy.content_brief.core_message
                data["tone"] = strategy.content_brief.tone

        return data

    def _check_compliance(self, content: str) -> bool:
        try:
            strategy = strategy_loader.load_from_file()
            return compliance_checker.check_sensitive_words(content, strategy)
        except Exception:
            return True

    def _generate_compliant_content(self, oneid: str, channel: str,
                                    content_id: str, trace_id: str) -> GeneratedContent:
        profile = profile_adapter.get_profile(oneid)
        name = profile.get("demographics", {}).get("name", "客户") if profile else "客户"

        fallback_body = f"您好{name}！我们为您准备了专属优惠活动，详情请登录APP查看。"
        
        return GeneratedContent(
            content_id=content_id,
            channel=channel,
            variant="compliant",
            subject="专属优惠",
            body=fallback_body,
            personalization_fields={"customer_name": name},
            template_id="FALLBACK_COMPLIANT",
            trace_id=trace_id
        )

    def _generate_fallback_content(self, oneid: str, channel: str,
                                   content_id: str, trace_id: str) -> GeneratedContent:
        profile = profile_adapter.get_profile(oneid)
        name = profile.get("demographics", {}).get("name", "客户") if profile else "客户"

        fallback_body = f"【账单分期优惠】\n{name}您好！账单分期手续费低至0.45%/期，活动规则以页面展示为准。"
        
        return GeneratedContent(
            content_id=content_id,
            channel=channel,
            variant="fallback",
            subject="账单分期优惠",
            body=fallback_body,
            personalization_fields={"customer_name": name},
            template_id="FALLBACK_DEFAULT",
            trace_id=trace_id
        )


content_generator = ContentGenerator()