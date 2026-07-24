"""客户360视图 — DeepSeek六意图 + 渠道策略优化"""
import os, sys, sqlite3, pandas as pd, numpy as np, json, random, re, time
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import streamlit as st
import plotly.graph_objects as go
import plotly.express as px
from datetime import datetime

st.set_page_config(page_title="客户360", page_icon="", layout="wide")
st.markdown("""<style>
.mbox{background:rgba(255,255,255,0.05);border-radius:10px;padding:10px;border:1px solid rgba(255,255,255,0.08);margin:3px 0;text-align:center}
.cg{color:#66bb6a;font-weight:bold}.co{color:#ffa726;font-weight:bold}.cr{color:#ef5350;font-weight:bold}
</style>""", unsafe_allow_html=True)

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DB_PATH = os.path.join(BASE, "mock_data", "knowledge_agent.db")
NOW = datetime.now().strftime("%Y-%m-%d %H:%M")

def get_db():
    conn = sqlite3.connect(DB_PATH); conn.row_factory = sqlite3.Row; return conn

@st.cache_data(ttl=3600)
def load():
    conn = get_db()
    p = pd.read_sql("SELECT * FROM customer_profile", conn)
    mp = pd.read_sql("SELECT * FROM id_mapping WHERE id_type='cust_id'", conn)
    mp_phone = pd.read_sql("SELECT * FROM id_mapping WHERE id_type='phone'", conn)
    stats = {}
    for t in ["customer_profile","transaction_log_full","feedback_events"]:
        try: stats[t] = conn.execute(f"SELECT COUNT(*) FROM {t}").fetchone()[0]
        except: stats[t] = 0
    stats["db_size"] = f"{os.path.getsize(DB_PATH)/1024/1024:.0f}MB"
    conn.close()
    # Build name index (supports duplicate names)
    n2u = {}
    for _, r in p.iterrows():
        name = str(r.get("demographics_name",""))
        if name == "nan" or not name: continue
        oid = r["oneid"]
        if name not in n2u: n2u[name] = []
        n2u[name].append(oid)
    return {"p": p, "idx": dict(zip(p["oneid"], range(len(p)))),
        "c2u": dict(zip(mp["id_value"], mp["oneid"])),
        "p2u": dict(zip(mp_phone["id_value"], mp_phone["oneid"])),
        "n2u": n2u, "stats": stats}

def search(query, stype, data):
    if stype == "OneID" and query in data["idx"]: return query
    if stype == "cust_id": return data["c2u"].get(query)
    if stype == "姓名":
        n2u = data["n2u"]
        if query in n2u:
            matches = n2u[query]
            return matches[0] if len(matches) == 1 else matches
        for name, oids in n2u.items():
            if query in name:
                return oids[0] if len(oids) == 1 else oids
        return None
    if stype == "手机号": return data["p2u"].get(query)
    return None

def g(row, k, d=""):
    v = row.get(k, d)
    return d if v is None or (isinstance(v,float) and np.isnan(v)) else v

def add_d(oid, f, v):
    if "delta" not in st.session_state: st.session_state.delta = {}
    if oid not in st.session_state.delta: st.session_state.delta[oid] = {}
    st.session_state.delta[oid][f] = round(st.session_state.delta[oid].get(f,0)+v,2)

