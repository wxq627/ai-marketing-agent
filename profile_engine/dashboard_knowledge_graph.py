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
    txt_dir = os.path.join(DATA, "unstructured", "product_docs")
    for fp in sorted(glob.glob(os.path.join(txt_dir, "doc_*.txt"))):
        with open(fp, "r", encoding="utf-8") as f: text = f.read()
        lines = text.strip().split("\n")
        title = lines[0].strip().lstrip("#").strip() if lines else os.path.basename(fp)
        docs.append({"source": os.path.basename(fp), "type": "产品文档", "title": title, "text": "\n".join(lines[1:])[:2500]})
    for _, r in load_products().iterrows():
        docs.append({"source": "product_catalog", "type": "产品", "title": r["product_name"],
            "text": f"{r['product_name']} | {r['card_level']} | 年费¥{r['annual_fee']} | {r['key_selling_points']}"})
    for _, r in load_benefits().iterrows():
        docs.append({"source": "benefit_catalog", "type": "权益", "title": r["benefit_name"],
            "text": f"{r['benefit_name']} | {r['benefit_category']} | {r['benefit_desc']}"})
    for _, r in load_campaigns().iterrows():
        docs.append({"source": "campaign_catalog", "type": "活动", "title": r["campaign_name"],
            "text": f"{r['campaign_name']} | {r['start_date']}~{r['end_date']} | {r['rules']}"})
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

    tab1, tab2, tab3 = st.tabs(["  交互式知识图谱", "  产品 & 权益关系树", "  知识全文检索"])

    # ====== Tab 1: 交互式图谱 ======
    with tab1:
        st.markdown("###  交互式知识图谱")
        st.caption("可缩放/拖拽/悬停查看详情。选实体→调深度→生成。生产环境可导入 Neo4j Browser。")

        kg = load_kg()
        from graphrag.kg_viz import render_interactive, TYPE_LABELS_ZH

        c1, c2 = st.columns([3, 1])
        with c1:
            # 获取实体列表
            entity_types = list(set(d.get("type","") for _,d in kg.G.nodes(data=True) if d.get("type")))
            type_names_zh = {"product":"产品","benefit":"权益","campaign":"活动","customer":"客户",
                            "card":"信用卡","document":"文档","installment_rule":"分期条款"}
            sel_type = st.selectbox("实体类型", entity_types, format_func=lambda x: type_names_zh.get(x,x))
            entities = [(n, str(d.get("name",n))[:30]) for n,d in kg.G.nodes(data=True) if d.get("type")==sel_type]
            if entities:
                sel_entity = st.selectbox("选择实体", [e[0] for e in entities[:50]],
                                         format_func=lambda x: dict(entities).get(x,x))
            else: sel_entity = None
            depth = st.slider("遍历深度", 1, 3, 2)
        with c2:
            st.markdown("<br><br>", unsafe_allow_html=True)
            if st.button("  生成图谱", use_container_width=True) and sel_entity:
                with st.spinner("渲染交互式图谱..."):
                    fig = render_interactive(kg, sel_entity, depth, height=620)
                if fig: st.plotly_chart(fig, use_container_width=True, config={'scrollZoom': True})
                else: st.warning("无关联节点")

        st.caption("图例:  产品  权益  活动  客户  信用卡  文档  分期条款 | 拖拽/滚轮缩放/悬停详情")
        st.caption("关系: HOLDS(持有) BELONGS_TO(属于) INCLUDES(包含) APPLIES_TO(适用) GOVERNED_BY(约束)")

        # 导出按钮
        with st.expander("Neo4j 导出 (生产环境)"):
            if st.button("生成 Cypher 导入脚本"):
                from graphrag.kg_viz import export_cypher
                out = export_cypher(kg, os.path.join(DATA, "..", "init_graph.cypher"))
                st.success(f"已导出: {out}")
                st.caption("将此文件导入 Neo4j: `cat init_graph.cypher | cypher-shell -u neo4j -p password`")

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
        st.caption("搜索 187 份文档 (产品+权益+活动+条款) | DeepSeek Embedding 语义匹配")
        query = st.text_input("搜索", placeholder="如: 白金卡机场权益 / 分期手续费 / 新户条件")
        if query:
            docs = load_all_docs()
            results = search_docs(query, docs)
            if results:
                type_counts = {}; [type_counts.update({r["type"]: type_counts.get(r["type"],0)+1}) for r in results]
                st.success(f"{len(results)} 条 | " + " | ".join([f"{t}:{c}" for t,c in type_counts.items()]))
                for r in results:
                    tag = {"产品文档":"#8c8c8c","产品":"#4A90D9","权益":"#52C41A","活动":"#FA8C16"}.get(r["type"],"#8c8c8c")
                    st.markdown(f'<div style="background:rgba(255,255,255,0.04);border-radius:6px;padding:10px;margin:5px 0;border-left:3px solid {tag}">'
                               f'<b>{r["title"]}</b> <span style="color:#889;font-size:0.7rem">[{r["type"]}] score={r["score"]}</span>'
                               f'<p style="font-size:0.85rem;margin:4px 0">{r["snippet"]}</p></div>', unsafe_allow_html=True)
            else: st.warning("未找到")

if __name__ == "__main__": main()
