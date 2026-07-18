"""客户360视图 v11 — DB版, 新增数据立即可见"""
import os, sys, sqlite3, pandas as pd, numpy as np, json, random
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import streamlit as st
import plotly.graph_objects as go
import plotly.express as px
from datetime import datetime

st.set_page_config(page_title="客户360视图", page_icon="", layout="wide")
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
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn

@st.cache_data(ttl=15)  # 15秒刷新
def load():
    conn = get_db()
    p = pd.read_sql("SELECT * FROM customer_profile", conn)
    mp = pd.read_sql("SELECT * FROM id_mapping WHERE id_type='cust_id'", conn)
    stats = {}
    for t in ["customer_profile","transaction_log_full","feedback_events"]:
        try: stats[t] = conn.execute(f"SELECT COUNT(*) FROM {t}").fetchone()[0]
        except: stats[t] = 0
    stats["db_size"] = f"{os.path.getsize(DB_PATH)/1024/1024:.1f}MB" if os.path.exists(DB_PATH) else "N/A"
    conn.close()
    return {"p": p, "idx": dict(zip(p["oneid"], range(len(p)))),
        "c2u": dict(zip(mp["id_value"], mp["oneid"])), "stats": stats}

def search(query, stype, data):
    if stype == "OneID" and query in data["idx"]: return query
    if stype == "cust_id": return data["c2u"].get(query)
    return None

def g(row, k, d=""):
    v = row.get(k, d)
    return d if v is None or (isinstance(v, float) and np.isnan(v)) else v

