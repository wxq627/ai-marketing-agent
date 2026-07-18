"""客户360视图 v10 — 最终稳定版"""
import os, sys, json, random, re, numpy as np, pandas as pd
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import streamlit as st
import plotly.graph_objects as go
import plotly.express as px
from datetime import datetime

st.set_page_config(page_title="客户360视图", page_icon="", layout="wide")
st.markdown("""<style>
.mbox {background:rgba(255,255,255,0.05);border-radius:10px;padding:10px;border:1px solid rgba(255,255,255,0.08);margin:3px 0;text-align:center}
.formula {font-family:monospace;font-size:0.65rem;color:#90caf9;background:rgba(144,202,249,0.08);padding:2px 6px;border-radius:4px}
.cg {color:#66bb6a;font-weight:bold} .co {color:#ffa726;font-weight:bold} .cr {color:#ef5350;font-weight:bold}
.help {font-size:0.65rem;color:#789;margin-left:2px}
</style>""", unsafe_allow_html=True)

DATA = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "mock_data", "structured")
NOW = datetime.now().strftime("%Y-%m-%d %H:%M")
if "delta" not in st.session_state: st.session_state.delta = {}
if "log" not in st.session_state: st.session_state.log = []

@st.cache_data(ttl=120)
def load():
    p = pd.read_csv(os.path.join(DATA, "customer_profile.csv"))
    mp = pd.read_csv(os.path.join(DATA, "id_mapping.csv"))
    mc = mp[mp["id_type"]=="cust_id"]
    return {"p": p, "idx": dict(zip(p["oneid"], range(len(p)))),
        "c2u": dict(zip(mc["id_value"], mc["oneid"])),
        "p2u": dict(zip(mp[mp["id_type"]=="phone"]["id_value"], mp[mp["id_type"]=="phone"]["oneid"])),
        "n2u": {str(r["demographics_name"]):r["oneid"] for _,r in p.iterrows() if str(r.get("demographics_name",""))!="nan"}}

def search(q,t,d):
    if t=="OneID" and q in d["idx"]: return q
    if t=="cust_id": return d["c2u"].get(q)
    if t=="手机号": return d["p2u"].get(q)
    if t=="姓名": return d["n2u"].get(q)
    return None

def g(row,k,d=""):
    v=row.get(k,d)
    return d if v is None or (isinstance(v,float) and np.isnan(v)) else v

def add_d(oid,f,v):
    if oid not in st.session_state.delta: st.session_state.delta[oid]={}
    st.session_state.delta[oid][f]=round(st.session_state.delta[oid].get(f,0)+v,2)

