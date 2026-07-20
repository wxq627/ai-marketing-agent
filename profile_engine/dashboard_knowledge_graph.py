"""知识图谱 & 知识检索 v4 — DeepSeek + 交互式图谱"""
import os, sys, json, glob, pandas as pd
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import streamlit as st

st.set_page_config(page_title="知识图谱", page_icon="", layout="wide")

DATA = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "mock_data")

@st.cache_data
def load_products(): return pd.read_csv(os.path.join(DATA, "structured", "product_catalog.csv"))
@st.cache_data
def load_benefits(): return pd.read_csv(os.path.join(DATA, "structured", "benefit_catalog.csv"))
@st.cache_data
def load_mapping(): return pd.read_csv(os.path.join(DATA, "structured", "product_benefit_mapping.csv"))
@st.cache_data
def load_campaigns(): return pd.read_csv(os.path.join(DATA, "structured", "campaign_catalog.csv"))
@st.cache_data
def load_eligibility(): return pd.read_csv(os.path.join(DATA, "structured", "product_eligibility.csv"))

@st.cache_resource
def load_kg():
    from graphrag.kg_builder import KnowledgeGraph
    kg = KnowledgeGraph(); kg.build()
    return kg

@st.cache_data
def load_all_docs():
    docs = []
    # 产品文档
    txt_dir = os.path.join(DATA, "unstructured", "product_docs")
    for fp in sorted(glob.glob(os.path.join(txt_dir, "doc_*.txt"))):
        with open(fp, "r", encoding="utf-8") as f: text = f.read()
        lines = text.strip().split("\n")
        title = lines[0].strip().lstrip("#").strip() if lines else os.path.basename(fp)
        docs.append({"source": os.path.basename(fp), "type": "产品文档", "title": title, "text": "\n".join(lines[1:])[:2500]})
    # 产品目录
    for _, r in load_products().iterrows():
        docs.append({"source": "product_catalog", "type": "产品", "title": r["product_name"],
            "text": f"{r['product_name']} | {r['card_level']} | 年费¥{r['annual_fee']} | {r['key_selling_points']}"})
    # 权益目录
    for _, r in load_benefits().iterrows():
        docs.append({"source": "benefit_catalog", "type": "权益", "title": r["benefit_name"],
            "text": f"{r['benefit_name']} | {r['benefit_category']} | {r['benefit_desc']}"})
    # 活动目录
    for _, r in load_campaigns().iterrows():
        docs.append({"source": "campaign_catalog", "type": "活动", "title": r["campaign_name"],
            "text": f"{r['campaign_name']} | {r['start_date']}~{r['end_date']} | {r['rules']}"})
    # 海报 (作为知识库的一部分)
    poster_dir = os.path.join(DATA, "unstructured", "posters")
    poster_img_dir = os.path.join(poster_dir, "images")
    for jf in sorted(glob.glob(os.path.join(poster_dir, "*.json"))):
        with open(jf, "r", encoding="utf-8") as f:
            info = json.load(f)
        # 构造海报文本(与multimodal_engine相同的字段选择)
        parts = [info.get("activity_name",""), info.get("main_title",""), info.get("sub_title",""),
                 info.get("target_segment",""), info.get("cta_text","")]
        parts.extend(info.get("rules_summary", []))
        poster_text = " | ".join(p for p in parts if p)
        img_name = info.get("image_file", "")
        img_path = os.path.join(poster_img_dir, img_name) if img_name else ""
        docs.append({
            "source": os.path.basename(jf), "type": "海报",
            "title": info.get("activity_name", info.get("campaign_id", "")),
            "text": poster_text[:2000],
            "image_path": img_path if os.path.exists(img_path) else "",
        })
    return docs

