"""客户360视图 v12 — DB版全功能"""
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
    st.subheader("动态记忆 — 五类信号")
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
        st.subheader("意图雷达")
        intents={"分期":random.randint(20,90),"出行":random.randint(10,60),"升级":random.randint(10,50),"权益":random.randint(15,70),"流失":random.randint(5,40),"激活":random.randint(5,30)}
        fig2=go.Figure(data=go.Scatterpolar(r=list(intents.values()),theta=list(intents.keys()),fill='toself',marker=dict(color='#64b5f6')))
        fig2.update_layout(height=250,margin=dict(l=40,r=40,t=10,b=10),polar=dict(radialaxis=dict(range=[0,100])),paper_bgcolor='rgba(0,0,0,0)',plot_bgcolor='rgba(0,0,0,0)',font=dict(color='#aaa'))
        st.plotly_chart(fig2,use_container_width=True)

def render_intent(oneid, row):
    st.subheader("  意图识别 & 情感分析")
    search_kw = str(g(row,"short_term_7d_top_search_keywords",""))
    overdue_cnt = int(g(row,"risk_history_overdue_count_6m",0))
    churn_score = int(g(row,"risk_churn_risk_score",0))
    risk_level = g(row,"risk_risk_level","low")
    lifecycle = g(row,"lifecycle_stage","")
    # 六类意图评分
    try:
        from intent_engine.rule_scorer import RuleScorer
        scorer=RuleScorer()
        profile={"lifecycle_stage":lifecycle,"usage_rate":float(g(row,"account_usage_rate",0)),"income_level":g(row,"demographics_income_level",""),"card_level":g(row,"account_primary_card_level","")}
        events={"search_keywords":search_kw,"browse_pages":str(g(row,"mid_term_30d_browse_preferences","")),"overdue_count":overdue_cnt,"min_payment_count":int(g(row,"risk_min_payment_frequency_6m",0)),"complaint_count":1 if risk_level=="high" else 0}
        result=scorer.score_all(profile,events)
    except:
        result={"intents":[],"primary_intent":"无"}
        try:
            iv=pd.read_csv(os.path.join(BASE,"mock_data","structured","intent_vector.csv"))
            ir=iv[iv["cust_id"]==row.get("cust_id","")]
            if len(ir)>0:
                scores=json.loads(ir.iloc[0]["intent_json"]) if isinstance(ir.iloc[0]["intent_json"],str) else {}
                for t,s in scores.items():
                    conf="high" if s>=70 else ("medium" if s>=40 else "low")
                    result["intents"].append({"type":t,"score":s,"confidence":conf,"sub_signals":[]})
                result["primary_intent"]=ir.iloc[0]["primary_intent"]
        except: pass
    if not result["intents"]: st.info("暂无意图数据"); return
    st.markdown("### 六类意图评分")
    cols=st.columns(6)
    for i,intent in enumerate(result["intents"]):
        with cols[i]:
            s=intent["score"]; bg="#ef5350" if s>=70 else ("#ffa726" if s>=40 else "#64b5f6")
            st.markdown(f'<div style="background:rgba(255,255,255,0.05);border-radius:10px;padding:10px;text-align:center;border-left:3px solid {bg}"><p style="font-size:0.6rem;color:#889;margin:0">{intent["type"][:6]}</p><h2 style="color:{bg};margin:4px 0">{s}</h2><p style="font-size:0.6rem;color:#889;margin:0">{intent["confidence"]}</p></div>',unsafe_allow_html=True)
    # 主意图解释
    primary=[i for i in result["intents"] if i["type"]==result["primary_intent"]]
    st.markdown("---")
    if primary and primary[0].get("sub_signals"):
        p=primary[0]; st.markdown(f"### 主意图: {result['primary_intent']} ({p['score']}分)")
        st.caption(" + ".join([f"{s['signal'][:12]}({s['weight']}分)" for s in p["sub_signals"]]) if p["sub_signals"] else "")
    # 情感分析
    st.markdown("---"); st.markdown("### 情感分析")
    anxiety=20; satisfaction=60; reasons=[]
    if overdue_cnt>=3: anxiety+=35; reasons.append(f"逾期{overdue_cnt}次")
    elif overdue_cnt>=2: anxiety+=25; reasons.append(f"逾期{overdue_cnt}次")
    elif overdue_cnt>=1: anxiety+=15; reasons.append(f"逾期{overdue_cnt}次")
    if churn_score>=70: anxiety+=20; reasons.append(f"高流失({churn_score})")
    elif churn_score>=40: anxiety+=10
    if risk_level=="high": anxiety+=20; reasons.append("高风险")
    elif risk_level=="medium": anxiety+=8
    if any(w in search_kw for w in["注销","销户","投诉"]): anxiety+=20; reasons.append("搜索销户/投诉")
    if lifecycle=="沉睡期": anxiety+=10
    anxiety=min(anxiety,100)
    val_lvl=g(row,"value_value_level","medium")
    if val_lvl=="high": satisfaction+=20; reasons.append("高价值")
    act=int(g(row,"long_term_90d_activity_score",0))
    if act>=60: satisfaction+=15
    elif act>=30: satisfaction+=5
    satisfaction=min(satisfaction,100)
    overall="焦虑" if anxiety>=70 else ("轻微焦虑" if anxiety>=45 else ("满意" if satisfaction>=70 else "中性"))
    c1,c2=st.columns(2)
    with c1: st.markdown(f'<div style="background:rgba(255,255,255,0.05);border-radius:10px;padding:12px;text-align:center"><h2>{overall}</h2><p>焦虑度:{anxiety}/100 | 满意度:{satisfaction}/100</p></div>',unsafe_allow_html=True)
    with c2: st.caption("证据:"+";".join(reasons) if reasons else "日常正常使用"); st.caption("T+1批量每日03:00 | 事件驱动<100ms | DeepSeek可用时启用语义分析")

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
        st.markdown("###  新增客户(DB INSERT)")
        name=st.text_input("姓名","Demo",key="s1"); city=st.selectbox("城市",["深圳","上海","北京","广州","杭州"],key="s2")
        age=st.number_input("年龄",18,65,30,key="s3"); inc=st.selectbox("收入",["H","M","L"],key="s4")
        card=st.selectbox("卡等级",["金卡","白金卡","普卡","钻石卡","校园卡"],key="s5"); annual=st.number_input("年消费",0,500000,80000,key="s6")
        if st.button("INSERT到DB",use_container_width=True):
            conn=get_db()
            max_id=conn.execute("SELECT MAX(CAST(SUBSTR(cust_id,2) AS INTEGER)) FROM customer_profile WHERE cust_id LIKE 'C%'").fetchone()[0] or 8000
            conn.close(); new_id=max_id+1; oneid=f"UID{new_id:06d}"
            conn=get_db()
            conn.execute("""INSERT INTO customer_profile (oneid,cust_id,demographics_name,demographics_gender,demographics_age,demographics_city,demographics_occupation,demographics_income_level,demographics_education,account_primary_card_level,account_total_credit_amount,account_used_amount,account_usage_rate,account_card_count,account_active_cards,account_tenure_months,lifecycle_stage,lifecycle_months_since_open,lifecycle_vip_tier,value_annual_consumption,value_monthly_avg_consumption,value_value_level,risk_risk_level,risk_overdue_status,risk_history_overdue_count_6m,risk_churn_risk_score,long_term_90d_activity_score,long_term_90d_dormancy_risk,generated_at,update_type) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                [oneid,f"C{new_id:06d}",name,'M',age,city,'IT',inc,'本科',card,200000,50000,0.25,2,2,12,'成长期',12,'金卡',annual,annual/12,'medium','low','M0',0,5,50,'medium',datetime.now().strftime("%Y-%m-%d"),'manual'])
            conn.commit(); conn.close(); st.cache_data.clear()
            st.success(f"INSERT: {oneid} (C{new_id:06d}) | 姓名={name}")
            st.info(f"搜索框输入 {name} 或 {oneid} → 立即可见!")
        st.markdown("---")
        st.markdown("###  项目三回传")
        oid=st.text_input("OneID","UID000001",key="s7"); amt=st.number_input("金额",0,100000,5000,key="s8")
        if st.button("回传→UPDATE DB",use_container_width=True):
            conn=get_db()
            conn.execute("INSERT INTO feedback_events (oneid,event_type,campaign_id,channel,detail,timestamp) VALUES (?,?,?,?,?,datetime('now'))",[oid,'conversion','DEMO','APP Push',str(amt)])
            conn.execute("UPDATE customer_profile SET value_annual_consumption=value_annual_consumption+?, value_monthly_avg_consumption=value_monthly_avg_consumption+? WHERE oneid=?",[float(amt),float(amt)/12,oid])
            conn.commit(); conn.close(); st.cache_data.clear()
            st.success(f"回传: {oid} 年消费+{amt}")
        st.caption("项目三: POST /api/v1/db/feedback/import")
        st.caption("---")
        st.caption("  DB持久化: 写入SQLite, 点击清空缓存后大屏可见")
        st.caption("  Tab5 Session: 仅当前页面内存, 刷新后消失")
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
        tabs=st.tabs(["静态画像","动态记忆","意图识别","活动效果&归因","实时更新&公式"])
        with tabs[0]: render_static(row,oneid)
        with tabs[1]: render_dynamic(row,oneid)
        with tabs[2]: render_intent(oneid,row)
        with tabs[3]: render_roi(oneid,row)
        with tabs[4]: render_input(oneid,row)
        st.markdown("---")
        st.caption("DB实时 | 15秒刷新 | INSERT/UPDATE→清空缓存→立即可见 | T+1批量(03:00) | 微批(每小时) | 事件(<100ms)")

if __name__=="__main__": main()