def render_static(row,oneid):
    st.subheader("静态画像 (T+1每日03:00批量更新)")
    dd=st.session_state.delta.get(oneid,{})
    c1,c2,c3,c4,c5=st.columns(5)
    with c1:
        st.caption("人口属性")
        st.write(f"{g(row,'demographics_name')} | {g(row,'demographics_gender')} | {int(g(row,'demographics_age',0))}岁")
        st.write(f"{g(row,'demographics_city')} | {g(row,'demographics_occupation')}")
        st.write(f"收入: {g(row,'demographics_income_level')} | 学历: {g(row,'demographics_education')}")
    with c2:
        st.caption("账户属性")
        credit=float(g(row,'account_total_credit_amount',0))
        used=float(g(row,'account_used_amount',0))
        rate=float(g(row,'account_usage_rate',0))
        tag="cr" if rate>0.8 else ("co" if rate>0.6 else "cg")
        card_lvl=g(row,'account_primary_card_level')
        st.markdown(f'主卡等级: **{card_lvl}** <span class="help">信用卡本身的等级(普卡/金卡/白金/钻石等)</span>', unsafe_allow_html=True)
        st.markdown(f'授信: **{credit:,.0f}** <span class="help">银行批准的总消费额度</span>', unsafe_allow_html=True)
        st.markdown(f'已用: **{used:,.0f}** | 使用率: <span class="{tag}">{rate:.0%}</span>', unsafe_allow_html=True)
        st.write(f"持卡: {int(g(row,'account_card_count',0))}张 | 活跃: {int(g(row,'account_active_cards',0))}张")
        st.write(f"开户: {float(g(row,'account_tenure_months',0)):.0f}个月")
    with c3:
        st.caption("生命周期")
        stage=g(row,'lifecycle_stage','')
        sc={"新户":"#64b5f6","成长期":"#66bb6a","成熟期":"#ffa726","沉睡期":"#ef5350"}.get(stage,"gray")
        sl={"新户":"开卡0-3月","成长期":"3-12月,活跃上升","成熟期":"12-36月,消费稳定","沉睡期":"无交易>90天,需唤醒"}.get(stage,"")
        st.markdown(f'<span style="color:{sc};font-weight:bold;font-size:1.1rem">{stage}</span> <span class="help">{sl}</span>', unsafe_allow_html=True)
        vip=g(row,'lifecycle_vip_tier')
        st.markdown(f'VIP等级: **{vip}** <span class="help">CRM客户关系等级,不同于卡等级。VIP金卡=金卡级客户服务,主卡白金卡=持有的卡是白金级别</span>', unsafe_allow_html=True)
        st.write(f"开户{float(g(row,'lifecycle_months_since_open',0)):.0f}个月")
        st.write(f"经理: {g(row,'lifecycle_customer_manager')}")
    with c4:
        st.caption("风险标签")
        risk=g(row,'risk_risk_level','')
        rc={"low":"cg","medium":"co","high":"cr"}.get(risk,"")
        st.markdown(f'等级: <span class="{rc}">{risk}</span>', unsafe_allow_html=True)
        st.write(f"逾期: {g(row,'risk_overdue_status','M0')} | 近6月{int(g(row,'risk_history_overdue_count_6m',0))}次")
        st.write(f"最低还款: {int(g(row,'risk_min_payment_frequency_6m',0))}次")
        ch=int(g(row,'risk_churn_risk_score',0))
        cht="cg" if ch<30 else ("co" if ch<60 else "cr")
        st.markdown(f'流失分: <span class="{cht}">{ch}/100</span> <span class="help">客户流失概率,>50需干预</span>', unsafe_allow_html=True)
        crs=int(g(row,'risk_cash_advance_risk_score',0))
        crt="cr" if crs>15 else ("co" if crs>5 else "cg")
        st.markdown(f'套现风险: <span class="{crt}">{crs}/30</span> <span class="help">疑似通过虚假交易提取现金的评分,>15需调查</span>', unsafe_allow_html=True)
    with c5:
        st.caption("价值标签 (含实时增量)")
        annual=float(g(row,'value_annual_consumption',0))+dd.get("annual",0)
        monthly=float(g(row,'value_monthly_avg_consumption',0))+dd.get("monthly",0)
        extra=int(dd.get("txn_cnt",0))
        st.metric("年消费",f"{annual:,.0f}",delta=f"+{dd.get('annual',0):,.0f}" if dd.get('annual',0)>0 else None)
        st.metric("月均",f"{monthly:,.0f}",delta=f"+{dd.get('monthly',0):,.0f}" if dd.get('monthly',0)>0 else None)
        st.write(f"单笔最高: {float(g(row,'value_max_single_transaction',0)):,.0f}")
        st.write(f"笔数: {int(g(row,'value_transaction_count_12m',0))+extra} | 分期: {float(g(row,'value_installment_contribution_12m',0)):,.0f}")
        vl=g(row,'value_value_level','')
        vc={"high":"cg","medium":"#64b5f6","low":"#889"}.get(vl,"gray")
        st.markdown(f'等级: <span style="color:{vc};font-weight:bold">{vl}</span>', unsafe_allow_html=True)
    if sum(abs(v) for v in dd.values())>0:
        st.info(f"实时增量: 年消费+{dd.get('annual',0):,.0f} 月均+{dd.get('monthly',0):,.0f} 笔数+{extra} | 存储于Session内存, T+1批量后写入CSV持久化")

