"""
文件路径: d:\库文件\桌面\Summer_Intern\c_marketing_agent\api_server\routes\__init__.py
功能描述: API路由模块导出
"""

from .strategy import router as strategy_router, router as strategy
from .reach import router as reach_router, router as reach
from .chat import router as chat_router, router as chat
from .monitor import router as monitor_router, router as monitor
from .feedback import router as feedback_router, router as feedback

__all__ = [
    "strategy_router",
    "strategy",
    "reach_router",
    "reach",
    "chat_router",
    "chat",
    "monitor_router",
    "monitor",
    "feedback_router",
    "feedback",
]