# ═══════════════════════
def render_static(row, oneid):
    st.subheader("静态画像 (T+1每日, DB实时)")
    dd = st.session_state.get("delta",{}).get(oneid,{})
    c1,c2,c3,c4,c5 = st.columns(5)
    with c1:
        st.caption("人口"); st.write(f"{g(row,'demographics_name')} | {g(row,'demographics_gender')} | {int(g(row,'demographics_age',0))}岁")
        st.write(f"{g(row,'demographics_city')} | {g(row,'demographics_occupation')}")
        st.write(f"收入:{g(row,'demographics_income_level')} | 学历:{g(row,'demographics_education')}")
    with c2:
        st.caption("账户"); credit=float(g(row,'account_total_credit_amount',0)); used=float(g(row,'account_used_amount',0)); rate=float(g(row,'account_usage_rate',0))
        tag="cr" if rate>0.8 else ("co" if rate>0.6 else "cg")
        st.write(f"主卡:{g(row,'account_primary_card_level')}"); st.markdown(f'授信:<b>{credit:,.0f}</b> | 已用:<b>{used:,.0f}</b> | 率:<span class="{tag}">{rate:.0%}</span>',unsafe_allow_html=True)
        st.write(f"持卡{int(g(row,'account_card_count',0))}张 | 开户{float(g(row,'account_tenure_months',0)):.0f}月")
        pref = g(row,'contact_preference','APP Push')
        st.write(f"渠道偏好: {pref} | App活跃: {int(g(row,'long_term_90d_active_days',0))}天")
    with c3:
        st.caption("生命周期"); stage=g(row,'lifecycle_stage',''); sc={"新户":"#64b5f6","成长期":"#66bb6a","成熟期":"#ffa726","沉睡期":"#ef5350"}.get(stage,"gray")
        st.markdown(f'<span style="color:{sc};font-weight:bold;font-size:1.1rem">{stage}</span>',unsafe_allow_html=True)
        st.write(f"VIP:{g(row,'lifecycle_vip_tier')}"); st.write(f"开户{float(g(row,'lifecycle_months_since_open',0)):.0f}月")
    with c4:
        st.caption("风险"); risk=g(row,'risk_risk_level',''); rc={"low":"cg","medium":"co","high":"cr"}.get(risk,"")
        st.markdown(f'等级:<span class="{rc}">{risk}</span>',unsafe_allow_html=True)
        st.write(f"逾期:{g(row,'risk_overdue_status','M0')} | 近6月{int(g(row,'risk_history_overdue_count_6m',0))}次")
        ch=int(g(row,'risk_churn_risk_score',0)); cht="cg" if ch<30 else ("co" if ch<60 else "cr")
        st.markdown(f'流失:<span class="{cht}">{ch}/100</span>',unsafe_allow_html=True)
    with c5:
        st.caption("价值"); annual=float(g(row,'value_annual_consumption',0))+dd.get("annual",0); monthly=float(g(row,'value_monthly_avg_consumption',0))+dd.get("monthly",0)
        st.metric("年消费",f"{annual:,.0f}",delta=f"+{dd.get('annual',0):,.0f}" if dd.get('annual',0)>0 else None)
        st.metric("月均",f"{monthly:,.0f}",delta=f"+{dd.get('monthly',0):,.0f}" if dd.get('monthly',0)>0 else None)
        vl=g(row,'value_value_level',''); vc={"high":"cg","medium":"#64b5f6","low":"#889"}.get(vl,"gray")
        st.markdown(f'等级:<span style="color:{vc};font-weight:bold">{vl}</span>',unsafe_allow_html=True)

