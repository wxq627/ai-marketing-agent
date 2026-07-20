"""
common\errors.py
功能描述: 全局异常定义模块，统一错误类型和HTTP状态码映射
"""

from fastapi import HTTPException, status


class MarketingAgentError(Exception):
    """营销Agent基础异常"""
    code: int = 500
    message: str = "营销Agent内部错误"

    def __init__(self, message: str = None):
        super().__init__(message or self.message)
        self.message = message or self.message


class StrategyError(MarketingAgentError):
    """策略相关异常"""
    code: int = 400
    message: str = "策略解析错误"


class StrategyNotFoundError(StrategyError):
    code: int = 404
    message: str = "策略包未找到"


class StrategyValidationError(StrategyError):
    code: int = 400
    message: str = "策略包校验失败"


class ComplianceError(MarketingAgentError):
    """合规相关异常"""
    code: int = 400
    message: str = "合规校验失败"


class SensitiveWordError(ComplianceError):
    message: str = "文案包含敏感词"


class FrequencyLimitError(ComplianceError):
    message: str = "触达频率超限"


class AgeRestrictionError(ComplianceError):
    message: str = "用户年龄不符合要求"


class AgentError(MarketingAgentError):
    """Agent相关异常"""
    code: int = 500
    message: str = "Agent执行错误"


class IntentRecognitionError(AgentError):
    message: str = "意图识别失败"


class ContentGenerationError(AgentError):
    message: str = "内容生成失败"


class ChannelError(MarketingAgentError):
    """渠道相关异常"""
    code: int = 500
    message: str = "渠道分发错误"


class ChannelNotFoundError(ChannelError):
    code: int = 404
    message: str = "渠道不存在"


class ChannelDeliveryError(ChannelError):
    message: str = "渠道投递失败"


class FeedbackError(MarketingAgentError):
    """反馈相关异常"""
    code: int = 500
    message: str = "反馈采集错误"


class DatabaseError(MarketingAgentError):
    """数据库相关异常"""
    code: int = 503
    message: str = "数据库服务不可用"


class RedisError(DatabaseError):
    message: str = "Redis服务不可用"


class PostgreSQLConnectionError(DatabaseError):
    message: str = "PostgreSQL连接失败"


class LLMError(MarketingAgentError):
    """LLM相关异常"""
    code: int = 503
    message: str = "LLM服务不可用"


class LLMConnectionError(LLMError):
    message: str = "LLM连接失败"


class LLMGenerationError(LLMError):
    message: str = "LLM生成失败"


class SessionError(MarketingAgentError):
    """会话相关异常"""
    code: int = 400
    message: str = "会话错误"


class SessionNotFoundError(SessionError):
    code: int = 404
    message: str = "会话不存在"


class SessionExpiredError(SessionError):
    code: int = 410
    message: str = "会话已过期"


ERROR_CODE_MAP = {
    MarketingAgentError: status.HTTP_500_INTERNAL_SERVER_ERROR,
    StrategyError: status.HTTP_400_BAD_REQUEST,
    StrategyNotFoundError: status.HTTP_404_NOT_FOUND,
    StrategyValidationError: status.HTTP_400_BAD_REQUEST,
    ComplianceError: status.HTTP_400_BAD_REQUEST,
    SensitiveWordError: status.HTTP_400_BAD_REQUEST,
    FrequencyLimitError: status.HTTP_400_BAD_REQUEST,
    AgeRestrictionError: status.HTTP_400_BAD_REQUEST,
    AgentError: status.HTTP_500_INTERNAL_SERVER_ERROR,
    IntentRecognitionError: status.HTTP_500_INTERNAL_SERVER_ERROR,
    ContentGenerationError: status.HTTP_500_INTERNAL_SERVER_ERROR,
    ChannelError: status.HTTP_500_INTERNAL_SERVER_ERROR,
    ChannelNotFoundError: status.HTTP_404_NOT_FOUND,
    ChannelDeliveryError: status.HTTP_500_INTERNAL_SERVER_ERROR,
    FeedbackError: status.HTTP_500_INTERNAL_SERVER_ERROR,
    DatabaseError: status.HTTP_503_SERVICE_UNAVAILABLE,
    RedisError: status.HTTP_503_SERVICE_UNAVAILABLE,
    PostgreSQLConnectionError: status.HTTP_503_SERVICE_UNAVAILABLE,
    LLMError: status.HTTP_503_SERVICE_UNAVAILABLE,
    LLMConnectionError: status.HTTP_503_SERVICE_UNAVAILABLE,
    LLMGenerationError: status.HTTP_503_SERVICE_UNAVAILABLE,
    SessionError: status.HTTP_400_BAD_REQUEST,
    SessionNotFoundError: status.HTTP_404_NOT_FOUND,
    SessionExpiredError: status.HTTP_410_GONE,
}


def exception_to_http(exception: Exception) -> HTTPException:
    """将自定义异常转换为HTTP异常"""
    for error_type, status_code in ERROR_CODE_MAP.items():
        if isinstance(exception, error_type):
            return HTTPException(status_code=status_code, detail=str(exception))
    return HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(exception))