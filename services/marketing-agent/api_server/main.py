"""
api_server\main.py
功能描述: FastAPI主应用入口，包含CORS、WebSocket、静态文件和API路由注册
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from fastapi import FastAPI, WebSocket, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import RedirectResponse, JSONResponse
from common import logger, app_config, exception_to_http
from api_server.websocket_manager import websocket_manager
from api_server.middleware import RateLimitMiddleware, AuthMiddleware

logger.info("初始化Marketing Agent API服务...")

websocket_manager.register_log_handler(logger)

app = FastAPI(
    title="Marketing Agent API",
    description="C端智能交互与触达执行系统API",
    version="1.0.0"
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:8080", "http://localhost:3000"],
    allow_credentials=True,
    allow_methods=["GET", "POST", "PUT", "DELETE", "OPTIONS"],
    allow_headers=["*"],
)

app.add_middleware(RateLimitMiddleware, rate_limit=100, window_seconds=60)
app.add_middleware(AuthMiddleware)

api_prefix = "/api/v3"

from api_server.routes.strategy import router as strategy_router
from api_server.routes.reach import router as reach_router
from api_server.routes.chat import router as chat_router
from api_server.routes.monitor import router as monitor_router
from api_server.routes.feedback import router as feedback_router

app.include_router(strategy_router, prefix=api_prefix, tags=["策略管理"])
app.include_router(reach_router, prefix=api_prefix, tags=["触达管理"])
app.include_router(chat_router, prefix=api_prefix, tags=["对话交互"])
app.include_router(monitor_router, prefix=api_prefix, tags=["监控统计"])
app.include_router(feedback_router, prefix=api_prefix, tags=["反馈交互"])

static_dir = Path(__file__).parent / "static"
app.mount("/static", StaticFiles(directory=str(static_dir)), name="static")


@app.get("/", response_class=RedirectResponse)
async def root():
    return RedirectResponse(url="/static/index.html")


@app.get("/health", tags=["健康检查"])
async def health_check():
    return {
        "status": "healthy",
        "service": "marketing_agent",
        "websocket_connections": websocket_manager.connection_count
    }


@app.get(f"{api_prefix}/health", tags=["健康检查"])
async def health_check_v3():
    return {
        "status": "healthy",
        "service": "marketing_agent",
        "websocket_connections": websocket_manager.connection_count
    }


@app.websocket("/ws/logs")
async def websocket_logs(websocket: WebSocket):
    await websocket_manager.connect(websocket)
    logger.info(f"WebSocket连接建立: 总连接数={websocket_manager.connection_count}")
    
    try:
        while True:
            await websocket.receive_text()
    except Exception:
        websocket_manager.disconnect(websocket)
        logger.info(f"WebSocket连接断开: 总连接数={websocket_manager.connection_count}")


@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception):
    http_exc = exception_to_http(exc)
    return JSONResponse(
        status_code=http_exc.status_code,
        content={"detail": http_exc.detail}
    )


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(
        app,
        host=app_config.APP_HOST,
        port=app_config.APP_PORT,
        log_level="info"
    )