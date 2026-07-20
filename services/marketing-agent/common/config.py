"""
common\config.py
功能描述: 全局配置管理模块，使用pydantic-settings加载环境变量
"""

from pydantic_settings import BaseSettings, SettingsConfigDict
from typing import Optional
from pathlib import Path


class AppConfig(BaseSettings):
    APP_ENV: str = "development"
    APP_HOST: str = "0.0.0.0"
    APP_PORT: int = 8080
    APP_DEBUG: bool = False
    API_PREFIX: str = "/api/v3"

    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

class LogConfig(BaseSettings):
    LOG_LEVEL: str = "INFO"
    LOG_FORMAT: str = "json"
    LOG_FILE_PATH: str = "./logs/app.log"

    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

class RedisConfig(BaseSettings):
    REDIS_HOST: str = "localhost"
    REDIS_PORT: int = 6379
    REDIS_DB: int = 0
    REDIS_PASSWORD: Optional[str] = None
    REDIS_TIMEOUT: int = 5

    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

class PostgresConfig(BaseSettings):
    POSTGRES_HOST: str = "localhost"
    POSTGRES_PORT: int = 5432
    POSTGRES_USER: str = "postgres"
    POSTGRES_PASSWORD: str = "postgres"
    POSTGRES_DB: str = "marketing_agent"
    POSTGRES_TIMEOUT: int = 10

    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    @property
    def dsn(self) -> str:
        return (
            f"postgresql://{self.POSTGRES_USER}:{self.POSTGRES_PASSWORD}"
            f"@{self.POSTGRES_HOST}:{self.POSTGRES_PORT}/{self.POSTGRES_DB}"
        )


class LLMConfig(BaseSettings):
    LLM_PROVIDER: str = "openai"
    LLM_API_KEY: Optional[str] = None
    LLM_API_BASE_URL: str = "https://api.openai.com/v1"
    LLM_MODEL: str = "gpt-4o-mini"
    LLM_MAX_TOKENS: int = 2048
    LLM_TEMPERATURE: float = 0.7

    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

class OllamaConfig(BaseSettings):
    OLLAMA_HOST: str = "http://localhost:11434"
    OLLAMA_MODEL: str = "qwen2.5:7b"

    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

class KnowledgeEngineConfig(BaseSettings):
    KE_API_BASE: str = "http://localhost:8000"
    KE_API_TIMEOUT: int = 10
    KE_CACHE_TTL: int = 300
    KE_FALLBACK_TO_MOCK: bool = True

    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

class StrategyAgentConfig(BaseSettings):
    """strategy_agent 服务对接配置"""
    SA_API_BASE: str = "http://localhost:8765"
    SA_API_TIMEOUT: int = 15
    SA_CACHE_TTL: int = 600
    SA_FALLBACK_TO_MOCK: bool = True

    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

class FeedbackConfig(BaseSettings):
    """反馈与回流配置"""
    KE_FEEDBACK_URL: str = "http://localhost:8000"
    KE_FEEDBACK_TIMEOUT: int = 10
    SA_FEEDBACK_URL: str = "http://localhost:8765"
    SA_FEEDBACK_TIMEOUT: int = 10

    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")


app_config = AppConfig()
log_config = LogConfig()
redis_config = RedisConfig()
postgres_config = PostgresConfig()
llm_config = LLMConfig()
ollama_config = OllamaConfig()
ke_config = KnowledgeEngineConfig()
sa_strategy_config = StrategyAgentConfig()
feedback_config = FeedbackConfig()