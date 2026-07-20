"""
common\llm_client.py
功能描述: LLM客户端封装，支持OpenAI和Ollama两种模式，提供mock fallback
"""

from typing import Optional, Dict, Any, List
from langchain_openai import ChatOpenAI
from langchain_community.chat_models import ChatOllama
from langchain_core.messages import BaseMessage, HumanMessage, SystemMessage
from langchain_core.outputs import ChatResult
from .config import llm_config, ollama_config
from .logger import logger
from .errors import LLMConnectionError, LLMGenerationError


class MockLLM:
    def __init__(self):
        self._responses = {
            "分期": "根据您的账单情况，建议选择12期分期，手续费率低至0.45%，每月还款约1652元。",
            "权益": "您的白金卡享有机场贵宾厅全年60次、接送机12次/年、延误险2000元等权益。",
            "账单": "您本期账单应还金额为￥3,850.00，账单日为每月5日。",
            "利率": "当前信用卡分期利率为0.45%/月，具体以系统显示为准。",
            "投诉": "非常抱歉给您带来不便，我们会尽快处理您的问题，请提供更多详细信息。",
            "办理": "好的，我可以帮您办理分期业务，请确认您要分期的金额和期数。",
        }

    def generate(self, messages: List[BaseMessage]) -> str:
        user_content = ""
        for msg in messages:
            if isinstance(msg, HumanMessage):
                user_content = msg.content
                break

        for keyword, response in self._responses.items():
            if keyword in user_content:
                logger.info(f"Mock LLM匹配关键词: {keyword}")
                return response

        return "感谢您的咨询，我会尽快为您解答。"


class LLMClient:
    _instance: Optional["LLMClient"] = None
    _llm = None
    _use_mock: bool = False

    def __new__(cls, *args, **kwargs):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance

    def __init__(self):
        if self._llm is None:
            self._init_llm()

    def _init_llm(self):
        try:
            provider = llm_config.LLM_PROVIDER.lower()

            if provider == "ollama":
                self._llm = ChatOllama(
                    model=ollama_config.OLLAMA_MODEL,
                    base_url=ollama_config.OLLAMA_HOST,
                    temperature=llm_config.LLM_TEMPERATURE,
                    max_tokens=llm_config.LLM_MAX_TOKENS,
                )
                logger.info(f"Ollama LLM客户端初始化成功: {ollama_config.OLLAMA_MODEL}")

            elif provider == "openai" and llm_config.LLM_API_KEY:
                self._llm = ChatOpenAI(
                    model=llm_config.LLM_MODEL,
                    api_key=llm_config.LLM_API_KEY,
                    base_url=llm_config.LLM_API_BASE_URL,
                    temperature=llm_config.LLM_TEMPERATURE,
                    max_tokens=llm_config.LLM_MAX_TOKENS,
                )
                logger.info(f"OpenAI LLM客户端初始化成功: {llm_config.LLM_MODEL}")

            else:
                logger.warning("未配置有效的LLM提供者，使用Mock模式")
                self._llm = MockLLM()
                self._use_mock = True

        except Exception as e:
            logger.warning(f"LLM初始化失败，使用Mock模式: {str(e)}")
            self._llm = MockLLM()
            self._use_mock = True

    @property
    def llm(self):
        if self._llm is None:
            self._init_llm()
        return self._llm

    @property
    def use_mock(self) -> bool:
        return self._use_mock

    def chat(self, messages: List[BaseMessage]) -> str:
        try:
            if self._use_mock:
                return self._llm.generate(messages)

            response = self._llm.invoke(messages)
            if isinstance(response, ChatResult):
                return response.generations[0].text if response.generations else ""
            return response.content

        except Exception as e:
            logger.error(f"LLM调用失败: {str(e)}")
            if self._use_mock:
                raise LLMGenerationError(f"LLM生成失败: {str(e)}")

            logger.warning("LLM调用失败，切换到Mock模式")
            mock_llm = MockLLM()
            return mock_llm.generate(messages)

    def generate_text(self, prompt: str, system_prompt: Optional[str] = None) -> str:
        messages = []
        if system_prompt:
            messages.append(SystemMessage(content=system_prompt))
        messages.append(HumanMessage(content=prompt))
        return self.chat(messages)

    def generate_with_context(
        self,
        user_query: str,
        context: Optional[str] = None,
        system_prompt: Optional[str] = None,
    ) -> str:
        prompt = user_query
        if context:
            prompt = f"参考信息：\n{context}\n\n用户问题：\n{user_query}"

        messages = []
        if system_prompt:
            messages.append(SystemMessage(content=system_prompt))
        messages.append(HumanMessage(content=prompt))
        return self.chat(messages)

    def summarize(self, text: str, max_length: int = 500) -> str:
        system_prompt = f"请对以下文本进行总结，控制在{max_length}字以内："
        return self.generate_text(text, system_prompt)


llm_client = LLMClient()