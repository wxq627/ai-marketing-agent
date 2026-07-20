"""
feedback_collector\summarizer.py
功能描述: 对话摘要生成器，使用LLM合成结构化对话摘要
"""

import uuid
from typing import List, Dict, Any, Optional
from datetime import datetime
from pathlib import Path
from .models import ConversationSummary
from common.logger import logger
from common.llm_client import llm_client
from common.errors import LLMError, FeedbackError


class ConversationSummarizer:
    _SUMMARY_PROMPT_TEMPLATE = """
你是一个智能营销对话摘要助手，请对以下对话进行分析并生成结构化摘要：

对话内容：
{conversation_text}

请按照以下格式输出：
1. 【对话摘要】：简要概括对话核心内容（50-100字）
2. 【用户意图】：识别用户主要意图（如：查询账单、办理分期、咨询权益、投诉问题等）
3. 【情绪标签】：判断用户情绪（正面/中性/负面）
4. 【核心关注点】：列出用户最关心的3个问题或需求
5. 【推荐行动】：基于对话内容给出下一步营销建议

请直接输出结果，不需要额外解释。
"""

    _MOCK_SUMMARIES = {
        "账单": {
            "summary": "用户查询本期账单金额，了解到应还金额为￥3,850.00，账单日为每月5日。",
            "intent": "查询账单",
            "sentiment": "中性",
            "top_concerns": ["账单金额", "还款日期", "最低还款额"],
            "recommended_action": "可推荐分期还款方案"
        },
        "分期": {
            "summary": "用户咨询分期业务，了解了12期分期方案，手续费率0.45%/月。",
            "intent": "办理分期",
            "sentiment": "正面",
            "top_concerns": ["分期费率", "还款金额", "办理流程"],
            "recommended_action": "推送分期办理链接"
        },
        "权益": {
            "summary": "用户查询信用卡权益，了解到白金卡享有机场贵宾厅、接送机等权益。",
            "intent": "查询权益",
            "sentiment": "中性",
            "top_concerns": ["权益内容", "使用次数", "有效期"],
            "recommended_action": "推送权益使用指南"
        },
        "投诉": {
            "summary": "用户投诉账单有误，对收费有疑问，情绪较为不满。",
            "intent": "投诉问题",
            "sentiment": "负面",
            "top_concerns": ["账单错误", "收费疑问", "处理进度"],
            "recommended_action": "升级人工客服处理"
        },
        "优惠": {
            "summary": "用户询问当前优惠活动，对分期优惠和积分兑换感兴趣。",
            "intent": "了解优惠",
            "sentiment": "正面",
            "top_concerns": ["优惠内容", "活动期限", "参与条件"],
            "recommended_action": "推送活动详情"
        }
    }

    def __init__(self):
        self._summaries: Dict[str, ConversationSummary] = {}
        self._summary_file_path = Path("./logs/conversation_summaries.json")

    def generate_summary(self, conversation_id: str, session_id: str, oneid: str,
                         messages: List[Dict[str, Any]]) -> ConversationSummary:
        conversation_text = self._format_conversation(messages)

        try:
            if llm_client.use_mock:
                summary_data = self._generate_mock_summary(conversation_text)
            else:
                summary_data = self._generate_llm_summary(conversation_text)

            summary = ConversationSummary(
                conversation_id=conversation_id,
                session_id=session_id,
                oneid=oneid,
                summary=summary_data["summary"],
                intent=summary_data.get("intent"),
                sentiment=summary_data.get("sentiment"),
                top_concerns=summary_data.get("top_concerns", []),
                recommended_action=summary_data.get("recommended_action"),
                generated_at=datetime.now()
            )

            self._summaries[conversation_id] = summary
            self._persist_summary(summary)

            logger.info(f"对话摘要生成成功: conversation_id={conversation_id}, sentiment={summary.sentiment}")
            return summary

        except LLMError as e:
            logger.error(f"LLM生成摘要失败: {str(e)}")
            raise FeedbackError(f"对话摘要生成失败: {str(e)}")
        except Exception as e:
            logger.error(f"对话摘要生成异常: {str(e)}")
            raise FeedbackError(f"对话摘要生成异常: {str(e)}")

    def _format_conversation(self, messages: List[Dict[str, Any]]) -> str:
        lines = []
        for msg in messages:
            role = msg.get("role", "unknown")
            content = msg.get("content", "")
            if role == "user":
                lines.append(f"用户: {content}")
            elif role == "assistant":
                lines.append(f"助手: {content}")
            else:
                lines.append(f"{role}: {content}")
        return "\n".join(lines)

    def _generate_llm_summary(self, conversation_text: str) -> Dict[str, Any]:
        prompt = self._SUMMARY_PROMPT_TEMPLATE.format(conversation_text=conversation_text)
        response = llm_client.generate_text(prompt)

        return self._parse_summary_response(response)

    def _generate_mock_summary(self, conversation_text: str) -> Dict[str, Any]:
        for keyword, summary_data in self._MOCK_SUMMARIES.items():
            if keyword in conversation_text:
                logger.info(f"Mock摘要匹配关键词: {keyword}")
                return summary_data.copy()

        return {
            "summary": "用户与助手进行了一般性对话，内容涉及账户相关咨询。",
            "intent": "咨询",
            "sentiment": "中性",
            "top_concerns": ["账户信息"],
            "recommended_action": "继续跟进用户需求"
        }

    def _parse_summary_response(self, response: str) -> Dict[str, Any]:
        result = {
            "summary": "",
            "intent": None,
            "sentiment": None,
            "top_concerns": [],
            "recommended_action": None
        }

        lines = response.strip().split("\n")
        for line in lines:
            line = line.strip()
            if line.startswith("【对话摘要】"):
                result["summary"] = line.replace("【对话摘要】", "").strip()
            elif line.startswith("【用户意图】"):
                result["intent"] = line.replace("【用户意图】", "").strip()
            elif line.startswith("【情绪标签】"):
                result["sentiment"] = line.replace("【情绪标签】", "").strip()
            elif line.startswith("【核心关注点】"):
                concerns_str = line.replace("【核心关注点】", "").strip()
                if concerns_str:
                    result["top_concerns"] = [c.strip() for c in concerns_str.split("、")]
            elif line.startswith("【推荐行动】"):
                result["recommended_action"] = line.replace("【推荐行动】", "").strip()

        if not result["summary"]:
            result["summary"] = response[:200]

        return result

    def _persist_summary(self, summary: ConversationSummary):
        self._summary_file_path.parent.mkdir(parents=True, exist_ok=True)

        summaries_data = []
        if self._summary_file_path.exists():
            try:
                import json
                with open(self._summary_file_path, 'r', encoding='utf-8') as f:
                    summaries_data = json.load(f)
            except Exception:
                summaries_data = []

        summaries_data.append(summary.model_dump())

        import json
        with open(self._summary_file_path, 'w', encoding='utf-8') as f:
            json.dump(summaries_data, f, ensure_ascii=False, indent=2, default=str)

    def get_summary(self, conversation_id: str) -> Optional[ConversationSummary]:
        return self._summaries.get(conversation_id)

    def get_summaries_by_oneid(self, oneid: str) -> List[ConversationSummary]:
        return [s for s in self._summaries.values() if s.oneid == oneid]

    def get_summary_stats(self) -> Dict[str, Any]:
        sentiment_counts = {"正面": 0, "中性": 0, "负面": 0}
        for summary in self._summaries.values():
            sentiment = summary.sentiment or "中性"
            sentiment_counts[sentiment] = sentiment_counts.get(sentiment, 0) + 1

        return {
            "total_summaries": len(self._summaries),
            "sentiment_distribution": sentiment_counts
        }


conversation_summarizer = ConversationSummarizer()