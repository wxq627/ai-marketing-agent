"""商品画像资源池 v5 — GraphRAG + 多模态 + CRUD"""
import os, sys, json, glob, time, pandas as pd
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import streamlit as st
from datetime import datetime

st.set_page_config(page_title="商品画像资源池", page_icon="", layout="wide")

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA = os.path.join(BASE, "mock_data")
POSTERS_DIR = os.path.join(DATA, "unstructured", "posters")
POSTERS_IMG = os.path.join(POSTERS_DIR, "images")
DOCS_DIR = os.path.join(DATA, "unstructured", "product_docs")
os.makedirs(POSTERS_IMG, exist_ok=True)
os.makedirs(DOCS_DIR, exist_ok=True)

@st.cache_data(ttl=3600)
def load_products(): return pd.read_csv(os.path.join(DATA,"structured","product_catalog.csv"))
@st.cache_data(ttl=3600)
def load_benefits(): return pd.read_csv(os.path.join(DATA,"structured","benefit_catalog.csv"))
@st.cache_data(ttl=3600)
def load_mapping(): return pd.read_csv(os.path.join(DATA,"structured","product_benefit_mapping.csv"))
@st.cache_data(ttl=3600)
def load_campaigns(): return pd.read_csv(os.path.join(DATA,"structured","campaign_catalog.csv"))
@st.cache_data(ttl=3600)
def load_eligibility(): return pd.read_csv(os.path.join(DATA,"structured","product_eligibility.csv"))

@st.cache_resource(ttl=3600)
def load_kg():
    from graphrag.kg_builder import KnowledgeGraph
    kg = KnowledgeGraph(); kg.build(); return kg

@st.cache_data(ttl=3600)
def _get_posters(): return sorted(glob.glob(os.path.join(POSTERS_DIR,"*.json")))
@st.cache_data(ttl=3600)
def _get_docs(): return sorted(glob.glob(os.path.join(DOCS_DIR,"doc_*.txt")))

@st.cache_data(ttl=3600)
def load_all_docs():
    docs = []
    for fp in _get_docs():
        with open(fp,"r",encoding="utf-8") as f: text = f.read()
        lines = text.strip().split("\n")
        title = lines[0].strip().lstrip("#").strip() if lines else os.path.basename(fp)
        docs.append({"source":os.path.basename(fp),"type":"产品文档","title":title,"text":"\n".join(lines[1:])[:2500]})
    for _,r in load_products().iterrows():
        docs.append({"source":"product_catalog","type":"产品","title":r["product_name"],
            "text":f"{r['product_name']} | {r['card_level']} | 年费{r['annual_fee']} | {r['key_selling_points']}"})
    for _,r in load_benefits().iterrows():
        docs.append({"source":"benefit_catalog","type":"权益","title":r["benefit_name"],
            "text":f"{r['benefit_name']} | {r['benefit_category']} | {r['benefit_desc']}"})
    for _,r in load_campaigns().iterrows():
        docs.append({"source":"campaign_catalog","type":"活动","title":r["campaign_name"],
            "text":f"{r['campaign_name']} | {r['start_date']}~{r['end_date']} | {r['rules']}"})
    for jf in _get_posters():
        with open(jf,"r",encoding="utf-8") as f: info = json.load(f)
        parts = [info.get("activity_name",""),info.get("main_title",""),info.get("sub_title",""),
                 info.get("target_segment",""),info.get("cta_text","")]
        parts.extend(info.get("rules_summary",[]))
        # 从visual_description提取实体名(品牌/平台/产品名) — 与多模态检索同步
        vis = info.get("visual_description","")
        if vis:
            import re as _re3
            entities = _re3.findall(r'[一-鿿]{2,6}', vis)
            stop_words = {"背景","展示","画面","整体","风格","色调","按钮","文字",
                          "设计","海报","底部","顶部","左侧","右侧","中间","场景",
                          "渐变","手机","购物","消费","看到","查看","突出","呈现"}
            vis_entities = [e for e in entities if e not in stop_words]
            parts.extend(vis_entities[:8])
        # 优先使用完整OCR文本
        ocr_full = info.get("ocr_full_text","")
        ocr_kw = info.get("ocr_keywords",[])
        base_text = " | ".join(p for p in parts if p)
        poster_text = f"{base_text} | {ocr_full} | {' '.join(ocr_kw)}" if ocr_full else base_text
        img_name = info.get("image_file","")
        img_path = os.path.join(POSTERS_IMG,img_name) if img_name else ""
        docs.append({"source":os.path.basename(jf),"type":"海报","title":info.get("activity_name",""),
            "text":poster_text[:3000],"image_path":img_path if os.path.exists(img_path) else ""})
    return docs

