"""
feedback_collector\data_reflow.py
功能描述: 数据回流队列，调用项目一（知识引擎）和项目二（策略优化）接口
"""

import json
import uuid
import urllib.request
import urllib.error
from typing import List, Dict, Any, Optional
from datetime import datetime
from pathlib import Path
from abc import ABC, abstractmethod
from .models import ReflowRecord, ReflowStatus
from common import logger, feedback_config
from common.errors import FeedbackError


class ProjectInterface(ABC):
    @abstractmethod
    def send(self, data: Dict[str, Any]) -> bool:
        pass

    @abstractmethod
    def get_status(self) -> Dict[str, Any]:
        pass

    @property
    @abstractmethod
    def project_name(self) -> str:
        pass


class ProjectOneInterface(ProjectInterface):
    """项目一接口：知识引擎（客户洞察系统）"""

    def __init__(self):
        self._api_base = feedback_config.KE_FEEDBACK_URL
        self._timeout = feedback_config.KE_FEEDBACK_TIMEOUT

    @property
    def project_name(self) -> str:
        return "project_one"

    def send(self, data: Dict[str, Any]) -> bool:
        try:
            if data.get("event_type") == "conversation":
                url = f"{self._api_base}/api/v1/feedback/events"
            else:
                url = f"{self._api_base}/api/v1/feedback/events"

            event_type = data.get("event_type", "")
            event_type_mapping = {
                "user_click": "click",
                "user_reject": "dismiss",
                "interaction": "click"
            }
            ke_event_type = event_type_mapping.get(event_type, event_type)

            payload = {
                "oneid": data.get("oneid", "") or "",
                "event_type": ke_event_type,
                "campaign_id": data.get("campaign_id", "") or "",
                "channel": data.get("channel", "") or "",
                "timestamp": data.get("timestamp", datetime.now().isoformat()),
                "detail": data.get("detail", {})
            }

            req = urllib.request.Request(
                url,
                data=json.dumps(payload, ensure_ascii=False).encode("utf-8"),
                headers={"Content-Type": "application/json"},
                method="POST"
            )

            with urllib.request.urlopen(req, timeout=self._timeout) as resp:
                result = json.loads(resp.read().decode("utf-8"))
                logger.info(f"项目一回流成功: url={url}, event_type={data.get('event_type')}")
                self._persist_reflow(data, result, True)
                return True

        except urllib.error.HTTPError as e:
            error_msg = f"HTTP错误: {e.code} - {e.read().decode()[:200]}"
            logger.error(f"项目一回流失败: {error_msg}")
            self._persist_reflow(data, {"error": error_msg}, False)
            return False
        except Exception as e:
            logger.error(f"项目一回流失败: {e}")
            self._persist_reflow(data, {"error": str(e)}, False)
            return False

    def get_status(self) -> Dict[str, Any]:
        return {
            "project": "project_one",
            "name": "知识引擎",
            "status": "online",
            "api_base": self._api_base,
            "last_sync_time": datetime.now().isoformat()
        }

    def _persist_reflow(self, data: Dict[str, Any], response: Dict[str, Any], success: bool):
        file_path = Path("./logs/project_one_reflow.json")
        file_path.parent.mkdir(parents=True, exist_ok=True)

        records = []
        if file_path.exists():
            try:
                with open(file_path, 'r', encoding='utf-8') as f:
                    records = json.load(f)
            except json.JSONDecodeError:
                records = []

        records.append({
            "data": data,
            "response": response,
            "success": success,
            "timestamp": datetime.now().isoformat()
        })

        with open(file_path, 'w', encoding='utf-8') as f:
            json.dump(records, f, ensure_ascii=False, indent=2)


class ProjectTwoInterface(ProjectInterface):
    """项目二接口：策略优化系统"""

    def __init__(self):
        self._api_base = feedback_config.SA_FEEDBACK_URL
        self._timeout = feedback_config.SA_FEEDBACK_TIMEOUT

    @property
    def project_name(self) -> str:
        return "project_two"

    def send(self, data: Dict[str, Any]) -> bool:
        try:
            url = f"{self._api_base}/api/feedback"

            req = urllib.request.Request(
                url,
                data=json.dumps(data, ensure_ascii=False).encode("utf-8"),
                headers={"Content-Type": "application/json"},
                method="POST"
            )

            with urllib.request.urlopen(req, timeout=self._timeout) as resp:
                result = json.loads(resp.read().decode("utf-8"))
                logger.info(f"项目二回流成功: url={url}, campaign_id={data.get('campaign_id')}")
                self._persist_reflow(data, result, True)
                return True

        except urllib.error.HTTPError as e:
            error_msg = f"HTTP错误: {e.code} - {e.read().decode()[:200]}"
            logger.error(f"项目二回流失败: {error_msg}")
            self._persist_reflow(data, {"error": error_msg}, False)
            return False
        except Exception as e:
            logger.error(f"项目二回流失败: {e}")
            self._persist_reflow(data, {"error": str(e)}, False)
            return False

    def get_status(self) -> Dict[str, Any]:
        return {
            "project": "project_two",
            "name": "策略优化系统",
            "status": "online",
            "api_base": self._api_base,
            "last_sync_time": datetime.now().isoformat()
        }

    def _persist_reflow(self, data: Dict[str, Any], response: Dict[str, Any], success: bool):
        file_path = Path("./logs/project_two_reflow.json")
        file_path.parent.mkdir(parents=True, exist_ok=True)

        records = []
        if file_path.exists():
            try:
                with open(file_path, 'r', encoding='utf-8') as f:
                    records = json.load(f)
            except json.JSONDecodeError:
                records = []

        records.append({
            "data": data,
            "response": response,
            "success": success,
            "timestamp": datetime.now().isoformat()
        })

        with open(file_path, 'w', encoding='utf-8') as f:
            json.dump(records, f, ensure_ascii=False, indent=2)