def quick_insert(oneid, cid, name, gender, age, city, income, edu, card, lifecycle, annual, monthly, val_lvl, risk_lvl):
    """INSERT一行到customer_profile (29个必填列)。"""
    conn = get_db()
    conn.execute("""INSERT INTO customer_profile
        (oneid,cust_id,demographics_name,demographics_gender,demographics_age,demographics_city,
         demographics_occupation,demographics_income_level,demographics_education,
         account_primary_card_level,account_total_credit_amount,account_used_amount,
         account_usage_rate,account_card_count,account_active_cards,account_tenure_months,
         lifecycle_stage,lifecycle_months_since_open,lifecycle_vip_tier,
         value_annual_consumption,value_monthly_avg_consumption,value_value_level,
         risk_risk_level,risk_overdue_status,risk_history_overdue_count_6m,
         risk_churn_risk_score,long_term_90d_activity_score,long_term_90d_dormancy_risk,
         generated_at,update_type)
        VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
        [oneid,cid,name,gender,age,city,"IT/互联网",income,edu,card,100000,30000,0.3,2,2,12,
         lifecycle,12,"金卡",annual,monthly,val_lvl,risk_lvl,"M0",0,10,50,"medium",
         datetime.now().strftime("%Y-%m-%d"),"manual_insert"])
    conn.commit(); conn.close()

def quick_feedback(oneid, amt):
    """回传转化事件+更新画像。"""
    conn = get_db()
    conn.execute("INSERT INTO feedback_events (oneid,event_type,campaign_id,channel,detail,timestamp) VALUES (?,?,?,?,?,datetime('now'))",
        [oneid,'conversion','DEMO','APP Push',str(amt)])
    conn.execute("UPDATE customer_profile SET value_annual_consumption=value_annual_consumption+?, value_monthly_avg_consumption=value_monthly_avg_consumption+? WHERE oneid=?",
        [float(amt),float(amt)/12,oneid])
    conn.commit(); conn.close()

def render_static(row, oneid):
    st.subheader("静态画像 (T+1每日03:00批量 | 当前查询: DB实时)")
    c1,c2,c3,c4,c5 = st.columns(5)
    with c1:
        st.caption("人口"); st.write(f"{g(row,'demographics_name')} | {g(row,'demographics_gender')} | {int(g(row,'demographics_age',0))}岁")
        st.write(f"{g(row,'demographics_city')} | {g(row,'demographics_occupation')}")
        st.write(f"收入:{g(row,'demographics_income_level')} | 学历:{g(row,'demographics_education')}")
    with c2:
        st.caption("账户"); credit=float(g(row,'account_total_credit_amount',0)); used=float(g(row,'account_used_amount',0)); rate=float(g(row,'account_usage_rate',0))
        tag="cr" if rate>0.8 else ("co" if rate>0.6 else "cg")
        st.write(f"主卡:{g(row,'account_primary_card_level')}")
        st.markdown(f'授信:<b>{credit:,.0f}</b> <span class="help">银行批准额度</span>',unsafe_allow_html=True)
        st.markdown(f'已用:<b>{used:,.0f}</b> | 使用率:<span class="{tag}">{rate:.0%}</span>',unsafe_allow_html=True)
        st.write(f"持卡:{int(g(row,'account_card_count',0))}张 | 活跃:{int(g(row,'account_active_cards',0))}张")
    with c3:
        st.caption("生命周期"); stage=g(row,'lifecycle_stage','')
        sc={"新户":"#64b5f6","成长期":"#66bb6a","成熟期":"#ffa726","沉睡期":"#ef5350"}.get(stage,"gray")
        st.markdown(f'<span style="color:{sc};font-weight:bold;font-size:1.1rem">{stage}</span>',unsafe_allow_html=True)
        st.write(f"VIP:{g(row,'lifecycle_vip_tier')} | 开户{float(g(row,'lifecycle_months_since_open',0)):.0f}月")
    with c4:
        st.caption("风险"); risk=g(row,'risk_risk_level',''); rc={"low":"cg","medium":"co","high":"cr"}.get(risk,"")
        st.markdown(f'等级:<span class="{rc}">{risk}</span>',unsafe_allow_html=True)
        st.write(f"逾期:{g(row,'risk_overdue_status','M0')} | 近6月:{int(g(row,'risk_history_overdue_count_6m',0))}次")
        ch=int(g(row,'risk_churn_risk_score',0)); cht="cg" if ch<30 else ("co" if ch<60 else "cr")
        st.markdown(f'流失:<span class="{cht}">{ch}/100</span>',unsafe_allow_html=True)
    with c5:
        st.caption("价值"); annual=float(g(row,'value_annual_consumption',0)); monthly=float(g(row,'value_monthly_avg_consumption',0))
        st.metric("年消费",f"{annual:,.0f}"); st.metric("月均",f"{monthly:,.0f}")
        vl=g(row,'value_value_level',''); vc={"high":"cg","medium":"#64b5f6","low":"#889"}.get(vl,"gray")
        st.markdown(f'等级:<span style="color:{vc};font-weight:bold">{vl}</span>',unsafe_allow_html=True)

def main():
    st.title("  客户360视图 v11 — DB实时版")
    st.caption(f"{NOW} | 数据源: SQLite ({os.path.getsize(DB_PATH)/1024/1024:.0f}MB) | 15秒自动刷新 | INSERT→立即可见")

    data = load()

    # === 侧边栏 ===
    with st.sidebar:
        st.markdown("###  数据库状态")
        stats = data.get("stats", {})
        st.metric("客户画像", f"{stats.get('customer_profile',8000):,}")
        st.metric("交易流水", f"{stats.get('transaction_log_full',0):,}")
        st.metric("回传事件", stats.get('feedback_events', 0))
        st.caption(f"DB: {stats.get('db_size','N/A')}")

        st.markdown("---")
        st.markdown("###  模拟新增客户")
        name = st.text_input("姓名", "Demo客户", key="s1")
        city = st.selectbox("城市", ["深圳","上海","北京","广州","杭州"], key="s2")
        age = st.number_input("年龄", 18, 65, 30, key="s3")
        inc = st.selectbox("收入", ["H","M","L"], key="s4")
        card = st.selectbox("卡等级", ["金卡","白金卡","普卡","钻石卡","校园卡"], key="s5")
        annual = st.number_input("年消费估算", 0, 500000, 80000, key="s6")

        if st.button("  INSERT到数据库", use_container_width=True, key="btn1"):
            conn = get_db()
            max_id = conn.execute("SELECT MAX(CAST(SUBSTR(cust_id,2) AS INTEGER)) FROM customer_profile WHERE cust_id LIKE 'C%'").fetchone()[0] or 8000
            conn.close()
            new_id = max_id + 1
            oneid = f"UID{new_id:06d}"
            quick_insert(oneid, f"C{new_id:06d}", name, "M", age, city, inc, "本科", card, "成长期", annual, annual/12, "medium", "low")
            st.cache_data.clear()
            st.success(f"INSERT成功! {oneid} (C{new_id:06d})")
            st.info("搜索框输入上面这个OneID → 大屏立即可见新客户! (无需重启)")

        st.markdown("---")
        st.markdown("###  模拟项目三回传")
        oid = st.text_input("目标OneID", "UID000001", key="s7")
        amt = st.number_input("转化金额", 0, 100000, 5000, key="s8")
        if st.button("  回传转化→更新画像", use_container_width=True, key="btn2"):
            quick_feedback(oid, amt)
            st.cache_data.clear()
            st.success(f"回传+画像更新: {oid} 年消费+{amt}")
            st.info("搜索该OneID → 年消费立即更新! C→A闭环完成")

        st.markdown("---")
        st.caption("项目三负责人: 调用 POST /api/v1/db/feedback/import 即自动更新DB")
        st.caption("大屏15秒自动刷新(或点'清空缓存')→新数据立即可见")
        st.caption("升级PG: db_store.py改连接字符串,SQL不变")

    # === 主面板 ===
    cq, ct, cb, cr = st.columns([3, 1, 1, 1])
    with cq: query = st.text_input("搜索", placeholder="OneID (如 UID000001)")
    with ct: stype = st.selectbox("方式", ["OneID", "cust_id"])
    with cb:
        st.markdown("<br>", unsafe_allow_html=True)
        btn = st.button("搜索", use_container_width=True)
    with cr:
        st.markdown("<br>", unsafe_allow_html=True)
        if st.button("清空缓存", use_container_width=True):
            st.cache_data.clear()
            st.rerun()

    if not btn and not query: query, stype = "UID000001", "OneID"
    if query:
        oneid = search(query, stype, data)
        if oneid is None: st.error(f"未找到: {query}"); st.stop()
        row = data["p"].iloc[data["idx"][oneid]].to_dict()
        name = g(row, "demographics_name"); cid = row.get("cust_id", "")
        st.markdown(f"## {name} | `{oneid}` | {cid}")
        render_static(row, oneid)
        st.markdown("---")
        st.caption("更新: T+1批量(03:00) | 微批(每小时) | 实时INSERT(<1ms) | 项目三回传→DB UPDATE→15秒大屏刷新")

if __name__ == "__main__": main()
