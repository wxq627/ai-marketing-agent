"""
GraphRAG 知识检索 API — router_knowledge.py
=============================================
POST /api/v1/knowledge/search  — 完整 GraphRAG 检索
GET  /api/v1/knowledge/graph/{entity_id} — 查询子图
POST /api/v1/knowledge/path — 查找两实体间路径
"""
import os, sys, json
from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel, Field
from typing import List, Dict, Optional

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from graphrag.retrieval import full_search
from graphrag.kg_builder import get_kg

router = APIRouter(tags=["GraphRAG"])


class SearchRequest(BaseModel):
    query: str
    customer_oneid: Optional[str] = None
    top_k: int = 10
    include_graph: bool = True
    include_vector: bool = True

class PathRequest(BaseModel):
    from_id: str
    to_id: str


@router.post("/search", summary="GraphRAG 知识检索（图谱+向量+合规融合）")
def knowledge_search(req: SearchRequest):
    """输入自然语言查询, 返回图谱+向量+合规融合的检索结果。"""
    result = full_search(
        query=req.query,
        customer_id=req.customer_oneid,
        top_k=req.top_k,
        include_graph=req.include_graph,
        include_vector=req.include_vector,
    )
    return result


@router.get("/graph/{entity_id}", summary="查询实体子图")
def get_subgraph(entity_id: str, depth: int = Query(2, ge=1, le=4)):
    kg = get_kg()
    if not kg.G.has_node(entity_id):
        raise HTTPException(404, f"Entity not found: {entity_id}")
    return kg.get_subgraph(entity_id, depth)


@router.post("/path", summary="查找两实体间最短路径")
def find_path(req: PathRequest):
    kg = get_kg()
    path = kg.find_path(req.from_id, req.to_id)
    if path is None:
        return {"found": False, "path": [], "message": f"No path between {req.from_id} and {req.to_id}"}
    return {"found": True, "path": path, "length": len(path)}


@router.get("/stats", summary="知识图谱统计")
def kg_stats():
    kg = get_kg()
    return kg.stats()