class DataReflowQueue:
    def __init__(self):
        self._queue: List[ReflowRecord] = []
        self._processed_records: Dict[str, ReflowRecord] = {}
        self._project_interfaces: Dict[str, ProjectInterface] = {
            "project_one": ProjectOneInterface(),
            "project_two": ProjectTwoInterface()
        }
        self._queue_file_path = Path("./logs/reflow_queue.json")

    def enqueue(self, source: str, target: str, data: Dict[str, Any]) -> ReflowRecord:
        if target not in self._project_interfaces:
            raise FeedbackError(f"目标项目不存在: {target}, 有效项目: {list(self._project_interfaces.keys())}")

        record = ReflowRecord(
            record_id=str(uuid.uuid4())[:12],
            source=source,
            target=target,
            data=data,
            status="pending",
            created_at=datetime.now()
        )

        self._queue.append(record)
        self._persist_queue()

        logger.info(f"数据回流入队: record_id={record.record_id}, target={target}")
        return record

    def process_next(self) -> Optional[ReflowRecord]:
        if not self._queue:
            return None

        record = self._queue.pop(0)
        target_interface = self._project_interfaces.get(record.target)

        if not target_interface:
            record.status = "failed"
            record.error_message = f"目标项目接口不存在: {record.target}"
            record.processed_at = datetime.now()
            self._processed_records[record.record_id] = record
            self._persist_queue()
            logger.error(record.error_message)
            return record

        try:
            success = target_interface.send(record.data)

            if success:
                record.status = "success"
                logger.info(f"数据回流处理成功: record_id={record.record_id}")
            else:
                record.status = "failed"
                record.error_message = "目标项目接口返回失败"
                logger.warning(f"数据回流处理失败: record_id={record.record_id}")

        except Exception as e:
            record.status = "failed"
            record.error_message = str(e)
            logger.error(f"数据回流处理异常: record_id={record.record_id}, error={str(e)}")

        record.processed_at = datetime.now()
        self._processed_records[record.record_id] = record
        self._persist_queue()

        return record

    def process_all(self) -> int:
        count = 0
        while self._queue:
            self.process_next()
            count += 1
        return count

    def get_status(self) -> ReflowStatus:
        pending = len(self._queue)
        success = sum(1 for r in self._processed_records.values() if r.status == "success")
        failed = sum(1 for r in self._processed_records.values() if r.status == "failed")

        last_processed = None
        for record in self._processed_records.values():
            if record.processed_at:
                if not last_processed or record.processed_at > last_processed:
                    last_processed = record.processed_at

        return ReflowStatus(
            total_count=len(self._processed_records) + pending,
            success_count=success,
            failed_count=failed,
            pending_count=pending,
            last_processed_at=last_processed
        )

    def get_record(self, record_id: str) -> Optional[ReflowRecord]:
        for record in self._queue:
            if record.record_id == record_id:
                return record
        return self._processed_records.get(record_id)

    def get_project_status(self, project_name: str) -> Optional[Dict[str, Any]]:
        interface = self._project_interfaces.get(project_name)
        if interface:
            return interface.get_status()
        return None

    def _persist_queue(self):
        self._queue_file_path.parent.mkdir(parents=True, exist_ok=True)

        queue_data = [record.model_dump() for record in self._queue]
        processed_data = [record.model_dump() for record in self._processed_records.values()]

        data = {
            "queue": queue_data,
            "processed": processed_data
        }

        with open(self._queue_file_path, 'w', encoding='utf-8') as f:
            json.dump(data, f, ensure_ascii=False, indent=2, default=str)

    def get_recent_events(self, limit: int = 20) -> List[Dict[str, Any]]:
        all_records = list(self._processed_records.values())
        all_records.sort(key=lambda r: r.processed_at or r.created_at, reverse=True)
        
        events = []
        for record in all_records[:limit]:
            data = record.data
            
            if record.target == "project_two":
                detail_data = {
                    "feedback_metrics": data.get("feedback_metrics", {}),
                    "channel_attribution": data.get("channel_attribution", []),
                    "segment_performance": data.get("segment_performance", []),
                    "conversation_outcome": data.get("conversation_outcome", {})
                }
            else:
                detail_data = data.get("detail", {})
            
            events.append({
                "record_id": record.record_id,
                "event_type": data.get("event_type", ""),
                "oneid": data.get("oneid", ""),
                "campaign_id": data.get("campaign_id", ""),
                "channel": data.get("channel", ""),
                "target": record.target,
                "status": record.status,
                "detail": detail_data,
                "timestamp": (record.processed_at or record.created_at).isoformat() if record.processed_at or record.created_at else ""
            })
        
        return events


data_reflow_queue = DataReflowQueue()