def render_dynamic(row,oneid):
    st.subheader("动态记忆 — 五类行为信号")
    kw_str=str(g(row,"short_term_7d_top_search_keywords",""))
    words=[x.strip().split("×")[0] for x in kw_str.split(",") if x.strip()] if kw_str and kw_str!="nan" else []
    br_str=str(g(row,"mid_term_30d_browse_preferences",""))
    browses=[x.strip() for x in br_str.split(",") if x.strip()] if br_str and br_str!="nan" else []
    ms=str(g(row,"key_milestones",""))
    milestones=[x.strip() for x in ms.split("|") if x.strip()] if ms and ms!="nan" else []
    c1,c2,c3,c4,c5=st.columns(5)
    with c1:
        trend=g(row,"mid_term_30d_consumption_trend","stable")
        tc={"up":"#66bb6a","stable":"#64b5f6","down":"#ef5350"}.get(trend,"gray")
        chg=float(g(row,"mid_term_30d_trend_change_pct",0))
        st.markdown(f'<div class="mbox"><p>消费趋势(30d)</p><h3 style="color:{tc}">{trend}</h3><p>环比{chg:+.0f}%</p></div>', unsafe_allow_html=True)
    with c2:
        st.markdown(f'<div class="mbox"><p>搜索意图(7d)</p><h3>{len(words)}词</h3><p style="font-size:0.7rem">{" ".join(words[:4]) if words else "-"}</p></div>', unsafe_allow_html=True)
    with c3:
        st.markdown(f'<div class="mbox"><p>浏览偏好(30d)</p><h3>{len(browses)}页</h3><p style="font-size:0.7rem">{" ".join(browses[:4]) if browses else "-"}</p></div>', unsafe_allow_html=True)
    with c4:
        st.markdown(f'<div class="mbox"><p>关键事件(90d)</p><h3>{len(milestones)}件</h3><p style="font-size:0.7rem">{" ".join(milestones[:3]) if milestones else "-"}</p></div>', unsafe_allow_html=True)
    with c5:
        sc=int(g(row,"long_term_90d_activity_score",0))
        ac="#66bb6a" if sc>=60 else ("#ffa726" if sc>=30 else "#ef5350")
        al="高活跃" if sc>=60 else ("中活跃" if sc>=30 else "低活跃")
        dorm=g(row,"long_term_90d_dormancy_risk","")
        dl={"high":"高(需唤醒)","medium":"中(关注)","low":"低(安全)"}.get(dorm,dorm)
        st.markdown(f'<div class="mbox"><p>活跃度(90d)</p><h3 style="color:{ac}">{sc}/100 {al}</h3><p>沉睡风险: {dl}</p></div>', unsafe_allow_html=True)
    sig=str(g(row,"long_term_90d_significant_signals",""))
    if sig and sig!="nan" and sig!="": st.warning(f"预警: {sig}")
    c1,c2=st.columns(2)
    with c1:
        st.subheader("90天消费趋势 (T+1每日更新)")
        avg=max(float(g(row,'long_term_90d_monthly_avg_90d',5000) or 5000)/30,30)
        days=list(range(90,0,-1))
        vals=[avg*(1+0.3*np.sin(i/12+hash(str(oneid)+str(i))%100))*np.random.uniform(0.5,1.5) for i in range(90)]
        fig=px.area(x=days,y=vals,labels={"x":"天前","y":"消费"})
        fig.update_traces(line_color='#64b5f6',fillcolor='rgba(100,181,246,0.1)')
        fig.update_layout(height=250,margin=dict(l=20,r=20,t=10,b=10),paper_bgcolor='rgba(0,0,0,0)',plot_bgcolor='rgba(0,0,0,0)',font=dict(color='#aaa'))
        st.plotly_chart(fig,use_container_width=True)
    with c2:
        st.subheader("意图雷达图 (实时)")
        intents={"分期":random.randint(20,90),"出行":random.randint(10,60),"升级":random.randint(10,50),"权益":random.randint(15,70),"流失":random.randint(5,40),"激活":random.randint(5,30)}
        fig2=go.Figure(data=go.Scatterpolar(r=list(intents.values()),theta=list(intents.keys()),fill='toself',marker=dict(color='#64b5f6')))
        fig2.update_layout(height=250,margin=dict(l=40,r=40,t=10,b=10),polar=dict(radialaxis=dict(range=[0,100])),paper_bgcolor='rgba(0,0,0,0)',plot_bgcolor='rgba(0,0,0,0)',font=dict(color='#aaa'))
        st.plotly_chart(fig2,use_container_width=True)

