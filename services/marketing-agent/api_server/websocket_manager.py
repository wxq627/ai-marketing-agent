"""
api_server\websocket_manager.py
功能描述: WebSocket日志管理器，支持实时日志推送和客户端连接管理
"""

import json
import logging
import asyncio
from datetime import datetime
from typing import Set, Dict, Any
from websockets.exceptions import WebSocketException

from fastapi import WebSocket, WebSocketDisconnect


class WebSocketLogHandler(logging.Handler):
    def __init__(self, websocket_manager):
        super().__init__()
        self.websocket_manager = websocket_manager

    def emit(self, record):
        try:
            log_entry = {
                "timestamp": datetime.utcnow().isoformat() + "Z",
                "level": record.levelname,
                "logger": record.name,
                "message": record.getMessage(),
                "module": record.module,
                "function": record.funcName,
                "line": record.lineno,
            }
            if record.exc_info:
                log_entry["exception"] = self.formatException(record.exc_info)
            
            loop = asyncio.get_event_loop()
            if loop.is_running():
                asyncio.run_coroutine_threadsafe(
                    self.websocket_manager.broadcast_log(log_entry),
                    loop
                )
        except Exception:
            self.handleError(record)


class WebSocketManager:
    def __init__(self):
        self.active_connections: Set[WebSocket] = set()
        self._log_handler: WebSocketLogHandler = WebSocketLogHandler(self)
        self._registered = False

    def register_log_handler(self, logger: logging.Logger):
        if not self._registered:
            logger.addHandler(self._log_handler)
            self._registered = True

    async def connect(self, websocket: WebSocket):
        await websocket.accept()
        self.active_connections.add(websocket)

    def disconnect(self, websocket: WebSocket):
        self.active_connections.remove(websocket)

    async def broadcast(self, message: Dict[str, Any]):
        message_json = json.dumps(message, ensure_ascii=False)
        disconnected = []
        
        for connection in self.active_connections:
            try:
                await connection.send_text(message_json)
            except WebSocketException:
                disconnected.append(connection)
        
        for conn in disconnected:
            self.active_connections.discard(conn)

    async def broadcast_log(self, log_entry: Dict[str, Any]):
        await self.broadcast({
            "type": "log",
            "data": log_entry
        })

    async def broadcast_event(self, event_type: str, data: Dict[str, Any]):
        await self.broadcast({
            "type": event_type,
            "data": data
        })

    @property
    def connection_count(self) -> int:
        return len(self.active_connections)


websocket_manager = WebSocketManager()