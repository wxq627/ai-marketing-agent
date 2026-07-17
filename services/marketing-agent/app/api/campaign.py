"""
策略部署接口。
接收上游 Strategy Agent 下发的策略包，校验后投递至 Celery 队列。
"""

import logging
from fastapi import APIRouter, HTTPException, status
from pydantic import BaseModel

from app.models.strategy import StrategyPackage
from app.tasks.execution_tasks import batch_dispatch_task

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/campaign", tags=["Campaign"])


class DeployRequest(BaseModel):
    """部署请求体"""
    strategy: StrategyPackage
    customer_list: list[dict]


class DeployResponse(BaseModel):
    """部署响应体"""
    task_id: str
    campaign_id: str
    dispatched_count: int
    message: str


@router.post("/deploy", response_model=DeployResponse, status_code=status.HTTP_202_ACCEPTED)
async def deploy_campaign(request: DeployRequest):
    """
    部署营销活动。
    立即返回 202 Accepted，实际执行在后台异步进行。
    """
    try:
        # 序列化策略包用于 Celery 传输
        strategy_data = request.strategy.model_dump(mode="json")

        # 异步投递批量分发任务
        result = batch_dispatch_task.delay(strategy_data, request.customer_list)

        logger.info(
            f"活动部署成功 | campaign={request.strategy.campaign_id} | "
            f"task_id={result.id} | customers={len(request.customer_list)}"
        )

        return DeployResponse(
            task_id=result.id,
            campaign_id=request.strategy.campaign_id,
            dispatched_count=len(request.customer_list) * len(request.strategy.channels),
            message="活动已提交执行，请通过 feedback 接口查询进度",
        )

    except Exception as e:
        logger.error(f"活动部署失败 | error={e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))