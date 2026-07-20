"""
agents\intent_classifier.py
功能描述: 层级化意图识别器 - 第一层大类分类（加权关键词 + 上下文记忆）
输出: (category, score, confidence)
"""

from typing import Optional, Dict, Any, List, Tuple
from common import logger


class IntentClassifier:
    """层级化意图识别器 - 第一层大类分类"""

    # 大类关键词（加权）
    # 权重说明: 3=核心词, 2=重要词, 1=辅助词
    CATEGORY_KEYWORDS: Dict[str, Dict[str, int]] = {
        "query": {
            # 账单类
            "账单": 3, "应还": 2, "还款": 2, "账单日": 3, "还款日": 3, "欠款": 3,
            # 额度类
            "额度": 2, "可用": 2, "授信": 2, "信用额度": 3,
            # 利息类
            "利息": 3, "利率": 3, "费率": 2, "手续费": 2,
            # 积分类
            "积分": 3, "积分兑换": 3,
            # 账户类
            "账户": 2, "卡号": 3, "卡片": 2, "开户行": 3,
            # 查询动词
            "查询": 2, "查一下": 2, "多少": 1, "余额": 3,
        },
        "service": {
            # 业务办理类
            "办理": 3, "开通": 3, "激活": 3, "注销": 3, "申请": 2,
            # 投诉类
            "投诉": 3, "问题": 2, "错误": 2, "异常": 2, "失败": 2,
            # 咨询类
            "咨询": 2, "如何": 1, "怎么": 1, "怎么样": 1,
            # 帮助类
            "帮助": 2, "指导": 2, "教程": 2, "步骤": 2,
        },
        "marketing": {
            # 优惠活动类
            "优惠": 3, "活动": 3, "红包": 3, "折扣": 3, "券": 3, "省钱": 3,
            # 权益类
            "权益": 2, "福利": 3,
            # 推荐对比类
            "推荐": 2, "对比": 2, "哪个好": 2, "选择": 1,
            # 需求类（低权重，避免与service冲突）
            "想要": 1, "想办": 1,
            # 价格类
            "多少钱": 2, "价格": 2, "费用": 1, "贵吗": 2,
        }
    }

    # 优先级（同分时）：查询 > 服务 > 营销
    CATEGORY_PRIORITY: List[str] = ["query", "service", "marketing"]

    # 话题切换词（出现时强制重新识别，不使用上下文）
    TOPIC_SWITCH_WORDS: List[str] = ["另外", "对了", "我想问", "换个话题", "话说", "顺便"]

    # 代词/短消息继承词
    PRONOUN_WORDS: List[str] = ["它", "这个", "那个", "继续", "嗯", "是的", "对", "好", "可以", "还有呢", "然后呢"]

    # 上下文使用的阈值
    SHORT_MESSAGE_THRESHOLD: int = 4  # 短消息字数阈值
    LOW_SCORE_THRESHOLD: float = 10.0  # 低分阈值
    SCORE_DIFF_THRESHOLD: float = 5.0  # 得分差距阈值（小于此值视为接近）
    CONTEXT_INHERIT_FACTOR: float = 0.5  # 上下文继承分数因子

    def classify(self, message: str, context: Optional[Dict[str, Any]] = None) -> Tuple[str, float, str]:
        """
        第一层大类分类

        Args:
            message: 用户消息
            context: 上下文信息，包含:
                - last_agent_type: 上一轮Agent类型
                - last_intent_type: 上一轮细类意图
                - last_intent_score: 上一轮意图分数
                - recent_messages: 最近几轮对话

        Returns:
            (category, score, confidence)
            - category: "query" / "service" / "marketing"
            - score: 得分
            - confidence: "high" / "medium" / "low"
        """
        # 1. 检测话题切换词 - 强制重新识别
        has_topic_switch = any(word in message for word in self.TOPIC_SWITCH_WORDS)

        # 2. 计算各大类得分
        scores: Dict[str, float] = {}
        for category, keywords in self.CATEGORY_KEYWORDS.items():
            score = sum(weight for kw, weight in keywords.items() if kw in message) * 10
            scores[category] = float(score)

        # 3. 上下文增强（仅在未检测到话题切换词时）
        context_used = False
        if context and not has_topic_switch:
            context_used, scores = self._apply_context(message, scores, context)

        # 4. 选择最高分大类
        sorted_scores = sorted(scores.items(), key=lambda x: x[1], reverse=True)
        top_category, top_score = sorted_scores[0]
        second_category, second_score = sorted_scores[1] if len(sorted_scores) > 1 else ("", 0.0)

        # 5. 置信度判断
        confidence = self._determine_confidence(top_score, top_score - second_score)

        # 6. 日志记录
        log_msg = (f"[意图分类] message='{message[:30]}', "
                   f"scores={scores}, "
                   f"top={top_category}({top_score}), "
                   f"confidence={confidence}")
        if context_used:
            log_msg += f", context_used=True(last={context.get('last_agent_type')})"
        logger.info(log_msg)

        return top_category, top_score, confidence

    def _apply_context(self, message: str, scores: Dict[str, float],
                       context: Dict[str, Any]) -> Tuple[bool, Dict[str, float]]:
        """
        应用上下文记忆增强

        Returns:
            (context_used, updated_scores)
        """
        last_agent = context.get("last_agent_type")
        last_intent_score = context.get("last_intent_score", 0)

        if not last_agent:
            return False, scores

        context_used = False
        message_len = len(message.strip())

        # 场景1: 短消息或含代词 - 直接继承上一轮意图
        is_short = message_len <= self.SHORT_MESSAGE_THRESHOLD and message_len > 0
        has_pronoun = any(word in message for word in self.PRONOUN_WORDS)

        if is_short or has_pronoun:
            # 继承上一轮Agent，给予上下文加分
            inherit_score = max(last_intent_score * self.CONTEXT_INHERIT_FACTOR, 15.0)
            scores[last_agent] = scores.get(last_agent, 0) + inherit_score
            context_used = True
            logger.info(f"[上下文] 短消息/代词继承: last_agent={last_agent}, +{inherit_score}")

        # 场景2: 最高分低于阈值 - 参考上一轮
        elif max(scores.values()) < self.LOW_SCORE_THRESHOLD and last_intent_score > 0:
            inherit_score = last_intent_score * self.CONTEXT_INHERIT_FACTOR
            scores[last_agent] = scores.get(last_agent, 0) + inherit_score
            context_used = True
            logger.info(f"[上下文] 低分回退继承: last_agent={last_agent}, +{inherit_score}")

        # 场景3: 得分接近 - 优先上一轮Agent
        else:
            sorted_scores = sorted(scores.items(), key=lambda x: x[1], reverse=True)
            if len(sorted_scores) >= 2:
                top_cat, top_score = sorted_scores[0]
                second_cat, second_score = sorted_scores[1]
                # 如果前两名差距很小，且上一轮Agent在其中
                if (top_score - second_score) <= self.SCORE_DIFF_THRESHOLD \
                        and last_agent in [top_cat, second_cat] \
                        and last_intent_score > 0:
                    # 给上一轮Agent额外加分
                    bonus = 10.0
                    scores[last_agent] = scores.get(last_agent, 0) + bonus
                    context_used = True
                    logger.info(f"[上下文] 冲突消解加分: last_agent={last_agent}, +{bonus}")

        return context_used, scores

    def _determine_confidence(self, top_score: float, score_diff: float) -> str:
        """根据得分和分差判断置信度"""
        if top_score >= 30 and score_diff >= 15:
            return "high"
        elif top_score >= 15 and score_diff >= 5:
            return "medium"
        else:
            return "low"


# 全局单例
intent_classifier = IntentClassifier()
