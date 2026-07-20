"""客户360视图 v14 — 渠道策略优化版 (contact_preference + app_active_days)"""
import os, sys, sqlite3, pandas as pd, numpy as np, json, random, re, time
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import streamlit as st
import plotly.graph_objects as go
import plotly.express as px
from datetime import datetime

st.set_page_config(page_title="客户360", page_icon="", layout="wide")
st.markdown("""<style>
.mbox{background:rgba(255,255,255,0.05);border-radius:10px;padding:10px;border:1px solid rgba(255,255,255,0.08);margin:3px 0;text-align:center}
.formula{font-family:monospace;font-size:0.6rem;color:#90caf9;background:rgba(144,202,249,0.08);padding:2px 6px;border-radius:4px}
.cg{color:#66bb6a;font-weight:bold}.co{color:#ffa726;font-weight:bold}.cr{color:#ef5350;font-weight:bold}
.help{font-size:0.65rem;color:#789}
</style>""", unsafe_allow_html=True)

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DB_PATH = os.path.join(BASE, "mock_data", "knowledge_agent.db")
NOW = datetime.now().strftime("%Y-%m-%d %H:%M")

def get_db():
    conn = sqlite3.connect(DB_PATH); conn.row_factory = sqlite3.Row; return conn

@st.cache_data(ttl=15)
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
    prof = p.copy()
    prof["name_str"] = prof["demographics_name"].astype(str)
    return {"p": p, "idx": dict(zip(p["oneid"], range(len(p)))),
        "c2u": dict(zip(mp["id_value"], mp["oneid"])),
        "p2u": dict(zip(mp_phone["id_value"], mp_phone["oneid"])),
        "n2u": {str(r["demographics_name"]):r["oneid"] for _,r in p.iterrows() if str(r["demographics_name"])!="nan"},
        "stats": stats}

def search(query, stype, data):
    if stype == "OneID" and query in data["idx"]: return query
    if stype == "cust_id": return data["c2u"].get(query)
    if stype == "姓名":
        n2u = data["n2u"]
        for name, oid in n2u.items():
            if query in name: return oid
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