@st.cache_data(ttl=600, show_spinner=False)
def search_docs_cached(query, top_k=20):
    """缓存搜索结果, 避免每次按键都重算O(n*m)"""
    docs = load_all_docs()
    return search_docs(query, docs, top_k)

def search_docs(query,docs,top_k=20):
    terms = []
    for L in [4,3,2]:
        for i in range(len(query)-L+1):
            t = query[i:i+L]
            if t not in terms: terms.append(t)
    scored = []
    for doc in docs:
        score = sum(doc["text"].count(t)*len(t)*len(t) for t in terms)  # 平方权重: 完整匹配权重更高
        # 海报加分: 视觉内容天然比文本文档匹配少, 适当提升可见度
        if doc.get("type") == "海报":
            score = int(score * 1.5)
        if score > 0: scored.append({**doc,"score":score,"matched":[t for t in terms if t in doc["text"]]})
    scored.sort(key=lambda x:x["score"],reverse=True)
    seen=set(); unique=[]
    for r in scored:
        k=r["title"][:40]
        if k not in seen: seen.add(k); unique.append(r)
    for r in unique:
        t=r["text"]
        bp=max(range(max(1,len(t)-150)),key=lambda i:sum(t[i:i+200].count(x)*len(x) for x in r["matched"]),default=0)
        snippet=t[bp:bp+300]
        for x in sorted(r["matched"],key=lambda x:-len(x)): snippet=snippet.replace(x,f"**{x}**")
        r["snippet"]=snippet.strip()
    return unique[:top_k]

