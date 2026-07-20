"""
api_server\routes\feedback.py
功能描述: 用户交互反馈API接口（点击/拒绝）
"""

from fastapi import APIRouter
from pydantic import BaseModel
from typing import Dict, Any, Optional

from common import logger, exception_to_http
from agent_orchestrator import orchestrator

router = APIRouter(prefix="/feedback", tags=["反馈交互"])


class UserInteractionRequest(BaseModel):
    session_id: str
    interaction_type: str
    channel: Optional[str] = None
    message: Optional[str] = None


class UserInteractionResponse(BaseModel):
    success: bool
    session_id: str
    interaction_type: str
    message: str


@router.post("/interaction", response_model=UserInteractionResponse)
async def user_interaction(request: UserInteractionRequest):
    try:
        valid_types = ["user_click", "user_reject"]
        if request.interaction_type not in valid_types:
            return UserInteractionResponse(
                success=False,
                session_id=request.session_id,
                interaction_type=request.interaction_type,
                message=f"无效的交互类型: {request.interaction_type}, 有效类型: {valid_types}"
            )

        logger.info(f"用户交互事件: session_id={request.session_id}, type={request.interaction_type}, channel={request.channel}")

        state = orchestrator.get_workflow_state(request.session_id)
        if not state:
            return UserInteractionResponse(
                success=False,
                session_id=request.session_id,
                interaction_type=request.interaction_type,
                message="工作流状态不存在"
            )

        state.interaction_type = request.interaction_type
        state.interaction_channel = request.channel
        state.user_response = request.message or ""

        state = orchestrator.continue_workflow(request.session_id, request.message or "")

        return UserInteractionResponse(
            success=True,
            session_id=request.session_id,
            interaction_type=request.interaction_type,
            message=f"{request.interaction_type} 事件已触发并回流"
        )

    except Exception as e:
        logger.error(f"用户交互处理失败: {e}")
        raise exception_to_http(e)