# ================================================================
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
        pref = g(row, 'contact_preference', 'APP Push')
        st.write(f"渠道偏好: {pref} | App活跃: {int(g(row,'long_term_90d_active_days',0))}天")
    with c3:
        st.caption("生命周期"); stage=g(row,'lifecycle_stage',''); sc={"新户":"#64b5f6","成长期":"#66bb6a","成熟期":"#ffa726","沉睡期":"#ef5350"}.get(stage,"gray")
        st.markdown(f'<span style="color:{sc};font-weight:bold;font-size:1.1rem">{stage}</span>',unsafe_allow_html=True)
        st.write(f"VIP:{g(row,'lifecycle_vip_tier')} (CRM等级,≠卡等级)")
        st.write(f"开户{float(g(row,'lifecycle_months_since_open',0)):.0f}月")
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
    st.subheader("动态记忆 — 五类信号 + 消费雷达")
    kw=str(g(row,"short_term_7d_top_search_keywords","")); words=[x.strip().split("×")[0] for x in kw.split(",") if x.strip()] if kw and kw!="nan" else []
    br=str(g(row,"mid_term_30d_browse_preferences","")); browses=[x.strip() for x in br.split(",") if x.strip()] if br and br!="nan" else []
    ms=str(g(row,"key_milestones","")); milestones=[x.strip() for x in ms.split("|") if x.strip()] if ms and ms!="nan" else []
    c1,c2,c3,c4,c5=st.columns(5)
    with c1:
        trend=g(row,"mid_term_30d_consumption_trend","stable"); tc={"up":"#66bb6a","stable":"#64b5f6","down":"#ef5350"}.get(trend,"gray")
        chg=float(g(row,"mid_term_30d_trend_change_pct",0))
        st.markdown(f'<div class="mbox"><p>消费趋势(30d)</p><h3 style="color:{tc}">{trend}</h3><p>环比{chg:+.0f}%</p></div>',unsafe_allow_html=True)
    with c2: st.markdown(f'<div class="mbox"><p>搜索意图(7d)</p><h3>{len(words)}词</h3><p style="font-size:0.7rem">{" ".join(words[:4]) if words else "-"}</p></div>',unsafe_allow_html=True)
    with c3: st.markdown(f'<div class="mbox"><p>浏览偏好(30d)</p><h3>{len(browses)}页</h3><p style="font-size:0.7rem">{" ".join(browses[:4]) if browses else "-"}</p></div>',unsafe_allow_html=True)
    with c4: st.markdown(f'<div class="mbox"><p>关键事件(90d)</p><h3>{len(milestones)}件</h3><p style="font-size:0.7rem">{" ".join(milestones[:3]) if milestones else "-"}</p></div>',unsafe_allow_html=True)
    with c5:
        sc=int(g(row,"long_term_90d_activity_score",0)); ac="#66bb6a" if sc>=60 else ("#ffa726" if sc>=30 else "#ef5350")
        al="高" if sc>=60 else ("中" if sc>=30 else "低"); dorm=g(row,"long_term_90d_dormancy_risk","")
        dl={"high":"高(需唤醒)","medium":"中(关注)","low":"低(安全)"}.get(dorm,dorm)
        st.markdown(f'<div class="mbox"><p>活跃度(90d)</p><h3 style="color:{ac}">{sc}/100 {al}</h3><p>沉睡:{dl}</p></div>',unsafe_allow_html=True)
    sig=str(g(row,"long_term_90d_significant_signals",""))
    if sig and sig!="nan" and sig!="": st.warning(f"预警:{sig}")
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
        # 从真实数据构建六维消费画像 (归一化到0-100)
        raw_annual = float(g(row, 'value_annual_consumption', 0))
        raw_txn = int(g(row, 'value_transaction_count_12m', 0))
        raw_active = int(g(row, 'long_term_90d_active_days', 0))
        raw_install = float(g(row, 'value_installment_contribution_12m', 0))
        raw_max = float(g(row, 'value_max_single_transaction', 0))
        raw_monthly = float(g(row, 'value_monthly_avg_consumption', 0))

        # 归一化：max values for scaling
        radar_vals = {
            "年消费": min(raw_annual / 500000 * 100, 100),
            "交易笔数": min(raw_txn / 500 * 100, 100),
            "活跃天数": min(raw_active / 90 * 100, 100),
            "分期贡献": min(raw_install / 50000 * 100, 100),
            "单笔最大": min(raw_max / 100000 * 100, 100),
            "月均消费": min(raw_monthly / 50000 * 100, 100),
        }
        fig2 = go.Figure(data=go.Scatterpolar(
            r=list(radar_vals.values()), theta=list(radar_vals.keys()),
            fill='toself', marker=dict(color='#66bb6a'),
            hovertemplate='%{theta}: %{r:.0f}分<extra></extra>'
        ))
        fig2.update_layout(height=250, margin=dict(l=40, r=40, t=10, b=10),
                          polar=dict(radialaxis=dict(range=[0, 100])),
                          paper_bgcolor='rgba(0,0,0,0)', plot_bgcolor='rgba(0,0,0,0)',
                          font=dict(color='#aaa'))
        st.plotly_chart(fig2, use_container_width=True)


