"""
OneID FastAPI 路由 — router_id.py
===================================
提供 OneID 解析的 REST API 接口。

接口清单:
  GET  /api/v1/oneid/resolve         — OneID 解析 (根据任意 ID 查 OneID)
  POST /api/v1/oneid/register        — 注册新客户 ID 映射
  POST /api/v1/oneid/batch-register  — 批量注册
  GET  /api/v1/oneid/{oneid}/ids     — 获取指定 OneID 的所有已知 ID
  POST /api/v1/oneid/merge           — 手动合并两个 OneID
  GET  /api/v1/oneid/stats           — 引擎统计信息
  GET  /api/v1/oneid/conflicts       — 查看冲突日志
"""

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel, Field
from typing import List, Dict, Optional
from .id_resolver import OneIdResolver
from .id_mapping_store import IdMappingStore
from .conflict_detector import ConflictDetector

router = APIRouter(prefix="/api/v1/oneid", tags=["OneID"])

# 全局单例
_resolver: OneIdResolver = None


def get_resolver() -> OneIdResolver:
    global _resolver
    if _resolver is None:
        _resolver = OneIdResolver(
            store=IdMappingStore(),
            detector=ConflictDetector(),
        )
    return _resolver


# ================================================================
# Pydantic 模型
# ================================================================

class ResolveResponse(BaseModel):
    oneid: Optional[str]
    resolved_from: Dict[str, str]
    confidence: float
    all_known_ids: List[Dict]
    customer_name: Optional[str] = None
    is_verified: bool
    error: Optional[str] = None


class RegisterRequest(BaseModel):
    ids: Dict[str, str] = Field(..., description="{id_type: id_value}, 如 {id_card: '4403****001', phone: '138****8888'}")
    source_system: str = "api"
    customer_name: str = ""


class RegisterResponse(BaseModel):
    oneid: str
    is_new: bool
    ids_registered: int
    conflicts: List[Dict] = []
    all_known_ids: List[Dict] = []


class BatchRegisterRequest(BaseModel):
    records: List[Dict[str, str]] = Field(..., description="批量客户ID记录")
    source_system: str = "api"


class MergeRequest(BaseModel):
    oneid_a: str
    oneid_b: str


class StatsResponse(BaseModel):
    mapping: Dict
    conflicts: Dict
    id_confidence_map: Dict


# ================================================================
# API-01: OneID 解析
# ================================================================

@router.get("/resolve", response_model=ResolveResponse,
            summary="OneID 解析 — 根据任意 ID 查询全局唯一客户标识",
            description="支持 id_card / phone / card_no / device_id / open_id / crm_id / cust_id 七种 ID 类型")
def resolve_oneid(
    type: str = Query(..., description="ID 类型",
                      regex="^(id_card|phone|card_no|device_id|open_id|crm_id|cust_id)$"),
    value: str = Query(..., description="ID 值"),
):
    """根据任意 ID 查询对应的 OneID。"""
    resolver = get_resolver()
    result = resolver.resolve(id_type=type, id_value=value)
    if result.get("error"):
        raise HTTPException(status_code=404, detail=result["error"])
    return result


# ================================================================
# API-02: 注册新客户 ID
# ================================================================

@router.post("/register", response_model=RegisterResponse,
             summary="注册新客户 ID 映射",
             description="为一条新的客户记录建立 OneID 映射。自动检测冲突。")
def register_ids(req: RegisterRequest):
    resolver = get_resolver()
    result = resolver.register(
        ids=req.ids,
        source_system=req.source_system,
        customer_name=req.customer_name,
    )
    return result


# ================================================================
# API-03: 批量注册
# ================================================================

@router.post("/batch-register",
             summary="批量注册客户 ID 映射")
def batch_register(req: BatchRegisterRequest):
    resolver = get_resolver()
    results = resolver.register_batch(
        id_records=req.records,
        source_system=req.source_system,
    )
    return {"total": len(results), "new": sum(1 for r in results if r["is_new"]), "results": results}


# ================================================================
# API-04: 获取某 OneID 的所有 ID
# ================================================================

@router.get("/{oneid}/ids",
            summary="获取指定 OneID 的所有已知 ID")
def get_oneid_ids(oneid: str):
    resolver = get_resolver()
    ids = resolver.store.get_all_ids(oneid)
    if not ids:
        raise HTTPException(status_code=404, detail=f"OneID not found: {oneid}")
    return {"oneid": oneid, "ids": ids, "count": len(ids)}


# ================================================================
# API-05: 手动合并
# ================================================================

@router.post("/merge",
             summary="手动合并两个疑似重复的 OneID")
def merge_oneids(req: MergeRequest):
    resolver = get_resolver()
    result = resolver.detector.merge_duplicates(resolver.store, req.oneid_a, req.oneid_b)
    if result.get("merged"):
        resolver.store.save()
        resolver.detector.save_log()
    return result


# ================================================================
# API-06: 统计
# ================================================================

@router.get("/stats", response_model=StatsResponse,
            summary="引擎统计信息")
def get_stats():
    resolver = get_resolver()
    return resolver.stats()


# ================================================================
# API-07: 冲突日志
# ================================================================

@router.get("/conflicts",
            summary="查看 ID 映射冲突日志")
def get_conflicts():
    resolver = get_resolver()
    resolver.detector.load_log()
    return {
        "total": len(resolver.detector._logs),
        "auto_resolved": sum(1 for l in resolver.detector._logs if l.get("resolution") == "自动合并"),
        "pending_manual": sum(1 for l in resolver.detector._logs if l.get("resolution") == "人工确认"),
        "logs": resolver.detector._logs[-20:],  # 最近20条
    }
