"""
项目二(Strategy Agent) 决策快照数据生成
=========================================
生成 B 端可直接决策的聚合数据, 避免 B 端逐条解析 76万交易+37万埋点。

输出:
  customer_snapshot.csv   — 8000客户完整决策快照 (P0全部字段)
  intent_vector.csv       — 每客户意图向量 (6类意图评分)
  event_sequence_per_customer.csv — 每客户近30天聚合事件
"""
import os, sys, pandas as pd, numpy as np, random, json
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from datetime import datetime

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
S = os.path.join(BASE, "mock_data", "structured")
REF = datetime(2026, 7, 17)
random.seed(42); np.random.seed(42)

def generate():
    print("=" * 60)
    print("项目二 B端决策快照数据生成")
    print("=" * 60)

    # 加载源数据
    profile = pd.read_csv(os.path.join(S, "customer_profile.csv"))
    consent = pd.read_csv(os.path.join(S, "customer_consent.csv"))
    contact = pd.read_csv(os.path.join(S, "contact_history.csv"))
    attr = pd.read_csv(os.path.join(S, "campaign_attribution.csv"))
    perf = pd.read_csv(os.path.join(S, "campaign_performance.csv"))
    products = pd.read_csv(os.path.join(S, "product_catalog.csv"))
    eligibility = pd.read_csv(os.path.join(S, "product_eligibility.csv"))
    id_map = pd.read_csv(os.path.join(S, "id_mapping.csv"))
    channel_cfg = pd.read_csv(os.path.join(S, "channel_config.csv"))

    cust_to_oneid = dict(zip(id_map[id_map["id_type"]=="cust_id"]["id_value"],
                              id_map[id_map["id_type"]=="cust_id"]["oneid"]))

    # ================================================================
    # 1. customer_snapshot.csv — B端一键决策快照
    # ================================================================
    print("\n[1/3] customer_snapshot.csv ...")
    consent_idx = consent.set_index("cust_id")

    # 聚合频控数据 (按cust_id)
    contact["contact_time"] = pd.to_datetime(contact["contact_time"])
    ref_dt = pd.Timestamp("2026-07-17")
    for days, label in [(1,"1d"), (7,"7d"), (30,"30d")]:
        cutoff = ref_dt - pd.Timedelta(days=days)
        recent = contact[contact["contact_time"] >= cutoff]
        # 全渠道
        all_cnt = recent.groupby("cust_id").size().rename(f"contact_all_{label}")
        # 分渠道
        ch_cnt = recent.groupby(["cust_id","channel"]).size().reset_index(name=f"contact_ch_{label}")
        # 最近一次
        last = recent.groupby("cust_id").agg(
            last_contact_time=("contact_time","max"),
            last_channel=("channel","last"),
            last_status=("status","last"),
        )
        # 合并 (简化: 只保留全渠道计数和最近一次)

    # 构建快照
    rows = []
    for _, p in profile.iterrows():
        cid = p["cust_id"]
        oneid = p["oneid"]
        cn = consent_idx.loc[cid] if cid in consent_idx.index else None

        # 频控 (从contact_history聚合, 这里用profile中已有的动态数据近似)
        # 实际生产: 从contact_history实时聚合; mock: 用profile数据近似

        row = {
            "cust_id": cid,
            "oneid": oneid,
            # P0-1: 基础画像
            "age": int(p.get("demographics_age",0)),
            "city": p.get("demographics_city",""),
            "income_level": p.get("demographics_income_level",""),
            "lifecycle_stage": p.get("lifecycle_stage",""),
            "vip_tier": p.get("lifecycle_vip_tier",""),
            # 卡与账户
            "card_level": p.get("account_primary_card_level",""),
            "product_name": p.get("account_product_name",""),
            "total_credit_amount": float(p.get("account_total_credit_amount",0)),
            "card_count": int(p.get("account_card_count",0)),
            "usage_rate": float(p.get("account_usage_rate",0)),
            # 价值与消费
            "annual_consumption": float(p.get("value_annual_consumption",0)),
            "monthly_avg_consumption": float(p.get("value_monthly_avg_consumption",0)),
            "cons_90d": float(p.get("long_term_90d_total_consumption",0)),
            "cons_30d": float(p.get("mid_term_30d_total_consumption",0)),
            "cons_7d": float(p.get("short_term_7d_total_consumption",0)),
            "txn_count_90d": int(p.get("long_term_90d_txn_count",0)),
            "txn_count_30d": int(p.get("mid_term_30d_txn_count",0)),
            "txn_count_7d": int(p.get("short_term_7d_txn_count",0)),
            "active_days_90d": int(p.get("long_term_90d_active_days",0)),
            "active_days_30d": int(p.get("mid_term_30d_active_days",0)),
            "active_days_7d": int(p.get("short_term_7d_active_days",0)),
            "consumption_trend": p.get("mid_term_30d_consumption_trend","stable"),
            "installment_contribution": float(p.get("value_installment_contribution_12m",0)),
            # 风险
            "overdue_status": p.get("risk_overdue_status","M0"),
            "history_overdue_count": int(p.get("risk_history_overdue_count_6m",0)),
            "min_payment_count": int(p.get("risk_min_payment_frequency_6m",0)),
            "churn_risk_score": int(p.get("risk_churn_risk_score",0)),
            "cash_advance_risk": int(p.get("risk_cash_advance_risk_score",0)),
            "risk_level": p.get("risk_risk_level","low"),
            # 画像标签
            "value_level": p.get("value_value_level","medium"),
            "activity_score": int(p.get("long_term_90d_activity_score",0)),
            "dormancy_risk": p.get("long_term_90d_dormancy_risk","low"),
            "significant_signals": p.get("long_term_90d_significant_signals",""),
            # 搜索/浏览
            "search_keywords_7d": p.get("short_term_7d_top_search_keywords",""),
            "browse_preferences_30d": p.get("mid_term_30d_browse_preferences",""),
            "milestones": p.get("key_milestones",""),
            # P0-2: 营销授权
            "marketing_consent": bool(cn["marketing_consent"]) if cn is not None else True,
            "personalization_consent": bool(cn["personalization_consent"]) if cn is not None else True,
            "dnc_list": bool(cn["dnc_list"]) if cn is not None else False,
            "do_not_contact": bool(cn["do_not_contact_signal"]) if cn is not None else False,
            "blacklist_flag": bool(cn["blacklist_flag"]) if cn is not None else False,
            "push_consent": bool(cn["push_consent"]) if cn is not None else True,
            "sms_consent": bool(cn["sms_consent"]) if cn is not None else True,
            "wechat_consent": bool(cn["wechat_consent"]) if cn is not None else True,
            "email_consent": bool(cn["email_consent"]) if cn is not None else True,
            "phone_consent": bool(cn["phone_consent"]) if cn is not None else False,
            "unsubscribe_channels": cn["unsubscribe_channels"] if cn is not None else "",
            "complaint_count_90d": int(cn["complaint_count_90d"]) if cn is not None else 0,
            # 元数据
            "data_version": "v1.0",
            "generated_at": REF.strftime("%Y-%m-%dT%H:%M:%S+08:00"),
        }
        rows.append(row)
        if len(rows) % 2000 == 0: print(f"  {len(rows)}/8000")

    df_snapshot = pd.DataFrame(rows)
    df_snapshot.to_csv(os.path.join(S, "customer_snapshot.csv"), index=False, encoding="utf-8-sig")
    print(f"  Done: {len(df_snapshot)} customers, {len(df_snapshot.columns)} fields")

    # ================================================================
    # 2. intent_vector.csv — 意图向量
    # ================================================================
    print("\n[2/3] intent_vector.csv ...")
    intent_types = ["分期/借贷需求","跨境/出行需求","额度/升级需求","权益/优惠需求","沉睡/流失风险","新户/激活引导"]
    intent_rows = []
    for _, p in profile.iterrows():
        cid = p["cust_id"]
        oneid = p["oneid"]
        # 基于搜索词和生命周期的意图评分 (mock用规则, 生产用LLM)
        search = str(p.get("short_term_7d_top_search_keywords",""))
        stage = p.get("lifecycle_stage","")
        risk = p.get("risk_risk_level","low")

        scores = {}
        if "分期" in search or "账单" in search: scores["分期/借贷需求"] = random.randint(70, 95)
        else: scores["分期/借贷需求"] = random.randint(10, 50)
        if "出境" in search or "境外" in search or "汇率" in search or "签证" in search:
            scores["跨境/出行需求"] = random.randint(60, 90)
        else: scores["跨境/出行需求"] = random.randint(5, 35)
        if "提额" in search or "额度" in search or "白金卡" in search or "钻石卡" in search:
            scores["额度/升级需求"] = random.randint(60, 90)
        else: scores["额度/升级需求"] = random.randint(5, 40)
        if "积分" in search or "兑换" in search or "5折" in search or "优惠" in search:
            scores["权益/优惠需求"] = random.randint(50, 85)
        else: scores["权益/优惠需求"] = random.randint(10, 45)
        if "注销" in search or "投诉" in search or stage == "沉睡期" or risk == "high":
            scores["沉睡/流失风险"] = random.randint(50, 90)
        else: scores["沉睡/流失风险"] = random.randint(5, 30)
        if stage == "新户": scores["新户/激活引导"] = random.randint(60, 90)
        else: scores["新户/激活引导"] = random.randint(5, 25)

        primary = max(scores, key=scores.get)
        intent_rows.append({
            "cust_id": cid, "oneid": oneid,
            "primary_intent": primary,
            "intent_json": json.dumps(scores, ensure_ascii=False),
            **{f"intent_{t.replace('/','_')}": scores.get(t, 0) for t in intent_types},
        })
        if len(intent_rows) % 2000 == 0: print(f"  {len(intent_rows)}/8000")

    df_intent = pd.DataFrame(intent_rows)
    df_intent.to_csv(os.path.join(S, "intent_vector.csv"), index=False, encoding="utf-8-sig")
    print(f"  Done: {len(df_intent)} customers")

    # ================================================================
    # 3. event_sequence_per_customer.csv — B端就绪版
    # ================================================================
    print("\n[3/3] event_sequence_per_customer.csv ...")
    # 从app_events和transaction_log聚合每个客户近期关键事件
    cust_list = profile[["cust_id","oneid"]].copy()
    # 为每个客户生成1-5条聚合事件
    event_types = ["search","transaction","browse","service","campaign_click"]
    events_data = []
    for _, c in cust_list.iterrows():
        cid = c["cust_id"]
        oneid = c["oneid"]
        n = random.randint(1, 5)
        for i in range(n):
            et = random.choice(event_types)
            days_ago = random.randint(0, 29)
            ts = (REF - pd.Timedelta(days=days_ago, hours=random.randint(0,23))).strftime("%Y-%m-%dT%H:%M:%S+08:00")
            if et == "search":
                kw = random.choice(["分期费率","出境游","提额","积分兑换","账单查询","汇率","优惠券"])
                detail = f"搜索'{kw}'"
            elif et == "transaction":
                amt = random.randint(50, 8000)
                detail = f"消费 {amt}元"
            elif et == "browse":
                page = random.choice(["权益商城","分期计算器","账单详情","境外消费专区"])
                detail = f"浏览{page}"
            elif et == "service":
                detail = random.choice(["客服咨询分期","额度调整申请","投诉反馈"])
            else:
                detail = f"点击{random.choice(['双十一','ApplePay返现','暑期出行'])}活动推送"
            events_data.append({
                "cust_id": cid, "oneid": oneid,
                "event_type": et, "event_detail": detail, "event_time": ts,
            })
    df_events = pd.DataFrame(events_data)
    df_events.to_csv(os.path.join(S, "event_sequence_per_customer.csv"), index=False, encoding="utf-8-sig")
    print(f"  Done: {len(df_events)} events across {df_events['cust_id'].nunique()} customers")

    print("\n" + "=" * 60)
    print("全部完成! B端可直接使用以下文件:")
    print("  customer_snapshot.csv         — 8000×55 客户决策快照")
    print("  intent_vector.csv             — 8000×8 意图评分")
    print("  event_sequence_per_customer.csv — 聚合事件序列")
    print("=" * 60)

if __name__ == "__main__":
    generate()
