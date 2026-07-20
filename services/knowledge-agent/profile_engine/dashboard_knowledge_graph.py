"""知识图谱 & 知识检索 v3 — 完整版"""
import os, sys, json, glob, re, pandas as pd, numpy as np
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import streamlit as st

st.set_page_config(page_title="知识图谱 & 检索", page_icon="", layout="wide")
st.markdown("""<style>
.tree-node {background:rgba(255,255,255,0.04);border-radius:6px;padding:8px 12px;margin:3px 0;border-left:3px solid #64b5f6}
.tree-node h4 {margin:0;font-size:0.95rem}
.tree-node p {margin:2px 0;font-size:0.8rem;color:#889}
.result-box {background:rgba(255,255,255,0.04);border-radius:6px;padding:10px;margin:5px 0;border-left:3px solid #81c784}
.result-box .title {color:#81c784;font-weight:bold}
.hl {background:rgba(255,167,38,0.25);padding:1px 3px;border-radius:2px}
.tag {display:inline-block;padding:2px 7px;border-radius:10px;font-size:0.65rem;margin:1px 3px}
.tag-product {background:rgba(100,181,246,0.2);color:#64b5f6}
.tag-benefit {background:rgba(129,199,132,0.2);color:#81c784}
.tag-campaign {background:rgba(255,183,77,0.2);color:#ffb74d}
.tag-doc {background:rgba(144,164,174,0.2);color:#90a4ae}
.tag-rule {background:rgba(186,104,200,0.2);color:#ba68c8}
</style>""", unsafe_allow_html=True)

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

@st.cache_data
def load_all_docs():
    """加载全部知识库文档, 去重。"""
    docs = []
    seen_titles = set()

    # 1. 产品文档TXT (20份) — 只取每份文档的前2000字(超出的模板重复内容去重)
    txt_dir = os.path.join(DATA, "unstructured", "product_docs")
    txt_files = sorted(glob.glob(os.path.join(txt_dir, "doc_*.txt")))
    for fp in txt_files:
        with open(fp, "r", encoding="utf-8") as f:
            text = f.read()
        # 取标题(第一行)
        lines = text.strip().split("\n")
        title = lines[0].strip().lstrip("#").strip() if lines else os.path.basename(fp)
        # 只取前2500字, 避免模板重复内容
        body = "\n".join(lines[1:])[:2500]
        if title not in seen_titles:
            seen_titles.add(title)
            docs.append({"source": os.path.basename(fp), "type": "产品文档", "title": title, "text": body})

    # 2. 产品CSV — 每条独立
    prods = load_products()
    for _, r in prods.iterrows():
        title = r["product_name"]
        text = f"产品名称: {title}\n卡等级: {r['card_level']}\n年费: ¥{r['annual_fee']}\n年费减免: {r['annual_fee_waiver']}\n目标收入: {r['target_income']}\n核心卖点: {r['key_selling_points']}"
        docs.append({"source": "product_catalog", "type": "产品", "title": title, "text": text})

    # 3. 权益CSV — 每条独立
    benefits = load_benefits()
    for _, r in benefits.iterrows():
        title = r["benefit_name"]
        text = f"权益名称: {title}\n类别: {r['benefit_category']}\n详细描述: {r['benefit_desc']}"
        docs.append({"source": "benefit_catalog", "type": "权益", "title": title, "text": text})

    # 4. 活动CSV — 每条独立
    camps = load_campaigns()
    for _, r in camps.iterrows():
        title = r["campaign_name"]
        text = f"活动名称: {title}\n时间: {r['start_date']} 至 {r['end_date']}\n目标客群: {r['target_segment']}\n活动规则: {r['rules']}\n预算: ¥{r['budget']:,} | 预期触达: {r['expected_reach']:,}"
        docs.append({"source": "campaign_catalog", "type": "活动", "title": title, "text": text})

    # 5. 产品办理资格
    elig = load_eligibility()
    for _, r in elig.iterrows():
        pid = r["product_id"]
        prod_name = prods[prods["product_id"]==pid]["product_name"].values[0] if pid in prods["product_id"].values else pid
        title = f"办理资格: {prod_name}"
        text = f"产品: {prod_name}\n收入要求: {r['required_income']}\n年龄: {r['min_age']}-{r['max_age']}岁\n需持有卡等级: {r['required_card_level']}\n最低授信额度: ¥{r['min_credit']:,}\n特殊条件: {r['special_conditions']}"
        docs.append({"source": "product_eligibility", "type": "办理资格", "title": title, "text": text})

    # 6. 合规规则
    rules_path = os.path.join(DATA, "unstructured", "compliance_rules.json")
    if os.path.exists(rules_path):
        with open(rules_path, "r", encoding="utf-8") as f:
            rules = json.load(f)
        for cat_name, cat_data in rules.get("categories", {}).items():
            for rule in cat_data.get("rules", []):
                title = f"[{rule['rule_id']}] {rule['rule']}"
                text = f"规则分类: {cat_data['label']}\n规则: {rule['rule']}\n说明: {rule['description']}\n严重程度: {rule['severity']}\n适用范围: {', '.join(rule.get('applicable_to',[]))}"
                docs.append({"source": "compliance_rules", "type": "合规规则", "title": title, "text": text})

    # 7. 渠道配置
    ch = pd.read_csv(os.path.join(DATA, "structured", "channel_config.csv"))
    for _, r in ch.iterrows():
        title = f"渠道: {r['channel_name']}"
        text = f"渠道: {r['channel_name']}({r['channel_code']})\n类型: {r['channel_type']}\n单次成本: ¥{r['cost_per_send']}\n日容量: {r['daily_capacity']:,} | 月容量: {r['monthly_capacity']:,}\n打开率: {r['avg_open_rate']} | 点击率: {r['avg_click_rate']}\n需授权: {r['requires_consent']} | 状态: {r['status']}"
        docs.append({"source": "channel_config", "type": "渠道", "title": title, "text": text})

    return docs


