"""
客户画像数据生成 v3 — 全面对齐技术方案
=======================================
静态画像 5维度32字段 + 动态记忆 4窗口25指标 + 搜索意图 + 浏览偏好 + 关键事件

card_no碰撞解决方案: 基于客户属性(收入×卡等级×生命周期)生成金融指标,
不依赖脱敏card_no映射, 通过OneID保证唯一性。
"""
import os, sys, time, pandas as pd, json, random, numpy as np
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from datetime import datetime

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUT = os.path.join(BASE, "mock_data", "structured", "customer_profile.csv")
REF = datetime(2026, 7, 15, 15, 0, 0)
random.seed(42); np.random.seed(42)

# 搜索关键词库 (按意图分类)
SEARCH_KW = {
    "分期": ["分期费率","12期","账单分期","免息分期","手续费","最低还款","现金分期"],
    "出行": ["出境游","汇率","东京","海淘","免税","签证","境外取现","机票","酒店"],
    "升级": ["提额","额度不够","白金卡","钻石卡","临时额度","固定额度"],
    "权益": ["积分兑换","里程","优惠券","5折","星巴克","电影票","贵宾厅","接送机"],
    "沉睡": ["销户","注销","年费","退卡","投诉"],
}
# 浏览页面库
BROWSE_PAGES = ["权益商城","分期计算器","账单详情","境外消费专区","活动中心",
                "积分兑换","额度管理","信用卡申请","还款页面","高端卡专区","新手指引"]
# 关键事件库
MILESTONE_EVENTS = ["首次境外消费","额度首次提升","首笔分期办理","年消费突破10万",
                    "升级白金卡","首次使用机场贵宾厅","办理自动还款","首投投诉"]

