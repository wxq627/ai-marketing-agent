"""
知识图谱构建器 v2 — kg_builder.py
================================
基于 NetworkX 构建 XX银行信用卡业务知识图谱。

设计理念:
  图谱展示的是「业务实体之间的关联关系」，用于理解:
    - 一个产品包含哪些权益？
    - 一个营销活动适用于哪些产品/客户群？
    - 持卡客户通过什么产品获得了什么权益？
    - 哪些产品共享相似权益（可交叉销售）？

实体类型 (7种):
  Product(产品)  Benefit(权益)  Campaign(活动)
  Customer(代表性客户)  CreditCard(信用卡)  Document(文档)
  InstallmentRule(分期条款)

关系类型 (7种):
  INCLUDES      产品 → 权益       (产品包含哪些权益)
  APPLIES_TO    活动 → 产品       (活动适用于哪些产品)
  TARGETS       活动 → 客户群     (活动面向哪类客户)
  HOLDS         客户 → 信用卡     (客户持有哪张卡)
  BELONGS_TO    信用卡 → 产品     (这张卡属于哪个产品)
  SIMILAR_TO    产品 ↔ 产品      (共享权益的相似产品)
  GOVERNED_BY   产品 → 分期条款   (产品适用的分期规则)

深度语义:
  depth=1: 直接邻居 —— 我直接关联了什么？
    产品→权益、活动、分期条款、持卡客户(少量代表)
  depth=2: 间接关联 —— 通过直接邻居还能关联到什么？
    产品→权益→共享该权益的其他产品(相似产品发现)
    产品→客户→该客户还持有的其他产品(交叉销售机会)
    客户→信用卡→产品的权益(客户享有的权益清单)

说明: 当前使用 NetworkX (内存图)，生产环境可切换 Neo4j。
      客户节点仅选取代表性样本(30人)，全量8000太大不适合可视化。
"""

import os, json, pandas as pd, networkx as nx, numpy as np
from typing import Dict, List, Optional

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA = os.path.join(BASE, "mock_data", "structured")

# 每层深度各类型最大节点数（防止可视化爆炸）
# 设计原则: depth=1 展示核心关联, depth>=2 只展示最有价值的间接关联
DEPTH_LIMITS = {
    1: {"customer": 5, "card": 4, "product": 6, "benefit": 18, "campaign": 6, "document": 3, "installment_rule": 3},
    2: {"customer": 3, "card": 2, "product": 4, "benefit": 8,  "campaign": 3, "document": 0, "installment_rule": 0},
    3: {"customer": 2, "card": 1, "product": 2, "benefit": 4,  "campaign": 2, "document": 0, "installment_rule": 0},
}
# depth=1 总节点上限
MAX_NODES_DEPTH1 = 55
MAX_NODES_DEPTH2 = 80