def search_docs(query, docs, top_k=15):
    """全文搜索, 关键词滑动窗口 + 去重 + 排序。"""
    if not query: return []

    # 提取2-4字关键词
    terms = []
    for L in [4, 3, 2]:
        for i in range(len(query) - L + 1):
            t = query[i:i+L]
            if t not in terms: terms.append(t)

    scored = []
    for doc in docs:
        text = doc["text"]
        score = 0
        matched = set()
        for t in terms:
            c = text.count(t)
            if c > 0:
                score += c * len(t)
                matched.add(t)
        if score > 0:
            scored.append({**doc, "score": score, "matched": list(matched)})

    scored.sort(key=lambda x: x["score"], reverse=True)

    # 去重: 标题相同的只保留最高分
    seen = set()
    unique = []
    for r in scored:
        key = r["title"][:40]
        if key not in seen:
            seen.add(key)
            unique.append(r)

    # 提取高亮片段
    for r in unique:
        text = r["text"]
        best_pos = 0
        best_cnt = 0
        for i in range(0, max(1, len(text)-150), 40):
            cnt = sum(text[i:i+200].count(t)*len(t) for t in r["matched"])
            if cnt > best_cnt:
                best_cnt = cnt
                best_pos = max(0, i-15)
        snippet = text[best_pos:best_pos+350]
        for t in sorted(r["matched"], key=lambda x:-len(x)):
            snippet = snippet.replace(t, f"<span class='hl'>{t}</span>")
        r["snippet"] = snippet.strip()

    return unique[:top_k]