def main():
    st.title("  商品画像资源池")
    st.caption("GraphRAG混合检索 | 彩色关系图谱 | 多模态检索 | 知识CRUD | DeepSeek驱动")
    tab1,tab2,tab3,tab4 = st.tabs(["  交互式知识图谱","  产品 & 权益关系树","  知识全文检索","   多模态检索"])

    # ═══ 侧边栏 CRUD ═══
    with st.sidebar:
        st.markdown("###  知识管理 (CRUD)")
        crud_tabs = st.tabs(["  新增","  删除","  状态"])

        with crud_tabs[0]:
            st.markdown("**新增海报**")
            st.caption("上传图片→OCR自动提取文字→入库→Tab3+Tab4检索")
            new_img = st.file_uploader("上传海报图片*",type=["png","jpg","jpeg"],key="crud_img")
            if new_img:
                st.image(new_img,width=300,caption="预览")
                # 检测OCR是否就绪
                from multimodal_engine import _init_tesseract, _ocr_tesseract
                has_tess = _init_tesseract()
                if not has_tess:
                    st.warning("  Tesseract OCR未就绪, 将使用手动输入模式")
                else:
                    st.caption("  Tesseract OCR就绪, 将自动提取图中文字")
                # 手动输入作为补充（非必填）
                manual_text = st.text_area("补充/修正文字 (OCR自动提取不理想时填写)",key="crud_manual",
                    placeholder="可选: 如OCR结果不理想, 在此手动输入图中文字...",height=60)
                manual_topic = st.text_input("活动名称 (留空则自动从OCR提取)",key="crud_topic",placeholder="如: 双十二年终回馈")
                if st.button("  入库",use_container_width=True,type="primary"):
                    with st.spinner("处理中..."):
                        import json as j, re as _re
                        safe_name = f"uploaded_{int(time.time())}"
                        img_path = os.path.join(POSTERS_IMG,f"{safe_name}.png")
                        with open(img_path,"wb") as f: f.write(new_img.getbuffer())

                        all_text=""; main_topic=""; keywords=[]; src="unknown"

                        # ══ Step 1: Tesseract OCR 自动提取 ══
                        ocr_text = _ocr_tesseract(img_path) if has_tess else ""
                        if ocr_text and len(ocr_text.strip()) >= 3:
                            all_text = ocr_text.strip()
                            # 自动提取主题: OCR第一行中文文本
                            ocr_lines = [l.strip() for l in all_text.split('\n') if l.strip()]
                            # 找第一个包含中文的行作为主题
                            for line in ocr_lines:
                                chinese_chars = sum(1 for c in line if '一' <= c <= '鿿' or '㐀' <= c <= '䶿')
                                if chinese_chars >= 2 and len(line) <= 50:
                                    main_topic = line
                                    break
                            if not main_topic:
                                main_topic = ocr_lines[0][:40] if ocr_lines else all_text[:40]
                            # 自动提取关键词: 按标点和空格分词, 取2-8字中文词组
                            kw_set = set()
                            for line in ocr_lines:
                                # 用竖线、标点、空格拆分
                                segments = _re.split(r'[|\s,，、。！？；：()（）【】《》\[\]{{}}]+', line)
                                for seg in segments:
                                    seg = seg.strip()
                                    if not seg:
                                        continue
                                    # 提取连续中文+数字(跳过纯英文)
                                    chinese_parts = _re.findall(r'[一-鿿㐀-䶿\d]+', seg)
                                    for part in chinese_parts:
                                        part = part.strip()
                                        if 2 <= len(part) <= 8:
                                            if part.isdigit() and len(part) <= 3:
                                                continue
                                            kw_set.add(part)
                            keywords = sorted(kw_set, key=lambda x: -len(x))[:15]

                            # 尝试DeepSeek增强
                            try:
                                from llm_client import chat, is_available as ds_ok
                                if ds_ok():
                                    prompt = f'分析OCR输出JSON:{{"main_topic":"主题","keywords":["k1"]}}\nOCR:{ocr_text[:800]}'
                                    resp = chat([{"role":"user","content":prompt}], temperature=0.1)
                                    resp = resp.strip()
                                    if resp.startswith("```"): resp = resp.split("\n",1)[1].rsplit("\n",1)[0]
                                    if resp.startswith("json"): resp = resp[4:]
                                    s = j.loads(resp)
                                    main_topic = s.get("main_topic", main_topic) or main_topic
                                    keywords = s.get("keywords", keywords) or keywords
                                    src = "ocr+llm"
                                else:
                                    src = "ocr_auto"
                            except Exception:
                                src = "ocr_auto"
                            st.success(f"  OCR自动提取成功 ({src}): {len(all_text)}字, {len(keywords)}词")
                        else:
                            if has_tess:
                                st.info(f"  OCR未提取到足够文字 ({len(ocr_text.strip())}字), 请手动输入")
                            else:
                                st.info("  OCR未就绪, 请手动输入")

                        # ══ Step 2: 手动输入补充 (OCR失败时必填) ══
                        if not all_text:
                            if manual_text.strip():
                                all_text = manual_text.strip()
                                main_topic = manual_topic.strip() or all_text.split("\n")[0][:40]
                                keywords = [w.strip() for w in all_text.replace("\n"," ").split() if len(w.strip())>=2][:10]
                                src = "manual"
                                st.success("  使用手动输入")
                            elif manual_topic.strip():
                                # 只有活动名称, 没有内容
                                all_text = manual_topic.strip()
                                main_topic = manual_topic.strip()
                                src = "manual_title_only"
                                st.warning("  仅保存活动名称, 建议补充文字内容")
                            else:
                                st.error("OCR未提取到文字且未手动输入, 请填写图片中的文字内容")
                                st.stop()

                        # ══ Step 3: 预填充vision_cache (让Tab4立即可搜) ══
                        try:
                            from multimodal_engine import vision_recognize
                            vision_recognize(img_path, use_cache=False)
                        except Exception:
                            pass

                        # ══ Step 4: 保存JSON ══
                        st.markdown(f"**主题**: {main_topic}")
                        if keywords: st.markdown(f"**关键词**: {', '.join(keywords[:10])}")
                        st.text_area("入库文字", all_text[:500], height=80, disabled=True)

                        json_data = {
                            "image_file": f"{safe_name}.png",
                            "activity_name": main_topic,
                            "campaign_id": f"CAMP_{datetime.now().strftime('%Y%m%d%H%M%S')}",
                            "start_date": datetime.now().strftime("%Y-%m-%d"),
                            "end_date": "2026-12-31",
                            "main_title": all_text[:100],
                            "sub_title": "",
                            "visual_description": f"来源:{src}",
                            "rules_summary": keywords[:6],
                            "target_segment": "所有持卡人",
                            "cta_text": "立即参与",
                            "ocr_full_text": all_text[:3000],
                            "ocr_keywords": keywords[:15],
                        }
                        json_path = os.path.join(POSTERS_DIR, f"{safe_name}.json")
                        with open(json_path, "w", encoding="utf-8") as f:
                            j.dump(json_data, f, ensure_ascii=False, indent=2)

                        # 清空所有缓存, 强制重新加载
                        st.cache_data.clear()
                        st.cache_resource.clear()
                        st.success(f"  已入库: {safe_name} ({src}) → Tab3全文检索 + Tab4多模态检索 均可搜索")

            st.markdown("---")
            st.markdown("**新增文档**")
            doc_title=st.text_input("文档标题",key="crud_doc_title")
            doc_content=st.text_area("文档内容",key="crud_doc_content",height=100)
            if st.button("  新增文档",use_container_width=True):
                if doc_title and doc_content:
                    idx=len(_get_docs())+1
                    dp=os.path.join(DOCS_DIR,f"doc_{idx:03d}_{doc_title[:10]}.txt")
                    with open(dp,"w",encoding="utf-8") as f: f.write(f"# {doc_title}\n\n{doc_content}")
                    st.cache_data.clear(); st.success(f"已新增: {os.path.basename(dp)}")
                else: st.error("请输入标题和内容")

        with crud_tabs[1]:
            st.markdown("**删除海报**")
            posters=[os.path.basename(p) for p in _get_posters()]
            if posters:
                dp=st.selectbox("选择海报",posters,key="crud_del_p")
                if st.button("  删除此海报",use_container_width=True):
                    jp=os.path.join(POSTERS_DIR,dp)
                    if os.path.exists(jp):
                        with open(jp,"r",encoding="utf-8") as f: info=json.load(f)
                        im=info.get("image_file",""); ip=os.path.join(POSTERS_IMG,im)
                        if os.path.exists(ip): os.remove(ip)
                        os.remove(jp); st.cache_data.clear(); st.success(f"已删除: {dp}"); st.rerun()
            else: st.caption("无海报")
            st.markdown("---")
            st.markdown("**删除文档**")
            docs=[os.path.basename(d) for d in _get_docs()]
            if docs:
                dd=st.selectbox("选择文档",docs,key="crud_del_d")
                if st.button("  删除此文档",use_container_width=True):
                    os.remove(os.path.join(DOCS_DIR,dd)); st.cache_data.clear(); st.success(f"已删除: {dd}"); st.rerun()
            else: st.caption("无文档")

        with crud_tabs[2]:
            st.metric("海报",len(_get_posters())); st.metric("文档",len(_get_docs()))
            st.metric("产品",len(load_products())); st.metric("权益",len(load_benefits()))
            st.metric("活动",len(load_campaigns()))
            if st.button("  刷新缓存",use_container_width=True):
                st.cache_data.clear(); st.cache_resource.clear(); st.rerun()

    # ====== Tab 1: 交互式图谱 ======
    with tab1:
        st.markdown("###  交互式知识图谱 (GraphRAG)")
        kg = load_kg()
        from graphrag.kg_viz import render_interactive, TYPE_LABELS_ZH, RELATION_LABELS_ZH
        stats = kg.stats(); nt = stats['node_types']

        with st.expander("  图谱说明",expanded=False):
            tab_a,tab_b=st.tabs(["实体与关系","深度与搜索"])
            with tab_a:
                c1,c2=st.columns(2)
                with c1:
                    st.markdown(f"""
**实体 (节点):**
| 颜色 | 类型 | 数量 |
|------|------|------|
|  蓝 | 产品 | {nt.get('product',0)} |
|  绿 | 权益 | {nt.get('benefit',0)} |
|  橙 | 活动 | {nt.get('campaign',0)} |
|  红 | 客户 | {nt.get('customer',0)} |
|  紫 | 信用卡 | {nt.get('card',0)} |
|  灰 | 文档 | {nt.get('document',0)} |
|  青 | 分期条款 | {nt.get('installment_rule',0)} |
> 客户按card_level×lifecycle分层抽样,卡按cust_id唯一
                    """)
                with c2:
                    st.markdown("""
**关系 (边):**
| 颜色 | 关系 | 含义 |
|------|------|------|
|  绿 | 包含权益 | 产品有哪些权益 |
|  橙 | 活动适用 | 活动适用哪些产品 |
|  红 | 面向客户 | 活动目标哪些客户 |
|  紫 | 持有/属于 | 客户持卡/卡属产品 |
|  青 | 分期规则 | 产品适用分期 |
                    """)
            with tab_b:
                st.markdown("""
**深度**: depth=1直接邻居(推荐), depth=2间接关联(交叉持卡)
**GraphRAG**: 关键词锚定种子→图扩展邻居→综合评分排序
                """)

        st.caption(f"图谱: {stats['nodes']}节点 {stats['edges']}边 | "+
            " | ".join([f"{TYPE_LABELS_ZH.get(k,k)}:{v}" for k,v in nt.items()]))

        st.markdown("---")
        st.markdown("####  GraphRAG 混合检索")
        sq = st.text_input("输入查询",placeholder="白金卡机场权益 / 618返现 / 分期免息",key="kg_search")
        search_results=[]
        if sq:
            try:
                search_results=kg.hybrid_search(sq,top_k=12)
                if search_results:
                    st.success(f"找到 {len(search_results)} 条")
                    for i,r in enumerate(search_results[:8]):
                        st.markdown(f"**{i+1}. [{r['type_zh']}] {r['name']}** score={r['score']:.0f}")
                        if r.get("seed_path"):
                            for s in r["seed_path"]: st.caption(f"  {s}")
                else: st.info("无匹配结果")
            except Exception as e: st.warning(f"搜索出错: {e}")

        st.markdown("---")
        st.markdown("####  实体浏览器")
        c1,c2=st.columns([3,1])
        with c1:
            etypes=sorted(set(d.get("type","") for _,d in kg.G.nodes(data=True) if d.get("type")))
            tf={t:f"{TYPE_LABELS_ZH.get(t,t)}({nt.get(t,0)})" for t in etypes}
            stp=st.selectbox("实体类型",etypes,format_func=lambda x:tf.get(x,x))
            ents=[(n,str(d.get("name",n))[:35]) for n,d in kg.G.nodes(data=True) if d.get("type")==stp]
            if ents:
                ents.sort(key=lambda x:x[1])
                rid={r["node_id"] for r in search_results}
                di=0
                if rid:
                    for i,(eid,_) in enumerate(ents):
                        if eid in rid: di=i; break
                se=st.selectbox("选择实体",[e[0] for e in ents],format_func=lambda x:dict(ents).get(x,x),index=min(di,len(ents)-1))
            else: se=None
            depth=st.slider("遍历深度",1,3,1,help="1=直接邻居 | 2=间接关联")
        with c2:
            st.markdown("<br>",unsafe_allow_html=True)
            if st.button("  生成图谱",use_container_width=True,type="primary") and se:
                try:
                    with st.spinner("渲染..."):
                        fig=render_interactive(kg,se,depth,height=650)
                    if fig: st.plotly_chart(fig,use_container_width=True,config={'scrollZoom':True})
                    else: st.warning("无关联节点")
                except Exception as e: st.error(f"渲染出错: {e}")
        with st.expander("  Neo4j 导出"):
            if st.button("生成 Cypher 脚本"):
                from graphrag.kg_viz import export_cypher
                out=export_cypher(kg,os.path.join(DATA,"..","init_graph.cypher"))
                st.success(f"已导出: {out}")

    # ====== Tab 2: 产品权益树 ======
    with tab2:
        products=load_products(); benefits=load_benefits()
        mapping=load_mapping(); campaigns=load_campaigns(); eligibility=load_eligibility()
        pn=products["product_name"].tolist()
        si=st.selectbox("选择产品",range(len(pn)),format_func=lambda i:f"{products.iloc[i]['card_level']} | {pn[i]}")
        sp=products.iloc[si]; pid=sp["product_id"]
        st.markdown(f"## {sp['product_name']}")
        c1,c2,c3=st.columns(3)
        c1.metric("卡等级",sp["card_level"]); c2.metric("年费",f"{sp['annual_fee']}"); c3.metric("目标收入",sp["target_income"])
        st.caption(f"卖点: {sp['key_selling_points']} | 减免: {sp['annual_fee_waiver']}")
        st.markdown("---")
        rel_df=benefits[benefits["benefit_id"].isin(mapping[mapping["product_id"]==pid]["benefit_id"])]
        st.markdown(f"### 关联权益: {len(rel_df)} 项")
        cats=rel_df.groupby("benefit_category")
        for cat,group in cats:
            with st.expander(f"{cat} ({len(group)}项)",expanded=(len(cats)<=4)):
                for _,b in group.iterrows(): st.markdown(f"- **{b['benefit_name']}**: {b['benefit_desc'][:120]}")
        st.markdown("---"); st.markdown("### 办理资格")
        elig=eligibility[eligibility["product_id"]==pid]
        if len(elig)>0:
            e=elig.iloc[0]
            c1,c2,c3,c4=st.columns(4)
            c1.metric("收入",e["required_income"]); c2.metric("年龄",f"{e['min_age']}-{e['max_age']}")
            c3.metric("需持有",e["required_card_level"]); c4.metric("最低额度",f"{e['min_credit']:,}")

    # ====== Tab 3: 知识检索 ======
    with tab3:
        st.markdown("### 知识全文检索")
        st.caption("搜索文档库(产品文档+产品+权益+活动+海报)")
        q=st.text_input("搜索文档",placeholder="白金卡机场权益 / 618返现 / 分期免息",key="doc_search")
        if q and len(q)>=2:
            results=search_docs_cached(q, top_k=20)
            if results:
                tc={}
                for r in results: tc[r.get("type","其他")]=tc.get(r.get("type","其他"),0)+1
                st.success(f"找到 {len(results)} 条 | "+" | ".join([f"{t}:{c}" for t,c in tc.items()]))
                for r in results:
                    rt=r.get("type",""); tag={"产品文档":"#8c8c8c","产品":"#4A90D9","权益":"#52C41A","活动":"#FA8C16","海报":"#EB2F96"}.get(rt,"#8c8c8c")
                    if rt=="海报" and r.get("image_path"):
                        c1,c2=st.columns([1,3])
                        with c1: st.image(r["image_path"],width=180,caption=r.get("title","")[:15])
                        with c2: st.markdown(f'<div style="background:rgba(255,255,255,0.04);border-radius:6px;padding:10px;margin:5px 0;border-left:3px solid {tag}"><b>{r.get("title","")}</b> <span style="color:#889;font-size:0.7rem">[海报] score={r.get("score",0)}</span><p style="font-size:0.85rem;margin:4px 0">{r.get("snippet","")[:200]}</p></div>',unsafe_allow_html=True)
                    else: st.markdown(f'<div style="background:rgba(255,255,255,0.04);border-radius:6px;padding:10px;margin:5px 0;border-left:3px solid {tag}"><b>{r.get("title","")}</b> <span style="color:#889;font-size:0.7rem">[{rt}] score={r.get("score",0)}</span><p style="font-size:0.85rem;margin:4px 0">{r.get("snippet","")}</p></div>',unsafe_allow_html=True)
            else: st.info("未找到匹配结果")
        elif q and len(q)<2: st.caption("请输入至少2个字符")

    # ====== Tab 4: 多模态检索 ======
    with tab4:
        st.markdown("###  多模态检索")
        try:
            from multimodal_engine import __version__; ver=__version__
        except: ver="?"
        st.caption(f"OCR+LLM+关键词+语义验证 | v{ver} | DeepSeek驱动")
        cq, cb2 = st.columns([3,1])
        with cq:
            q=st.text_input("搜索海报",placeholder="双十一 / 天猫 / 618 / 返现 / 双十二",key="mm_query")
        with cb2:
            st.markdown("<br>",unsafe_allow_html=True)
            if st.button("  清缓存",use_container_width=True,key="mm_clear"):
                import shutil
                vcd = os.path.join(POSTERS_DIR,".vision_cache")
                if os.path.exists(vcd): shutil.rmtree(vcd); os.makedirs(vcd)
                st.cache_data.clear(); st.cache_resource.clear(); st.rerun()
        if q:
            from multimodal_engine import multimodal_search
            results=multimodal_search(q,top_k=8)
            if results:
                st.success(f"找到 {len(results)} 条")
                for r in results:
                    ip=r.get("image_path",""); c1,c2=st.columns([1,3])
                    with c1:
                        if ip and os.path.exists(ip): st.image(ip,width=200,caption=r.get("title",""))
                        else: st.markdown(f"[{r.get('vision_source','?')}]")
                    with c2:
                        st.markdown(f"**{r['title']}**"); st.caption(r.get("content",""))
                        with st.expander("详情"):
                            st.caption(f"总分:{r['score']:.1f} kw={r['kw_score']:.1f} sim={r['embed_sim']:.3f} LLM={r['llm_relevance']}/10")
                            if r.get('matched_terms'): st.caption(f"匹配: {r['matched_terms']}")
            else: st.info("无匹配 — 不相关内容已过滤")

if __name__=="__main__": main()
