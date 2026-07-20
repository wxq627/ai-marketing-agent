"""
OneID 核心解析引擎 — id_resolver.py
=====================================
实现 OneID 生成与解析算法（确定性、可复现）。

算法流程:
  步骤1: 检查强 ID (身份证号) → 存在则返回已有 OneID, 否则分配新 OneID
  步骤2: 处理中/弱 ID → 逐个检查是否存在, 关联到已有 OneID 或新建映射
  步骤3: 冲突检测 → 弱 ID 被映射到不同 OneID 时自动或人工处理
  步骤4: 定期去重 → 两个 OneID 共享同一身份证号时自动合并

ID 分级:
  强 ID: id_card (100% 确定性, OneID 锚点)
  中 ID: cust_id, card_no, crm_id (100% 确定性, 银行系统强关联)
  中 ID: phone (95% 确定性, 可能换号)
  弱 ID: device_id, open_id (90% 确定性, 可能换设备/多人共用)
"""

from typing import Optional, Dict, Any, List
from .id_mapping_store import IdMappingStore, CONFIDENCE_MAP
from .conflict_detector import ConflictDetector


class OneIdResolver:
    """OneID 统一解析引擎 — 核心算法实现。"""

    def __init__(self, store: IdMappingStore = None, detector: ConflictDetector = None):
        self.store = store or IdMappingStore()
        self.detector = detector or ConflictDetector()
        self.store.load()

    # ================================================================
    # 核心算法: OneID 解析
    # ================================================================

    def resolve(self, id_type: str, id_value: str) -> Dict[str, Any]:
        """
        根据任意 ID 查询 OneID — 主入口。

        参数:
          id_type  : id_card / phone / card_no / device_id / open_id / crm_id / cust_id
          id_value : ID 值

        返回:
          {
            "oneid": "UID000001",
            "resolved_from": {"type": "phone", "value": "138****8888"},
            "confidence": 0.95,
            "all_known_ids": [...],
            "customer_name": "张*明",
            "is_verified": true
          }
        """
        result = self.store.resolve(id_type, id_value)
        if result is None:
            return {
                "oneid": None,
                "resolved_from": {"type": id_type, "value": id_value},
                "confidence": 0.0,
                "all_known_ids": [],
                "customer_name": None,
                "is_verified": False,
                "error": f"ID not found: {id_type}={id_value}",
            }
        return result

    # ================================================================
    # 核心算法: OneID 注册 (为新数据建立映射)
    # ================================================================

    def register(self, ids: Dict[str, str],
                 source_system: str = "unknown",
                 customer_name: str = "") -> Dict[str, Any]:
        """
        注册一个新客户或更新已有客户的 ID 映射。

        参数:
          ids: {id_type: id_value, ...}
            例如: {"id_card": "4403****001", "phone": "138****8888",
                   "cust_id": "C000001", "card_no": "6225****01",
                   "crm_id": "CRM000001", "device_id": "DEV_A001"}
          source_system: 来源系统名称
          customer_name: 客户姓名

        返回:
          {"oneid": "UID000001", "is_new": false, "conflicts": [...]}
        """
        # ---- 步骤 1: 检查强 ID (身份证号) ----
        oneid = None
        id_card = ids.get("id_card")
        if id_card:
            existing = self.store.resolve("id_card", id_card)
            if existing and existing["oneid"]:
                oneid = existing["oneid"]

        # 若无身份证号，检查其他中 ID
        if oneid is None:
            for mid_type in ["cust_id", "card_no", "crm_id"]:
                mid_val = ids.get(mid_type)
                if mid_val:
                    existing = self.store.resolve(mid_type, mid_val)
                    if existing and existing["oneid"]:
                        oneid = existing["oneid"]
                        break

        # ---- 步骤 2: 分配新 OneID 或使用已有 ----
        is_new = False
        if oneid is None:
            oneid = self.store._generate_oneid()
            is_new = True

        # ---- 步骤 3: 逐 ID 建立映射 ----
        conflicts = []
        # 按确定性从高到低处理
        id_order = ["id_card", "cust_id", "card_no", "crm_id", "phone", "device_id", "open_id"]
        processed = 0

        for id_type in id_order:
            id_val = ids.get(id_type)
            if not id_val:
                continue

            # 检查是否已有映射
            existing = self.store.resolve(id_type, id_val)

            if existing is None:
                # 新 ID — 直接建立映射
                confidence = CONFIDENCE_MAP.get(id_type, 0.80)
                self.store.add_mapping(
                    oneid=oneid,
                    id_type=id_type,
                    id_value=id_val,
                    confidence=confidence,
                    source_system=source_system,
                )
            elif existing["oneid"] == oneid:
                # 已映射到同一 OneID — 跳过
                pass
            else:
                # ---- 步骤 3.1: 冲突! 此 ID 已映射到另一个 OneID ----
                conflict = self._handle_conflict(
                    id_type, id_val,
                    current_oneid=oneid,
                    existing_oneid=existing["oneid"],
                    source_system=source_system,
                )
                conflicts.append(conflict)

            processed += 1

        # ---- 步骤 4: 保存 ----
        if processed > 0:
            self.store.save()
            self.detector.save_log()

        return {
            "oneid": oneid,
            "is_new": is_new,
            "ids_registered": processed,
            "conflicts": conflicts,
            "all_known_ids": self.store.get_all_ids(oneid),
            "customer_name": customer_name,
        }

    # ================================================================
    # 内部: 冲突处理
    # ================================================================

    def _handle_conflict(self, id_type: str, id_value: str,
                         current_oneid: str, existing_oneid: str,
                         source_system: str) -> Dict[str, Any]:
        """
        处理 ID 映射冲突。

        策略:
          - 弱 ID (device_id, open_id) 置信度 < 0.85 → 自动迁移到新 OneID
          - 强/中 ID (id_card, phone, cust_id 等) → 记录日志, 标记人工确认
        """
        if id_type in ("device_id", "open_id"):
            # 弱 ID: 检查置信度
            existing_rec = self.store._id_to_oneid.get((id_type, id_value))
            old_conf = existing_rec.get("confidence", 0.80) if existing_rec else 0.80

            if old_conf < 0.85:
                # 自动迁移
                resolution, log = self.detector.resolve_conflict(
                    self.store, id_value, existing_oneid, current_oneid,
                    reason=f"弱ID({id_type})置信度低({old_conf}), 自动迁移至{current_oneid}"
                )
                return {"id": id_value, "type": id_type, "action": "auto_migrated",
                        "from": existing_oneid, "to": current_oneid, "resolution": resolution}
            else:
                # 置信度高, 保留原映射, 也建立新映射
                self.store.add_mapping(
                    oneid=current_oneid, id_type=id_type, id_value=id_value,
                    confidence=0.80, source_system=source_system,
                )
                return {"id": id_value, "type": id_type, "action": "dual_mapped",
                        "oneid_a": existing_oneid, "oneid_b": current_oneid,
                        "resolution": "保留原映射, 新映射标记低置信度"}

        # 强/中 ID: 记录日志待人工确认
        resolution, log = self.detector.resolve_conflict(
            self.store, id_value, existing_oneid, current_oneid,
            reason=f"中强ID({id_type})冲突: {existing_oneid} vs {current_oneid}"
        )
        return {"id": id_value, "type": id_type, "action": "pending_manual",
                "from": existing_oneid, "to": current_oneid, "resolution": resolution}

    # ================================================================
    # 工具: 批量注册 + 统计
    # ================================================================

    def register_batch(self, id_records: List[Dict[str, str]],
                       source_system: str = "batch") -> List[Dict]:
        """批量注册客户 ID 映射。"""
        results = []
        for i, ids in enumerate(id_records):
            name = ids.pop("name", f"Customer_{i}")
            result = self.register(ids, source_system=source_system, customer_name=name)
            results.append(result)
        return results

    def stats(self) -> Dict[str, Any]:
        """引擎统计信息。"""
        return {
            "mapping": self.store.stats(),
            "conflicts": self.detector.stats(),
            "id_confidence_map": CONFIDENCE_MAP,
        }

    def find_duplicates(self) -> List[Dict]:
        """
        定期去重: 检测两个 OneID 是否共享同一个强 ID。
        如发现 → 自动合并。
        """
        conflicts = self.store.find_conflicts()
        merged = []
        for c in conflicts:
            # 只关注 id_card 级别冲突
            oids = c["oneids"]
            if len(oids) <= 1:
                continue
            # 尝试合并不同的 oneid
            for i in range(len(oids)):
                for j in range(i + 1, len(oids)):
                    result = self.detector.merge_duplicates(self.store, oids[i], oids[j])
                    if result.get("merged"):
                        merged.append(result)
        if merged:
            self.store.save()
            self.detector.save_log()
        return merged