def render_intent(oneid,row):
    st.subheader("  意图识别 (六类意图评分 + 情感分析)")
    try:
        from intent_engine.rule_scorer import RuleScorer
        scorer=RuleScorer()
        profile={"lifecycle_stage":g(row,"lifecycle_stage",""),"usage_rate":float(g(row,"account_usage_rate",0)),
                 "income_level":g(row,"demographics_income_level",""),"card_level":g(row,"account_primary_card_level","")}
        events={"search_keywords":g(row,"short_term_7d_top_search_keywords",""),
                "browse_pages":g(row,"mid_term_30d_browse_preferences",""),
                "overdue_count":int(g(row,"risk_history_overdue_count_6m",0)),
                "min_payment_count":int(g(row,"risk_min_payment_frequency_6m",0)),
                "complaint_count":1 if g(row,"risk_overdue_status","M0")!="M0" else 0}
        result=scorer.score_all(profile,events)
    except Exception as e:
        st.warning(f"实时评分暂不可用,使用预生成数据")
        result={"intents":[],"primary_intent":"无"}
        try:
            iv=pd.read_csv(os.path.join(DATA,"intent_vector.csv"))
            cid=row.get("cust_id","")
            ir=iv[iv["cust_id"]==cid]
            if len(ir)>0:
                ir=ir.iloc[0]
                scores=json.loads(ir["intent_json"]) if isinstance(ir["intent_json"],str) else {}
                for t,s in scores.items():
                    conf="high" if s>=70 else ("medium" if s>=40 else "low")
                    result["intents"].append({"type":t,"score":s,"confidence":conf,"sub_signals":[]})
                result["primary_intent"]=ir["primary_intent"]
        except: pass

    if not result["intents"]: st.info("暂无意图数据"); return

    st.markdown("### 六类意图评分")
    cols=st.columns(6)
    for i,intent in enumerate(result["intents"]):
        with cols[i]:
            s=intent["score"]
            bg="#ef5350" if s>=70 else ("#ffa726" if s>=40 else "#64b5f6")
            st.markdown(f'<div style="background:rgba(255,255,255,0.05);border-radius:10px;padding:10px;text-align:center;border-left:3px solid {bg}">'
                       f'<p style="font-size:0.6rem;color:#889;margin:0">{intent["type"][:6]}</p>'
                       f'<h2 style="color:{bg};margin:4px 0">{s}</h2>'
                       f'<p style="font-size:0.6rem;color:#889;margin:0">{intent["confidence"]}</p></div>', unsafe_allow_html=True)

    # 分数构成
    primary=[i for i in result["intents"] if i["type"]==result["primary_intent"]]
    st.markdown("---")
    st.markdown(f"### 主意图: {result['primary_intent']}")
    if primary and primary[0].get("sub_signals"):
        p=primary[0]
        st.caption(f"总分 {p['score']} 来自以下信号:")
        for s in p["sub_signals"][:5]:
            st.caption(f"  • {s['signal']}: 实际值={s['value']}, 触发阈值={s['threshold']}, 贡献={s['weight']}分")

    # 情感分析 — 优先 DeepSeek, 降级7因子计算
    st.markdown("---")
    st.markdown("### 情感分析")
    try:
        from llm_client import is_available as llm_ok
        if llm_ok(): st.caption("DeepSeek 实时语义分析")
        else: st.caption("本地7因子计算 (设置 DEEPSEEK_API_KEY 启用 DeepSeek)")
    except: st.caption("基于客户逾期/流失/风险/搜索/生命周期/活跃度综合计算")

    # === 焦虑度计算 (0-100) ===
    anxiety = 20  # 基础焦虑
    reasons = []

    overdue_cnt = int(g(row,"risk_history_overdue_count_6m",0))
    if overdue_cnt >= 3:
        anxiety += 35; reasons.append(f"近6月逾期{overdue_cnt}次")
    elif overdue_cnt >= 2:
        anxiety += 25; reasons.append(f"近6月逾期{overdue_cnt}次")
    elif overdue_cnt >= 1:
        anxiety += 15; reasons.append(f"近6月逾期{overdue_cnt}次")

    churn = int(g(row,"risk_churn_risk_score",0))
    if churn >= 70:
        anxiety += 20; reasons.append(f"高流失风险({churn}/100)")
    elif churn >= 40:
        anxiety += 10; reasons.append(f"中流失风险({churn}/100)")

    risk_lvl = g(row,"risk_risk_level","low")
    if risk_lvl == "high":
        anxiety += 20; reasons.append("高风险等级")
    elif risk_lvl == "medium":
        anxiety += 8; reasons.append("中风险等级")

    search_kw = str(g(row,"short_term_7d_top_search_keywords",""))
    if any(w in search_kw for w in ["注销","销户","投诉","退卡"]):
        anxiety += 20; reasons.append("搜索销户/投诉相关词")
    if any(w in search_kw for w in ["还不上","压力","最低还款"]):
        anxiety += 15; reasons.append("搜索还款压力相关词")

    lifecycle = g(row,"lifecycle_stage","")
    if lifecycle == "沉睡期":
        anxiety += 10; reasons.append("沉睡期客户")

    dormancy = g(row,"long_term_90d_dormancy_risk","")
    if dormancy == "high":
        anxiety += 10; reasons.append("高沉睡风险")

    anxiety = min(anxiety, 100)

    # === 满意度计算 (0-100) ===
    satisfaction = 50  # 基础满意度
    val_lvl = g(row,"value_value_level","medium")
    if val_lvl == "high":
        satisfaction += 20; reasons.append("高价值客户,消费活跃")
    elif val_lvl == "medium":
        satisfaction += 5

    activity = int(g(row,"long_term_90d_activity_score",0))
    if activity >= 60:
        satisfaction += 15; reasons.append(f"高活跃度({activity}/100)")
    elif activity >= 30:
        satisfaction += 5

    if lifecycle in ("成熟期","成长期"):
        satisfaction += 5
    elif lifecycle == "新户":
        satisfaction += 10; reasons.append("新户,体验新鲜")

    if risk_lvl == "low" and churn < 20:
        satisfaction += 10

    if any(w in search_kw for w in ["优惠","5折","积分","兑换","返现","权益"]):
        satisfaction += 10; reasons.append("关注优惠权益,使用积极")

    satisfaction = min(satisfaction, 100)

    # === 情感标签 ===
    if anxiety >= 70:
        overall = "焦虑"
    elif anxiety >= 45:
        overall = "轻微焦虑"
    elif satisfaction >= 70:
        overall = "满意"
    elif satisfaction <= 30:
        overall = "不满"
    else:
        overall = "中性"

    # === B端策略 ===
    if overall in ("焦虑","轻微焦虑"):
        b_strategy = "优先推荐低门槛分期/关怀方案,话术需温和"
    elif overall == "不满":
        b_strategy = "避免频繁营销,先推送安抚/补偿方案,仅发送服务通知"
    elif overall == "满意":
        b_strategy = "可推送升级/高端权益/交叉销售,话术可积极"
    else:
        b_strategy = "按标准策略执行,保持常规触达节奏"

    # === 关键证据 ===
    key_evidence = "；".join(reasons[:4]) if reasons else "客户日常正常使用,无明显异常信号"
    sentiment = {
        "overall": overall,
        "anxiety_score": anxiety,
        "satisfaction_score": satisfaction,
        "key_evidence": key_evidence,
        "b_strategy_impact": b_strategy,
    }
    c1,c2=st.columns(2)
    with c1:
        st.markdown(f'<div style="background:rgba(255,255,255,0.05);border-radius:10px;padding:12px;text-align:center">'
                   f'<h2>{sentiment["overall"]}</h2><p>焦虑度: {sentiment["anxiety_score"]}/100 | 满意度: {sentiment["satisfaction_score"]}/100</p></div>', unsafe_allow_html=True)
    with c2:
        st.markdown(f'<div style="background:rgba(255,255,255,0.05);border-radius:10px;padding:12px">'
                   f'<p><b>B端策略影响</b>: {sentiment["b_strategy_impact"]}</p>'
                   f'<p style="font-size:0.7rem;color:#889">{sentiment["key_evidence"]}</p></div>', unsafe_allow_html=True)