# ═══════════════════════════════════════
# 统一意图计算 (DeepSeek → RuleScorer → CSV)
# ═══════════════════════════════════════
@st.cache_data(ttl=300, show_spinner=False)
def compute_intent(oneid: str, lifecycle: str, card_level: str,
                   search_kw: str, browse_prefs: str,
                   overdue_cnt: int, risk_level: str,
                   usage_rate: float, income_level: str) -> dict:
    """统一意图数据源 — Tab2雷达图 + Tab3意图评分 共用此结果。"""
    result = {"intents": [], "primary_intent": "无", "radar": {}, "ds_used": False}

    # 方案1: DeepSeek
    try:
        from llm_client import classify_intent, is_available
        if is_available():
            conv_text = (f"客户: 生命周期={lifecycle}, 卡={card_level}, "
                        f"搜索={search_kw[:100]}, 浏览={browse_prefs[:100]}")
            ds = classify_intent(conv_text)
            if ds and isinstance(ds, dict):
                intent_map = {
                    "分期借贷需求": "分期需求", "跨境出行需求": "出行需求",
                    "额度升级需求": "额度升级", "权益优惠需求": "权益需求",
                    "沉睡流失风险": "流失风险", "新户激活引导": "激活引导",
                }
                raw = ds.get("primary_intent", "")
                name = intent_map.get(raw, raw[:6] if raw else "其他")
                score = ds.get("intent_score", 50)
                result["intents"].append({
                    "type": name, "score": score,
                    "confidence": "high" if score >= 70 else ("medium" if score >= 40 else "low"),
                    "sub_signals": [{"signal": s, "weight": 10}
                                    for s in ds.get("key_phrases", [])[:3]],
                })
                result["primary_intent"] = name
                result["radar"] = {
                    "分期": min(score if "分期" in raw else 30, 100),
                    "出行": min(score if "出行" in raw else 20, 100),
                    "升级": min(score if "升级" in raw else 20, 100),
                    "权益": min(score if "权益" in raw else 25, 100),
                    "流失": min(ds.get("anxiety_score", 20), 100),
                    "激活": min(100 - ds.get("anxiety_score", 20), 100),
                }
                result["ds_used"] = True
                return result
    except Exception:
        pass

    # 方案2: RuleScorer
    try:
        from intent_engine.rule_scorer import RuleScorer
        scorer = RuleScorer()
        profile = {"lifecycle_stage": lifecycle, "usage_rate": usage_rate,
                   "income_level": income_level, "card_level": card_level}
        events = {"search_keywords": search_kw, "browse_pages": browse_prefs,
                  "overdue_count": overdue_cnt,
                  "min_payment_count": 0, "complaint_count": 1 if risk_level == "high" else 0}
        result = scorer.score_all(profile, events)
        if result.get("intents"):
            radar = {}
            for it in result["intents"]:
                radar[it["type"][:4]] = it["score"]
            result["radar"] = radar
        return result
    except Exception:
        pass

    # 方案3: CSV
    result["radar"] = {"分期": 0, "出行": 0, "升级": 0, "权益": 0, "流失": 0, "激活": 0}
    return result


def render_intent(oneid, row, intent_data=None):
    """意图识别 & 情感分析 — 使用预计算的 intent_data。"""
    st.subheader("  意图识别 & 情感分析")

    if intent_data is None:
        intent_data = {}

    search_kw = str(g(row, "short_term_7d_top_search_keywords", ""))
    overdue_cnt = int(g(row, "risk_history_overdue_count_6m", 0))
    churn_score = int(g(row, "risk_churn_risk_score", 0))
    risk_level = g(row, "risk_risk_level", "low")
    lifecycle = g(row, "lifecycle_stage", "")
    result = intent_data
    ds_used = result.get("ds_used", False)

    # ── 六类意图评分 ──
    if not result.get("intents"):
        st.info("暂无意图数据 (设置 DEEPSEEK_API_KEY 启用 LLM 实时分析)")
    else:
        src_tag = "  DeepSeek 实时分析" if ds_used else "  规则引擎"
        st.markdown(f"### 六类意图评分{src_tag}")
        cols = st.columns(min(6, len(result["intents"])))
        for i, intent in enumerate(result["intents"]):
            with cols[i % 6]:
                s = intent["score"]
                bg = "#ef5350" if s >= 70 else ("#ffa726" if s >= 40 else "#64b5f6")
                st.markdown(
                    f'<div style="background:rgba(255,255,255,0.05);border-radius:10px;padding:10px;text-align:center;border-left:3px solid {bg}">'
                    f'<p style="font-size:0.6rem;color:#889;margin:0">{intent["type"][:6]}</p>'
                    f'<h2 style="color:{bg};margin:4px 0">{s}</h2>'
                    f'<p style="font-size:0.6rem;color:#889;margin:0">{intent["confidence"]}</p></div>',
                    unsafe_allow_html=True,
                )
        primary = [i for i in result["intents"] if i["type"] == result.get("primary_intent")]
        if primary and primary[0].get("sub_signals"):
            p = primary[0]
            st.markdown(f"**主意图: {result.get('primary_intent','')}** ({p['score']}分)")
            st.caption(" + ".join([f"{s['signal'][:12]}({s['weight']}分)" for s in p["sub_signals"]]) if p["sub_signals"] else "")

    # ── 情感分析 ──
    st.markdown("---"); st.markdown("### 情感分析")
    anxiety = 20; satisfaction = 60; reasons = []
    if overdue_cnt >= 3: anxiety += 35; reasons.append(f"逾期{overdue_cnt}次")
    elif overdue_cnt >= 2: anxiety += 25; reasons.append(f"逾期{overdue_cnt}次")
    elif overdue_cnt >= 1: anxiety += 15; reasons.append(f"逾期{overdue_cnt}次")
    if churn_score >= 70: anxiety += 20; reasons.append(f"高流失({churn_score})")
    elif churn_score >= 40: anxiety += 10
    if risk_level == "high": anxiety += 20; reasons.append("高风险")
    elif risk_level == "medium": anxiety += 8
    if any(w in search_kw for w in ["注销", "销户", "投诉"]): anxiety += 20; reasons.append("搜索销户/投诉")
    if lifecycle == "沉睡期": anxiety += 10
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
        st.caption("T+1批量 | DeepSeek实时意图 | 事件驱动<100ms")