def render_dynamic(row, oneid):
    st.subheader("动态记忆 — 行为信号")

    with st.expander("💡 搜索意图 / 浏览偏好 / 关键事件 / 预警 — 定义与区别", expanded=False):
        st.markdown("""
| 信号 | 定义 | 触发标准 | 来源 |
|------|------|---------|------|
| **搜索意图(7d)** | 客户近期关注/搜索的话题 | 任何搜索/对话话题 | 客户自主 + 项目三`top_concerns` + `summary` |
| **浏览偏好(30d)** | 客户浏览的页面/内容类型 | 任何浏览/意图表达 | 客户自主 + 项目三`intent`->页面映射 |
| **关键事件(90d)** | **实际发生的重大里程碑** | 仅系统检测的实际行为 | 画像生成事件(非对话!), 项目三conversion等 |
| **预警信号** | 需关注的风险信号 | 活跃骤降/沉睡/逾期/高风险 | 系统计算(非对话情绪!) |
| **情绪(实时)** | 客户当前情绪状态 | 项目三对话`sentiment` | Tab3 意图识别->情感分析 |

> **关键事件**: 对话**不**自动成为关键事件。"咨询分期"!=已办分期，"问升级"!=已升级。仅系统检测到的实际行为才算里程碑。
> **预警 vs 情绪**: 日常对话的"不满"是情绪波动(->Tab3)，不是预警信号。预警=逾期+高流失+投诉等风险组合。
> **日常对话**: 更新搜索意图和浏览偏好 -> Tab2；情绪更新 -> Tab3。不写入关键事件和预警。
        """)

    kw=str(g(row,"short_term_7d_top_search_keywords","")); words=[x.strip().split("×")[0] for x in kw.split(",") if x.strip()] if kw and kw!="nan" else []
    br=str(g(row,"mid_term_30d_browse_preferences","")); browses=[x.strip() for x in br.split(",") if x.strip()] if br and br!="nan" else []
    ms=str(g(row,"key_milestones","")); milestones=[x.strip() for x in ms.split("|") if x.strip()] if ms and ms!="nan" else []

    # -- Read Project 3 feedback for conversation context --
    try:
        conn_fb = get_db()
        fb_df = pd.read_sql("SELECT * FROM feedback_events WHERE oneid=? AND event_type='conversation' ORDER BY created_at DESC LIMIT 5", conn_fb, params=[oneid])
        conn_fb.close()
        recent_sentiments = []
        recent_topics = []
        for _, fb in fb_df.iterrows():
            try:
                detail = json.loads(fb["detail"]) if fb["detail"] else {}
            except:
                detail = {}
            s = detail.get("sentiment", "")
            if s:
                recent_sentiments.append(s)
            c = detail.get("top_concerns", [])
            if c:
                recent_topics.extend(c)
            summary = detail.get("summary", "")
            if summary and summary not in recent_topics:
                recent_topics.append(summary)
    except Exception as e:
        fb_df = pd.DataFrame()
        recent_sentiments = []
        recent_topics = []
    c1,c2,c3,c4,c5=st.columns(5)
    with c1:
        trend=g(row,"mid_term_30d_consumption_trend","stable"); tc={"up":"#66bb6a","stable":"#64b5f6","down":"#ef5350"}.get(trend,"gray")
        chg=float(g(row,"mid_term_30d_trend_change_pct",0))
        st.markdown(f'<div class="mbox"><p>消费趋势(30d)</p><h3 style="color:{tc}">{trend}</h3><p>环比{chg:+.0f}%</p></div>',unsafe_allow_html=True)
    with c2:
        si_html = f'<div class="mbox"><p>搜索意图(7d)</p><h3>{len(words)}词</h3><p style="font-size:0.7rem">{" ".join(words[:4]) if words else "-"}</p>'
        if recent_topics:
            si_html += f'<p style="font-size:0.6rem;color:#889">P3:{" ".join(recent_topics[:2])[:30]}</p>'
        si_html += '</div>'
        st.markdown(si_html, unsafe_allow_html=True)
    with c3: st.markdown(f'<div class="mbox"><p>浏览偏好(30d)</p><h3>{len(browses)}页</h3><p style="font-size:0.7rem">{" ".join(browses[:4]) if browses else "-"}</p></div>',unsafe_allow_html=True)
    with c4: st.markdown(f'<div class="mbox"><p>关键事件(90d)</p><h3>{len(milestones)}件</h3><p style="font-size:0.7rem">{" ".join(milestones[:3]) if milestones else "-"}</p></div>',unsafe_allow_html=True)
    with c5:
        sc=int(g(row,"long_term_90d_activity_score",0)); ac="#66bb6a" if sc>=60 else ("#ffa726" if sc>=30 else "#ef5350")
        al="高" if sc>=60 else ("中" if sc>=30 else "低"); dorm=g(row,"long_term_90d_dormancy_risk","")
        dl={"high":"高(需唤醒)","medium":"中(关注)","low":"低(安全)"}.get(dorm,dorm)
        st.markdown(f'<div class="mbox"><p>活跃度(90d)</p><h3 style="color:{ac}">{sc}/100 {al}</h3><p>沉睡:{dl}</p></div>',unsafe_allow_html=True)

    # 预警信号 — 仅显示真正的风险信号
    sig=str(g(row,"long_term_90d_significant_signals",""))
    if sig and sig!="nan" and sig!="":
        # 筛选真正的预警(过滤掉活动和日常对话)
        sig_items = [s.strip() for s in sig.split("|") if s.strip()]
        warnings = [s for s in sig_items if any(w in s for w in ["预警","逾期","风险","降级","销户","投诉"])]

        if warnings:
            st.warning(" 预警: " + " | ".join(warnings[-5:]))
    c1,c2=st.columns(2)
    with c1:
        st.subheader("90天消费趋势")
        avg=max(float(g(row,'long_term_90d_monthly_avg_90d',5000) or 5000)/30,30); days=list(range(90,0,-1))
        vals=[avg*(1+0.3*np.sin(i/12+hash(oneid+str(i))%100))*np.random.uniform(0.5,1.5) for i in range(90)]
        fig=px.area(x=days,y=vals,labels={"x":"天前","y":"消费"})
        fig.update_traces(line_color='#64b5f6',fillcolor='rgba(100,181,246,0.1)')
        fig.update_layout(height=250,margin=dict(l=20,r=20,t=10,b=10),paper_bgcolor='rgba(0,0,0,0)',plot_bgcolor='rgba(0,0,0,0)',font=dict(color='#aaa'))
        st.plotly_chart(fig,use_container_width=True)
    with c2:
        st.subheader("消费行为雷达")
        raw_annual=float(g(row,'value_annual_consumption',0)); raw_txn=int(g(row,'value_transaction_count_12m',0))
        raw_active=int(g(row,'long_term_90d_active_days',0)); raw_install=float(g(row,'value_installment_contribution_12m',0))
        raw_max=float(g(row,'value_max_single_transaction',0)); raw_monthly=float(g(row,'value_monthly_avg_consumption',0))
        radar_vals={
            "年消费":min(raw_annual/500000*100,100),"交易笔数":min(raw_txn/500*100,100),
            "活跃天数":min(raw_active/90*100,100),"分期贡献":min(raw_install/50000*100,100),
            "单笔最大":min(raw_max/100000*100,100),"月均消费":min(raw_monthly/50000*100,100),
        }
        fig2=go.Figure(data=go.Scatterpolar(r=list(radar_vals.values()),theta=list(radar_vals.keys()),fill='toself',marker=dict(color='#66bb6a'),hovertemplate='%{theta}: %{r:.0f}分<extra></extra>'))
        fig2.update_layout(height=250,margin=dict(l=40,r=40,t=10,b=10),polar=dict(radialaxis=dict(range=[0,100])),paper_bgcolor='rgba(0,0,0,0)',plot_bgcolor='rgba(0,0,0,0)',font=dict(color='#aaa'))
        st.plotly_chart(fig2,use_container_width=True)

