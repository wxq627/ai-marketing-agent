"""
Celery 异步任务定义。
负责策略包的异步触达执行、频控检查、内容生成与渠道发送的完整编排。
支持失败重试与死信记录。
"""

import logging
import json
from typing import Dict, Any, Optional
from datetime import datetime

from celery import Celery
from celery.exceptions import MaxRetriesExceededError

from app.core.config import settings
from app.models.strategy import StrategyPackage
from app.services.content_gen import content_generator
from app.services.frequency import frequency_service, FrequencyLimitExceeded
from app.services.channel import channel_service, SendResult

logger = logging.getLogger(__name__)

# Celery App 实例
celery_app = Celery(
    "marketing_agent",
    broker=settings.celery.broker_url,
    backend=settings.celery.result_backend,
)

# Celery 配置
celery_app.conf.update(
    task_serializer="json",
    accept_content=["json"],
    result_serializer="json",
    timezone="Asia/Shanghai",
    enable_utc=False,
    # 重试策略
    task_max_retries=3,
    task_default_retry_delay=60,
    # 任务结果过期时间
    result_expires=86400,
)


@celery_app.task(
    bind=True,
    name="execute_campaign_task",
    max_retries=3,
    default_retry_delay=60,
    acks_late=True,
)
def execute_campaign_task(
    self,
    strategy_data: Dict[str, Any],
    customer_id: str,
    customer_profile: Dict[str, Any],
    channel: str,
) -> Dict[str, Any]:
    """
    单客户单渠道触达执行任务。

    执行流程：频控检查 → 内容生成 → 渠道发送 → 结果记录

    Args:
        strategy_data: 策略包字典（可序列化）
        customer_id: 目标客户 ID
        customer_profile: 客户画像
        channel: 目标渠道

    Returns:
        执行结果字典
    """
    campaign_id = strategy_data.get("campaign_metadata", {}).get("campaign_id", "UNKNOWN")
    task_id = self.request.id

    logger.info(
        f"触达任务开始 | task_id={task_id} | campaign={campaign_id} | "
        f"customer={customer_id} | channel={channel}"
    )

    try:
        # 1. 反序列化策略包
        strategy = StrategyPackage.model_validate(strategy_data)

        # 2. 频控检查
        frequency_limit = strategy.compliance_guard.frequency_limit
        frequency_service_sync_check(customer_id, campaign_id, frequency_limit)

        # 3. 内容生成（同步包装异步调用）
        content = run_async(content_generator.generate(strategy, customer_profile))

        # 4. 渠道发送
        result: SendResult = run_async(
            channel_service.send(channel, customer_id, content)
        )

        # 5. 构建返回结果
        execution_result = {
            "task_id": task_id,
            "campaign_id": campaign_id,
            "customer_id": customer_id,
            "channel": channel,
            "success": result.success,
            "message_id": result.message_id,
            "error_code": result.error_code,
            "error_message": result.error_message,
            "executed_at": datetime.now().isoformat(),
        }

        if result.success:
            logger.info(f"触达任务成功 | task_id={task_id} | message_id={result.message_id}")
        else:
            logger.warning(f"触达任务失败 | task_id={task_id} | error={result.error_message}")

        return execution_result

    except FrequencyLimitExceeded as e:
        # 频控超限不重试，直接标记跳过
        logger.warning(f"频控超限跳过 | task_id={task_id} | customer={customer_id} | {e}")
        return {
            "task_id": task_id,
            "campaign_id": campaign_id,
            "customer_id": customer_id,
            "channel": channel,
            "success": False,
            "skipped": True,
            "skip_reason": "frequency_limit_exceeded",
            "error_message": str(e),
            "executed_at": datetime.now().isoformat(),
        }

    except MaxRetriesExceededError:
        logger.error(f"触达任务重试耗尽 | task_id={task_id} | customer={customer_id}")
        return {
            "task_id": task_id,
            "campaign_id": campaign_id,
            "customer_id": customer_id,
            "channel": channel,
            "success": False,
            "error_code": "MAX_RETRIES_EXCEEDED",
            "error_message": "重试次数已耗尽",
            "executed_at": datetime.now().isoformat(),
        }

    except Exception as exc:
        logger.error(f"触达任务异常 | task_id={task_id} | error={exc}", exc_info=True)
        # 自动重试
        raise self.retry(exc=exc)


@celery_app.task(name="batch_dispatch_task")
def batch_dispatch_task(
    strategy_data: Dict[str, Any],
    customer_list: list[Dict[str, Any]],
) -> Dict[str, Any]:
    """
    批量分发任务。
    将策略包按客群×渠道拆分为多个单客户触达子任务。

    Args:
        strategy_data: 策略包字典
        customer_list: 客户列表 [{"customer_id": "...", "profile": {...}}, ...]

    Returns:
        分发统计信息
    """
    strategy = StrategyPackage.model_validate(strategy_data)
    campaign_id = strategy.campaign_id
    channels = strategy.channels

    dispatched_count = 0
    task_ids = []

    for customer in customer_list:
        customer_id = customer["customer_id"]
        profile = customer["profile"]

        for channel in channels:
            task = execute_campaign_task.delay(
                strategy_data=strategy_data,
                customer_id=customer_id,
                customer_profile=profile,
                channel=channel,
            )
            task_ids.append(task.id)
            dispatched_count += 1

    logger.info(
        f"批量分发完成 | campaign={campaign_id} | "
        f"customers={len(customer_list)} | channels={len(channels)} | "
        f"total_tasks={dispatched_count}"
    )

    return {
        "campaign_id": campaign_id,
        "dispatched_count": dispatched_count,
        "task_ids": task_ids[:100],  # 仅返回前100个避免结果过大
    }


# ==================== 工具函数 ====================

def frequency_service_sync_check(customer_id: str, campaign_id: str, frequency_limit: str) -> None:
    """
    在 Celery Worker（同步上下文）中调用异步频控服务。
    """
    import asyncio

    loop = asyncio.new_event_loop()
    try:
        loop.run_until_complete(
            frequency_service.check_frequency_limit(customer_id, campaign_id, frequency_limit)
        )
    finally:
        loop.close()


def run_async(coro):
    """
    在 Celery Worker（同步上下文）中运行异步协程。
    """
    import asyncio

    loop = asyncio.new_event_loop()
    try:
        return loop.run_until_complete(coro)
    finally:
        loop.close()