def render_roi(oneid, row):
    st.subheader("活动效果 & 归因 (触达→点击→转化)")

    # 概念解释
    with st.expander("  触达/点击/拒绝/转化 — 什么意思？", expanded=False):
        st.markdown("""
```
活动推送 ──→ 客户收到(触达) ──→ 点击"感兴趣"(click) ──→ 实际消费(转化)
  (touch)                         │
                                  └──→ 点击"不感兴趣"(reject)
```
| 阶段 | 含义 | 数据来源 |
|------|------|---------|
| **触达 (touch)** | 活动消息/推送/邮件送达客户 | campaign_attribution表 |
| **点击感兴趣 (click)** | 客户点了活动"感兴趣"按钮 | 项目三回传 POST /feedback/import |
| **拒绝 (reject)** | 客户点了"不感兴趣" | 项目三回传 POST /feedback/import |
| **转化 (conversion)** | 客户实际消费，产生金额 | campaign_attribution.converted=1 |
        """)

    try:
        cust_id_val = row.get("cust_id","")
        conn = get_db()

        # ── 1. campaign_attribution 归因数据 ──
        attr_sql = "SELECT * FROM campaign_attribution WHERE cust_id=?"
        attr = pd.read_sql(attr_sql, conn, params=[cust_id_val])

        # ── 2. feedback_events 项目三回传 ──
        fb_sql = "SELECT * FROM feedback_events WHERE oneid=? ORDER BY timestamp DESC LIMIT 50"
        fb = pd.read_sql(fb_sql, conn, params=[oneid])
        conn.close()

        # 统计
        total_touch = len(attr)
        conv = attr[attr["converted"] == True]
        total_conv = len(conv)
        total_rev = conv["conversion_amount"].sum() if total_conv > 0 else 0
        total_cost = attr["touch_cost"].sum() if total_touch > 0 else 1

        # 项目三回传导航计
        clicks = len(fb[fb["event_type"] == "click"]) if len(fb) > 0 else 0
        rejects = len(fb[fb["event_type"] == "reject"]) if len(fb) > 0 else 0
        conversations = len(fb[fb["event_type"] == "conversation"]) if len(fb) > 0 else 0

        # ── KPI 卡片 ──
        c1, c2, c3, c4, c5, c6 = st.columns(6)
        c1.metric(" 触达", f"{total_touch}次")
        c2.metric(" 点击感兴趣", f"{clicks}次")
        c3.metric(" 拒绝", f"{rejects}次")
        c4.metric(" 转化", f"{total_conv}次")
        c5.metric(" 归因收入", f"{total_rev:,.0f}")
        c6.metric(" ROI", f"{(total_rev-total_cost)/max(total_cost,1):.1f}x" if total_cost > 0 else "N/A")

        if total_touch > 0:
            click_rate = clicks / total_touch * 100
            conv_rate = total_conv / total_touch * 100
            st.caption(f"点击率: {click_rate:.1f}% | 转化率: {conv_rate:.1f}% | 触达成本: ¥{total_cost:,.0f}")

        # ── 按活动分组 ──
        if total_touch > 0:
            st.markdown("---")
            st.markdown("#### 按活动明细")
            camp_stats = attr.groupby("campaign_id").agg(
                触达次数=("touch_id","count"),
                转化次数=("converted","sum"),
                转化金额=("conversion_amount","sum"),
                总成本=("touch_cost","sum"),
            ).reset_index()
            # 加入点击/拒绝数
            camp_clicks = {}
            camp_rejects = {}
            for _, r2 in fb.iterrows():
                cid = str(r2.get("campaign_id",""))
                if r2.get("event_type") == "click":
                    camp_clicks[cid] = camp_clicks.get(cid,0) + 1
                elif r2.get("event_type") == "reject":
                    camp_rejects[cid] = camp_rejects.get(cid,0) + 1
            camp_stats["点击"] = camp_stats["campaign_id"].map(lambda x: camp_clicks.get(str(x),0))
            camp_stats["拒绝"] = camp_stats["campaign_id"].map(lambda x: camp_rejects.get(str(x),0))
            camp_stats["转化率"] = (camp_stats["转化次数"] / camp_stats["触达次数"] * 100).round(1)
            st.dataframe(camp_stats, use_container_width=True, hide_index=True)

        # ── 项目三最新回传记录 ──
        if len(fb) > 0:
            st.markdown("---")
            st.markdown("#### 项目三最新回传 (最近10条)")
            for _, r in fb.head(10).iterrows():
                etype = r.get("event_type","?")
                emoji_map = {"click":"", "reject":"", "conversation":"", "conversion":""}
                emoji = emoji_map.get(etype, "")
                campaign = str(r.get("campaign_id",""))[:25] or "-"
                detail = str(r.get("detail",""))[:60]
                ts = str(r.get("timestamp",""))[:19]
                st.caption(f"{emoji} [{etype}] {ts} | 活动:{campaign} | {detail}")

    except Exception as e:
        st.info(f"暂无活动数据 ({e})")