# ═══════════════════════
# 六类意图计算 (DeepSeek → RuleScorer)
# ═══════════════════════
@st.cache_data(ttl=300, show_spinner=False)
def compute_intent(oneid, lifecycle, card_level, search_kw, browse_prefs, overdue_cnt, risk_level, usage_rate, income_level):
    result = {"intents": [], "primary_intent": "无", "ds_used": False, "reasoning": "", "signals": []}
    # DeepSeek: 六类各自打分
    try:
        from llm_client import is_available, chat
        if is_available():
            ctx = f"客户: 生命周期={lifecycle}, 卡={card_level}, 搜索={search_kw[:100]}, 浏览={browse_prefs[:100]}, 逾期={overdue_cnt}次, 风险={risk_level}, 收入={income_level}"
            prompt = f"""你是银行信用卡意图分析专家。对以下客户六类意图打分(0-100)并给出分析理由,只输出JSON:
{{"分期需求":0,"出行需求":0,"额度升级":0,"权益需求":0,"流失风险":0,"激活引导":0,"primary":"最高分类","reasoning":"综合分析:客户行为特征、生命周期阶段、近期信号如何影响各意图评分的具体原因(80字以内)","signals":["信号1","信号2","信号3"]}}
{ctx}"""
            resp = chat([{"role":"user","content":prompt}], temperature=0.1)
            resp = resp.strip()
            if resp.startswith("```"): resp = resp.split("\n",1)[1].rsplit("\n",1)[0]
            if resp.startswith("json"): resp = resp[4:]
            ds = json.loads(resp)
            if ds and isinstance(ds, dict):
                for t in ["分期需求","出行需求","额度升级","权益需求","流失风险","激活引导"]:
                    s = int(ds.get(t, 0))
                    result["intents"].append({"type":t,"score":s,"confidence":"high" if s>=70 else ("medium" if s>=40 else "low")})
                result["primary_intent"] = ds.get("primary","")
                result["reasoning"] = ds.get("reasoning","")
                result["signals"] = ds.get("signals",[])
                result["ds_used"] = True
                return result
    except: pass
    # RuleScorer fallback
    try:
        from intent_engine.rule_scorer import RuleScorer
        scorer = RuleScorer()
        profile = {"lifecycle_stage":lifecycle,"usage_rate":usage_rate,"income_level":income_level,"card_level":card_level}
        events = {"search_keywords":search_kw,"browse_pages":browse_prefs,"overdue_count":overdue_cnt,"min_payment_count":0,"complaint_count":1 if risk_level=="high" else 0}
        sr = scorer.score_all(profile, events)
        if sr.get("intents"): return sr
    except: pass
    return result