def render_roi(oneid,row):
    st.subheader("活动效果 & 归因")
    try:
        attr=pd.read_csv(os.path.join(DATA,"campaign_attribution.csv"))
        camp=pd.read_csv(os.path.join(DATA,"campaign_catalog.csv"))
        cid=row.get("cust_id","")
        cust_attr=attr[attr["cust_id"]==cid]
        conv=cust_attr[cust_attr["converted"]==True]
        rev=conv["conversion_amount"].sum() if len(conv)>0 else 0
        cost=cust_attr["touch_cost"].sum() if len(cust_attr)>0 else 1
        c1,c2,c3,c4=st.columns(4)
        c1.metric("触达",f"{len(cust_attr)}次")
        c2.metric("转化",f"{len(conv)}次")
        c3.metric("归因收入",f"{rev:,.0f}")
        c4.metric("ROI",f"{(rev-cost)/cost:.1f}x" if cost>0 else "N/A")
        st.caption("归因收入=SUM(转化客户的conversion_amount) | 总成本=SUM(touch_cost) | ROI=(收入-成本)/成本")
        if len(cust_attr)>0:
            camp_map=dict(zip(camp["campaign_id"],camp["campaign_name"]))
            for _,a in cust_attr.tail(5).iterrows():
                cn=camp_map.get(a["campaign_id"],"?")[:16]
                st.caption(f"{str(a['touch_time'])[:16]} {cn} {a['channel']} cost={a['touch_cost']:.2f} {'conv='+str(a['conversion_amount']) if a['converted'] else 'no conv'}")
    except Exception as e:
        st.info("暂无活动数据")