def render_input(oneid, row):
    st.subheader("手动输入 & 实时更新")
    st.caption("此Tab为Session临时更新(页面内存, 刷新消失)。永久持久化请使用左侧边栏'项目三回传'(写DB)。")
    if "delta" not in st.session_state: st.session_state.delta = {}
    if "log" not in st.session_state: st.session_state.log = []
    c1,_=st.columns([1,5])
    with c1:
        if st.button("清空增量&刷新",use_container_width=True):
            if oneid in st.session_state.delta: st.session_state.delta[oneid]={}
            st.session_state.log=[]; st.cache_data.clear(); st.rerun()
    tab1,tab2,tab3=st.tabs(["手动输入","批量API","更新日志"])
    with tab1:
        evt=st.radio("事件",["转化(消费)","浏览","搜索","对话","点击","投诉"],key="evt12")
        if "转化" in evt:
            amt=st.number_input("金额",0,100000,5000,key="v12a"); st.text_input("商户","星巴克",key="v12m")
        elif "浏览" in evt: st.selectbox("页面",["权益商城","分期计算器","账单详情","境外消费专区"],key="v12b")
        elif "搜索" in evt: st.text_input("搜索词","分期费率",key="v12s")
        elif "对话" in evt: st.text_area("对话摘要","",key="v12c"); st.selectbox("情绪",["neutral","satisfied","anxious","dissatisfied"],key="v12se")
        elif "点击" in evt: st.selectbox("活动",["CAMP_2026_DOUBLE11","CAMP_2026_APPLEPAY"],key="v12cl")
        if st.button("发送事件",use_container_width=True,key="v12send"):
            now=datetime.now().strftime("%H:%M:%S")
            if "转化" in evt: add_d(oneid,"annual",amt); add_d(oneid,"monthly",amt/12); st.success(f"消费{amt}→年消费+{amt} (Session)")
            elif "投诉" in evt: st.warning("投诉→churn_risk+25→降频")
            else: st.success(f"{evt}已记录")
            if "log" not in st.session_state: st.session_state.log=[]
            st.session_state.log.append({"time":now,"type":evt})
    with tab2:
        n=st.number_input("批量事件数",1,50,5,key="v12n")
        if st.button("执行批量",use_container_width=True):
            for i in range(n): a=random.randint(200,5000); add_d(oneid,"annual",a); add_d(oneid,"monthly",a/12)
            st.session_state.log.append({"time":datetime.now().strftime("%H:%M:%S"),"type":"batch"})
            st.success(f"批量{n}完成")
    with tab3:
        for l in reversed(st.session_state.log[-10:]): st.caption(f"{l['time']} {l['type']}")
        st.markdown("---"); st.markdown("**活跃度公式**: 天40%+笔30%+额30%")
        st.markdown("**更新**: T+1批量(03:00) | 微批(每小时) | 事件(<100ms)")