def gen_finance(cust, cards, crm, consent, products):
    """生成每客户完整画像"""
    income_m = {"H":60000,"M":18000,"L":6000}
    card_m = {"无限卡":3.0,"钻石卡":2.5,"白金卡":1.8,"金卡":1.2,"普卡":0.8,"校园卡":0.3}
    lf_m = {"新户":1.2,"成长期":1.3,"成熟期":1.0,"沉睡期":0.2}

    crm_idx = crm.set_index("cust_id")
    consent_idx = consent.set_index("cust_id")
    primary = cards[cards["is_primary"]==True].set_index("cust_id")
    pid_to_name = dict(zip(products["product_id"], products["product_name"]))
    mp = pd.read_csv(os.path.join(BASE,"mock_data","structured","id_mapping.csv"))
    cust_to_oneid = dict(zip(mp[mp["id_type"]=="cust_id"]["id_value"],
                              mp[mp["id_type"]=="cust_id"]["oneid"]))

    rows = []
    for _, row in cust.iterrows():
        cid = row["cust_id"]
        oneid = cust_to_oneid.get(cid, f"UID_{cid}")
        inc = row["income_level"]
        mi = income_m.get(inc, 10000)
        reg_dt = datetime.strptime(str(row.get("register_date","2020-01-01")),"%Y-%m-%d")
        months = max(0, (REF-reg_dt).days/30.44)

        # 主卡
        pc = primary.loc[cid] if cid in primary.index else None
        cl = pc["card_level"] if pc is not None else "金卡"
        cm = card_m.get(cl, 1.0)
        total_credit = cards[cards["cust_id"]==cid]["credit_amount"].sum()
        used_amount = total_credit * np.random.uniform(0.1, 0.85)
        prod_id = pc["product_id"] if pc is not None else ""
        prod_name = pid_to_name.get(prod_id, "")
        card_count = len(cards[cards["cust_id"]==cid])
        active_c = int((cards[(cards["cust_id"]==cid)&(cards["card_status"]=="正常")]).shape[0])

        # 生命周期
        crm_r = crm_idx.loc[cid] if cid in crm_idx.index else None
        lfs = crm_r["lifecycle_stage"] if crm_r is not None else "成熟期"
        lm = lf_m.get(lfs, 1.0)

        # 风险
        cns = consent_idx.loc[cid] if cid in consent_idx.index else None
        risk_lvl = cns["risk_level"] if cns is not None else "low"
        churn = int(crm_r["churn_risk_score"]) if crm_r is not None else 0
        if risk_lvl=="high" or churn>50:
            ovc = np.random.choice([0,1,2,3],p=[0.3,0.3,0.25,0.15])
            mpc = np.random.choice([0,1,2,3],p=[0.4,0.3,0.2,0.1])
        elif risk_lvl=="medium":
            ovc = np.random.choice([0,1,2],p=[0.6,0.3,0.1])
            mpc = np.random.choice([0,1,2],p=[0.6,0.3,0.1])
        else:
            ovc = np.random.choice([0,1],p=[0.9,0.1])
            mpc = np.random.choice([0,1],p=[0.85,0.15])
        ol = "M3+" if ovc>=3 else ("M2" if ovc>=2 else ("M1" if ovc>=1 else "M0"))
        cash_adv_risk = np.random.randint(0,30) if risk_lvl!="low" else np.random.randint(0,10)

        # 价值
        sr = np.random.triangular(0.20, 0.40, 0.70)
        annual = mi * sr * 12 * cm * lm * np.random.uniform(0.6, 1.4)
        monthly = annual/12
        max_single = annual * np.random.uniform(0.03, 0.25)
        txn_cnt = int(annual / np.random.uniform(200, 1500))
        installment = annual * np.random.uniform(0.03, 0.12)
        vl = cns["value_level"] if cns is not None else "medium"

        # ===== 动态记忆 =====
        # 4窗口消费
        c90 = annual * 0.25 * lm * np.random.uniform(0.6, 1.4)
        t90 = int(txn_cnt * 0.25 * lm)
        ad90 = int(min(t90 * 0.6, 90))
        day_s = min(ad90/90*40, 40)
        cnt_s = min(t90/100*30, 30)
        amt_s = min(c90/50000*30, 30)
        activity = int(day_s + cnt_s + amt_s)
        dorm = "high" if activity<20 else ("medium" if activity<50 else "low")
        c30 = c90 * 0.35 * np.random.uniform(0.7, 1.3)
        t30 = int(t90 * 0.35)
        ad30 = int(ad90 * 0.35)
        prev30 = c30 * np.random.uniform(0.7, 1.3)
        tpct = round((c30-prev30)/prev30*100,1) if prev30>0 else 0
        trend = "up" if tpct>15 else ("down" if tpct<-20 else "stable")
        c7 = c30 * 0.25 * np.random.uniform(0.7, 1.3)
        t7 = int(t30 * 0.25)
        ad7 = int(ad30 * 0.25)

        # 搜索意图信号 (近7天)
        intent_cats = random.sample(list(SEARCH_KW.keys()), min(3, len(SEARCH_KW)))
        search_words = []
        for cat in intent_cats:
            w = random.choice(SEARCH_KW[cat])
            cnt = random.randint(2, 8)
            search_words.append(f"{w}×{cnt}")
        search_top5 = ", ".join(search_words[:5])

        # 浏览偏好 (近30天)
        browse = random.sample(BROWSE_PAGES, min(4, len(BROWSE_PAGES)))
        browse_ratios = np.random.dirichlet(np.ones(len(browse))*2)
        browse_str = ", ".join([f"{b}({r*100:.0f}%)" for b,r in zip(browse, browse_ratios)])

        # 关键事件 (里程碑)
        n_milestones = np.random.choice([0,1,2,3], p=[0.4,0.3,0.2,0.1])
        milestones = random.sample(MILESTONE_EVENTS, min(n_milestones, len(MILESTONE_EVENTS)))
        milestone_str = "|".join(milestones) if milestones else ""

        # 降级/预警信号
        signals = []
        if trend=="down" and abs(tpct)>25: signals.append("消费降级")
        if activity<25: signals.append("活跃度骤降")
        if dorm=="high": signals.append("沉睡预警")
        if ovc>=2: signals.append("逾期预警")
        sig_str = ", ".join(signals) if signals else ""

        # 实时信号
        rt_cnt = np.random.choice([0,0,0,1,1,2], p=[0.4,0.15,0.15,0.15,0.1,0.05])
        rt_high = np.random.random()<0.06

        r = {
            "oneid": oneid, "cust_id": cid,
            # 人口
            "demographics_name": row.get("name",""),"demographics_gender": row.get("gender",""),
            "demographics_age": int(row.get("age",0)),"demographics_city": row.get("city",""),
            "demographics_occupation": row.get("occupation",""),"demographics_income_level": inc,
            "demographics_education": row.get("education",""),
            # 账户
            "account_primary_card_level": cl, "account_product_name": prod_name,
            "account_total_credit_amount": float(total_credit),
            "account_used_amount": round(float(used_amount), 2),
            "account_usage_rate": round(float(used_amount/total_credit), 4) if total_credit>0 else 0,
            "account_card_count": card_count, "account_active_cards": active_c,
            "account_tenure_months": round(months, 1),
            # 生命周期
            "lifecycle_stage": lfs,"lifecycle_months_since_open": round(months,1),
            "lifecycle_vip_tier": crm_r["vip_tier"] if crm_r is not None else "普通",
            "lifecycle_customer_manager": crm_r["customer_manager"] if crm_r is not None else "",
            # 风险 (对齐技术方案: M0/M1/M2/M3+逾期 + 最低还款频率 + 套现风险)
            "risk_overdue_status": ol, "risk_history_overdue_count_6m": ovc,
            "risk_min_payment_frequency_6m": mpc, "risk_cash_advance_risk_score": cash_adv_risk,
            "risk_churn_risk_score": churn, "risk_risk_level": risk_lvl,
            "risk_blacklist_flag": bool(cns["blacklist_flag"]) if cns is not None else False,
            "risk_do_not_contact": bool(cns["do_not_contact_signal"]) if cns is not None else False,
            # 价值
            "value_annual_consumption": round(annual,2),
            "value_monthly_avg_consumption": round(monthly,2),
            "value_max_single_transaction": round(max_single,2),
            "value_transaction_count_12m": txn_cnt,
            "value_installment_contribution_12m": round(installment,2),
            "value_value_level": vl,
            # 动态 - 长期(90d)
            "long_term_90d_total_consumption": round(c90,2),
            "long_term_90d_txn_count": t90, "long_term_90d_active_days": ad90,
            "long_term_90d_activity_score": activity,
            "long_term_90d_dormancy_risk": dorm,
            "long_term_90d_significant_signals": sig_str,
            "long_term_90d_monthly_avg_90d": round(c90/3,2),
            # 动态 - 中期(30d)
            "mid_term_30d_total_consumption": round(c30,2),
            "mid_term_30d_txn_count": t30, "mid_term_30d_active_days": ad30,
            "mid_term_30d_consumption_trend": trend,
            "mid_term_30d_trend_change_pct": tpct,
            "mid_term_30d_browse_preferences": browse_str,
            # 动态 - 短期(7d)
            "short_term_7d_total_consumption": round(c7,2),
            "short_term_7d_txn_count": t7, "short_term_7d_active_days": ad7,
            "short_term_7d_top_search_keywords": search_top5,
            "short_term_7d_avg_daily_spend": round(c7/7,2),
            # 实时
            "realtime_signal_count": rt_cnt,
            "realtime_has_high_value_txn": rt_high,
            # 关键事件
            "key_milestones": milestone_str,
            # 元数据
            "generated_at": REF.strftime("%Y-%m-%d %H:%M:%S"),
            "update_type": "T+1_batch_v3",
        }
        rows.append(r)
        if len(rows)%2000==0: print(f"  {len(rows)}/8000")

    df = pd.DataFrame(rows)
    df.to_csv(OUT, index=False, encoding="utf-8-sig")
    return df

