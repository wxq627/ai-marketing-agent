"""
C端交互接口。
提供流式/同步对话能力，支撑仿真 App 的智能客服与营销推荐场景。
"""

import logging
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from typing import Optional

from app.agents.marketing_agent import marketing_agent
from app.models.strategy import StrategyPackage

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/chat", tags=["Chat"])


class ChatRequest(BaseModel):
    message: str
    session_id: str
    customer_profile: dict
    strategy: Optional[StrategyPackage] = None


class ChatResponse(BaseModel):
    response: str
    intent: str
    success: bool


@router.post("/", response_model=ChatResponse)
async def chat_with_agent(request: ChatRequest):
    """
    C端对话接口。
    支持多轮对话状态保持（通过 session_id）。
    """
    try:
        # 注入 last_message 供意图识别使用
        profile = {**request.customer_profile, "last_message": request.message}

        result = await marketing_agent.run(
            campaign_id=request.strategy.campaign_id if request.strategy else "DEFAULT",
            customer_id=request.session_id,
            customer_profile=profile,
            strategy=request.strategy,
            thread_id=request.session_id,
        )

        return ChatResponse(
            response=result["response"],
            intent=result["state"]["intent"],
            success=result["success"],
        )

    except Exception as e:
        logger.error(f"对话接口异常 | session={request.session_id} | error={e}")
        raise HTTPException(status_code=500, detail=str(e))