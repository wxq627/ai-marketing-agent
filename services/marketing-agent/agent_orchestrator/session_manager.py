"""
agent_orchestrator\session_manager.py
功能描述: 会话上下文管理模块，支持Redis和内存两种存储模式
"""

import uuid
import json
from datetime import datetime, timedelta
from typing import Optional, Dict, Any, List
from enum import Enum

from common import logger, redis_client, SessionError, SessionNotFoundError, SessionExpiredError, app_config


class SentimentType(str, Enum):
    POSITIVE = "positive"
    NEUTRAL = "neutral"
    NEGATIVE = "negative"


class SessionStatus(str, Enum):
    ACTIVE = "active"
    ENDED = "ended"
    EXPIRED = "expired"


class SessionContext:
    def __init__(self, session_id: str, oneid: str):
        self.session_id = session_id
        self.oneid = oneid
        self.current_round: int = 0
        self.messages: List[Dict[str, Any]] = []
        self.recommended_benefits: List[str] = []
        self.sentiment: SentimentType = SentimentType.NEUTRAL
        self.campaign_id: Optional[str] = None
        self.strategy_id: Optional[str] = None
        self.status: SessionStatus = SessionStatus.ACTIVE
        self.created_at: datetime = datetime.now()
        self.last_active_at: datetime = datetime.now()
        self.metadata: Dict[str, Any] = {}
        # 上下文记忆：记录上一轮意图，用于意图识别增强
        self.last_agent_type: Optional[str] = None      # 上一轮Agent类型 (query/service/marketing)
        self.last_intent_type: Optional[str] = None     # 上一轮细类意图 (bill/credit/business/...)
        self.last_intent_score: float = 0.0             # 上一轮意图分数

    def add_message(self, role: str, content: str):
        self.messages.append({
            "role": role,
            "content": content,
            "timestamp": datetime.now().isoformat()
        })
        self.current_round += 1
        self.last_active_at = datetime.now()

    def add_recommended_benefit(self, benefit_id: str):
        if benefit_id not in self.recommended_benefits:
            self.recommended_benefits.append(benefit_id)

    def update_sentiment(self, sentiment: SentimentType):
        self.sentiment = sentiment

    def set_campaign_id(self, campaign_id: str):
        self.campaign_id = campaign_id

    def set_strategy_id(self, strategy_id: str):
        self.strategy_id = strategy_id

    def end(self):
        self.status = SessionStatus.ENDED
        self.last_active_at = datetime.now()

    def to_dict(self) -> Dict[str, Any]:
        return {
            "session_id": self.session_id,
            "oneid": self.oneid,
            "current_round": self.current_round,
            "messages": self.messages,
            "recommended_benefits": self.recommended_benefits,
            "sentiment": self.sentiment.value,
            "campaign_id": self.campaign_id,
            "strategy_id": self.strategy_id,
            "status": self.status.value,
            "created_at": self.created_at.isoformat(),
            "last_active_at": self.last_active_at.isoformat(),
            "metadata": self.metadata,
            "last_agent_type": self.last_agent_type,
            "last_intent_type": self.last_intent_type,
            "last_intent_score": self.last_intent_score
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "SessionContext":
        session = cls(data["session_id"], data["oneid"])
        session.current_round = data.get("current_round", 0)
        session.messages = data.get("messages", [])
        session.recommended_benefits = data.get("recommended_benefits", [])
        session.sentiment = SentimentType(data.get("sentiment", "neutral"))
        session.campaign_id = data.get("campaign_id")
        session.strategy_id = data.get("strategy_id")
        session.status = SessionStatus(data.get("status", "active"))
        session.created_at = datetime.fromisoformat(data.get("created_at", datetime.now().isoformat()))
        session.last_active_at = datetime.fromisoformat(data.get("last_active_at", datetime.now().isoformat()))
        session.metadata = data.get("metadata", {})
        session.last_agent_type = data.get("last_agent_type")
        session.last_intent_type = data.get("last_intent_type")
        session.last_intent_score = data.get("last_intent_score", 0.0)
        return session

    @property
    def is_expired(self) -> bool:
        expiry_hours = app_config.APP_ENV == "development" and 24 or 1
        return datetime.now() - self.last_active_at > timedelta(hours=expiry_hours)


class SessionManager:
    def __init__(self):
        self._use_redis = True
        self._memory_cache: Dict[str, SessionContext] = {}
        self._redis_prefix = "session:"
        self._expiry_seconds = 86400

    def _get_redis_key(self, session_id: str) -> str:
        return f"{self._redis_prefix}{session_id}"

    def _redis_available(self) -> bool:
        if not self._use_redis:
            return False
        return redis_client.is_available()

    def create_session(self, oneid: str, campaign_id: Optional[str] = None) -> SessionContext:
        session_id = str(uuid.uuid4())[:16]
        session = SessionContext(session_id, oneid)
        
        if campaign_id:
            session.set_campaign_id(campaign_id)
        
        if self._redis_available():
            try:
                redis_client.set(
                    self._get_redis_key(session_id),
                    json.dumps(session.to_dict(), ensure_ascii=False),
                    expire=self._expiry_seconds
                )
                logger.info(f"会话已保存到Redis: session_id={session_id}")
            except Exception as e:
                logger.error(f"保存会话到Redis失败: {e}")
                self._memory_cache[session_id] = session
        else:
            self._memory_cache[session_id] = session
        
        logger.info(f"创建会话: session_id={session_id}, oneid={oneid}")
        return session

    def get_session(self, session_id: str) -> SessionContext:
        if self._redis_available():
            try:
                data = redis_client.get(self._get_redis_key(session_id))
                if data:
                    session = SessionContext.from_dict(json.loads(data))
                    if session.is_expired:
                        self.delete_session(session_id)
                        raise SessionExpiredError(f"会话已过期: {session_id}")
                    return session
            except SessionExpiredError:
                raise
            except Exception as e:
                logger.error(f"从Redis获取会话失败: {e}")
        
        if session_id in self._memory_cache:
            session = self._memory_cache[session_id]
            if session.is_expired:
                self.delete_session(session_id)
                raise SessionExpiredError(f"会话已过期: {session_id}")
            return session
        
        raise SessionNotFoundError(f"会话不存在: {session_id}")

    def save_session(self, session: SessionContext):
        if session.is_expired:
            session.status = SessionStatus.EXPIRED
        
        if self._redis_available():
            try:
                redis_client.set(
                    self._get_redis_key(session.session_id),
                    json.dumps(session.to_dict(), ensure_ascii=False),
                    expire=self._expiry_seconds
                )
            except Exception as e:
                logger.error(f"保存会话到Redis失败: {e}")
                self._memory_cache[session.session_id] = session
        else:
            self._memory_cache[session.session_id] = session
        
        logger.debug(f"保存会话: session_id={session.session_id}, status={session.status}")

    def delete_session(self, session_id: str):
        if self._redis_available():
            try:
                redis_client.delete(self._get_redis_key(session_id))
            except Exception as e:
                logger.error(f"从Redis删除会话失败: {e}")
        
        if session_id in self._memory_cache:
            del self._memory_cache[session_id]
        
        logger.info(f"删除会话: session_id={session_id}")

    def get_session_by_oneid(self, oneid: str) -> Optional[SessionContext]:
        if self._redis_available() and redis_client.client:
            try:
                keys = redis_client.client.keys(f"{self._redis_prefix}*")
                for key in keys:
                    data = redis_client.get(key)
                    if data:
                        session_data = json.loads(data)
                        if session_data.get("oneid") == oneid:
                            return SessionContext.from_dict(session_data)
            except Exception as e:
                logger.error(f"从Redis查询会话失败: {e}")
        
        for session in self._memory_cache.values():
            if session.oneid == oneid and session.status == SessionStatus.ACTIVE:
                return session
        
        return None

    def clear_expired_sessions(self):
        expired_ids = []
        
        if self._redis_available() and redis_client.client:
            try:
                keys = redis_client.client.keys(f"{self._redis_prefix}*")
                for key in keys:
                    data = redis_client.get(key)
                    if data:
                        session_data = json.loads(data)
                        session = SessionContext.from_dict(session_data)
                        if session.is_expired:
                            expired_ids.append(session.session_id)
                            redis_client.delete(key)
            except Exception as e:
                logger.error(f"清理Redis过期会话失败: {e}")
        
        for session_id in list(self._memory_cache.keys()):
            session = self._memory_cache[session_id]
            if session.is_expired:
                expired_ids.append(session_id)
                del self._memory_cache[session_id]
        
        if expired_ids:
            logger.info(f"清理过期会话: {len(expired_ids)}个")

    def get_active_sessions_count(self) -> int:
        if self._redis_available() and redis_client.client:
            try:
                return len(redis_client.client.keys(f"{self._redis_prefix}*"))
            except Exception:
                pass
        return len(self._memory_cache)

    def get_stats(self) -> Dict[str, Any]:
        active_count = 0
        ended_count = 0
        expired_count = 0
        
        for session in self._memory_cache.values():
            if session.status == SessionStatus.ACTIVE:
                active_count += 1
            elif session.status == SessionStatus.ENDED:
                ended_count += 1
            elif session.status == SessionStatus.EXPIRED:
                expired_count += 1
        
        return {
            "total": len(self._memory_cache),
            "active": active_count,
            "ended": ended_count,
            "expired": expired_count
        }

    def list_sessions(self) -> List[SessionContext]:
        return list(self._memory_cache.values())


session_manager = SessionManager()