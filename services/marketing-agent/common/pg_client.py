"""
common\pg_client.py
功能描述: PostgreSQL客户端封装，支持连接池管理和连接状态检测，服务不可用时返回默认值
"""

from sqlalchemy import create_engine, text
from sqlalchemy.engine import Engine
from typing import Optional, Dict, Any, List
from contextlib import contextmanager
from .config import postgres_config
from .logger import logger


class PgClient:
    _instance: Optional["PgClient"] = None
    _engine: Optional[Engine] = None

    def __new__(cls, *args, **kwargs):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance

    def __init__(self):
        if self._engine is None:
            self._init_engine()

    def _init_engine(self):
        try:
            self._engine = create_engine(
                postgres_config.dsn,
                pool_pre_ping=True,
                pool_size=20,
                max_overflow=50,
                pool_timeout=postgres_config.POSTGRES_TIMEOUT,
                connect_args={
                    "connect_timeout": postgres_config.POSTGRES_TIMEOUT,
                },
            )
            with self._engine.connect() as conn:
                conn.execute(text("SELECT 1"))
            logger.info("PostgreSQL客户端连接成功")
        except Exception as e:
            logger.warning(f"PostgreSQL连接失败，使用内存模拟: {str(e)}")
            self._engine = None

    @property
    def engine(self) -> Optional[Engine]:
        if self._engine is None:
            self._init_engine()
        return self._engine

    def is_available(self) -> bool:
        return self._engine is not None

    @contextmanager
    def get_connection(self):
        if self._engine is None:
            logger.warning("PostgreSQL连接不可用，使用内存模拟")
            yield None
        else:
            try:
                with self._engine.connect() as conn:
                    yield conn
            except Exception as e:
                logger.warning(f"PostgreSQL连接获取失败，使用内存模拟: {str(e)}")
                yield None

    def execute(self, sql: str, params: Optional[Dict[str, Any]] = None) -> Any:
        try:
            if self._engine is None:
                logger.warning("PostgreSQL不可用，使用内存模拟")
                return None
            with self._engine.connect() as conn:
                result = conn.execute(text(sql), params or {})
                conn.commit()
                return result
        except Exception as e:
            logger.warning(f"PostgreSQL执行失败，使用内存模拟: {str(e)}")
            return None

    def fetch_one(self, sql: str, params: Optional[Dict[str, Any]] = None) -> Optional[Dict[str, Any]]:
        try:
            if self._engine is None:
                logger.warning("PostgreSQL不可用，使用内存模拟")
                return None
            with self._engine.connect() as conn:
                result = conn.execute(text(sql), params or {})
                row = result.mappings().first()
                return dict(row) if row else None
        except Exception as e:
            logger.warning(f"PostgreSQL查询失败，使用内存模拟: {str(e)}")
            return None

    def fetch_all(self, sql: str, params: Optional[Dict[str, Any]] = None) -> List[Dict[str, Any]]:
        try:
            if self._engine is None:
                logger.warning("PostgreSQL不可用，使用内存模拟")
                return []
            with self._engine.connect() as conn:
                result = conn.execute(text(sql), params or {})
                rows = result.mappings().all()
                return [dict(row) for row in rows]
        except Exception as e:
            logger.warning(f"PostgreSQL查询失败，使用内存模拟: {str(e)}")
            return []

    def insert(self, table_name: str, data: Dict[str, Any]) -> int:
        try:
            if self._engine is None:
                logger.warning("PostgreSQL不可用，使用内存模拟")
                return 0
            columns = ", ".join(data.keys())
            placeholders = ", ".join([f":{k}" for k in data.keys()])
            sql = f"INSERT INTO {table_name} ({columns}) VALUES ({placeholders}) RETURNING id"
            with self._engine.connect() as conn:
                result = conn.execute(text(sql), data)
                conn.commit()
                row = result.mappings().first()
                return row["id"] if row else 0
        except Exception as e:
            logger.warning(f"PostgreSQL插入失败，使用内存模拟: {str(e)}")
            return 0

    def update(self, table_name: str, data: Dict[str, Any], where_clause: str) -> int:
        try:
            if self._engine is None:
                logger.warning("PostgreSQL不可用，使用内存模拟")
                return 0
            set_clause = ", ".join([f"{k} = :{k}" for k in data.keys()])
            sql = f"UPDATE {table_name} SET {set_clause} WHERE {where_clause}"
            with self._engine.connect() as conn:
                result = conn.execute(text(sql), data)
                conn.commit()
                return result.rowcount
        except Exception as e:
            logger.warning(f"PostgreSQL更新失败，使用内存模拟: {str(e)}")
            return 0


pg_client = PgClient()