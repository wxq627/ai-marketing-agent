"""
文件路径: d:\库文件\桌面\Summer_Intern\c_marketing_agent\channel_gateway\__init__.py
功能描述: 渠道网关模块导出
"""

from .channel_gateway import ChannelGateway, ChannelSenderInterface, MockPushChannel, MockSMSChannel, MockWechatChannel, DispatchLog, gateway

__all__ = [
    "ChannelGateway",
    "ChannelSenderInterface",
    "MockPushChannel",
    "MockSMSChannel",
    "MockWechatChannel",
    "DispatchLog",
    "gateway",
]