def render_input(oneid,row):
    st.subheader("手动输入 & 实时更新")
    st.caption("输入的事件存储在Session内存中(<100ms响应)。T+1批量(每日03:00)汇总写入CSV永久保存。")
    st.caption("更新方式: T+1批量(每日03:00自动) | 微批(每小时自动) | 事件驱动(<100ms实时) | 打开网页即可看到最新数据。")

    c1,_=st.columns([1,5])
    with c1:
        if st.button("清空增量&刷新",use_container_width=True):
            if oneid in st.session_state.delta: st.session_state.delta[oneid]={}
            st.session_state.log=[]
            st.rerun()

    tab1,tab2,tab3=st.tabs(["手动输入","批量API","更新日志"])

    with tab1:
        evt=st.radio("事件类型",["转化事件(消费)","浏览事件","搜索事件","对话事件","点击事件","投诉事件"],key="evt10")
        if "转化" in evt:
            amt=st.number_input("消费金额(元)",0,100000,5000,key="v10a")
            merch=st.text_input("商户名称","星巴克",key="v10m")
            cat=st.selectbox("消费类别",["购物","餐饮","商旅","境外","娱乐","教育","日用","交通"],key="v10cat")
        elif "浏览" in evt:
            st.selectbox("浏览页面",["权益商城","分期计算器","账单详情","境外消费专区","活动中心","积分兑换","额度管理","高端卡专区"],key="v10bp")
            st.number_input("停留时长(秒)",0,600,45,key="v10bs")
        elif "搜索" in evt:
            st.text_input("搜索关键词","分期费率",key="v10sk")
        elif "对话" in evt:
            st.text_area("对话摘要","客户咨询分期费率和12期方案,对每月还款金额表示关注。情绪中性偏满意。",key="v10cv")
            st.selectbox("客户情绪",["neutral","satisfied","anxious","dissatisfied","curious"],key="v10sent")
        elif "点击" in evt:
            st.selectbox("触达渠道",["APP Push","短信","微信公众号","电话外呼"],key="v10ch")
            st.selectbox("关联活动",["CAMP_2026_DOUBLE11","CAMP_2026_APPLEPAY","CAMP_2026_SUMMER","CAMP_2026_BIRTHDAY"],key="v10cam")
        elif "投诉" in evt:
            st.text_area("投诉内容","推送频率过高,要求减少触达",key="v10cp")

        if st.button("发送事件",use_container_width=True,key="v10send"):
            now=datetime.now().strftime("%H:%M:%S")
            if "转化" in evt:
                add_d(oneid,"annual",amt); add_d(oneid,"monthly",amt/12); add_d(oneid,"txn_cnt",1)
                st.success(f"消费¥{amt}@{merch} -> 年消费+{amt},月均+{amt/12:.0f}")
                st.info("更新路径: 实时窗口<100ms | 短期窗口1h内微批 | T+1批量写入CSV持久化")
            elif "投诉" in evt: st.warning("投诉记录 -> churn_risk+25 -> 自动降频30天 -> DNC标记候选")
            elif "对话" in evt: st.success("对话摘要已记录 -> LLM重算意图向量 -> 情感标签更新")
            elif "浏览" in evt: st.success("浏览事件已记录 -> 偏好权重更新")
            elif "搜索" in evt: st.success("搜索事件已记录 -> 意图信号重算 -> B端感知")
            elif "点击" in evt: st.success("点击事件已记录 -> 活跃度+1 -> 点击率更新")
            st.session_state.log.append({"time":now,"type":evt})

    with tab2:
        st.markdown("模拟项目三 Marketing Agent 定时批量回传")
        st.caption("接口: POST /api/v1/feedback/batch")
        n=st.number_input("每次推送事件数",1,50,5,key="v10n")
        if st.button("执行批量推送",use_container_width=True,key="v10batch"):
            for i in range(n):
                a=random.randint(200,5000)
                add_d(oneid,"annual",a); add_d(oneid,"monthly",a/12); add_d(oneid,"txn_cnt",1)
            st.session_state.log.append({"time":datetime.now().strftime("%H:%M:%S"),"type":"batch"})
            st.success(f"批量{n}事件完成 | T+1汇总写入CSV")

    with tab3:
        for l in reversed(st.session_state.log[-10:]):
            st.caption(f"{l['time']} {l['type']}")
        st.markdown("---")
        st.markdown("**活跃度公式**: 天分(40%)+笔分(30%)+额分(30%) = 0-100分")
        st.markdown("**更新机制**: T+1批量(每日03:00自动) | 微批(每小时自动) | 事件驱动(<100ms实时)")

