"""
ID 冲突检测与处理模块 — conflict_detector.py
===============================================
检测 OneID 映射中的冲突并自动或人工解决。

冲突场景:
  1. 同一 ID 值被映射到两个不同的 OneID (如手机号换号后重新分配给新客户)
  2. 两个 OneID 通过不同 ID 链关联到同一自然人 (待去重合并)
  3. 弱 ID (设备ID) 因共享设备而关联到多人

解决策略:
  - 情况 A: 弱 ID 置信度低 → 自动更新为强 ID 锚定的 OneID
  - 情况 B: 强/中 ID 冲突 → 写入日志, 标记人工确认
"""

import os
import pandas as pd
from datetime import datetime
from typing import List, Dict, Any, Optional, Tuple

DEFAULT_LOG_PATH = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
    "mock_data", "structured", "id_mapping_log.csv"
)

# 高置信度阈值 — 低于此值的 ID 可被自动覆盖
AUTO_RESOLVE_THRESHOLD = 0.85


class ConflictDetector:
    """ID 映射冲突检测器。"""

    def __init__(self, log_path: str = None):
        self.log_path = log_path or DEFAULT_LOG_PATH
        self._logs: List[Dict] = []

    def detect(self, store) -> List[Dict[str, Any]]:
        """
        扫描映射表检测冲突。
        返回冲突列表: [{id_value, oneids, severity}]
        """
        conflicts = store.find_conflicts()
        for c in conflicts:
            # 判断严重性
            all_oids = c["oneids"]
            severities = []
            for oid in all_oids:
                ids = store.get_all_ids(oid)
                has_strong = any(i["type"] == "id_card" for i in ids)
                severities.append("strong" if has_strong else "weak")
            c["severity"] = "critical" if sum(1 for s in severities if s == "strong") > 1 else "warning"
        return conflicts

    def resolve_conflict(self, store,
                         id_value: str,
                         current_oneid: str,
                         target_oneid: str,
                         reason: str = "auto_merge") -> Tuple[str, Dict]:
        """
        解决冲突: 将 id_value 的映射从 current_oneid 迁移到 target_oneid。

        返回 (resolution, log_entry)
        """
        # 查询当前映射信息
        current_ids = store.get_all_ids(current_oneid)
        target_ids = store.get_all_ids(target_oneid)

        # 获取冲突ID的信息
        conflict_rec = store._id_to_oneid.get(("phone", id_value)) or \
                        store._id_to_oneid.get(("device_id", id_value))
        old_confidence = conflict_rec.get("confidence", 0.0) if conflict_rec else 0.0

        # 决策逻辑
        if old_confidence < AUTO_RESOLVE_THRESHOLD:
            resolution = "自动合并"
            store.update_mapping(conflict_rec["id_type"], id_value, target_oneid)
        else:
            resolution = "人工确认"
            # 不自动更新，仅记录日志

        # 记录日志
        log_entry = {
            "log_id": f"LOG_{len(self._logs)+1:06d}",
            "id_value": id_value,
            "old_oneid": current_oneid,
            "new_oneid": target_oneid,
            "conflict_reason": reason,
            "resolution": resolution,
            "resolved_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        }
        self._logs.append(log_entry)
        return resolution, log_entry

    def merge_duplicates(self, store, oneid_a: str, oneid_b: str) -> Dict:
        """
        合并两个疑似重复的 OneID。
        当两个 OneID 共享同一个强 ID (身份证号) 时触发。
        """
        ids_a = store.get_all_ids(oneid_a)
        ids_b = store.get_all_ids(oneid_b)

        # 确认共享强 ID
        shared_strong = [
            i for i in ids_a
            if i["type"] == "id_card"
            and any(j["type"] == "id_card" and j["value"] == i["value"] for j in ids_b)
        ]

        if not shared_strong:
            return {"merged": False, "reason": "未找到共享强ID，无法自动合并"}

        # 将所有 oneid_b 的映射迁移到 oneid_a
        for id_rec in ids_b:
            store.update_mapping(id_rec["type"], id_rec["value"], oneid_a)

        log_entry = {
            "log_id": f"LOG_{len(self._logs)+1:06d}",
            "id_value": shared_strong[0]["value"],
            "old_oneid": oneid_b,
            "new_oneid": oneid_a,
            "conflict_reason": f"共享强ID(id_card={shared_strong[0]['value']}), 自动去重合并",
            "resolution": "自动合并",
            "resolved_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        }
        self._logs.append(log_entry)
        return {"merged": True, "from": oneid_b, "to": oneid_a, "shared_ids": len(shared_strong)}

    def save_log(self):
        """保存冲突日志到 CSV。"""
        if self._logs:
            df = pd.DataFrame(self._logs)
            os.makedirs(os.path.dirname(self.log_path), exist_ok=True)
            df.to_csv(self.log_path, index=False, encoding="utf-8-sig")

    def load_log(self) -> List[Dict]:
        """加载历史冲突日志。"""
        if os.path.exists(self.log_path):
            df = pd.read_csv(self.log_path)
            self._logs = df.to_dict(orient="records")
        return self._logs

    def stats(self) -> Dict[str, Any]:
        """冲突统计。"""
        return {
            "total_logs": len(self._logs),
            "auto_resolved": sum(1 for l in self._logs if l.get("resolution") == "自动合并"),
            "pending_manual": sum(1 for l in self._logs if l.get("resolution") == "人工确认"),
            "recent": self._logs[-3:] if self._logs else [],
        }
