"""
api_server\routes\reach.py
功能描述: 单客触达与渠道管理API接口
"""

from fastapi import APIRouter
from pydantic import BaseModel
from typing import Dict, Any, Optional, List

from common import logger, exception_to_http
from agent_orchestrator import orchestrator
from channel_gateway.channel_gateway import gateway

router = APIRouter(prefix="/reach", tags=["触达管理"])


class SingleReachRequest(BaseModel):
    oneid: str
    channel: Optional[str] = None


class SingleReachResponse(BaseModel):
    success: bool
    session_id: str
    content: Optional[str] = None
    dispatch_results: List[Dict[str, Any]] = []
    message: str


@router.post("/single", response_model=SingleReachResponse)
async def single_reach(request: SingleReachRequest):
    try:
        logger.info(f"单客触达请求: oneid={request.oneid}, channel={request.channel}")
        
        state = orchestrator.start_workflow(request.oneid)
        
        if state.workflow_status.value == "failed":
            return SingleReachResponse(
                success=False,
                session_id=state.session_id or "",
                message=state.error_message or "触达失败"
            )
        
        dispatch_results = [dr.model_dump() for dr in state.dispatch_results]
        
        return SingleReachResponse(
            success=True,
            session_id=state.session_id,
            content=state.generated_content,
            dispatch_results=dispatch_results,
            message="触达成功"
        )
    
    except Exception as e:
        logger.error(f"单客触达失败: {e}")
        raise exception_to_http(e)


@router.get("/channels")
async def get_channels():
    try:
        channels = gateway.get_available_channels()
        return {"channels": channels}
    except Exception as e:
        logger.error(f"获取渠道列表失败: {e}")
        raise exception_to_http(e)


@router.get("/dispatch-logs")
async def get_dispatch_logs(oneid: Optional[str] = None, limit: int = 50):
    try:
        logs = gateway.get_dispatch_logs(limit=limit)
        
        if oneid:
            logs = [log for log in logs if log.get("user_id") == oneid]
        
        return {"logs": logs}
    except Exception as e:
        logger.error(f"获取分发日志失败: {e}")
        raise exception_to_http(e)


@router.get("/touch-logs")
async def get_touch_logs(oneid: Optional[str] = None, limit: int = 50):
    try:
        logs = gateway.get_touch_logs(oneid=oneid, limit=limit)
        return {"logs": logs}
    except Exception as e:
        logger.error(f"获取触达日志失败: {e}")
        raise exception_to_http(e)


@router.get("/stats")
async def get_reach_stats():
    try:
        stats = gateway.get_dispatch_stats()
        return stats
    except Exception as e:
        logger.error(f"获取触达统计失败: {e}")
        raise exception_to_http(e)