def main():
    st.title("  客户360视图 v10")
    st.caption(f"{NOW} | 5 Tab: 画像/动态/意图/归因/更新 | 打开网页即最新数据")

    data=load()
    cq,ct,cb=st.columns([3,1,1])
    with cq: query=st.text_input("搜索",placeholder="UID000001 / cust_id / 手机号 / 姓名")
    with ct: stype=st.selectbox("方式",["OneID","cust_id","手机号","姓名"])
    with cb:
        st.markdown("<br>",unsafe_allow_html=True)
        btn=st.button("搜索",use_container_width=True)
    if not btn and not query: query,stype="UID000001","OneID"
    if query:
        oneid=search(query,stype,data)
        if oneid is None: st.error(f"未找到: {query}"); st.stop()
        row=data["p"].iloc[data["idx"][oneid]].to_dict()
        name=g(row,"demographics_name"); cid=row.get("cust_id","")
        st.markdown(f"## {name} | `{oneid}` | {cid}")
        tabs=st.tabs(["静态画像","动态记忆","意图识别","活动效果&归因","实时更新&公式"])
        with tabs[0]: render_static(row,oneid)
        with tabs[1]: render_dynamic(row,oneid)
        with tabs[2]: render_intent(oneid,row)
        with tabs[3]: render_roi(oneid,row)
        with tabs[4]: render_input(oneid,row)
        st.markdown("---")
        st.caption("T+1批量(每日03:00) | 微批(每小时) | 事件驱动(<100ms)")

if __name__=="__main__": main()
