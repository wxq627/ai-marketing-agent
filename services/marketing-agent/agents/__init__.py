"""
文件路径: d:\库文件\桌面\Summer_Intern\ai_marketing_agent_local\marketing_agent\agents\__init__.py
功能描述: Agent模块导出
"""

from .base_agent import (
    BaseAgent,
    AgentType,
    IntentResult,
    AgentResponse,
)
from .adapters import (
    ProfileMockAdapter,
    KnowledgeMockAdapter,
    ProfileAPIAdapter,
    KnowledgeAPIAdapter,
    IntentAPIAdapter,
    FrequencyAPIAdapter,
    profile_adapter,
    knowledge_adapter,
    intent_adapter,
    frequency_adapter,
)
from .query_agent import QueryAgent, query_agent
from .service_agent import ServiceAgent, service_agent
from .marketing_agent import MarketingAgent, marketing_agent

__all__ = [
    "BaseAgent",
    "AgentType",
    "IntentResult",
    "AgentResponse",
    "ProfileMockAdapter",
    "KnowledgeMockAdapter",
    "ProfileAPIAdapter",
    "KnowledgeAPIAdapter",
    "IntentAPIAdapter",
    "FrequencyAPIAdapter",
    "profile_adapter",
    "knowledge_adapter",
    "intent_adapter",
    "frequency_adapter",
    "QueryAgent",
    "query_agent",
    "ServiceAgent",
    "service_agent",
    "MarketingAgent",
    "marketing_agent",
]