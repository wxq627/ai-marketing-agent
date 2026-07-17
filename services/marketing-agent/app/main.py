"""
FastAPI 应用入口。
注册路由、中间件、生命周期事件，挂载仿真前端页面。
"""

import logging
from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse
from pathlib import Path

from app.core.config import settings
from app.api import campaign, chat, feedback
from app.services.frequency import frequency_service

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """应用生命周期管理"""
    logger.info(f"🚀 {settings.app_name} 启动中 | env={settings.app_env}")
    yield
    # 关闭时清理资源
    await frequency_service.close()
    logger.info(f"🛑 {settings.app_name} 已关闭")


app = FastAPI(
    title=settings.app_name,
    version="1.0.0",
    lifespan=lifespan,
)

# CORS 配置
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# 注册路由
app.include_router(campaign.router, prefix=settings.api_prefix)
app.include_router(chat.router, prefix=settings.api_prefix)
app.include_router(feedback.router, prefix=settings.api_prefix)


@app.get("/")
async def serve_simulation_ui():
    """提供仿真 App 界面"""
    ui_path = Path(__file__).parent.parent / "static" / "simulation.html"
    if not ui_path.exists():
        return HTMLResponse("<h1>simulation.html not found</h1>", status_code=404)
    return HTMLResponse(ui_path.read_text(encoding="utf-8"))


@app.get("/health")
async def health_check():
    return {"status": "ok", "env": settings.app_env}