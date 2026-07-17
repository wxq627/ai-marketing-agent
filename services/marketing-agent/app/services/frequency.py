"""
频控与幂等服务。
基于 Redis 实现"同一客户 N 小时内最多触达 M 次"的频控，
以及接口幂等性校验。
"""

import logging
import re
from typing import Optional
import redis.asyncio as redis
from datetime import datetime, timedelta

from app.core.config import settings
from app.models.strategy import StrategyPackage

logger = logging.getLogger(__name__)


class FrequencyLimitExceeded(Exception):
    """频控超限异常"""
    pass


class IdempotencyError(Exception):
    """幂等性校验失败异常"""
    pass


class FrequencyService:
    """
    频控与幂等服务。
    使用 Redis 的原子操作实现分布式频控。
    """

    # Redis Key 模板
    KEY_FREQUENCY = "marketing:freq:{campaign_id}:{customer_id}"
    KEY_IDEMPOTENCY = "marketing:idempotency:{request_id}"

    def __init__(self):
        self.redis = redis.from_url(
            settings.redis.url,
            max_connections=settings.redis.max_connections,
            decode_responses=True,
        )

    def _parse_frequency_limit(self, limit_str: str) -> tuple[int, int]:
        """
        解析频控规则字符串，如 "7天最多触达2次" -> (7, 2)
        默认返回 (24, 1) 即 24 小时 1 次
        """
        pattern = r"(\d+)\s*天.*?(\d+)\s*次"
        match = re.search(pattern, limit_str)
        if match:
            days = int(match.group(1))
            times = int(match.group(2))
            return days, times
        return 24, 1  # 默认 24 小时 1 次

    async def check_frequency_limit(
        self,
        customer_id: str,
        campaign_id: str,
        frequency_limit: str,
    ) -> bool:
        """
        检查频控是否超限。

        Args:
            customer_id: 客户 ID
            campaign_id: 活动 ID
            frequency_limit: 频控规则字符串，如 "7天最多触达2次"

        Returns:
            True: 未超限，允许触达
            False: 已超限，禁止触达

        Raises:
            FrequencyLimitExceeded: 频控超限时抛出
        """
        days, max_times = self._parse_frequency_limit(frequency_limit)
        key = self.KEY_FREQUENCY.format(campaign_id=campaign_id, customer_id=customer_id)
        expire_seconds = int(timedelta(days=days).total_seconds())

        # 原子操作：INCR + EXPIRE（如果 key 不存在则设置过期时间）
        current_count = await self.redis.incr(key)
        if current_count == 1:
            # 第一次触达，设置过期时间
            await self.redis.expire(key, expire_seconds)

        if current_count > max_times:
            logger.warning(
                f"频控超限 | customer_id={customer_id} | campaign_id={campaign_id} | "
                f"current={current_count} max={max_times}"
            )
            raise FrequencyLimitExceeded(
                f"客户 {customer_id} 在 {days} 天内已触达 {current_count} 次，超过限制 {max_times} 次"
            )

        logger.debug(
            f"频控检查通过 | customer_id={customer_id} | campaign_id={campaign_id} | "
            f"current={current_count}/{max_times}"
        )
        return True

    async def reset_frequency(self, customer_id: str, campaign_id: str) -> None:
        """重置某客户在某活动下的频控计数"""
        key = self.KEY_FREQUENCY.format(campaign_id=campaign_id, customer_id=customer_id)
        await self.redis.delete(key)
        logger.info(f"频控重置 | customer_id={customer_id} | campaign_id={campaign_id}")

    async def check_idempotency(self, request_id: str, expire_seconds: int = 3600) -> bool:
        """
        检查请求是否已处理（幂等性校验）。

        Args:
            request_id: 请求唯一标识
            expire_seconds: 幂等窗口期（秒）

        Returns:
            True: 首次请求，允许处理
            False: 重复请求，应直接返回缓存结果

        Raises:
            IdempotencyError: 重复请求时抛出
        """
        key = self.KEY_IDEMPOTENCY.format(request_id=request_id)
        # SETNX：仅当 key 不存在时设置
        is_first = await self.redis.set(key, "1", nx=True, ex=expire_seconds)

        if not is_first:
            logger.warning(f"幂等性校验失败 | request_id={request_id}")
            raise IdempotencyError(f"重复请求：{request_id}")

        return True

    async def store_idempotency_result(self, request_id: str, result: str, expire_seconds: int = 3600) -> None:
        """存储幂等性请求的结果（供重复请求直接返回）"""
        key = self.KEY_IDEMPOTENCY.format(request_id=request_id)
        await self.redis.set(key, result, ex=expire_seconds)

    async def get_idempotency_result(self, request_id: str) -> Optional[str]:
        """获取已缓存的幂等性请求结果"""
        key = self.KEY_IDEMPOTENCY.format(request_id=request_id)
        return await self.redis.get(key)

    async def close(self) -> None:
        """关闭 Redis 连接"""
        await self.redis.close()


# 全局单例
frequency_service = FrequencyService()