def render_intent(oneid, row, intent_data=None):
    st.subheader("  意图识别 & 情感分析")
    if intent_data is None: intent_data = {}
    search_kw = str(g(row,"short_term_7d_top_search_keywords",""))
    overdue_cnt = int(g(row,"risk_history_overdue_count_6m",0))
    churn_score = int(g(row,"risk_churn_risk_score",0))
    risk_level = g(row,"risk_risk_level","low")
    lifecycle = g(row,"lifecycle_stage","")

    # -- Read Project 3 feedback for sentiment/intent context --
    try:
        conn_fb = get_db()
        # P3回传事件类型: impression, view, conversation, ignore, unsubscribe
        fb_df = pd.read_sql("SELECT * FROM feedback_events WHERE oneid=? ORDER BY created_at DESC LIMIT 20", conn_fb, params=[oneid])
        conn_fb.close()
        p3_neg_signals = []   # 负面信号
        p3_pos_signals = []   # 正面信号
        p3_intents = []
        # 统计各事件类型(供情感分析和Tab3使用)
        p3_impressions = 0; p3_views = 0; p3_conversations = 0; p3_ignores = 0; p3_unsubs = 0
        for _, fb in fb_df.iterrows():
            etype = str(fb.get("event_type",""))
            # 计数
            if etype == "impression": p3_impressions += 1
            elif etype in ("view","browse"): p3_views += 1
            elif etype == "conversation": p3_conversations += 1
            elif etype == "ignore": p3_ignores += 1
            elif etype == "unsubscribe": p3_unsubs += 1
            # 从detail中提取情绪和意图
            detail = {}
            try:
                detail = json.loads(fb["detail"]) if fb.get("detail") else {}
            except:
                pass
            s = str(detail.get("sentiment","")).strip()
            if s:
                # P3回传的情绪值: 正面/负面/满意/中性/焦虑/不满/投诉
                if s in ("负面","焦虑","不满","投诉"):
                    p3_neg_signals.append(s)
                elif s in ("正面","满意","中性"):
                    p3_pos_signals.append(s)
            it = detail.get("intent","")
            if it: p3_intents.append(it)
    except:
        p3_neg_signals = []; p3_pos_signals = []; p3_intents = []
        p3_impressions = 0; p3_views = 0; p3_conversations = 0; p3_ignores = 0; p3_unsubs = 0

    ds_used = intent_data.get("ds_used", False)
    intents = intent_data.get("intents", [])

    if not intents:
        st.info("暂无意图数据 (配置 DEEPSEEK_API_KEY 启用实时六类评分)")
    else:
        src_tag = " (DeepSeek)" if ds_used else " (规则引擎)"
        st.markdown(f"### 六类意图评分{src_tag}")
        cols = st.columns(6)
        for i, intent in enumerate(intents):
            with cols[i]:
                s = intent["score"]
                bg = "#ef5350" if s >= 70 else ("#ffa726" if s >= 40 else "#64b5f6")
                st.markdown(
                    f'<div style="background:rgba(255,255,255,0.05);border-radius:10px;padding:10px;text-align:center;border-left:3px solid {bg}">'
                    f'<p style="font-size:0.65rem;color:#889;margin:0">{intent["type"]}</p>'
                    f'<h2 style="color:{bg};margin:4px 0">{s}</h2>'
                    f'<p style="font-size:0.6rem;color:#889;margin:0">{intent["confidence"]}</p></div>',
                    unsafe_allow_html=True)
        if intent_data.get("primary_intent"):
            st.markdown(f"**主意图: {intent_data['primary_intent']}**")
        if intent_data.get("reasoning"):
            st.markdown("---")
            st.markdown("#### 分析理由")
            st.info(intent_data["reasoning"])
        if intent_data.get("signals"):
            st.caption("关键信号: " + " | ".join(intent_data["signals"]))

    # ── 情感分析 (含DeepSeek非结构化理由) ──
    st.markdown("---"); st.markdown("### 情感分析")
    anxiety = 20; satisfaction = 60; reasons = []
    if overdue_cnt >= 3: anxiety += 35; reasons.append(f"逾期{overdue_cnt}次")
    elif overdue_cnt >= 2: anxiety += 25; reasons.append(f"逾期{overdue_cnt}次")
    elif overdue_cnt >= 1: anxiety += 15; reasons.append(f"逾期{overdue_cnt}次")
    if churn_score >= 70: anxiety += 20; reasons.append(f"高流失({churn_score})")
    elif churn_score >= 40: anxiety += 10
    if risk_level == "high": anxiety += 20; reasons.append("高风险")
    elif risk_level == "medium": anxiety += 8
    if any(w in search_kw for w in ["注销","销户","投诉"]): anxiety += 20; reasons.append("搜索销户/投诉")
    if lifecycle == "沉睡期": anxiety += 10
    anxiety = min(anxiety, 100)

    # -- Incorporate P3 real-time feedback (behavior + sentiment) --
    # P3回传事件直接影响情感评分:
    #   view/conversation → 正面(客户互动), ignore → 负面(反感), unsubscribe → 严重负面
    if p3_ignores > 0:
        anxiety += min(p3_ignores * 5, 20)
        reasons.append(f"P3忽略推送({p3_ignores}次)")
    if p3_unsubs > 0:
        anxiety += min(p3_unsubs * 15, 30)
        reasons.append(f"P3退订({p3_unsubs}次)")
    if p3_views + p3_conversations > 0:
        satisfaction += min((p3_views + p3_conversations) * 3, 15)
        reasons.append(f"P3浏览/对话({p3_views+p3_conversations}次)")
    # P3 detail中的情绪标签 (来自对话/反馈, P3回传: 正面/负面/满意/焦虑/不满/投诉)
    neg_count = len(p3_neg_signals)
    pos_count = len(p3_pos_signals)
    if neg_count > 0:
        anxiety += min(neg_count * 8, 25)
        reasons.append(f"P3负面情绪({','.join(p3_neg_signals[:3])}等{neg_count}次)")
    if pos_count > 0:
        satisfaction += min(pos_count * 5, 15)
        reasons.append(f"P3正面情绪({','.join(p3_pos_signals[:3])}等{pos_count}次)")
    anxiety = min(anxiety, 100)

    val_lvl = g(row, "value_value_level", "medium")
    if val_lvl == "high": satisfaction += 20; reasons.append("高价值")
    act = int(g(row, "long_term_90d_activity_score", 0))
    if act >= 60: satisfaction += 15
    elif act >= 30: satisfaction += 5
    satisfaction = min(satisfaction, 100)
    overall = "焦虑" if anxiety >= 70 else ("轻微焦虑" if anxiety >= 45 else ("满意" if satisfaction >= 70 else "中性"))
    c1, c2 = st.columns(2)
    with c1:
        st.markdown(f'<div style="background:rgba(255,255,255,0.05);border-radius:10px;padding:12px;text-align:center"><h2>{overall}</h2><p>焦虑度:{anxiety}/100 | 满意度:{satisfaction}/100</p></div>', unsafe_allow_html=True)
    with c2:
        st.caption("证据:" + ";".join(reasons) if reasons else "日常正常使用")

    # -- Show P3 real-time feedback summary --
    if p3_impressions + p3_views + p3_conversations + p3_ignores + p3_unsubs > 0:
        st.caption(f"P3实时: 曝光{p3_impressions}次 · 浏览/对话{p3_views+p3_conversations}次 · 忽略{p3_ignores}次 · 退订{p3_unsubs}次")
    if p3_neg_signals:
        st.caption(f"P3负面信号: {' | '.join(p3_neg_signals[:5])}")
    if p3_pos_signals:
        st.caption(f"P3正面信号: {' | '.join(p3_pos_signals[:5])}")
    if p3_intents:
        unique_intents = list(dict.fromkeys(p3_intents))
        st.caption("P3对话意图: " + " | ".join(unique_intents[:5]))
    

    # DeepSeek 情感分析理由
    try:
        from llm_client import is_available, chat
        if is_available():
            sent_ctx = f"客户画像: 焦虑度={anxiety}/100, 满意度={satisfaction}/100, 生命周期={lifecycle}, 逾期={overdue_cnt}次, 流失={churn_score}, 风险={risk_level}, 搜索词={search_kw[:80]}"
            sp = f"根据以下客户数据，用一段话(60字内)分析该客户的情感状态及营销建议，只输出分析文字:\n{sent_ctx}"
            sr = chat([{"role":"user","content":sp}], temperature=0.3).strip()
            if sr and len(sr) > 5:
                st.markdown("#### 分析理由")
                st.info(sr)
    except: pass