class KnowledgeGraph:
    """基于 NetworkX 的知识图谱 (Mock环境, 生产替换为 Neo4j)。"""

    def __init__(self):
        self.G = nx.MultiDiGraph()

    # ================================================================
    # 构建
    # ================================================================
    def build(self) -> "KnowledgeGraph":
        print("[KG] Building Knowledge Graph...")
        self._add_products()
        self._add_benefits()
        self._add_campaigns()
        self._add_representative_customers(n=30)
        self._add_documents()
        self._add_installment_rules()
        self._build_relations()
        print(f"[KG] Done: {self.G.number_of_nodes()} nodes, {self.G.number_of_edges()} edges")
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
                           annual_fee=int(r.get("annual_fee", 0)),
                           selling_points=str(r.get("key_selling_points", ""))[:80])

    def _add_benefits(self):
        df = pd.read_csv(os.path.join(DATA, "benefit_catalog.csv"))
        for _, r in df.iterrows():
            bid = r["benefit_id"]
            self.G.add_node(bid, label="Benefit", type="benefit",
                           name=r["benefit_name"],
                           category=r.get("benefit_category", ""))

    def _add_campaigns(self):
        df = pd.read_csv(os.path.join(DATA, "campaign_catalog.csv"))
        for _, r in df.iterrows():
            cid = r["campaign_id"]
            # 解析 target_segment JSON/Python-dict 字符串
            target_str = str(r.get("target_segment", "{}"))
            try:
                target = json.loads(target_str.replace("'", '"'))
            except Exception:
                target = {}
            self.G.add_node(cid, label="Campaign", type="campaign",
                           name=r["campaign_name"],
                           start=str(r.get("start_date", ""))[:10],
                           end=str(r.get("end_date", ""))[:10],
                           card_levels=target.get("card_level", []),
                           age_range=target.get("age_range", []),
                           income_level=target.get("income_level", []),
                           target_all=target.get("all", False),
                           target_lifecycle=target.get("lifecycle", []),
                           target_cross_border=target.get("has_cross_border", False))

    def _add_representative_customers(self, n: int = 30):
        """
        选取代表性客户节点（非全量）。
        策略: 按 card_level × lifecycle_stage 分层抽样，
        确保各类型客户都有代表，而非随机抽。
        """
        profile = pd.read_csv(os.path.join(DATA, "customer_profile.csv"))
        cards_df = pd.read_csv(os.path.join(DATA, "credit_card.csv"))

        # 按 card_level 分层，每组取等量
        sample_list = []
        card_levels = profile["account_primary_card_level"].unique()
        per_level = max(1, n // len(card_levels))
        for clevel in card_levels:
            group = profile[profile["account_primary_card_level"] == clevel]
            # 再按 lifecycle_stage 子分层
            for stage in group["lifecycle_stage"].unique():
                subgroup = group[group["lifecycle_stage"] == stage]
                k = max(1, min(3, len(subgroup)))  # 每子层最多3个
                samp = subgroup.sample(k, random_state=42)
                sample_list.append(samp)

        sample = pd.concat(sample_list, ignore_index=True)
        sample = sample.drop_duplicates(subset=["oneid"]).head(n)
        print(f"[KG] Sampled {len(sample)} representative customers from {len(profile)} total")

        # 构建 cust_id → primary card 映射 (确保每位客户至少1张卡)
        primary_cards = cards_df[cards_df["is_primary"] == True].groupby("cust_id").first().reset_index()

        for _, r in sample.iterrows():
            oneid = r["oneid"]
            cust_id = r["cust_id"]
            self.G.add_node(oneid, label="Customer", type="customer",
                           name=str(r.get("demographics_name", "")),
                           age=int(r.get("demographics_age", 0)),
                           city=str(r.get("demographics_city", "")),
                           income_level=str(r.get("demographics_income_level", "")),
                           lifecycle=str(r.get("lifecycle_stage", "")),
                           card_level=str(r.get("account_primary_card_level", "")),
                           value_level=str(r.get("value_value_level", "")))

            # 添加主卡
            pc = primary_cards[primary_cards["cust_id"] == cust_id]
            if len(pc) > 0:
                cc = pc.iloc[0]
                card_node = f"CARD_{str(cc['card_no'])[:8]}"
                self.G.add_node(card_node, label="CreditCard", type="card",
                               name=f"{cc.get('card_level', '')}卡(尾号{str(cc['card_no'])[-4:]})",
                               card_level=str(cc.get("card_level", "")),
                               credit_amount=float(cc.get("credit_amount", 0)))
                self.G.add_edge(oneid, card_node, relation="HOLDS")
                pid = str(cc.get("product_id", ""))
                if pid and pid != "nan" and self.G.has_node(pid):
                    self.G.add_edge(card_node, pid, relation="BELONGS_TO")
            else:
                # fallback: 取该客户的任意一张卡
                any_card = cards_df[cards_df["cust_id"] == cust_id].head(1)
                if len(any_card) > 0:
                    cc = any_card.iloc[0]
                    card_node = f"CARD_{str(cc['card_no'])[:8]}"
                    self.G.add_node(card_node, label="CreditCard", type="card",
                                   name=f"{cc.get('card_level', '')}卡(尾号{str(cc['card_no'])[-4:]})",
                                   card_level=str(cc.get("card_level", "")),
                                   credit_amount=float(cc.get("credit_amount", 0)))
                    self.G.add_edge(oneid, card_node, relation="HOLDS")
                    fb_pid = str(cc.get("product_id", ""))
                    if fb_pid and fb_pid != "nan" and self.G.has_node(fb_pid):
                        self.G.add_edge(card_node, fb_pid, relation="BELONGS_TO")

    def _add_documents(self):
        docs_path = os.path.join(BASE, "mock_data", "unstructured", "product_docs", "_index.json")
        if not os.path.exists(docs_path):
            return
        with open(docs_path, "r", encoding="utf-8") as f:
            docs = json.load(f)
        for doc in docs[:12]:  # 限制文档数量
            did = doc["doc_id"]
            self.G.add_node(did, label="Document", type="document",
                           title=str(doc.get("title", "")),
                           doc_type=str(doc.get("doc_type", "")),
                           product_name=str(doc.get("product_name", "")))
            # 关联到产品
            pname = str(doc.get("product_name", ""))[:4]
            if pname:
                for n, d in self.G.nodes(data=True):
                    if d.get("type") == "product" and pname in str(d.get("name", "")):
                        self.G.add_edge(did, n, relation="RELATES_TO")
                        break

    def _add_installment_rules(self):
        rules = [
            ("INST_3", 3, 0.0060), ("INST_6", 6, 0.0050),
            ("INST_12", 12, 0.0045), ("INST_18", 18, 0.0040), ("INST_24", 24, 0.0035),
        ]
        for rid, periods, rate in rules:
            self.G.add_node(rid, label="InstallmentRule", type="installment_rule",
                           name=f"{periods}期分期", periods=periods, fee_rate=rate)

    # ================================================================
    # 关系构建
    # ================================================================
    def _build_relations(self):
        # 1. 产品←→权益 (INCLUDES)
        mapping = pd.read_csv(os.path.join(DATA, "product_benefit_mapping.csv"))
        for _, r in mapping.iterrows():
            if self.G.has_node(r["product_id"]) and self.G.has_node(r["benefit_id"]):
                self.G.add_edge(r["product_id"], r["benefit_id"], relation="INCLUDES")

        # 2. 活动→产品 (APPLIES_TO) — 多种匹配策略
        campaigns = [n for n, d in self.G.nodes(data=True) if d.get("type") == "campaign"]
        products = [(n, d) for n, d in self.G.nodes(data=True) if d.get("type") == "product"]
        for cid in campaigns:
            cdata = self.G.nodes[cid]
            target_levels = cdata.get("card_levels", [])
            # 策略1: card_level 匹配
            if target_levels:
                for pid, pdata in products:
                    plevel = str(pdata.get("card_level", ""))
                    if any(tl in plevel for tl in target_levels):
                        self.G.add_edge(cid, pid, relation="APPLIES_TO")
            # 策略2: all=True → 适用所有产品
            elif cdata.get("target_all"):
                for pid, pdata in products:
                    self.G.add_edge(cid, pid, relation="APPLIES_TO")
            # 策略3: lifecycle=新户 → 入门级产品
            elif "新户" in str(cdata.get("target_lifecycle", [])):
                for pid, pdata in products:
                    if pdata.get("card_level", "") in ("校园卡", "普卡"):
                        self.G.add_edge(cid, pid, relation="APPLIES_TO")
            # 策略4: has_cross_border → 旅行/国际产品
            elif cdata.get("target_cross_border"):
                for pid, pdata in products:
                    pname = str(pdata.get("name", ""))
                    if any(kw in pname for kw in ("国际", "旅行", "携程", "全币种")):
                        self.G.add_edge(cid, pid, relation="APPLIES_TO")
            # 策略5: 其他条件 → 连代表性产品 (每种等级1个)
            else:
                seen_levels = set()
                for pid, pdata in products:
                    plevel = str(pdata.get("card_level", ""))
                    if plevel not in seen_levels and len(seen_levels) < 4:
                        self.G.add_edge(cid, pid, relation="APPLIES_TO")
                        seen_levels.add(plevel)

        # 3. 活动→客户 (TARGETS) — 基于客户画像匹配活动目标
        cust_nodes = [(n, d) for n, d in self.G.nodes(data=True) if d.get("type") == "customer"]
        for cid in campaigns:
            cdata = self.G.nodes[cid]
            target_levels = cdata.get("card_levels", [])
            target_age = cdata.get("age_range", [])
            target_income = cdata.get("income_level", [])
            matched = 0
            for oneid, cdata_c in cust_nodes:
                if matched >= 5:
                    break
                cust_cards = [n for n in self.G.successors(oneid) if self.G.nodes[n].get("type") == "card"]
                cust_levels = [str(self.G.nodes[cn].get("card_level", "")) for cn in cust_cards]
                cust_age = cdata_c.get("age", 0)
                cust_income = str(cdata_c.get("income_level", ""))
                # 检查匹配
                level_match = any(tl in cl for tl in target_levels for cl in cust_levels)
                age_match = (not target_age) or (target_age[0] <= cust_age <= target_age[-1]) if target_age else True
                income_match = (not target_income) or (cust_income in target_income)
                if level_match and age_match and income_match:
                    self.G.add_edge(cid, oneid, relation="TARGETS")
                    matched += 1

        # 4. 分期条款 → 所有产品 (GOVERNED_BY)
        for n, d in self.G.nodes(data=True):
            if d.get("type") == "product":
                for inst_id in ["INST_3", "INST_6", "INST_12"]:
                    if self.G.has_node(inst_id):
                        self.G.add_edge(n, inst_id, relation="GOVERNED_BY")

    # ================================================================
    # 图查询 — 智能深度遍历 (选择性边类型)
    # ================================================================
    # depth>=2 时跳过的边类型: 这些在 depth=1 已经充分覆盖，再遍历只会制造噪音
    _SKIP_EDGES_AT_DEEP = {"INCLUDES", "GOVERNED_BY"}
    # depth>=2 时跳过的节点类型: 这些类型在深度遍历中价值低
    _SKIP_NODE_TYPES_AT_DEEP = {"document", "installment_rule"}

    def get_subgraph(self, entity_id: str, depth: int = 1) -> Dict:
        """
        获取以 entity_id 为中心的子图。

        智能深度:
          depth=1: 直接邻居 — 所有直接关联的实体
          depth=2: 间接关联 — 仅遍历"桥接"关系(HOLDS/BELONGS_TO/SIMILAR_TO/TARGETS/APPLIES_TO),
                   跳过会造成信息冗余的关系(INCLUDES/GOVERNED_BY)
          depth=3: 更远关联 — 进一步收紧限制

        防止爆炸策略:
          1. 选择性边遍历: depth>=2 跳过 INCLUDES/GOVERNED_BY 边
          2. 选择性节点: depth>=2 跳过 document/installment_rule
          3. 每层类型数量限制 (DEPTH_LIMITS)
        """
        if entity_id not in self.G:
            return {"nodes": [], "edges": [], "center": entity_id}

        visited: Dict[str, int] = {entity_id: 0}
        frontier = {entity_id}

        for current_depth in range(1, depth + 1):
            new_frontier = set()
            skip_edges = self._SKIP_EDGES_AT_DEEP if current_depth >= 2 else set()
            skip_types = self._SKIP_NODE_TYPES_AT_DEEP if current_depth >= 2 else set()

            for n in frontier:
                # 出边遍历 (带选择性过滤)
                for _, neighbor, edata in self.G.out_edges(n, data=True):
                    if neighbor not in visited:
                        rel = edata.get("relation", "")
                        if rel in skip_edges:
                            continue
                        ntype = self.G.nodes[neighbor].get("type", "")
                        if ntype in skip_types:
                            continue
                        visited[neighbor] = current_depth
                        new_frontier.add(neighbor)
                # 入边遍历 (带选择性过滤)
                for neighbor, _, edata in self.G.in_edges(n, data=True):
                    if neighbor not in visited:
                        rel = edata.get("relation", "")
                        if rel in skip_edges:
                            continue
                        ntype = self.G.nodes[neighbor].get("type", "")
                        if ntype in skip_types:
                            continue
                        visited[neighbor] = current_depth
                        new_frontier.add(neighbor)

            # 类型数量限制
            limits = DEPTH_LIMITS.get(current_depth, {})
            if limits and new_frontier:
                typed_new = {}
                for node in new_frontier:
                    ntype = self.G.nodes[node].get("type", "unknown")
                    typed_new.setdefault(ntype, []).append(node)
                filtered_frontier = set()
                for ntype, nodes in typed_new.items():
                    limit = limits.get(ntype, len(nodes))
                    nodes_sorted = sorted(nodes,
                        key=lambda x: len(list(self.G.neighbors(x))),
                        reverse=True)
                    filtered_frontier.update(nodes_sorted[:limit])
                frontier = filtered_frontier
            else:
                frontier = new_frontier

            if not frontier:
                break

        # 构建结果 + 总节点上限裁剪
        all_nodes = []
        for n in visited:
            d = self.G.nodes[n]
            attrs = {k: v for k, v in d.items()
                     if k not in ("label", "type", "name") and not isinstance(v, (dict, list))}
            all_nodes.append({
                "id": n, "label": d.get("label", ""), "type": d.get("type", ""),
                "name": d.get("name", ""), "depth": visited[n],
                "attrs": attrs,
            })

        # 总节点上限: 超出部分裁剪最远深度的节点
        max_nodes = MAX_NODES_DEPTH2 if depth >= 2 else MAX_NODES_DEPTH1
        if len(all_nodes) > max_nodes:
            # 按深度优先级保留: depth=0 必留, depth=1 优先, depth>=2 可裁剪
            priority = {0: 0, 1: 1}
            all_nodes.sort(key=lambda x: (priority.get(x["depth"], x["depth"]),
                                          -self.G.degree(x["id"]),
                                          -len(str(x.get("name", "")))))

            all_nodes = all_nodes[:max_nodes]

        kept_ids = {n["id"] for n in all_nodes}

        edges = []
        for u, v, k in self.G.edges(keys=True):
            if u in kept_ids and v in kept_ids:
                rel = self.G.edges[u, v, k].get("relation", "")
                edges.append({"from": u, "to": v, "label": rel})

        return {"nodes": all_nodes, "edges": edges, "center": entity_id}

    def traverse_relations(self, entity_id: str, relation: str = None) -> List[Dict]:
        """沿特定关系遍历。"""
        results = []
        for _, neighbor, data in self.G.out_edges(entity_id, data=True):
            if relation is None or data.get("relation") == relation:
                results.append({
                    "entity": neighbor, "relation": data.get("relation", ""),
                    "info": dict(self.G.nodes[neighbor]),
                })
        return results

    def find_path(self, from_id: str, to_id: str) -> Optional[List]:
        """查找两个实体间的最短路径。"""
        try:
            path = nx.shortest_path(self.G, from_id, to_id)
            relations = []
            for i in range(len(path) - 1):
                edge_data = self.G.get_edge_data(path[i], path[i + 1])
                rel = list(edge_data.values())[0].get("relation", "") if edge_data else ""
                relations.append({"from": path[i], "to": path[i + 1], "relation": rel})
            return relations
        except (nx.NetworkXNoPath, nx.NodeNotFound):
            return None

    # ================================================================
    # 向量+图混合检索 (GraphRAG Search)
    # ================================================================
    def hybrid_search(self, query: str, top_k: int = 10,
                      expand_hops: int = 1) -> List[Dict]:
        """
        向量+图混合检索。

        流程:
          1. 关键词匹配所有节点 → 找到种子节点 (seed nodes)
          2. 从每个种子节点扩展1跳 → 发现图邻居
          3. 综合评分: 关键词分 × 0.5 + 图中心度 × 0.2 + 嵌入相似 × 0.3
          4. 返回排序结果 + 图路径

        参数:
          query: 搜索查询
          top_k: 返回Top-K结果
          expand_hops: 从种子节点扩展的跳数

        返回: [{node_id, name, type, score, seed_path, ...}, ...]
        """
        if not query:
            return []

        # ── 阶段1: 关键词找种子节点 ──
        seeds = self._find_seed_nodes(query)
        if not seeds:
            return []

        # ── 阶段2: 图扩展 ──
        expanded_ids = set(seeds.keys())
        for seed_id in list(seeds.keys()):
            sub = self.get_subgraph(seed_id, depth=expand_hops)
            for n in sub["nodes"]:
                expanded_ids.add(n["id"])

        # ── 阶段3: 嵌入相似度 (尝试) ──
        embed_scores = {}
        try:
            from llm_client import embed
            q_vec = embed(query)
            for nid in expanded_ids:
                d = self.G.nodes[nid]
                node_text = f"{d.get('name','')} {d.get('type','')} {' '.join(str(v) for v in d.values() if isinstance(v,str))}"
                if node_text.strip():
                    t_vec = embed(node_text[:300])
                    cos = float(np.dot(q_vec, t_vec) / (np.linalg.norm(q_vec) * np.linalg.norm(t_vec) + 1e-8))
                    embed_scores[nid] = max(0.0, cos)
        except Exception:
            pass

        # ── 阶段4: 综合评分 ──
        results = []
        for nid in expanded_ids:
            d = self.G.nodes[nid]
            ntype = d.get("type", "unknown")
            name = str(d.get("name", ""))

            # 关键词分 (0-100)
            kw_score = seeds.get(nid, 0.0)

            # 图中心度分 (0-100, 归一化)
            degree = self.G.degree(nid)
            max_degree = max(self.G.degree(n) for n in expanded_ids) or 1
            graph_score = (degree / max_degree) * 100

            # 嵌入分 (0-100)
            embed_s = embed_scores.get(nid, 0.5) * 100

            # 综合: 关键词权重最高
            final = kw_score * 0.5 + graph_score * 0.2 + embed_s * 0.3

            # 找到从最近种子节点的路径
            seed_path = []
            best_seed = max(seeds.items(), key=lambda x: x[1])[0] if seeds else None
            if best_seed and best_seed != nid:
                path = self.find_path(best_seed, nid)
                if path:
                    seed_path = [
                        f"{p['from'][:12]} -[{p['relation']}]-> {p['to'][:12]}"
                        for p in path
                    ]

            results.append({
                "node_id": nid,
                "name": name[:40],
                "type": ntype,
                "type_zh": {
                    "product": "产品", "benefit": "权益", "campaign": "活动",
                    "customer": "客户", "card": "信用卡", "document": "文档",
                    "installment_rule": "分期条款",
                }.get(ntype, ntype),
                "score": round(final, 1),
                "kw_score": round(kw_score, 1),
                "graph_score": round(graph_score, 1),
                "embed_score": round(embed_s, 1),
                "seed_path": seed_path[:3],  # 最多显示3步路径
                "degree": degree,
            })

        results.sort(key=lambda x: x["score"], reverse=True)
        return results[:top_k]

    def _find_seed_nodes(self, query: str) -> Dict[str, float]:
        """
        关键词匹配找种子节点。
        返回: {node_id: match_score}
        """
        seeds = {}
        qlen = len(query)

        for n, d in self.G.nodes(data=True):
            name = str(d.get("name", ""))
            ntype = d.get("type", "")
            node_text = f"{name} {ntype}"

            score = 0.0
            # 完整匹配
            if query in node_text:
                cnt = node_text.count(query)
                score += cnt * 30.0

            # n-gram匹配 (2-4字)
            for L in [4, 3, 2]:
                for i in range(max(0, qlen - L + 1)):
                    sub = query[i:i + L]
                    if len(sub) >= 2 and sub in node_text:
                        score += len(sub) * 2.0

            if score > 0:
                seeds[n] = score

        # 也搜索 attrs 字段
        for n, d in self.G.nodes(data=True):
            for k, v in d.items():
                if isinstance(v, str) and query in v and n not in seeds:
                    seeds[n] = 15.0

        return seeds

    def stats(self) -> Dict:
        return {
            "nodes": self.G.number_of_nodes(),
            "edges": self.G.number_of_edges(),
            "node_types": {
                t: sum(1 for _, d in self.G.nodes(data=True) if d.get("type") == t)
                for t in sorted(set(d.get("type", "") for _, d in self.G.nodes(data=True)))
            },
        }


_kg_instance = None


def get_kg() -> KnowledgeGraph:
    global _kg_instance
    if _kg_instance is None:
        _kg_instance = KnowledgeGraph().build()
    return _kg_instance
