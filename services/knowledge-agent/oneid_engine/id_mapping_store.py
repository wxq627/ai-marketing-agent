"""
ID 映射存储层 — id_mapping_store.py
=====================================
提供 id_mapping 表的 CRUD 操作。生产环境对接 PostgreSQL，
当前使用 CSV 文件 + 内存缓存实现（可直接替换为数据库实现）。

表结构:
  id          BIGINT       自增主键
  oneid       VARCHAR(32)  全局唯一客户 ID (如 UID000001)
  id_type     VARCHAR(16)  ID 类型: id_card/phone/card_no/device_id/open_id/crm_id/cust_id
  id_value    VARCHAR(128) ID 值
  confidence  DECIMAL(3,2) 映射置信度 (0.00 ~ 1.00)
  source_system VARCHAR(32) 来源系统: 银行核心/CRM/APP埋点/ASR系统
  first_seen  DATETIME     首次发现时间
  last_updated DATETIME    最后更新时间
  is_active   BOOLEAN      是否仍有效
"""

import os
import pandas as pd
from datetime import datetime
from typing import Optional, List, Dict, Any

# 默认数据路径
DEFAULT_MAPPING_PATH = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
    "mock_data", "structured", "id_mapping.csv"
)

# ID 类型 → 置信度映射表
CONFIDENCE_MAP = {
    "id_card":    1.00,   # 强 ID — 绝对唯一
    "card_no":    1.00,   # 中 ID — 与身份强绑定
    "phone":      0.95,   # 中 ID — 可能换号
    "crm_id":     1.00,   # 中 ID — 与身份强绑定
    "cust_id":    1.00,   # 中 ID — 银行核心系统
    "device_id":  0.90,   # 弱 ID — 可能换设备
    "open_id":    0.90,   # 弱 ID — 微信/支付宝
}


class IdMappingStore:
    """ID 映射存储 — 支持 CSV/内存/数据库 三种后端。"""

    def __init__(self, csv_path: str = None):
        self.csv_path = csv_path or DEFAULT_MAPPING_PATH
        self._records: List[Dict] = []
        self._oneid_to_ids: Dict[str, List[Dict]] = {}   # oneid → [id records]
        self._id_to_oneid: Dict[str, Dict[str, Any]] = {} # (type,value) → mapping record
        self._next_oneid_seq = 0
        self._loaded = False

    def load(self) -> "IdMappingStore":
        """从 CSV 加载映射数据到内存。"""
        if self._loaded:
            return self
        if os.path.exists(self.csv_path):
            df = pd.read_csv(self.csv_path)
            for _, row in df.iterrows():
                rec = row.to_dict()
                self._records.append(rec)
                oneid = rec["oneid"]
                if oneid not in self._oneid_to_ids:
                    self._oneid_to_ids[oneid] = []
                self._oneid_to_ids[oneid].append(rec)
                key = (rec["id_type"], rec["id_value"])
                self._id_to_oneid[key] = rec
            # 解析最大 oneid 序号
            seqs = [int(r["oneid"].replace("UID", "")) for r in self._records if r["oneid"].startswith("UID")]
            self._next_oneid_seq = max(seqs) + 1 if seqs else 1
        self._loaded = True
        return self

    def _generate_oneid(self) -> str:
        """生成新的唯一 OneID。"""
        uid = f"UID{self._next_oneid_seq:06d}"
        self._next_oneid_seq += 1
        return uid

    def resolve(self, id_type: str, id_value: str) -> Optional[Dict[str, Any]]:
        """根据任意 ID 查询对应的 OneID。"""
        self.load()
        rec = self._id_to_oneid.get((id_type, id_value))
        if rec is None or not rec.get("is_active", True):
            return None
        return {
            "oneid": rec["oneid"],
            "resolved_from": {"type": id_type, "value": id_value},
            "confidence": rec.get("confidence", CONFIDENCE_MAP.get(id_type, 0.80)),
            "all_known_ids": self.get_all_ids(rec["oneid"]),
            "is_verified": rec.get("confidence", 0) >= 0.95,
        }

    def get_all_ids(self, oneid: str) -> List[Dict[str, Any]]:
        """获取某个 OneID 下的所有已知 ID。"""
        self.load()
        records = self._oneid_to_ids.get(oneid, [])
        return [
            {
                "type": r["id_type"],
                "value": r["id_value"],
                "confidence": r.get("confidence", CONFIDENCE_MAP.get(r["id_type"], 0.80)),
                "source_system": r.get("source_system", ""),
            }
            for r in records
            if r.get("is_active", True)
        ]

    def add_mapping(self, oneid: str, id_type: str, id_value: str,
                    confidence: float = None, source_system: str = "") -> Dict[str, Any]:
        """添加一条新的 ID 映射记录。"""
        self.load()
        if confidence is None:
            confidence = CONFIDENCE_MAP.get(id_type, 0.80)

        now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        rec = {
            "id": len(self._records) + 1,
            "oneid": oneid,
            "id_type": id_type,
            "id_value": id_value,
            "confidence": confidence,
            "source_system": source_system,
            "first_seen": now,
            "last_updated": now,
            "is_active": True,
        }
        self._records.append(rec)
        if oneid not in self._oneid_to_ids:
            self._oneid_to_ids[oneid] = []
        self._oneid_to_ids[oneid].append(rec)
        self._id_to_oneid[(id_type, id_value)] = rec
        return rec

    def update_mapping(self, id_type: str, id_value: str, new_oneid: str):
        """更新某条 ID 映射的 OneID 归属。"""
        self.load()
        key = (id_type, id_value)
        if key in self._id_to_oneid:
            old_rec = self._id_to_oneid[key]
            old_oneid = old_rec["oneid"]
            # 从旧 oneid 移除
            if old_oneid in self._oneid_to_ids:
                self._oneid_to_ids[old_oneid] = [
                    r for r in self._oneid_to_ids[old_oneid]
                    if r["id_value"] != id_value or r["id_type"] != id_type
                ]
            # 更新
            old_rec["oneid"] = new_oneid
            old_rec["last_updated"] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            # 加入新 oneid
            if new_oneid not in self._oneid_to_ids:
                self._oneid_to_ids[new_oneid] = []
            self._oneid_to_ids[new_oneid].append(old_rec)
            self._id_to_oneid[key] = old_rec

    def find_conflicts(self) -> List[Dict[str, Any]]:
        """检测冲突: 同一个 ID 值被映射到多个 OneID。"""
        self.load()
        value_to_oneids: Dict[str, set] = {}
        for rec in self._records:
            if not rec.get("is_active", True):
                continue
            key = rec["id_value"]
            if key not in value_to_oneids:
                value_to_oneids[key] = set()
            value_to_oneids[key].add(rec["oneid"])
        return [
            {"id_value": v, "oneids": list(oids), "count": len(oids)}
            for v, oids in value_to_oneids.items()
            if len(oids) > 1
        ]

    def save(self):
        """将内存中的映射数据写回 CSV。"""
        if self._records:
            df = pd.DataFrame(self._records)
            os.makedirs(os.path.dirname(self.csv_path), exist_ok=True)
            df.to_csv(self.csv_path, index=False, encoding="utf-8-sig")

    def stats(self) -> Dict[str, Any]:
        """统计信息。"""
        self.load()
        return {
            "total_mappings": len(self._records),
            "unique_oneids": len(self._oneid_to_ids),
            "active_mappings": sum(1 for r in self._records if r.get("is_active", True)),
            "id_types": {
                t: sum(1 for r in self._records if r["id_type"] == t)
                for t in set(r["id_type"] for r in self._records)
            },
        }