def render_roi(oneid, row):
    st.subheader("活动效果 (触达→点击→转化)")
    try:
        cust_id_val = row.get("cust_id","")
        conn = get_db()

        # 从 contact_history 取营销触达 (过滤掉服务通知类无campaign_id的记录)
        ch_sql = "SELECT * FROM contact_history WHERE cust_id=? AND campaign_id IS NOT NULL"
        ch = pd.read_sql(ch_sql, conn, params=[cust_id_val])

        # 从 campaign_attribution 取转化
        attr_sql = "SELECT * FROM campaign_attribution WHERE cust_id=?"
        attr = pd.read_sql(attr_sql, conn, params=[cust_id_val])

        # 从 feedback_events 取项目三回传
        fb_sql = "SELECT * FROM feedback_events WHERE oneid=? ORDER BY timestamp DESC LIMIT 50"
        fb = pd.read_sql(fb_sql, conn, params=[oneid])
        conn.close()

        total_touch = len(ch)
        ch_clicks = len(ch[ch["status"]=="clicked"]) if len(ch)>0 else 0
        total_conv = len(attr[attr["converted"]==True])

        # -- Part 1: Historical marketing touch -> click -> conversion --
        st.markdown("###  历史触达转化 (营销活动)")
        c1,c2,c3 = st.columns(3)
        c1.metric("  触达", f"{total_touch}次", help="营销活动触达(已过滤服务通知)")
        c2.metric("  点击", f"{ch_clicks}次", help="contact_history中status=clicked")
        c3.metric("  转化", f"{total_conv}次", help="campaign_attribution中converted=True")
        if total_touch>0:
            st.caption(f"点击率: {ch_clicks/total_touch*100:.1f}% | 转化率(触达): {total_conv/total_touch*100:.1f}% | 点击→转化: {total_conv/max(ch_clicks,1)*100:.0f}%")

        if total_touch>0 or total_conv>0:
            st.markdown("#### 按活动明细")
            # Build per-campaign stats with OUTER JOIN (both tables may have different campaign_ids)
            camp_touch = ch.groupby("campaign_id").size().reset_index(name="触达")
            camp_click = ch[ch["status"]=="clicked"].groupby("campaign_id").size().reset_index(name="点击")
            camp_conv = attr[attr["converted"]==True].groupby("campaign_id").size().reset_index(name="转化")
            camp_stats = camp_touch.merge(camp_click, on="campaign_id", how="outer").merge(camp_conv, on="campaign_id", how="outer")
            camp_stats = camp_stats.fillna(0).astype({"触达": int, "点击": int, "转化": int})
            camp_stats = camp_stats.sort_values("触达", ascending=False)
            # Totals row
            total_row = {"campaign_id": "合计", "触达": int(camp_stats["触达"].sum()), "点击": int(camp_stats["点击"].sum()), "转化": int(camp_stats["转化"].sum())}
            camp_stats = pd.concat([camp_stats, pd.DataFrame([total_row])], ignore_index=True)
            st.dataframe(camp_stats, use_container_width=True, hide_index=True)
            # 解释转化>触达的原因
            if (camp_stats["转化"] > camp_stats["触达"]).any() or (camp_stats["触达"] == 0).any():
                with st.expander("  为什么有的活动转化>触达或0触达有转化？"):
                    st.caption(
                        "触达和点击来自 `contact_history`(系统主动推送记录)，"
                        "转化来自 `campaign_attribution`(全渠道归因)。"
                        "客户可能通过线下网点、非追踪渠道或自然到访完成转化，"
                        "这些转化不经过系统推送但会被归因记录。这是正常业务现象。"
                    )
        else:
            st.caption("暂无营销活动触达数据")

        # -- Part 2: Project 3 real-time strategy effect --
        st.markdown("---")
        st.markdown("###  项目三实时策略效果 (feedback_events)")

        # P3回传事件类型: impression(曝光), view(浏览), conversation(对话), ignore(忽略), unsubscribe(退订)
        p3_total = len(fb)
        p3_impressions = len(fb[fb["event_type"]=="impression"]) if len(fb)>0 else 0
        p3_views = len(fb[fb["event_type"].isin(["view","browse"])]) if len(fb)>0 else 0
        p3_conversations = len(fb[fb["event_type"]=="conversation"]) if len(fb)>0 else 0
        p3_ignores = len(fb[fb["event_type"]=="ignore"]) if len(fb)>0 else 0
        p3_unsubs = len(fb[fb["event_type"]=="unsubscribe"]) if len(fb)>0 else 0

        if p3_total>0:
            c1,c2,c3,c4 = st.columns(4)
            c1.metric("  曝光(推送触达)", f"{p3_impressions}次", help="P3推送曝光")
            c2.metric("  浏览/对话", f"{p3_views+p3_conversations}次", help="客户浏览了推送或进行了对话")
            c3.metric("  忽略", f"{p3_ignores}次", help="客户忽略/跳过推送")
            c4.metric("  退订", f"{p3_unsubs}次", help="客户主动退订")
            engaged = p3_views + p3_conversations + p3_ignores + p3_unsubs
            if engaged > 0:
                st.caption(f"互动率(浏览+对话): {(p3_views+p3_conversations)/max(engaged,1)*100:.1f}% | 忽略率: {p3_ignores/max(engaged,1)*100:.1f}% | 退订率: {p3_unsubs/max(engaged,1)*100:.1f}%")

            st.markdown("#### 项目三实时回传明细")
            for _, r in fb.head(10).iterrows():
                etype=r.get("event_type","?")
                emoji_map={"impression":"📨","view":"👀","browse":"👀","conversation":"💬","ignore":"⏭️","unsubscribe":"🚫"}
                emoji=emoji_map.get(etype,"📌")
                ts=str(r.get('timestamp',''))[:19]
                cid=str(r.get('campaign_id',''))[:25]
                channel=str(r.get('channel',''))[:15]
                detail_raw=r.get('detail','')
                if detail_raw:
                    try:
                        detail=json.loads(detail_raw) if isinstance(detail_raw,str) else detail_raw
                        detail_str=str(detail.get('summary',detail.get('reason',str(detail)[:40])))[:50]
                    except:
                        detail_str=str(detail_raw)[:50]
                else:
                    detail_str=f"渠道:{channel}" if channel else ""
                st.caption(f"{emoji} [{etype}] {ts} | {cid} | {detail_str}")
        else:
            st.caption("暂无项目三实时回传数据")
    except Exception as e:
        st.info(f"暂无活动数据")

