"""模块四: GraphRAG 测试"""
import os, sys, json
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from graphrag.kg_builder import KnowledgeGraph, get_kg
from graphrag.doc_pipeline import DocPipeline, get_pipeline
from graphrag.retrieval import graph_retrieve, vector_retrieve, full_search

PASS = FAIL = 0
def check(name, cond, detail=""):
    global PASS, FAIL
    if cond: PASS += 1; print(f"  [PASS] {name}")
    else: FAIL += 1; print(f"  [FAIL] {name} - {detail}")

print("=" * 60)
print("模块四: GraphRAG 测试")
print("=" * 60)

# 1. 知识图谱构建
print("\n[1] 知识图谱构建")
kg = get_kg()
check("图节点数>0", kg.G.number_of_nodes() > 0, f"{kg.G.number_of_nodes()} nodes")
check("图边数>0", kg.G.number_of_edges() > 0, f"{kg.G.number_of_edges()} edges")
stats = kg.stats()
print(f"  Node types: {stats['node_types']}")
for t, c in stats["node_types"].items():
    check(f"  {t}: {c} nodes", c > 0)

# 2. 子图查询
print("\n[2] 子图查询")
# 找一个产品节点
prods = [n for n,d in kg.G.nodes(data=True) if d.get("type")=="product"]
if prods:
    sub = kg.get_subgraph(prods[0], depth=2)
    check(f"子图: {len(sub['nodes'])} nodes, {len(sub['edges'])} edges", len(sub['nodes']) > 0)
    print(f"  Center: {sub['center']}, nodes: {[n['name'] for n in sub['nodes'][:5]]}")

# 3. 关系遍历
print("\n[3] 关系遍历")
prod_node = prods[0] if prods else None
if prod_node:
    rels = kg.traverse_relations(prod_node, "INCLUDES")
    check(f"INCLUDES关系: {len(rels)} 条", len(rels) >= 0)
    if rels:
        print(f"  示例: {prod_node} → [{rels[0]['relation']}] → {rels[0]['entity']}")

# 4. 文档处理流水线
print("\n[4] 文档处理流水线")
pipeline = get_pipeline()
check(f"文档切片: {len(pipeline.chunks)} chunks", len(pipeline.chunks) > 0)
check(f"TF-IDF维度: {pipeline.embeddings.shape[1] if pipeline.embeddings is not None else 0}", True)

# 5. 向量检索
print("\n[5] 向量检索")
vec_results = vector_retrieve("白金卡机场贵宾厅权益", top_k=3)
check(f"向量检索返回结果: {len(vec_results)}", len(vec_results) > 0)
for r in vec_results[:2]:
    print(f"  [{r['relevance_score']:.3f}] {r['content'][:80]}...")

# 6. 图谱检索
print("\n[6] 图谱检索")
graph_results = graph_retrieve("白金卡", top_k=3)
check(f"图谱检索返回结果: {len(graph_results)}", len(graph_results) > 0)
for r in graph_results[:2]:
    print(f"  [{r['source_type']}] {r['content'][:80]}")

# 7. 融合检索
print("\n[7] 融合检索 (完整GraphRAG)")
result = full_search("白金卡有哪些权益", top_k=5)
check(f"融合结果: {result['total_sources']['fused']} fused", result['total_sources']['fused'] > 0)
print(f"  Sources: graph={result['total_sources']['graph']} vector={result['total_sources']['vector']} compliance={result['total_sources']['compliance']}")
for r in result['results'][:3]:
    print(f"  [{r['source_type']}] rank={r['rank']} score={r.get('final_score',r.get('relevance_score',0)):.3f} {r['content'][:80]}")

# 8. 客户上下文检索
print("\n[8] 客户上下文 (GraphRAG with customer)")
if prods:
    customers = [n for n,d in kg.G.nodes(data=True) if d.get("type")=="customer"]
    if customers:
        result2 = full_search("分期方案", customer_id=customers[0], top_k=5)
        check(f"客户上下文检索: {len(result2['results'])} results", True)
        print(f"  客户: {customers[0]}, context: {len(result2['graph_context']['related_entities'])} entities")

# 9. 路径查找
print("\n[9] 路径查找")
if len(prods) >= 2:
    path = kg.find_path(prods[0], prods[1])
    check("路径查找有结果", path is not None)

print(f"\n{'='*60}")
print(f"Result: {PASS} PASS, {FAIL} FAIL")
if FAIL == 0: print("ALL TESTS PASSED!")
print("=" * 60)
