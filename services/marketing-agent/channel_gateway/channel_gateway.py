"""
channel_gateway\channel_gateway.py
功能描述: 渠道网关模块，支持多渠道路由与分发，包含分发日志记录与状态回写
"""

import uuid
import json
from abc import ABC, abstractmethod
from typing import Dict, Any, Optional, List
from datetime import datetime
from pathlib import Path

from common import logger, ChannelError, ChannelNotFoundError, ChannelDeliveryError
from agent_orchestrator.schemas import DispatchResult, TouchLog


class ChannelSenderInterface(ABC):
    @abstractmethod
    def send(self, user_id: str, content: str, trace_id: str) -> DispatchResult:
        pass

    @abstractmethod
    def get_channel_name(self) -> str:
        pass


class MockPushChannel(ChannelSenderInterface):
    def send(self, user_id: str, content: str, trace_id: str) -> DispatchResult:
        logger.info(f"[MOCK] Push to {user_id}: {content}")
        success = True
        error_message = None
        
        return DispatchResult(
            success=success,
            trace_id=trace_id,
            channel=self.get_channel_name(),
            user_id=user_id,
            content=content,
            error_message=error_message
        )

    def get_channel_name(self) -> str:
        return "app_push"


class MockSMSChannel(ChannelSenderInterface):
    def send(self, user_id: str, content: str, trace_id: str) -> DispatchResult:
        logger.info(f"[MOCK] SMS to {user_id}: {content}")
        success = True
        error_message = None
        
        return DispatchResult(
            success=success,
            trace_id=trace_id,
            channel=self.get_channel_name(),
            user_id=user_id,
            content=content,
            error_message=error_message
        )

    def get_channel_name(self) -> str:
        return "sms"


class MockWechatChannel(ChannelSenderInterface):
    def send(self, user_id: str, content: str, trace_id: str) -> DispatchResult:
        logger.info(f"[MOCK] WeChat to {user_id}: {content}")
        success = True
        error_message = None
        
        return DispatchResult(
            success=success,
            trace_id=trace_id,
            channel=self.get_channel_name(),
            user_id=user_id,
            content=content,
            error_message=error_message
        )

    def get_channel_name(self) -> str:
        return "wechat"


class DispatchLog:
    def __init__(self, dispatch_id: str, trace_id: str, user_id: str, channel: str,
                 content: str, success: bool, error_message: Optional[str] = None):
        self.dispatch_id = dispatch_id
        self.trace_id = trace_id
        self.user_id = user_id
        self.channel = channel
        self.content = content
        self.success = success
        self.error_message = error_message
        self.dispatched_at = datetime.now()
        self.status = "success" if success else "failed"

    def to_dict(self) -> Dict[str, Any]:
        return {
            "dispatch_id": self.dispatch_id,
            "trace_id": self.trace_id,
            "user_id": self.user_id,
            "channel": self.channel,
            "content": self.content,
            "success": self.success,
            "status": self.status,
            "error_message": self.error_message,
            "dispatched_at": self.dispatched_at.isoformat()
        }


class ChannelGateway:
    def __init__(self):
        self._channels: Dict[str, ChannelSenderInterface] = {
            "app_push": MockPushChannel(),
            "sms": MockSMSChannel(),
            "wechat": MockWechatChannel()
        }
        self._dispatch_logs: List[DispatchLog] = []
        self._log_file_path = Path("./logs/dispatch_log.json")
        self._touch_logs: List[TouchLog] = []

    def register_channel(self, channel_name: str, sender: ChannelSenderInterface):
        self._channels[channel_name] = sender
        logger.info(f"注册渠道: {channel_name}")

    def dispatch(self, user_id: str, channel: str, content: str, 
                 trace_id: Optional[str] = None, campaign_id: Optional[str] = None) -> DispatchResult:
        if channel not in self._channels:
            raise ChannelNotFoundError(f"渠道不存在: {channel}")
        
        dispatch_id = str(uuid.uuid4())[:12]
        trace_id = trace_id or str(uuid.uuid4())
        
        try:
            sender = self._channels[channel]
            result = sender.send(user_id, content, trace_id)
            
            self._log_dispatch(dispatch_id, trace_id, user_id, channel, content, True, None)
            self._write_touch_log(user_id, campaign_id, channel, "push", content, "success", trace_id)
            
            logger.info(f"渠道分发成功: channel={channel}, user_id={user_id}, trace_id={result.trace_id}, dispatch_id={dispatch_id}")
            return result
            
        except Exception as e:
            error_msg = str(e)
            self._log_dispatch(dispatch_id, trace_id, user_id, channel, content, False, error_msg)
            self._write_touch_log(user_id, campaign_id, channel, "push", content, "failed", trace_id)
            
            logger.error(f"渠道分发失败: {e}")
            raise ChannelDeliveryError(f"渠道投递失败: {e}")

    def _log_dispatch(self, dispatch_id: str, trace_id: str, user_id: str, channel: str,
                      content: str, success: bool, error_message: Optional[str]):
        log_entry = DispatchLog(dispatch_id, trace_id, user_id, channel, content, success, error_message)
        self._dispatch_logs.append(log_entry)
        
        self._persist_logs()
        logger.debug(f"分发日志已记录: dispatch_id={dispatch_id}, status={log_entry.status}")

    def _write_touch_log(self, oneid: str, campaign_id: Optional[str], channel: str,
                         touch_type: str, content: str, status: str, trace_id: str):
        touch_log = TouchLog(
            oneid=oneid,
            campaign_id=campaign_id or "unknown",
            channel=channel,
            touch_type=touch_type,
            content=content,
            status=status,
            trace_id=trace_id
        )
        self._touch_logs.append(touch_log)
        logger.debug(f"触达日志已记录: oneid={oneid}, channel={channel}, status={status}")

    def _persist_logs(self):
        try:
            self._log_file_path.parent.mkdir(parents=True, exist_ok=True)
            
            logs_data = [log.to_dict() for log in self._dispatch_logs[-100:]]
            
            with open(self._log_file_path, 'w', encoding='utf-8') as f:
                json.dump(logs_data, f, ensure_ascii=False, indent=2)
                
        except Exception as e:
            logger.error(f"保存分发日志失败: {e}")

    def get_dispatch_logs(self, limit: int = 50) -> List[Dict[str, Any]]:
        return [log.to_dict() for log in self._dispatch_logs[-limit:]]

    def get_touch_logs(self, oneid: Optional[str] = None, limit: int = 50) -> List[Dict[str, Any]]:
        logs = self._touch_logs
        if oneid:
            logs = [log for log in logs if log.oneid == oneid]
        return [log.model_dump() for log in logs[-limit:]]

    def get_available_channels(self) -> list:
        return list(self._channels.keys())

    def get_dispatch_stats(self) -> Dict[str, Any]:
        total = len(self._dispatch_logs)
        success_count = sum(1 for log in self._dispatch_logs if log.success)
        failed_count = total - success_count
        
        channel_stats = {}
        for log in self._dispatch_logs:
            if log.channel not in channel_stats:
                channel_stats[log.channel] = {"total": 0, "success": 0, "failed": 0}
            channel_stats[log.channel]["total"] += 1
            if log.success:
                channel_stats[log.channel]["success"] += 1
            else:
                channel_stats[log.channel]["failed"] += 1
        
        return {
            "total_dispatches": total,
            "success_count": success_count,
            "failed_count": failed_count,
            "success_rate": success_count / total if total > 0 else 0,
            "channel_stats": channel_stats
        }


gateway = ChannelGateway()