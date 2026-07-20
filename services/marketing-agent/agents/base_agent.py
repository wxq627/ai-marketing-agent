"""
agents\base_agent.py
功能描述: Agent基类定义，提供统一的Agent接口和基础功能
支持加权关键词意图识别和上下文记忆
"""

from abc import ABC, abstractmethod
from typing import Optional, Dict, Any, List, Union
from enum import Enum

from common import logger, AgentError, IntentRecognitionError
from .adapters import intent_adapter


class AgentType(str, Enum):
    QUERY = "query"
    SERVICE = "service"
    MARKETING = "marketing"


class IntentResult:
    def __init__(self, intent_type: str, score: float, confidence: str):
        self.intent_type = intent_type
        self.score = score
        self.confidence = confidence

    def to_dict(self) -> Dict[str, Any]:
        return {
            "intent_type": self.intent_type,
            "score": self.score,
            "confidence": self.confidence
        }


class AgentResponse:
    def __init__(self, content: str, agent_type: AgentType, 
                 intent: Optional[IntentResult] = None, 
                 metadata: Optional[Dict[str, Any]] = None):
        self.content = content
        self.agent_type = agent_type
        self.intent = intent
        self.metadata = metadata or {}

    def to_dict(self) -> Dict[str, Any]:
        return {
            "content": self.content,
            "agent_type": self.agent_type.value,
            "intent": self.intent.to_dict() if self.intent else None,
            "metadata": self.metadata
        }


class BaseAgent(ABC):
    def __init__(self, agent_type: AgentType, name: str):
        self.agent_type = agent_type
        self.name = name
        # 细类关键词：Dict[str, Dict[str, int]] 格式
        # key=意图类型, value={关键词: 权重}
        self._intent_keywords: Dict[str, Dict[str, int]] = {}

    @abstractmethod
    def process(self, message: str, oneid: Optional[str] = None, 
                context: Optional[Dict[str, Any]] = None) -> AgentResponse:
        pass

    def recognize_intent(self, message: str, context: Optional[Dict[str, Any]] = None) -> List[IntentResult]:
        """
        第二层细类识别（加权关键词 + 上下文增强）

        Args:
            message: 用户消息
            context: 上下文信息（包含last_intent_type等）
        """
        results = []
        for intent_type, keywords in self._intent_keywords.items():
            # 加权计分：匹配到的关键词权重之和 × 10
            score = sum(weight for kw, weight in keywords.items() if kw in message) * 10
            if score > 0:
                confidence = "high" if score >= 30 else ("medium" if score >= 15 else "low")
                results.append(IntentResult(intent_type, float(score), confidence))

        # 上下文增强：如果当前匹配分数低，参考上一轮细类
        if context and context.get("last_intent_type"):
            last_intent = context.get("last_intent_type")
            last_score = context.get("last_intent_score", 0)
            # 当前无匹配或最高分低于阈值，且上一轮意图属于当前Agent
            if last_intent in self._intent_keywords:
                current_top_score = results[0].score if results else 0
                if current_top_score < 15:
                    # 继承上一轮细类（降权）
                    inherit_score = last_score * 0.5
                    # 避免重复添加
                    existing_types = [r.intent_type for r in results]
                    if last_intent not in existing_types:
                        results.append(IntentResult(last_intent, inherit_score, "low"))
                        logger.info(f"[上下文] 细类继承: last_intent={last_intent}, +{inherit_score}")

        results.sort(key=lambda x: x.score, reverse=True)
        return results

    def get_intent_vector(self, oneid: str) -> Dict:
        return intent_adapter.get_intent(oneid)

    def _format_response(self, content: str, intent: Optional[IntentResult] = None,
                         metadata: Optional[Dict[str, Any]] = None) -> AgentResponse:
        return AgentResponse(content, self.agent_type, intent, metadata)

    def log_interaction(self, message: str, response: AgentResponse):
        logger.info(f"Agent交互: type={self.agent_type.value}, name={self.name}, "
                    f"message={message[:50]}, response={response.content[:50]}")