# ================================================================
def main():
    st.title("  客户360视图 v12 — DB全功能版")
    st.caption(f"{NOW} | SQLite({os.path.getsize(DB_PATH)/1024/1024:.0f}MB) | 5 Tab | 姓名/手机号/OneID/cust_id搜索 | 15秒刷新")

    data = load()
    # === 侧边栏 ===
    with st.sidebar:
        st.markdown("###  DB状态")
        s = data.get("stats",{})
        st.metric("客户",f"{s.get('customer_profile',8000):,}"); st.metric("回传",s.get('feedback_events',0)); st.caption(s.get('db_size',''))
        st.markdown("---")
        st.markdown("###  新增客户 (全新开户)")
        st.caption("从未办卡·无历史·生命周期=新户")
        name  = st.text_input("姓名*", key="s1", placeholder="必填")
        c1, c2 = st.columns(2)
        with c1: gender = st.selectbox("性别", ["M","F"], key="s1g", format_func=lambda x: "男" if x=="M" else "女")
        with c2: age    = st.number_input("年龄", 18, 65, 25, key="s3")
        city = st.selectbox("城市", ["深圳","上海","北京","广州","杭州","成都","武汉","南京"], key="s2")
        c1, c2 = st.columns(2)
        with c1: edu  = st.selectbox("学历", ["本科","硕士","博士","大专","高中"], key="s1e")
        with c2: occ  = st.selectbox("职业", ["IT/互联网","金融/银行","企业/贸易","公务员/事业","学生","其他"], key="s1o")
        c1, c2 = st.columns(2)
        with c1: inc  = st.selectbox("收入等级", ["H","M","L"], key="s4", format_func=lambda x: {"H":"高","M":"中","L":"低"}.get(x,x))
        with c2: card = st.selectbox("办卡等级", ["金卡","白金卡","普卡","钻石卡","校园卡"], key="s5")
        credit = st.number_input("授信额度", 5000, 500000, 50000, 10000, key="s5c")
        if st.button("  开户入网", use_container_width=True, type="primary"):
            if not name:
                st.error("请输入姓名")
            else:
                try:
                    conn = get_db()
                    max_id = conn.execute(
                        "SELECT MAX(CAST(SUBSTR(cust_id,2) AS INTEGER)) FROM customer_profile WHERE cust_id LIKE 'C%'"
                    ).fetchone()[0] or 8000
                    conn.close()
                    new_id = max_id + 1
                    oneid = f"UID{new_id:06d}"
                    cust_id = f"C{new_id:06d}"

                    from db_store import customer_insert
                    r = customer_insert({
                        "oneid": oneid, "cust_id": cust_id,
                        "demographics_name": name, "demographics_gender": gender,
                        "demographics_age": age, "demographics_city": city,
                        "demographics_education": edu, "demographics_occupation": occ,
                        "demographics_income_level": inc,
                        "account_primary_card_level": card,
                        "account_total_credit_amount": credit,
                    })
                    if r.get("status") == "ok":
                        st.cache_data.clear()
                        st.success("  新户开户成功!")
                        st.markdown(f"**{name}** | `{oneid}` | {cust_id}")
                        st.caption(f"学历={edu} 职业={occ} | 卡={card} 授信={credit:,} | 生命周期=新户 | 历史=空")
                        st.info(f"搜索框输入 {name} 或 {oneid} → 查看客户360")
                    else:
                        st.error(f"开户失败: {r.get('message','未知错误')}")
                except Exception as e:
                    st.error(f"开户异常: {e}")

        st.markdown("---")
        st.markdown("###  模拟回传 (测试)")
        evt_type = st.selectbox("事件类型", ["click","reject","conversation","conversion"], key="s7t",
                                format_func=lambda x: {"click":"点击感兴趣","reject":"拒绝","conversation":"对话","conversion":"消费转化"}.get(x,x))
        oid = st.text_input("OneID", "UID000001", key="s7")
        if evt_type == "conversation":
            summary = st.text_input("对话摘要", "咨询分期费率", key="s7s")
            intent = st.selectbox("意图", ["分期需求","权益咨询","额度升级","账户问题","销户咨询","其他"], key="s7i")
            sentiment = st.selectbox("情绪", ["中性","满意","焦虑","不满"], key="s7se")
            concerns = st.text_input("关注话题(逗号分隔)", "分期费率,手续费", key="s7c")
        elif evt_type == "conversion":
            amt = st.number_input("金额", 0, 100000, 5000, key="s8")
        else:
            campaign = st.text_input("活动ID", "CAMP_2026_DOUBLE11", key="s7ca")

        if st.button("  发送回传", use_container_width=True):
            from db_store import feedback_insert
            event = {"oneid": oid, "event_type": evt_type, "channel": "APP Push", "campaign_id": ""}
            if evt_type == "conversation":
                event.update({"summary": summary, "intent": intent, "sentiment": sentiment,
                              "top_concerns": [c.strip() for c in concerns.split(",") if c.strip()]})
            elif evt_type == "conversion":
                event["amount"] = amt; event["detail"] = {"amount": amt}
            elif evt_type in ("click","reject"):
                event["campaign_id"] = campaign
            r = feedback_insert(event)
            st.cache_data.clear()
            st.success(f"回传成功: {r.get('event_type')} | {oid}")
            if r.get("profile_updated"):
                st.caption(f"画像更新: {r['profile_updated']}")
            if r.get("signals"):
                st.caption(f"信号: {r['signals']}")
        st.caption("生产: POST /api/v1/db/feedback/import")
        st.caption("---")
        st.caption("  DB持久化: 写入SQLite, 点击清空缓存后大屏可见")
        st.caption("  Tab5 Session: 仅页面内存, 刷新消失")
        st.caption("OneID=唯一标识 | cust_id=银行客户号")

    # === 主面板 ===
    cq,ct,cb,cr=st.columns([3,1,1,1])
    with cq: query=st.text_input("搜索",placeholder="OneID / cust_id / 姓名 / 手机号")
    with ct: stype=st.selectbox("方式",["OneID","cust_id","姓名","手机号"])
    with cb:
        st.markdown("<br>",unsafe_allow_html=True); btn=st.button("搜索",use_container_width=True)
    with cr:
        st.markdown("<br>",unsafe_allow_html=True)
        if st.button("清空缓存",use_container_width=True): st.cache_data.clear(); st.rerun()
    if not btn and not query: query,stype="UID000001","OneID"
    if query:
        oneid=search(query,stype,data)
        if oneid is None: st.error(f"未找到: {query}"); st.stop()
        row=data["p"].iloc[data["idx"][oneid]].to_dict()
        name=g(row,"demographics_name"); cid=row.get("cust_id","")
        st.markdown(f"## {name} | `{oneid}` | {cid}")
        st.caption(f"OneID=系统唯一标识 | cust_id=银行客户号 | 搜索支持: 姓名/手机号/OneID/cust_id")
        # 预计算意图 (Tab2雷达 + Tab3评分 共享)
        intent_data = compute_intent(
            oneid,
            str(g(row, "lifecycle_stage", "")),
            str(g(row, "account_primary_card_level", "")),
            str(g(row, "short_term_7d_top_search_keywords", "")),
            str(g(row, "mid_term_30d_browse_preferences", "")),
            int(g(row, "risk_history_overdue_count_6m", 0)),
            str(g(row, "risk_risk_level", "low")),
            float(g(row, "account_usage_rate", 0)),
            str(g(row, "demographics_income_level", "")),
        )

        tabs = st.tabs(["静态画像", "动态记忆", "意图识别", "活动效果&归因", "实时更新&公式"])
        with tabs[0]: render_static(row, oneid)
        with tabs[1]: render_dynamic(row, oneid)
        with tabs[2]: render_intent(oneid, row, intent_data)
        with tabs[3]: render_roi(oneid, row)
        with tabs[4]: render_input(oneid, row)
        st.markdown("---")
        st.caption("DB实时 | 15秒刷新 | INSERT/UPDATE→清空缓存→立即可见 | T+1批量(03:00) | 微批(每小时) | 事件(<100ms)")

if __name__=="__main__": main()
