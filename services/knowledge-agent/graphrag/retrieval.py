"""
GraphRAG 检索层 — retrieval.py
=================================
① 图谱检索 (graph_retriever): 从知识图谱遍历实体关系
② 向量检索 (vector_retriever): TF-IDF 文档片段相似匹配
③ 融合排序 (fusion): 相关性+新鲜度+权威性加权去重

Source types: graph, vector, compliance
"""
import os
from typing import List, Dict, Any, Optional
from datetime import datetime
from .kg_builder import get_kg
from .doc_pipeline import get_pipeline

REF_DATE = datetime(2026, 7, 17)


def graph_retrieve(query: str, customer_id: str = None, top_k: int = 5) -> List[Dict]:
    """第一步: 知识图谱检索。"""
    kg = get_kg()
    results = []

    # 1. 客户上下文检索
    if customer_id and kg.G.has_node(customer_id):
        subgraph = kg.get_subgraph(customer_id, depth=2)
        relations = kg.traverse_relations(customer_id)
        for r in relations[:top_k]:
            info = r.get("info", {})
            entity_name = info.get("name", r["entity"])
            entity_type = info.get("type", "unknown")
            results.append({
                "source_type": "graph",
                "content": f"{entity_name} ({entity_type}) — 关系: {r['relation']}",
                "source_doc": f"knowledge_graph/{entity_type}",
                "relevance_score": 0.90,
                "entity_path": [customer_id, r["entity"]],
                "entity_type": entity_type,
            })

    # 2. 产品和权益实体匹配 (中文用字符包含匹配)
    for n, d in kg.G.nodes(data=True):
        node_type = d.get("type", "")
        node_name = str(d.get("name", ""))
        if node_type in ("product", "benefit", "campaign", "installment_rule"):
            # 中文: 检查 query 中的关键词是否在 node_name 中
            matched = False
            # 提取 query 中的2-4字关键词
            for kw_len in [4, 3, 2]:
                for i in range(len(query)-kw_len+1):
                    kw = query[i:i+kw_len]
                    if kw in node_name:
                        matched = True
                        break
                if matched: break
            # 也检查 node_name 中的词是否在 query 中
            if not matched:
                for kw_len in [4, 3, 2]:
                    for i in range(len(node_name)-kw_len+1):
                        if node_name[i:i+kw_len] in query:
                            matched = True
                            break
                    if matched: break
            if matched:
                results.append({
                    "source_type": "graph",
                    "content": f"{node_name} ({node_type}) — {d.get('category','')} {d.get('card_level','')}",
                    "source_doc": f"knowledge_graph/{node_type}",
                    "relevance_score": 0.85,
                    "entity_type": node_type,
                })

    # 去重 + 排序
    seen = set()
    unique = []
    for r in sorted(results, key=lambda x: x["relevance_score"], reverse=True):
        key = r["content"][:50]
        if key not in seen:
            seen.add(key)
            unique.append(r)
    return unique[:top_k]


def vector_retrieve(query: str, top_k: int = 5) -> List[Dict]:
    """第二步: 向量检索 (TF-IDF 文档片段)。"""
    pipeline = get_pipeline()
    results = pipeline.search(query, top_k=top_k)
    for r in results:
        r["source_type"] = "vector"
        r["source_doc"] = r.get("doc_name", "")
    return results


def compliance_retrieve(query: str) -> List[Dict]:
    """合规规则检索。"""
    import json
    rules_path = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                              "mock_data", "unstructured", "compliance_rules.json")
    results = []
    if os.path.exists(rules_path):
        with open(rules_path, "r", encoding="utf-8") as f:
            rules_data = json.load(f)
        for cat_name, cat_data in rules_data.get("categories", {}).items():
            for rule in cat_data.get("rules", []):
                if any(kw in query for kw in rule.get("description","").split()[:5]):
                    results.append({
                        "source_type": "compliance",
                        "content": f"[{rule['rule_id']}] {rule['rule']}: {rule['description']}",
                        "source_doc": "compliance_rules.json",
                        "relevance_score": 0.80,
                        "severity": rule.get("severity",""),
                    })
    return results


def fusion_rank(graph_results: List, vector_results: List, compliance_results: List,
                top_k: int = 10) -> List[Dict]:
    """第三步: 融合排序。"""
    import numpy as np
    all_results = graph_results + vector_results + compliance_results

    for r in all_results:
        base_score = r.get("relevance_score", 0.5)

        # 新鲜度加权
        if "2026" in r.get("content", ""): base_score *= 1.05
        if "过期" in r.get("content", ""): base_score *= 0.8

        # 权威性加权: 条款 > 产品文档 > 活动海报
        doc = r.get("source_doc", "")
        if "compliance" in doc: base_score *= 1.10
        elif "条款" in doc or "rule" in doc: base_score *= 1.05

        r["final_score"] = round(min(base_score, 1.0), 4)

    # 去重
    seen_contents = set()
    unique = []
    for r in sorted(all_results, key=lambda x: x.get("final_score", 0), reverse=True):
        content_key = r.get("content", "")[:80]
        if content_key not in seen_contents:
            seen_contents.add(content_key)
            r["rank"] = len(unique) + 1
            unique.append(r)

    return unique[:top_k]


def full_search(query: str, customer_id: str = None, top_k: int = 10,
                include_graph: bool = True, include_vector: bool = True) -> Dict:
    """完整四步检索。"""
    graph_results = graph_retrieve(query, customer_id, top_k) if include_graph else []
    vector_results = vector_retrieve(query, top_k) if include_vector else []
    compliance = compliance_retrieve(query)

    fused = fusion_rank(graph_results, vector_results, compliance, top_k)

    # 构建graph_context
    graph_context = {"related_entities": []}
    for r in graph_results[:5]:
        graph_context["related_entities"].append({
            "type": r.get("entity_type", ""),
            "name": r.get("content", "")[:50],
        })

    return {
        "query": query,
        "customer_id": customer_id,
        "results": fused,
        "graph_context": graph_context,
        "total_sources": {"graph": len(graph_results), "vector": len(vector_results),
                         "compliance": len(compliance), "fused": len(fused)},
    }


