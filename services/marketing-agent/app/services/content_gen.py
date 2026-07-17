"""
内容生成服务。
封装大模型调用，结合策略模板和客户画像生成个性化文案。
包含异常捕获与 Fallback 机制。
"""

import logging
from typing import Optional, Dict, Any
from langchain_openai import ChatOpenAI
from langchain_core.prompts import ChatPromptTemplate
from langchain_core.output_parsers import StrOutputParser
from langchain_core.exceptions import OutputParserException

from app.core.config import settings
from app.models.strategy import StrategyPackage, ContentBrief
from app.services.frequency import frequency_service

logger = logging.getLogger(__name__)


class ContentGenerationError(Exception):
    """内容生成异常基类"""
    pass


class ContentGenerator:
    """
    内容生成器。
    负责调用 LLM 生成个性化营销文案，内置 Fallback 机制。
    """

    def __init__(self):
        self.llm = ChatOpenAI(
            model=settings.llm.model_name,
            temperature=settings.llm.temperature,
            api_key=settings.llm.api_key,
            base_url=settings.llm.base_url,
        )
        self.output_parser = StrOutputParser()

    def _build_prompt(self, strategy: StrategyPackage, customer_profile: Dict[str, Any]) -> ChatPromptTemplate:
        """
        构建 Prompt 模板。
        将策略包中的 content_brief 与客户画像结合。
        """
        content: ContentBrief = strategy.content_brief
        compliance = strategy.compliance_guard

        # 构建个性化字段的渲染上下文
        personalization_context = self._render_personalization(content, customer_profile)

        # 系统提示词：注入合规要求和文案风格
        system_prompt = f"""你是一个专业的银行营销文案生成器。

请根据以下要求生成营销文案：

**核心信息**: {content.core_message}
**语气风格**: {content.tone}
**必须包含的披露信息**: {', '.join(content.required_disclosure)}
**禁用词**: {', '.join(compliance.blocked_words)}
**禁止承诺**: {', '.join(compliance.must_not_claim)}

**个性化字段**:
{personalization_context}

要求：
1. 文案必须专业、克制、合规，符合金融行业规范
2. 不得使用任何禁用词
3. 不得做出任何禁止的承诺
4. 文案长度控制在 200 字以内
5. 必须包含所有要求的披露信息
"""

        # 用户提示词模板
        user_prompt = """请为以下客户生成个性化营销文案：

客户姓名：{customer_name}
客户特征：{customer_features}

请直接输出文案内容，不要包含任何解释或前缀。"""

        return ChatPromptTemplate.from_messages([
            ("system", system_prompt),
            ("user", user_prompt),
        ])

    def _render_personalization(self, content: ContentBrief, customer_profile: Dict[str, Any]) -> str:
        """渲染个性化字段的值"""
        lines = []
        for field in content.personalization_fields:
            value = customer_profile.get(field, f"<缺失:{field}>")
            lines.append(f"- {field}: {value}")
        return "\n".join(lines)

    def _get_fallback_content(self, strategy: StrategyPackage, customer_profile: Dict[str, Any]) -> str:
        """
        Fallback 文案：当 LLM 调用失败时返回的默认文案。
        保持简洁合规，仅包含核心信息。
        """
        customer_name = customer_profile.get("customer_name", "尊敬的客户")
        content = strategy.content_brief
        benefit = strategy.benefit_rule.benefit_name

        return f"""{customer_name}，您好！

我们为您准备了专属优惠：{benefit}。

{content.core_message}。活动规则以页面展示为准。

如需退订，请回复 TD。"""

    async def generate(
        self,
        strategy: StrategyPackage,
        customer_profile: Dict[str, Any],
        use_fallback: bool = False,
    ) -> str:
        """
        生成个性化内容。

        Args:
            strategy: 策略包
            customer_profile: 客户画像字典
            use_fallback: 是否强制使用 Fallback 文案

        Returns:
            生成的文案字符串

        Raises:
            ContentGenerationError: 生成失败时抛出
        """
        if use_fallback:
            logger.warning(f"Fallback 模式生成文案 | campaign_id={strategy.campaign_id}")
            return self._get_fallback_content(strategy, customer_profile)

        try:
            prompt = self._build_prompt(strategy, customer_profile)
            chain = prompt | self.llm | self.output_parser

            customer_name = customer_profile.get("customer_name", "客户")
            customer_features = ", ".join(customer_profile.get("features", []))

            content = await chain.ainvoke({
                "customer_name": customer_name,
                "customer_features": customer_features,
            })

            # 后处理：确保包含合规披露信息
            content = self._postprocess_content(content, strategy.content_brief)

            logger.info(f"内容生成成功 | campaign_id={strategy.campaign_id} | customer={customer_name}")
            return content

        except OutputParserException as e:
            logger.error(f"LLM 输出解析失败 | campaign_id={strategy.campaign_id} | error={e}")
            return self._get_fallback_content(strategy, customer_profile)

        except Exception as e:
            logger.error(f"内容生成异常 | campaign_id={strategy.campaign_id} | error={e}")
            # 自动降级到 Fallback
            return self._get_fallback_content(strategy, customer_profile)

    def _postprocess_content(self, content: str, content_brief: ContentBrief) -> str:
        """后处理：确保文案包含必须的披露信息"""
        for disclosure in content_brief.required_disclosure:
            if disclosure not in content:
                content = content.rstrip() + f"\n\n{disclosure}"
        return content


# 全局单例
content_generator = ContentGenerator()