def search_docs(query, docs, top_k=15):
    terms = []
    for L in [4,3,2]:
        for i in range(len(query)-L+1):
            t = query[i:i+L]
            if t not in terms: terms.append(t)
    scored = []
    for doc in docs:
        score = sum(doc["text"].count(t)*len(t) for t in terms)
        if score > 0:
            scored.append({**doc, "score": score, "matched": [t for t in terms if t in doc["text"]]})
    scored.sort(key=lambda x: x["score"], reverse=True)
    seen = set(); unique = []
    for r in scored:
        k = r["title"][:40]
        if k not in seen: seen.add(k); unique.append(r)
    for r in unique:
        t = r["text"]
        bp = max(range(max(1,len(t)-150)), key=lambda i: sum(t[i:i+200].count(x)*len(x) for x in r["matched"]), default=0)
        snippet = t[bp:bp+300]
        for x in sorted(r["matched"], key=lambda x:-len(x)): snippet = snippet.replace(x, f"**{x}**")
        r["snippet"] = snippet.strip()
    return unique[:top_k]

def main():
    st.title("  知识图谱 & 知识检索 v4")
    st.caption("DeepSeek 语义向量 | 交互式力导向图 | Neo4j 可导出 | XX银行知识库")

    tab1, tab2, tab3, tab4 = st.tabs(["  交互式知识图谱", "  产品 & 权益关系树", "  知识全文检索", "   多模态检索"])

    # ====== Tab 1: 交互式图谱 ======
    with tab1:
        st.markdown("###  交互式知识图谱 (GraphRAG)")
        st.caption("向量+图混合检索 | 彩色关系边+方向箭头 | 点击节点图定位 | Neo4j可导出")

        kg = load_kg()
        from graphrag.kg_viz import render_interactive, TYPE_LABELS_ZH, RELATION_LABELS_ZH

        # ── 图谱说明 (可折叠) ──
        with st.expander("  图谱说明 — 实体/关系/深度/GraphRAG详解", expanded=False):
            tab_a, tab_b, tab_c = st.tabs(["实体与关系", "深度含义", "GraphRAG混合检索"])

            with tab_a:
                c1, c2 = st.columns(2)
                with c1:
                    st.markdown("""
**实体 (节点) — 7种颜色:**

| 颜色 | 类型 | 数量 |
|------|------|------|
|  蓝 | 产品 | 15款信用卡 |
|  绿 | 权益 | 90项(机场/积分/保险等) |
|  橙 | 活动 | 25个营销活动 |
|  红 | 客户 | 30人(分层抽样代表) |
|  紫 | 信用卡 | 6张实体卡 |
|  灰 | 文档 | 12份产品文档 |
|  青 | 分期条款 | 5种(3/6/12/18/24期) |
                    """)
                with c2:
                    st.markdown("""
**关系 (边) — 9种彩色边:**

| 颜色 | 线型 | 关系 | 含义 |
|------|------|------|------|
|  绿 | 实线 | 包含权益 | 产品有哪些权益 |
|  橙 | 虚线 | 活动适用 | 活动适用哪些产品 |
|  红 | 点线 | 面向客户 | 活动目标哪些客户 |
|  紫 | 实线 | 持有 | 客户持有哪些卡 |
|  紫 | 虚线 | 属于产品 | 卡属于哪个产品 |
|  蓝 | 点划线 | 相似产品 | 同等级共享≥10权益 |
|  青 | 实线 | 分期规则 | 产品适用分期条款 |
                    """)

            with tab_b:
                st.markdown("""
**深度 (Depth) — 图谱遍历层数:**

| 深度 | 含义 | 示例 (从白金卡出发) |
|------|------|---------------------|
| **1** | **直接邻居** | 白金卡→63项权益、10个活动、5个相似产品、持卡客户 |
| **2** | **间接关联** | 通过持卡客户→客户还持有什么其他卡→其他产品 (交叉销售机会) |
|  |  | 通过相似产品→该产品的权益→发现共同权益模式 |
| **3** | **更远关联** | 仅特殊分析场景使用, 一般不需 |

> **推荐使用 depth=1**。depth=2 用于发现交叉销售和竞品分析。
> 为防止节点爆炸, depth≥2 时跳过"包含权益"和"分期规则"边(这些在depth=1已展示完整)。
                """)

            with tab_c:
                st.markdown("""
**向量+图混合检索 (GraphRAG) — 三步流程:**

```
用户输入: "618返现活动"
         │
    ┌────▼─────────────────────────────────────┐
    │ ① 关键词匹配 → 找种子节点                  │
    │   在所有节点名称/属性中搜索"618""返现"       │
    │   命中: 618购物节返现(活动), 白金卡(产品)... │
    └────┬─────────────────────────────────────┘
         │
    ┌────▼─────────────────────────────────────┐
    │ ② 图扩展 → 从种子节点沿边扩展1跳             │
    │   618活动→(活动适用)→产品→(包含权益)→权益   │
    │   618活动→(面向客户)→客户→(持有)→信用卡     │
    │   产品→(相似产品)→其他产品                  │
    └────┬─────────────────────────────────────┘
         │
    ┌────▼─────────────────────────────────────┐
    │ ③ 综合评分并排序                           │
    │   综合分 = 关键词匹配×0.5 + 图中心度×0.2    │
    │           + 嵌入向量相似度×0.3              │
    │   返回: Top-K 结果 + 从种子到目标的路径      │
    └──────────────────────────────────────────┘
```

**为什么比纯关键词搜索更好？**
- 纯关键词: 搜"618返现"只返回标题含618的条目
- **GraphRAG**: 还能找到618活动适用的产品、这些产品的权益、参与活动的客户、相似产品等图关联信息

**为什么比纯向量搜索更好？**
- 纯向量: 可能漏掉低语义相似但图结构相关的结果
- **GraphRAG**: 关键词锚定精确匹配 + 图结构补全关联 + 向量验证语义 = 更高召回+更准排序
                """)

        # ── 图谱统计 ──
        stats = kg.stats()
        st.caption(f"图谱: {stats['nodes']}节点 {stats['edges']}边 | " +
                   " | ".join([f"{TYPE_LABELS_ZH.get(k,k)}:{v}" for k, v in stats['node_types'].items()]))

        # ═══════════════════════════════════════════
        # 模式1: 向量+图混合检索
        # ═══════════════════════════════════════════
        st.markdown("---")
        st.markdown("####  向量+图混合检索 (GraphRAG Search)")
        search_query = st.text_input("输入查询", placeholder="如: 白金卡机场权益 / 618返现活动 / 校园卡毕业季 / 分期免息",
                                     key="kg_search")
        search_results = []
        if search_query:
            try:
                search_results = kg.hybrid_search(search_query, top_k=12)
                if search_results:
                    st.success(f"找到 {len(search_results)} 条 | 关键词+图扩展+嵌入 综合排序")
                    for i, r in enumerate(search_results[:8]):
                        st.markdown(
                            f"**{i+1}. [{r['type_zh']}] {r['name']}**  "
                            f"score={r['score']:.0f} (kw={r['kw_score']:.0f} graph={r['graph_score']:.0f} emb={r['embed_score']:.0f})"
                        )
                        if r.get("seed_path"):
                            for step in r["seed_path"]:
                                st.caption(f"    {step}")
                else:
                    st.info("无匹配结果, 尝试其他关键词")
            except Exception as e:
                st.warning(f"搜索出错: {e}")

        # ═══════════════════════════════════════════
        # 模式2: 实体浏览器 → 生成图谱
        # ═══════════════════════════════════════════
        st.markdown("---")
        st.markdown("####  实体浏览器 → 生成关联图谱")

        c1, c2 = st.columns([3, 1])
        with c1:
            entity_types = sorted(set(d.get("type", "") for _, d in kg.G.nodes(data=True) if d.get("type")))
            type_names_full = {"product": "产品(15)", "benefit": "权益(90)", "campaign": "活动(25)",
                              "customer": "客户(30)", "card": "信用卡(6)", "document": "文档(12)",
                              "installment_rule": "分期条款(5)"}
            sel_type = st.selectbox("实体类型", entity_types,
                                    format_func=lambda x: type_names_full.get(x, x))
            entities = [(n, str(d.get("name", n))[:35]) for n, d in kg.G.nodes(data=True) if d.get("type") == sel_type]
            if entities:
                entities.sort(key=lambda x: x[1])
                # 如果搜索结果中有该类型的节点, 默认选中
                default_idx = 0
                result_ids = {r["node_id"] for r in search_results}
                if result_ids:
                    for i, (eid, _) in enumerate(entities):
                        if eid in result_ids:
                            default_idx = i
                            break
                sel_entity = st.selectbox("选择实体", [e[0] for e in entities],
                                          format_func=lambda x: dict(entities).get(x, x),
                                          index=min(default_idx, len(entities)-1))
            else:
                sel_entity = None
            depth = st.slider("遍历深度", 1, 3, 1,
                             help="1=直接邻居 | 2=间接关联(交叉持卡/相似产品) | 3=更远(慎用)")
        with c2:
            st.markdown("<br>", unsafe_allow_html=True)
            if st.button("  生成图谱", use_container_width=True, type="primary") and sel_entity:
                try:
                    with st.spinner(f"渲染图谱: depth={depth} ..."):
                        fig = render_interactive(kg, sel_entity, depth, height=650)
                    if fig:
                        st.plotly_chart(fig, use_container_width=True, config={'scrollZoom': True})
                    else:
                        st.warning("该实体无关联节点 — 尝试其他实体或类型")
                except Exception as e:
                    st.error(f"图谱渲染出错: {e}")

        # ── Neo4j 导出 ──
        with st.expander("  Neo4j 导出 (生产环境)"):
            st.markdown("""
当前 **NetworkX** 内存图 | 生产切换 **Neo4j** 后支持: 全量8000+客户 | Cypher实时查询 | 无需抽样
            """)
            if st.button("生成 Cypher 导入脚本"):
                from graphrag.kg_viz import export_cypher
                out = export_cypher(kg, os.path.join(DATA, "..", "init_graph.cypher"))
                st.success(f"已导出: {out}")
                st.caption("导入: `cat init_graph.cypher | cypher-shell -u neo4j -p password`")

    # ====== Tab 2: 产品权益树 ======
    with tab2:
        products = load_products(); benefits = load_benefits()
        mapping = load_mapping(); campaigns = load_campaigns()
        eligibility = load_eligibility()

        prod_names = products["product_name"].tolist()
        sel_idx = st.selectbox("选择产品", range(len(prod_names)),
                               format_func=lambda i: f"{products.iloc[i]['card_level']} | {prod_names[i]}")
        sel_prod = products.iloc[sel_idx]; pid = sel_prod["product_id"]

        st.markdown(f"## {sel_prod['product_name']}")
        c1,c2,c3 = st.columns(3)
        c1.metric("卡等级", sel_prod["card_level"]); c2.metric("年费", f"¥{sel_prod['annual_fee']}")
        c3.metric("目标收入", sel_prod["target_income"])
        st.caption(f"卖点: {sel_prod['key_selling_points']} | 减免: {sel_prod['annual_fee_waiver']}")

        st.markdown("---")
        rel_df = benefits[benefits["benefit_id"].isin(mapping[mapping["product_id"]==pid]["benefit_id"])]
        st.markdown(f"### 关联权益: {len(rel_df)} 项")
        cats = rel_df.groupby("benefit_category")
        emojis = {"出行":"","生活":"","消费":"","分期":"","积分":"","保险":"","健康":"","新户":"","高端专属":""}
        for cat, group in cats:
            with st.expander(f"{emojis.get(cat,'')} {cat} ({len(group)}项)", expanded=(len(cats)<=4)):
                for _, b in group.iterrows():
                    st.markdown(f"- **{b['benefit_name']}**: {b['benefit_desc'][:120]}")

        st.markdown("---")
        st.markdown("### 办理资格")
        elig = eligibility[eligibility["product_id"]==pid]
        if len(elig)>0:
            e = elig.iloc[0]
            c1,c2,c3,c4 = st.columns(4)
            c1.metric("收入", e["required_income"]); c2.metric("年龄", f"{e['min_age']}-{e['max_age']}")
            c3.metric("需持有", e["required_card_level"]); c4.metric("最低额度", f"¥{e['min_credit']:,}")
            st.caption(f"特殊: {e['special_conditions']}")

    # ====== Tab 3: 知识检索 ======
    with tab3:
        st.markdown("### 知识全文检索")
        st.caption("搜索文档库 (产品文档+产品+权益+活动+海报) | 海报匹配时展示图片")
        query = st.text_input("搜索文档", placeholder="如: 白金卡机场权益 / 618返现 / 分期免息 / 新户条件", key="doc_search")
        if query and len(query) >= 2:
            docs = load_all_docs()
            results = search_docs(query, docs)
            if results:
                type_counts = {}
                for r in results:
                    t = r.get("type", "其他")
                    type_counts[t] = type_counts.get(t, 0) + 1
                st.success(f"找到 {len(results)} 条 | " + " | ".join([f"{t}:{c}" for t, c in type_counts.items()]))
                for r in results:
                    rtype = r.get("type", "")
                    tag = {"产品文档": "#8c8c8c", "产品": "#4A90D9", "权益": "#52C41A", "活动": "#FA8C16", "海报": "#EB2F96"}.get(rtype, "#8c8c8c")
                    # 海报: 展示图片+文字
                    if rtype == "海报" and r.get("image_path"):
                        c1, c2 = st.columns([1, 3])
                        with c1:
                            st.image(r["image_path"], width=180, caption=r.get("title", "")[:15])
                        with c2:
                            st.markdown(
                                f'<div style="background:rgba(255,255,255,0.04);border-radius:6px;padding:10px;margin:5px 0;border-left:3px solid {tag}">'
                                f'<b>{r.get("title","")}</b> <span style="color:#889;font-size:0.7rem">[海报] score={r.get("score",0)}</span>'
                                f'<p style="font-size:0.85rem;margin:4px 0">{r.get("snippet","")[:200]}</p></div>',
                                unsafe_allow_html=True,
                            )
                    else:
                        st.markdown(
                            f'<div style="background:rgba(255,255,255,0.04);border-radius:6px;padding:10px;margin:5px 0;border-left:3px solid {tag}">'
                            f'<b>{r.get("title","")}</b> <span style="color:#889;font-size:0.7rem">[{rtype}] score={r.get("score",0)}</span>'
                            f'<p style="font-size:0.85rem;margin:4px 0">{r.get("snippet","")}</p></div>',
                            unsafe_allow_html=True,
                        )
            else:
                st.info("未找到匹配结果, 请尝试其他关键词")
        elif query and len(query) < 2:
            st.caption("请输入至少2个字符")

    # ====== Tab 4: 多模态检索 (海报+图片) ======
    with tab4:
        # 强制重新加载模块 (避免Streamlit缓存旧版本)
        import importlib
        for mod_name in list(sys.modules.keys()):
            if 'multimodal_engine' in mod_name:
                del sys.modules[mod_name]

        st.markdown("###  多模态检索 — 海报 & 图片")
        try:
            from multimodal_engine import __version__
            ver = __version__
        except Exception:
            ver = "v4(旧)"
        st.caption(f"搜索海报图片(已生成12张PNG) | 版本: {ver} | 生产: DeepSeek Vision + Embedding")
        q = st.text_input("搜索海报", placeholder="如: 双十一 / 天猫 / 618 / 返现 / 沉睡", key="mm_query")
        if q:
            from multimodal_engine import multimodal_search
            results = multimodal_search(q, top_k=8)
            if results:
                st.success(f"找到 {len(results)} 条 | 仅展示真正相关的结果")
                for r in results:
                    img_path = r.get("image_path","")
                    c1, c2 = st.columns([1, 3])
                    with c1:
                        if img_path and os.path.exists(img_path):
                            st.image(img_path, width=200, caption=r.get("title",""))
                        else:
                            st.markdown(f"[{r.get('vision_source','?')}]")
                    with c2:
                        st.markdown(f"**{r['title']}**")
                        st.caption(r.get("content",""))
                        # 显示匹配详情
                        with st.expander("匹配详情"):
                            st.caption(f"总分: {r['score']:.1f} | 关键词分: {r['kw_score']:.1f} | 嵌入相似: {r['embed_sim']:.3f} | LLM相关: {r['llm_relevance']}/10")
                            if r.get('matched_terms'):
                                st.caption(f"匹配词: {r['matched_terms']}")
                            if r.get('llm_reason'):
                                st.caption(f"LLM判定: {r['llm_reason']}")
                            st.caption(f"来源: {r.get('vision_source','?')}")
            else:
                st.info("无匹配海报 — 不相关的内容已自动过滤")

if __name__ == "__main__": main()
