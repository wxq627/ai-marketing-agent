"""
多渠道触达适配器。
采用 Adapter 模式抽象统一发送接口，MVP 阶段内置 Mock 实现，
保留对接真实推送/短信/微信网关的扩展点。
"""

import logging
from abc import ABC, abstractmethod
from typing import Dict, Any, Optional
from dataclasses import dataclass
from enum import Enum

logger = logging.getLogger(__name__)


class ChannelType(str, Enum):
    """支持的渠道类型枚举"""
    APP_PUSH = "app_push"
    SMS = "sms"
    WECHAT = "wechat"
    CALL = "call"


@dataclass
class SendResult:
    """发送结果标准化结构"""
    success: bool
    channel: str
    message_id: Optional[str] = None
    error_code: Optional[str] = None
    error_message: Optional[str] = None
    raw_response: Optional[Dict[str, Any]] = None


class BaseChannelAdapter(ABC):
    """渠道适配器基类"""

    @abstractmethod
    async def send(self, customer_id: str, content: str, metadata: Dict[str, Any]) -> SendResult:
        """
        发送消息。

        Args:
            customer_id: 客户唯一标识
            content: 消息内容
            metadata: 扩展元数据（如模板ID、签名等）

        Returns:
            SendResult 标准化结果
        """
        ...


class MockAppPushAdapter(BaseChannelAdapter):
    """App Push 渠道 - Mock 实现"""

    async def send(self, customer_id: str, content: str, metadata: Dict[str, Any]) -> SendResult:
        logger.info(f"[Mock] App Push 发送成功 | customer={customer_id} | content_len={len(content)}")
        return SendResult(
            success=True,
            channel=ChannelType.APP_PUSH.value,
            message_id=f"push_mock_{customer_id}",
            raw_response={"status": "delivered"},
        )


class MockSmsAdapter(BaseChannelAdapter):
    """短信渠道 - Mock 实现"""

    async def send(self, customer_id: str, content: str, metadata: Dict[str, Any]) -> SendResult:
        # 模拟短信长度限制校验
        if len(content) > 500:
            logger.warning(f"[Mock] 短信超长被截断 | customer={customer_id}")
            content = content[:497] + "..."

        logger.info(f"[Mock] SMS 发送成功 | customer={customer_id} | content_len={len(content)}")
        return SendResult(
            success=True,
            channel=ChannelType.SMS.value,
            message_id=f"sms_mock_{customer_id}",
            raw_response={"status": "submitted", "segments": 1},
        )


class MockWechatAdapter(BaseChannelAdapter):
    """微信渠道 - Mock 实现"""

    async def send(self, customer_id: str, content: str, metadata: Dict[str, Any]) -> SendResult:
        logger.info(f"[Mock] WeChat 发送成功 | customer={customer_id}")
        return SendResult(
            success=True,
            channel=ChannelType.WECHAT.value,
            message_id=f"wx_mock_{customer_id}",
            raw_response={"status": "sent"},
        )


class ChannelService:
    """
    渠道服务管理器。
    根据渠道类型路由到对应适配器，提供统一的发送入口。
    """

    def __init__(self):
        self._adapters: Dict[str, BaseChannelAdapter] = {
            ChannelType.APP_PUSH.value: MockAppPushAdapter(),
            ChannelType.SMS.value: MockSmsAdapter(),
            ChannelType.WECHAT.value: MockWechatAdapter(),
        }

    def register_adapter(self, channel: str, adapter: BaseChannelAdapter) -> None:
        """注册或替换渠道适配器（用于后续接入真实网关）"""
        self._adapters[channel] = adapter
        logger.info(f"渠道适配器已注册 | channel={channel} | adapter={type(adapter).__name__}")

    async def send(
        self,
        channel: str,
        customer_id: str,
        content: str,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> SendResult:
        """
        统一发送入口。

        Args:
            channel: 渠道类型字符串
            customer_id: 客户 ID
            content: 消息内容
            metadata: 扩展元数据

        Returns:
            SendResult

        Raises:
            ValueError: 不支持的渠道类型
        """
        adapter = self._adapters.get(channel)
        if not adapter:
            supported = list(self._adapters.keys())
            raise ValueError(f"不支持的渠道类型: {channel}，当前支持: {supported}")

        try:
            result = await adapter.send(customer_id, content, metadata or {})
            return result
        except Exception as e:
            logger.error(f"渠道发送异常 | channel={channel} | customer={customer_id} | error={e}")
            return SendResult(
                success=False,
                channel=channel,
                error_code="CHANNEL_ERROR",
                error_message=str(e),
            )


# 全局单例
channel_service = ChannelService()