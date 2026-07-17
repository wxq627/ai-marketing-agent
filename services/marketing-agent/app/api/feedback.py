"""
反馈收集接口。
接收 C 端埋点数据与聚合指标，为 Knowledge Agent 回流提供数据源。
"""

import logging
from fastapi import APIRouter, HTTPException
from app.models.events import FeedbackEvent, CustomerActionEvent

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/feedback", tags=["Feedback"])


@router.post("/aggregate", status_code=204)
async def receive_aggregate_feedback(event: FeedbackEvent):
    """接收聚合反馈指标（如小时级报表）"""
    logger.info(
        f"收到聚合反馈 | campaign={event.campaign_id} | "
        f"exposure={event.feedback_metrics.exposure_count} | "
        f"conversion={event.feedback_metrics.conversion_count}"
    )
    # MVP 阶段仅记录日志，后续接入 Knowledge Agent 推送
    return None


@router.post("/action", status_code=204)
async def receive_customer_action(event: CustomerActionEvent):
    """接收单条客户行为事件（实时埋点）"""
    logger.debug(
        f"收到行为事件 | customer={event.customer_id} | "
        f"type={event.event_type} | channel={event.channel}"
    )
    return None