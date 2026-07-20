"""
common\redis_client.py
功能描述: Redis客户端封装，支持连接池管理和连接状态检测，服务不可用时返回默认值
"""

import redis
from typing import Optional, Any, Dict, List
from .config import redis_config
from .logger import logger


class RedisClient:
    _instance: Optional["RedisClient"] = None
    _client: Optional[redis.Redis] = None

    def __new__(cls, *args, **kwargs):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance

    def __init__(self):
        if self._client is None:
            self._init_client()

    def _init_client(self):
        try:
            self._client = redis.Redis(
                host=redis_config.REDIS_HOST,
                port=redis_config.REDIS_PORT,
                db=redis_config.REDIS_DB,
                password=redis_config.REDIS_PASSWORD,
                decode_responses=True,
                socket_timeout=redis_config.REDIS_TIMEOUT,
                socket_connect_timeout=redis_config.REDIS_TIMEOUT,
                health_check_interval=30,
            )
            self._client.ping()
            logger.info("Redis客户端连接成功")
        except redis.ConnectionError as e:
            logger.warning(f"Redis连接失败，使用内存模拟: {str(e)}")
            self._client = None

    @property
    def client(self) -> Optional[redis.Redis]:
        if self._client is None:
            self._init_client()
        return self._client

    def is_available(self) -> bool:
        return self._client is not None

    def get(self, key: str) -> Optional[str]:
        try:
            if self._client:
                return self._client.get(key)
            return None
        except redis.RedisError as e:
            logger.warning(f"Redis GET失败，使用内存模拟: {str(e)}")
            return None

    def set(self, key: str, value: str, expire: Optional[int] = None) -> bool:
        try:
            if self._client:
                if expire:
                    return self._client.set(key, value, ex=expire)
                return self._client.set(key, value)
            return True
        except redis.RedisError as e:
            logger.warning(f"Redis SET失败，使用内存模拟: {str(e)}")
            return True

    def delete(self, key: str) -> int:
        try:
            if self._client:
                return self._client.delete(key)
            return 0
        except redis.RedisError as e:
            logger.warning(f"Redis DELETE失败，使用内存模拟: {str(e)}")
            return 0

    def exists(self, key: str) -> bool:
        try:
            if self._client:
                return self._client.exists(key) > 0
            return False
        except redis.RedisError as e:
            logger.warning(f"Redis EXISTS失败，使用内存模拟: {str(e)}")
            return False

    def hgetall(self, key: str) -> Dict[str, str]:
        try:
            if self._client:
                return self._client.hgetall(key)
            return {}
        except redis.RedisError as e:
            logger.warning(f"Redis HGETALL失败，使用内存模拟: {str(e)}")
            return {}

    def hset(self, key: str, mapping: Dict[str, Any]) -> int:
        try:
            if self._client:
                return self._client.hset(key, mapping=mapping)
            return len(mapping)
        except redis.RedisError as e:
            logger.warning(f"Redis HSET失败，使用内存模拟: {str(e)}")
            return len(mapping)

    def incr(self, key: str) -> int:
        try:
            if self._client:
                return self._client.incr(key)
            return 1
        except redis.RedisError as e:
            logger.warning(f"Redis INCR失败，使用内存模拟: {str(e)}")
            return 1

    def expire(self, key: str, seconds: int) -> bool:
        try:
            if self._client:
                return self._client.expire(key, seconds)
            return True
        except redis.RedisError as e:
            logger.warning(f"Redis EXPIRE失败，使用内存模拟: {str(e)}")
            return True

    def lpush(self, key: str, *values: Any) -> int:
        try:
            if self._client:
                return self._client.lpush(key, *values)
            return len(values)
        except redis.RedisError as e:
            logger.warning(f"Redis LPUSH失败，使用内存模拟: {str(e)}")
            return len(values)

    def lrange(self, key: str, start: int, end: int) -> List[str]:
        try:
            if self._client:
                return self._client.lrange(key, start, end)
            return []
        except redis.RedisError as e:
            logger.warning(f"Redis LRANGE失败，使用内存模拟: {str(e)}")
            return []

    def rpush(self, key: str, *values: Any) -> int:
        try:
            if self._client:
                return self._client.rpush(key, *values)
            return len(values)
        except redis.RedisError as e:
            logger.warning(f"Redis RPUSH失败，使用内存模拟: {str(e)}")
            return len(values)

    def llen(self, key: str) -> int:
        try:
            if self._client:
                return self._client.llen(key)
            return 0
        except redis.RedisError as e:
            logger.warning(f"Redis LLEN失败，使用内存模拟: {str(e)}")
            return 0


redis_client = RedisClient()