if __name__ == "__main__":
    print("="*60)
    print("客户画像 v3 — 全面对齐技术方案")
    print("="*60)
    s = os.path.join(BASE,"mock_data","structured")
    t0 = time.time()
    df = gen_finance(
        pd.read_csv(os.path.join(s,"customer_basic.csv")),
        pd.read_csv(os.path.join(s,"credit_card.csv")),
        pd.read_csv(os.path.join(s,"crm_customer.csv")),
        pd.read_csv(os.path.join(s,"customer_consent.csv")),
        pd.read_csv(os.path.join(s,"product_catalog.csv")),
    )
    print(f"耗时: {time.time()-t0:.1f}s | {len(df)}客户 | {len(df.columns)}字段")

    # 验证
    print(f"\n=== 验证 ===")
    print(f"年消费=0: {(df['value_annual_consumption']==0).sum()}")
    print(f"搜索词为空: {(df['short_term_7d_top_search_keywords']=='').sum()}")
    print(f"浏览偏好为空: {(df['mid_term_30d_browse_preferences']=='').sum()}")
    print(f"关键事件为空: {(df['key_milestones']=='').sum()}")
    print(f"预警信号为空: {(df['long_term_90d_significant_signals']=='').sum()}")
    print(f"已用额度=0: {(df['account_used_amount']==0).sum()}")

    # 抽样
    for cid in ["C000001","C005000"]:
        r = df[df["cust_id"]==cid].iloc[0]
        print(f"\n{cid} ({r['demographics_income_level']}/{r['account_primary_card_level']}):")
        print(f"  年消费=¥{r['value_annual_consumption']:,.0f} 已用额度=¥{r['account_used_amount']:,.0f} 使用率={r['account_usage_rate']:.0%}")
        print(f"  搜索: {r['short_term_7d_top_search_keywords']}")
        print(f"  浏览: {r['mid_term_30d_browse_preferences']}")
        print(f"  里程碑: {r['key_milestones']}")
        print(f"  信号: {r['long_term_90d_significant_signals']}")
    print("\n完成!")
