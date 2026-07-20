"""
api_server\middleware.py
功能描述: API认证和限流中间件，支持API Key认证和基于令牌桶的限流策略
"""

import time
from typing import Dict, Optional
from fastapi import Request, HTTPException
from fastapi.security import APIKeyHeader
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.responses import JSONResponse

from common import logger, app_config, redis_client


api_key_header = APIKeyHeader(name="X-API-Key", auto_error=False)

ALLOWED_API_KEYS = {"demo_key_123", "internal_service_token"}


async def get_api_key(request: Request) -> Optional[str]:
    api_key = await api_key_header(request)
    if not api_key:
        api_key = request.query_params.get("api_key")
    return api_key


async def verify_api_key(request: Request):
    if app_config.APP_ENV == "development":
        return
    
    api_key = await get_api_key(request)
    if not api_key or api_key not in ALLOWED_API_KEYS:
        logger.warning(f"API认证失败: 无效的API Key, IP={request.client.host}")
        raise HTTPException(status_code=401, detail="未授权的访问，请提供有效的API Key")


class RateLimitMiddleware(BaseHTTPMiddleware):
    def __init__(self, app, rate_limit: int = 100, window_seconds: int = 60):
        super().__init__(app)
        self.rate_limit = rate_limit
        self.window_seconds = window_seconds
        self._memory_store: Dict[str, Dict[str, int]] = {}
    
    def _get_client_key(self, request: Request) -> str:
        client_ip = request.client.host if request.client else "unknown"
        api_key = request.headers.get("X-API-Key", "")
        return f"rate_limit:{client_ip}:{api_key}"
    
    def _get_redis_key(self, request: Request) -> str:
        return f"rate_limit:{request.client.host}" if request.client else "rate_limit:unknown"
    
    async def dispatch(self, request: Request, call_next):
        if app_config.APP_ENV == "development":
            return await call_next(request)
        
        if request.url.path in ["/health", f"{app_config.API_PREFIX}/health"]:
            return await call_next(request)
        
        if request.url.path.startswith("/static"):
            return await call_next(request)
        
        if request.url.path == "/ws/logs":
            return await call_next(request)
        
        client_key = self._get_client_key(request)
        now = int(time.time())
        
        if redis_client.is_available():
            try:
                redis_key = self._get_redis_key(request)
                
                current_count = redis_client.get(redis_key)
                current_count = int(current_count) if current_count else 0
                
                if current_count >= self.rate_limit:
                    reset_time = redis_client.client.ttl(redis_key)
                    logger.warning(f"限流触发: IP={request.client.host}, count={current_count}")
                    return JSONResponse(
                        status_code=429,
                        content={
                            "error": "请求过于频繁",
                            "rate_limit": self.rate_limit,
                            "window_seconds": self.window_seconds,
                            "retry_after": reset_time if reset_time > 0 else self.window_seconds
                        }
                    )
                
                if current_count == 0:
                    redis_client.set(redis_key, "1", expire=self.window_seconds)
                else:
                    redis_client.client.incr(redis_key)
                
                return await call_next(request)
            
            except Exception as e:
                logger.warning(f"Redis限流失败，降级到内存模式: {e}")
        
        if client_key not in self._memory_store:
            self._memory_store[client_key] = {"count": 0, "window_start": now}
        
        entry = self._memory_store[client_key]
        
        if now - entry["window_start"] >= self.window_seconds:
            entry["count"] = 0
            entry["window_start"] = now
        
        if entry["count"] >= self.rate_limit:
            remaining = self.window_seconds - (now - entry["window_start"])
            logger.warning(f"限流触发(内存模式): IP={request.client.host}, count={entry['count']}")
            return JSONResponse(
                status_code=429,
                content={
                    "error": "请求过于频繁",
                    "rate_limit": self.rate_limit,
                    "window_seconds": self.window_seconds,
                    "retry_after": remaining
                }
            )
        
        entry["count"] += 1
        
        return await call_next(request)


class AuthMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        if app_config.APP_ENV == "development":
            return await call_next(request)
        
        if request.url.path in ["/health", f"{app_config.API_PREFIX}/health"]:
            return await call_next(request)
        
        if request.url.path.startswith("/static"):
            return await call_next(request)
        
        if request.url.path == "/ws/logs":
            return await call_next(request)
        
        api_key = await get_api_key(request)
        if not api_key or api_key not in ALLOWED_API_KEYS:
            logger.warning(f"API认证失败: IP={request.client.host}, path={request.url.path}")
            return JSONResponse(
                status_code=401,
                content={"error": "未授权的访问，请提供有效的API Key"}
            )
        
        return await call_next(request)