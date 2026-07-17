"""
全局配置管理，基于 pydantic-settings。
统一读取 .env 环境变量，避免硬编码。
"""

from pydantic import BaseModel, Field
from pydantic_settings import BaseSettings, SettingsConfigDict
from typing import Optional


class RedisConfig(BaseModel):
    """Redis 配置"""
    url: str = Field(default="redis://localhost:6379/0", description="Redis 连接 URL")
    max_connections: int = Field(default=10, description="最大连接数")


class CeleryConfig(BaseModel):
    """Celery 配置"""
    broker_url: str = Field(default="redis://localhost:6379/1", description="Broker URL")
    result_backend: str = Field(default="redis://localhost:6379/1", description="结果后端")


class LLMConfig(BaseModel):
    """大模型配置"""
    provider: str = Field(default="openai", description="LLM 提供商: openai / azure / qwen")
    api_key: str = Field(..., description="LLM API Key")
    base_url: Optional[str] = Field(default=None, description="自定义 API Base URL")
    model_name: str = Field(default="gpt-4o-mini", description="默认模型名称")
    temperature: float = Field(default=0.7, description="生成温度")


class ComplianceConfig(BaseModel):
    """合规配置"""
    blocked_words: list[str] = Field(
        default=["稳赚", "保证", "无条件通过"],
        description="全局禁用词列表"
    )
    must_not_claim: list[str] = Field(
        default=["承诺一定省钱", "承诺审批通过"],
        description="禁止承诺内容"
    )


class Settings(BaseSettings):
    """全局应用配置"""

    # 应用基础
    app_name: str = "Marketing Agent"
    app_env: str = Field(default="development", description="运行环境: development / staging / production")
    debug: bool = Field(default=True, description="调试模式")

    # API 配置
    api_prefix: str = "/api/marketing"
    cors_origins: list[str] = Field(
        default=["http://localhost:3000", "http://localhost:8000"],
        description="CORS 允许的源"
    )

    # 子服务配置
    redis: RedisConfig = Field(default_factory=RedisConfig)
    celery: CeleryConfig = Field(default_factory=CeleryConfig)
    llm: LLMConfig = Field(default_factory=LLMConfig)
    compliance: ComplianceConfig = Field(default_factory=ComplianceConfig)

    # 上游 Strategy Agent 地址
    strategy_agent_base_url: Optional[str] = Field(
        default="http://localhost:8001",
        description="Strategy Agent 基础 URL"
    )

    # 下游 Knowledge Agent 地址（用于反馈回流）
    knowledge_agent_base_url: Optional[str] = Field(
        default="http://localhost:8002",
        description="Knowledge Agent 基础 URL"
    )

    # 配置加载方式
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        env_nested_delimiter="__",  # 支持嵌套配置: REDIS__URL
        extra="ignore"
    )


# 全局单例
settings = Settings()