def main():
    st.title("  知识图谱 & 知识检索 v3")
    st.caption("产品→权益层级关系 + 190份文档全文检索 | XX银行信用卡业务知识库")

    tab1, tab2 = st.tabs(["  产品 & 权益关系图", "  知识全文检索"])

    # ================================================================
    # Tab 1
    # ================================================================
    with tab1:
        products = load_products()
        benefits = load_benefits()
        mapping = load_mapping()
        campaigns = load_campaigns()
        eligibility = load_eligibility()

        st.markdown("### 选择产品, 查看其关联权益、办理资格和适用活动")
        st.caption("树形结构: 产品 → 权益类别 → 具体权益 → 办理条件 → 适用活动。不需要选实体类型和深度。")

        # 产品选择器 — 用 selectbox + 按钮, 不是session_state
        prod_names = products["product_name"].tolist()
        sel_idx = st.selectbox("选择产品", range(len(prod_names)),
                               format_func=lambda i: f"{products.iloc[i]['card_level']} | {prod_names[i]}")
        sel_prod = products.iloc[sel_idx]
        pid = sel_prod["product_id"]
        pname = sel_prod["product_name"]

        st.markdown("---")
        st.markdown(f"## {pname}")
        c1, c2, c3 = st.columns(3)
        c1.metric("卡等级", sel_prod["card_level"])
        c2.metric("年费", f"¥{sel_prod['annual_fee']}")
        c3.metric("目标收入", sel_prod["target_income"])
        st.caption(f"**卖点**: {sel_prod['key_selling_points']}")
        st.caption(f"**年费减免**: {sel_prod['annual_fee_waiver']}")

        # 权益树
        st.markdown("---")
        rel_benefits = mapping[mapping["product_id"]==pid]
        benefit_ids = rel_benefits["benefit_id"].tolist()
        rel_df = benefits[benefits["benefit_id"].isin(benefit_ids)]

        st.markdown(f"### 关联权益: {len(rel_df)} 项")

        if len(rel_df) > 0:
            cats = rel_df.groupby("benefit_category")
            cat_emojis = {"出行":"","生活":"","消费":"","分期":"","积分":"","保险":"","健康":"","新户":"","高端专属":""}
            for cat, group in cats:
                emoji = cat_emojis.get(cat,"")
                with st.expander(f"{emoji} {cat} ({len(group)}项)", expanded=(len(cats)<=4)):
                    for _, b in group.iterrows():
                        st.markdown(f'<div class="tree-node"><b>{b["benefit_name"]}</b><br>'
                                   f'<span style="font-size:0.8rem;color:#889">{b["benefit_desc"][:150]}</span></div>',
                                   unsafe_allow_html=True)

        # 办理资格
        st.markdown("---")
        st.markdown("### 办理资格")
        elig = eligibility[eligibility["product_id"]==pid]
        if len(elig) > 0:
            e = elig.iloc[0]
            c1,c2,c3,c4 = st.columns(4)
            c1.metric("收入要求", e["required_income"])
            c2.metric("年龄", f"{e['min_age']}-{e['max_age']}岁")
            c3.metric("需持有", e["required_card_level"])
            c4.metric("最低额度", f"¥{e['min_credit']:,}")
            st.caption(f"特殊条件: {e['special_conditions']}")

        # 适用活动
        st.markdown("---")
        st.markdown("### 适用活动")
        card_level = sel_prod["card_level"]
        # 匹配活动
        rel_camps = []
        for _, c in campaigns.iterrows():
            seg = str(c["target_segment"])
            if card_level in seg or ("all" in str(c.get("target_segment","")).lower()):
                rel_camps.append(c)
        if rel_camps:
            for c in rel_camps[:8]:
                with st.expander(c["campaign_name"], expanded=False):
                    c1,c2 = st.columns(2)
                    c1.caption(f"时间: {c['start_date']} ~ {c['end_date']}")
                    c1.caption(f"预算: ¥{c['budget']:,} | 触达: {c['expected_reach']:,}")
                    c2.caption(f"客群: {c['target_segment']}")
                    c2.caption(f"规则: {c['rules']}")
        else:
            st.caption("暂无匹配活动")

    # ================================================================
    # Tab 2: 知识全文检索
    # ================================================================
    with tab2:
        st.markdown("### 知识全文检索")
        st.caption("搜索范围: 20份产品文档 + 15产品 + 90权益 + 25活动 + 15办理资格 + 14合规规则 + 8渠道 = **~190份知识条目**")

        query = st.text_input("输入问题或关键词", placeholder="如: 白金卡机场权益 / 分期手续费率 / 新户开卡条件 / 套现风险 / 短信渠道成本")
        if query:
            docs = load_all_docs()
            with st.spinner(f"搜索 {len(docs)} 份文档..."):
                results = search_docs(query, docs, top_k=15)

            if results:
                # 统计类型分布
                type_counts = {}
                for r in results:
                    t = r["type"]
                    type_counts[t] = type_counts.get(t, 0) + 1

                st.success(f"找到 {len(results)} 条结果 | " + " | ".join([f"{t}:{c}" for t,c in type_counts.items()]))

                # 类型筛选
                types = list(type_counts.keys())
                sel_types = st.multiselect("筛选类型", types, default=types,
                                          format_func=lambda x: f"{x}({type_counts[x]})")

                for r in results:
                    if r["type"] not in sel_types: continue
                    tag_cls = {"产品文档":"tag-doc","产品":"tag-product","权益":"tag-benefit",
                              "活动":"tag-campaign","合规规则":"tag-rule","办理资格":"tag-product",
                              "渠道":"tag-doc"}.get(r["type"],"tag-doc")
                    st.markdown(f'<div class="result-box">'
                               f'<span class="tag {tag_cls}">{r["type"]}</span> '
                               f'<span style="font-size:0.65rem;color:#789">{r["source"]}</span>'
                               f'<p class="title">{r["title"]}</p>'
                               f'<p style="font-size:0.85rem">{r["snippet"]}</p>'
                               f'<p style="font-size:0.65rem;color:#789">相关度: {r["score"]} | 匹配: {", ".join(r["matched"][:5])}</p>'
                               f'</div>', unsafe_allow_html=True)
            else:
                st.warning("未找到匹配结果, 请尝试其他关键词")

if __name__ == "__main__": main()
