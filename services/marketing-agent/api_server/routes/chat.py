"""
api_server\routes\chat.py
功能描述: 对话交互API接口
"""

from fastapi import APIRouter
from pydantic import BaseModel
from typing import Dict, Any, Optional, List

from common import logger, exception_to_http
from agent_orchestrator import orchestrator, session_manager

router = APIRouter(prefix="/chat", tags=["对话交互"])


class ChatStartRequest(BaseModel):
    oneid: str


class ChatStartResponse(BaseModel):
    success: bool
    session_id: str
    content: Optional[str] = None
    message: str


@router.post("/start", response_model=ChatStartResponse)
async def chat_start(request: ChatStartRequest):
    try:
        logger.info(f"对话开始请求: oneid={request.oneid}")
        
        state = orchestrator.start_workflow(request.oneid)
        
        if state.workflow_status.value == "failed":
            return ChatStartResponse(
                success=False,
                session_id=state.session_id or "",
                message=state.error_message or "对话开始失败"
            )
        
        return ChatStartResponse(
            success=True,
            session_id=state.session_id,
            content=state.generated_content,
            message="对话已开始"
        )
    
    except Exception as e:
        logger.error(f"对话开始失败: {e}")
        raise exception_to_http(e)


class ChatMessageRequest(BaseModel):
    session_id: str
    message: str


class ChatMessageResponse(BaseModel):
    success: bool
    session_id: str
    agent_response: Optional[str] = None
    workflow_status: str = "running"
    message: str


@router.post("/message", response_model=ChatMessageResponse)
async def chat_message(request: ChatMessageRequest):
    try:
        logger.info(f"对话消息请求: session_id={request.session_id}, message={request.message[:30]}...")
        
        state = orchestrator.continue_workflow(request.session_id, request.message)
        
        if state.workflow_status.value == "failed":
            return ChatMessageResponse(
                success=False,
                session_id=request.session_id,
                workflow_status=state.workflow_status.value,
                message=state.error_message or "对话处理失败"
            )
        
        return ChatMessageResponse(
            success=True,
            session_id=request.session_id,
            agent_response=state.agent_response,
            workflow_status=state.workflow_status.value,
            message="消息已处理"
        )
    
    except Exception as e:
        logger.error(f"对话消息处理失败: {e}")
        raise exception_to_http(e)


@router.get("/session/{session_id}")
async def get_session(session_id: str):
    from common import SessionNotFoundError
    
    try:
        session = session_manager.get_session(session_id)
        
        workflow_state = orchestrator.get_workflow_state(session_id)
        
        result = {
            "session_id": session.session_id,
            "oneid": session.oneid,
            "current_round": session.current_round,
            "status": session.status.value,
            "sentiment": session.sentiment.value,
            "messages": session.messages,
            "recommended_benefits": session.recommended_benefits,
            "created_at": session.created_at.isoformat(),
            "last_active_at": session.last_active_at.isoformat()
        }
        
        if workflow_state:
            result["workflow_state"] = workflow_state.to_dict()
        
        return result
    
    except SessionNotFoundError:
        logger.warning(f"会话不存在: {session_id}")
        return {"error": "会话不存在"}
    except Exception as e:
        logger.error(f"获取会话失败: {e}")
        raise exception_to_http(e)


class ChatEndRequest(BaseModel):
    session_id: str


@router.post("/end")
async def chat_end(request: ChatEndRequest):
    try:
        logger.info(f"对话结束请求: session_id={request.session_id}")
        
        orchestrator.end_workflow(request.session_id)
        
        return {
            "success": True,
            "session_id": request.session_id,
            "message": "对话已结束"
        }
    
    except Exception as e:
        logger.error(f"对话结束失败: {e}")
        raise exception_to_http(e)


@router.get("/sessions")
async def list_sessions():
    try:
        sessions = session_manager.list_sessions()
        
        result = []
        for session in sessions:
            workflow_state = orchestrator.get_workflow_state(session.session_id)
            
            item = {
                "session_id": session.session_id,
                "oneid": session.oneid,
                "current_round": session.current_round,
                "status": session.status.value,
                "sentiment": session.sentiment.value,
                "created_at": session.created_at.isoformat(),
                "last_active_at": session.last_active_at.isoformat()
            }
            
            if workflow_state:
                item["workflow_status"] = workflow_state.workflow_status.value
            
            result.append(item)
        
        return {"sessions": result}
    
    except Exception as e:
        logger.error(f"获取会话列表失败: {e}")
        raise exception_to_http(e)