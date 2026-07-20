"""
知识图谱构建器 — kg_builder.py
================================
基于 NetworkX 构建 XX银行信用卡业务知识图谱。
实体类型: Customer, CreditCard, Product, Benefit, Campaign, Document, InstallmentRule
关系类型: HOLDS, BELONGS_TO, INCLUDES, PARTICIPATES_IN, APPLIES_TO, RELATES_TO, SIMILAR_TO
"""
import os, pandas as pd, networkx as nx, numpy as np
from typing import Dict, List, Any, Optional

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA = os.path.join(BASE, "mock_data", "structured")


class KnowledgeGraph:
    """基于 NetworkX 的知识图谱 (Mock环境, 生产替换为 Neo4j)。"""

    def __init__(self):
        self.G = nx.MultiDiGraph()
        self._node_index: Dict[str, Dict] = {}  # entity_id → {label, attrs}

    def build(self) -> "KnowledgeGraph":
        """从 Mock 数据构建完整知识图谱。"""
        print("Building Knowledge Graph from mock data...")
        self._add_products()
        self._add_benefits()
        self._add_campaigns()
        self._add_customers()
        self._add_documents()
        self._add_installment_rules()
        self._build_relations()
        print(f"Done: {self.G.number_of_nodes()} nodes, {self.G.number_of_edges()} edges")
        return self

    # ================================================================
    # 节点创建
    # ================================================================
    def _add_products(self):
        df = pd.read_csv(os.path.join(DATA, "product_catalog.csv"))
        for _, r in df.iterrows():
            pid = r["product_id"]
            self.G.add_node(pid, label="Product", type="product",
                           name=r["product_name"], card_level=r["card_level"],
                           annual_fee=int(r["annual_fee"]))

    def _add_benefits(self):
        df = pd.read_csv(os.path.join(DATA, "benefit_catalog.csv"))
        for _, r in df.iterrows():
            bid = r["benefit_id"]
            self.G.add_node(bid, label="Benefit", type="benefit",
                           name=r["benefit_name"], category=r["benefit_category"])

    def _add_campaigns(self):
        df = pd.read_csv(os.path.join(DATA, "campaign_catalog.csv"))
        for _, r in df.iterrows():
            cid = r["campaign_id"]
            self.G.add_node(cid, label="Campaign", type="campaign",
                           name=r["campaign_name"], start=r["start_date"], end=r["end_date"],
                           budget=int(r["budget"]))

    def _add_customers(self, sample_n: int = 200):
        """抽样客户节点（全量8000太大，取代表性样本）。"""
        profile = pd.read_csv(os.path.join(DATA, "customer_profile.csv"))
        cards = pd.read_csv(os.path.join(DATA, "credit_card.csv"))
        sample = profile.sample(min(sample_n, len(profile)), random_state=42)
        for _, r in sample.iterrows():
            oneid = r["oneid"]
            self.G.add_node(oneid, label="Customer", type="customer",
                           name=r.get("demographics_name",""), age=int(r.get("demographics_age",0)),
                           city=r.get("demographics_city",""), income_level=r.get("demographics_income_level",""),
                           lifecycle=r.get("lifecycle_stage",""))
            # 客户的信用卡节点
            cust_cards = cards[cards["cust_id"]==r["cust_id"]]
            for _, cc in cust_cards.iterrows():
                card_node = f"CARD_{cc['card_no'][:8]}"
                self.G.add_node(card_node, label="CreditCard", type="card",
                               card_level=cc["card_level"], credit_amount=float(cc["credit_amount"]))
                self.G.add_edge(oneid, card_node, relation="HOLDS")
                if pd.notna(cc["product_id"]):
                    self.G.add_edge(card_node, cc["product_id"], relation="BELONGS_TO")

    def _add_documents(self):
        """产品文档作为Document节点。"""
        docs_path = os.path.join(BASE, "mock_data", "unstructured", "product_docs", "_index.json")
        if os.path.exists(docs_path):
            import json
            with open(docs_path, "r", encoding="utf-8") as f:
                docs = json.load(f)
            for doc in docs:
                did = doc["doc_id"]
                self.G.add_node(did, label="Document", type="document",
                               title=doc["title"], doc_type=doc["doc_type"],
                               product_name=doc.get("product_name",""))
                # 关联到产品
                if doc.get("product_name"):
                    # 简单匹配
                    for n, d in self.G.nodes(data=True):
                        if d.get("type") == "product" and doc["product_name"][:4] in str(d.get("name","")):
                            self.G.add_edge(did, n, relation="RELATES_TO")

    def _add_installment_rules(self):
        rules = [
            ("INST_3", 3, 0.0060), ("INST_6", 6, 0.0050), ("INST_12", 12, 0.0045),
            ("INST_18", 18, 0.0040), ("INST_24", 24, 0.0035),
        ]
        for rid, periods, rate in rules:
            self.G.add_node(rid, label="InstallmentRule", type="installment_rule",
                           periods=periods, fee_rate=rate)

    def _build_relations(self):
        """构建产品-权益、活动-产品等关系。"""
        # 产品-权益关联
        mapping = pd.read_csv(os.path.join(DATA, "product_benefit_mapping.csv"))
        for _, r in mapping.iterrows():
            if self.G.has_node(r["product_id"]) and self.G.has_node(r["benefit_id"]):
                self.G.add_edge(r["product_id"], r["benefit_id"], relation="INCLUDES")

        # 活动-产品关系（适用产品）
        camp = pd.read_csv(os.path.join(DATA, "campaign_catalog.csv"))
        prod = pd.read_csv(os.path.join(DATA, "product_catalog.csv"))
        prod_ids = set(prod["product_id"])
        for _, c in camp.iterrows():
            cid = c["campaign_id"]
            if not self.G.has_node(cid): continue
            for pid in list(prod_ids)[:3]:  # 每个活动关联前3个产品
                if self.G.has_node(pid):
                    self.G.add_edge(cid, pid, relation="APPLIES_TO")

        # 分期条款 → 产品
        for n, d in self.G.nodes(data=True):
            if d.get("type") == "product" and self.G.has_node("INST_12"):
                self.G.add_edge(n, "INST_12", relation="GOVERNED_BY")

        # 模拟客户参与活动
        customers = [n for n, d in self.G.nodes(data=True) if d.get("type")=="customer"]
        campaigns = [n for n, d in self.G.nodes(data=True) if d.get("type")=="campaign"]
        for c in customers[:50]:
            if campaigns:
                camp_node = np.random.choice(campaigns)
                self.G.add_edge(c, camp_node, relation="PARTICIPATES_IN")

    # ================================================================
    # 图查询
    # ================================================================
    def get_subgraph(self, entity_id: str, depth: int = 2) -> Dict:
        """获取以entity_id为中心的子图。"""
        if entity_id not in self.G:
            return {"nodes": [], "edges": []}
        # BFS遍历
        visited = {entity_id}
        frontier = {entity_id}
        for _ in range(depth):
            new_frontier = set()
            for n in frontier:
                for _, neighbor in self.G.out_edges(n):
                    if neighbor not in visited:
                        visited.add(neighbor)
                        new_frontier.add(neighbor)
                for neighbor, _ in self.G.in_edges(n):
                    if neighbor not in visited:
                        visited.add(neighbor)
                        new_frontier.add(neighbor)
            frontier = new_frontier
            if not frontier: break

        nodes = []
        for n in visited:
            d = self.G.nodes[n]
            nodes.append({"id": n, "label": d.get("label",""), "type": d.get("type",""),
                         "name": d.get("name",""), "attrs": {k:v for k,v in d.items()
                            if k not in ("label","type","name") and not isinstance(v,(dict,list))}})
        edges = []
        for u, v, k in self.G.edges(keys=True):
            if u in visited and v in visited:
                rel = self.G.edges[u,v,k].get("relation","")
                edges.append({"from": u, "to": v, "label": rel})
        return {"nodes": nodes, "edges": edges, "center": entity_id}

    def traverse_relations(self, entity_id: str, relation: str = None) -> List[Dict]:
        """沿特定关系遍历。"""
        results = []
        for _, neighbor, data in self.G.out_edges(entity_id, data=True):
            if relation is None or data.get("relation") == relation:
                results.append({"entity": neighbor, "relation": data.get("relation",""),
                               "info": dict(self.G.nodes[neighbor])})
        return results

    def find_path(self, from_id: str, to_id: str) -> Optional[List]:
        """查找两个实体间的最短路径。"""
        try:
            path = nx.shortest_path(self.G, from_id, to_id)
            relations = []
            for i in range(len(path)-1):
                edge_data = self.G.get_edge_data(path[i], path[i+1])
                rel = list(edge_data.values())[0].get("relation","") if edge_data else ""
                relations.append({"from": path[i], "to": path[i+1], "relation": rel})
            return relations
        except (nx.NetworkXNoPath, nx.NodeNotFound):
            return None

    def stats(self) -> Dict:
        return {"nodes": self.G.number_of_nodes(), "edges": self.G.number_of_edges(),
                "node_types": {t: sum(1 for _,d in self.G.nodes(data=True) if d.get("type")==t)
                              for t in set(d.get("type","") for _,d in self.G.nodes(data=True))}}


_kg_instance = None
def get_kg() -> KnowledgeGraph:
    global _kg_instance
    if _kg_instance is None:
        _kg_instance = KnowledgeGraph().build()
    return _kg_instance