# ═══════════════════════
def main():
    st.title("  客户360视图")
    st.caption(f"{NOW} | SQLite({os.path.getsize(DB_PATH)/1024/1024:.0f}MB) | DeepSeek六类意图")

    data = load()
    with st.sidebar:
        st.markdown("###  DB状态")
        s = data.get("stats",{})
        st.metric("客户",f"{s.get('customer_profile',8000):,}"); st.metric("回传",s.get('feedback_events',0)); st.caption(s.get('db_size',''))
        st.markdown("---")
        st.markdown("###  新增客户 (全新开户)")
        st.caption("从未办卡·无历史·生命周期=新户")
        name = st.text_input("姓名*",key="s1",placeholder="必填")
        c1,c2=st.columns(2)
        with c1: gender=st.selectbox("性别",["M","F"],key="s1g",format_func=lambda x:"男" if x=="M" else "女")
        with c2: age=st.number_input("年龄",18,65,25,key="s3")
        city=st.selectbox("城市",["深圳","上海","北京","广州","杭州","成都","武汉","南京"],key="s2")
        c1,c2=st.columns(2)
        with c1: edu=st.selectbox("学历",["本科","硕士","博士","大专","高中"],key="s1e")
        with c2: occ=st.selectbox("职业",["IT/互联网","金融/银行","企业/贸易","公务员/事业","学生","其他"],key="s1o")
        c1,c2=st.columns(2)
        with c1: inc=st.selectbox("收入等级",["H","M","L"],key="s4",format_func=lambda x:{"H":"高","M":"中","L":"低"}.get(x,x))
        with c2: card=st.selectbox("办卡等级",["金卡","白金卡","普卡","钻石卡","校园卡"],key="s5")
        credit=st.number_input("授信额度",5000,500000,50000,10000,key="s5c")
        if st.button("  开户入网",use_container_width=True,type="primary"):
            if not name: st.error("请输入姓名")
            else:
                try:
                    conn=get_db()
                    max_id=conn.execute("SELECT MAX(CAST(SUBSTR(cust_id,2) AS INTEGER)) FROM customer_profile WHERE cust_id LIKE 'C%'").fetchone()[0] or 8000
                    conn.close(); new_id=max_id+1; oneid=f"UID{new_id:06d}"; cust_id=f"C{new_id:06d}"
                    from db_store import customer_insert
                    r=customer_insert({"oneid":oneid,"cust_id":cust_id,"demographics_name":name,"demographics_gender":gender,"demographics_age":age,"demographics_city":city,"demographics_education":edu,"demographics_occupation":occ,"demographics_income_level":inc,"account_primary_card_level":card,"account_total_credit_amount":credit})
                    if r.get("status")=="ok": st.cache_data.clear(); st.success(f"新户: {name} | {oneid}")
                    else: st.error(f"失败: {r.get('message','?')}")
                except Exception as e: st.error(f"异常: {e}")

        st.markdown("---")
        st.markdown("###  模拟回传")
        evt_type=st.selectbox("事件类型",["click","reject","conversation","conversion"],key="s7t",format_func=lambda x:{"click":"点击感兴趣","reject":"拒绝","conversation":"对话","conversion":"消费转化"}.get(x,x))
        oid=st.text_input("OneID","UID000001",key="s7")
        if evt_type=="conversation":
            summary=st.text_input("摘要","咨询分期费率",key="s7s"); intent=st.selectbox("意图",["分期需求","权益咨询","额度升级","账户问题","销户咨询"],key="s7i")
            sentiment=st.selectbox("情绪",["中性","满意","焦虑","不满"],key="s7se"); concerns=st.text_input("关注话题","分期费率,手续费",key="s7c")
        elif evt_type=="conversion": amt=st.number_input("金额",0,100000,5000,key="s8")
        else: campaign=st.text_input("活动ID","CAMP_2026_DOUBLE11",key="s7ca")
        if st.button("  发送回传",use_container_width=True):
            from db_store import feedback_insert
            event={"oneid":oid,"event_type":evt_type,"channel":"APP Push","campaign_id":""}
            if evt_type=="conversation": event.update({"summary":summary,"intent":intent,"sentiment":sentiment,"top_concerns":[c.strip() for c in concerns.split(",") if c.strip()]})
            elif evt_type=="conversion": event["amount"]=amt; event["detail"]={"amount":amt}
            elif evt_type in ("click","reject"): event["campaign_id"]=campaign
            r=feedback_insert(event)
            st.cache_data.clear()
            st.success(f"回传: {r.get('event_type')} | {oid}")
            if r.get("profile_updated"):
                st.caption(f"  已更新: {', '.join(r['profile_updated'])}")
            if r.get("signals"):
                st.caption(f"  预警: {', '.join(r['signals'])}")
            st.info("  已写DB → 点「清空缓存」→ 所有Tab立即刷新")
        st.caption("---")
        st.caption("  更新链路: 回传→写DB→清缓存→load()重读→compute_intent重算→Tab刷新")

    # ═══ 主面板 ═══
    cq,ct,cb,cr=st.columns([3,1,1,1])
    with cq: query=st.text_input("搜索",placeholder="OneID / cust_id / 姓名 / 手机号")
    with ct: stype=st.selectbox("方式",["OneID","cust_id","姓名","手机号"])
    with cb: st.markdown("<br>",unsafe_allow_html=True); btn=st.button("搜索",use_container_width=True)
    with cr: st.markdown("<br>",unsafe_allow_html=True)
    if st.button("清空缓存",use_container_width=True): st.cache_data.clear(); st.rerun()
    if not btn and not query: query,stype="UID000001","OneID"
    if query:
        result=search(query,stype,data)
        if result is None: st.error(f"未找到: {query}"); st.stop()
        if isinstance(result,list):
            oids=result; profiles=data["p"][data["p"]["oneid"].isin(oids)]
            choices=[f"{r['demographics_name']} | {r['demographics_city']} | {r['account_primary_card_level']} | {r['oneid']}" for _,r in profiles.iterrows()]
            choice=st.selectbox(f"找到{len(oids)}位同名客户:",range(len(choices)),format_func=lambda i:choices[i])
            oneid=oids[choice]
        else: oneid=result
        row=data["p"].iloc[data["idx"][oneid]].to_dict()
        name=g(row,"demographics_name"); cid=row.get("cust_id","")
        st.markdown(f"## {name} | `{oneid}` | {cid}")
        st.caption("OneID=唯一标识 | 姓名/手机号/OneID/cust_id搜索")

        intent_data=compute_intent(oneid,str(g(row,"lifecycle_stage","")),str(g(row,"account_primary_card_level","")),str(g(row,"short_term_7d_top_search_keywords","")),str(g(row,"mid_term_30d_browse_preferences","")),int(g(row,"risk_history_overdue_count_6m",0)),str(g(row,"risk_risk_level","low")),float(g(row,"account_usage_rate",0)),str(g(row,"demographics_income_level","")))
        tabs=st.tabs(["静态画像","动态记忆","意图识别","活动效果"])
        with tabs[0]: render_static(row,oneid)
        with tabs[1]: render_dynamic(row,oneid)
        with tabs[2]: render_intent(oneid,row,intent_data)
        with tabs[3]: render_roi(oneid,row)
        st.markdown("---"); st.caption("DB实时 | 15秒刷新 | DeepSeek六类意图")

if __name__=="__main__": main()
