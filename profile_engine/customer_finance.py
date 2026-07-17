"""
客户金融指标生成器
===================
绕过 card_no 脱敏碰撞问题, 基于客户属性(收入/卡等级/生命周期)直接生成
与业务逻辑一致的金融指标。

生成逻辑:
  年消费 = 月收入 × 消费收入比 × 12 × 随机波动(0.5~1.5)
  月均消费 = 年消费 / 12
  单笔最高 与卡等级正相关
  分期贡献 ≈ 年消费 × 5%~15%
  逾期次数 与风险等级正相关
  活跃度评分 与生命周期 + 消费频率正相关
"""

import pandas as pd, numpy as np, os, random

random.seed(42)
np.random.seed(42)

def generate_finance_metrics():
    """为每个客户生成一致的金融指标。"""
    BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    s = os.path.join(BASE, "mock_data", "structured")

    cust = pd.read_csv(os.path.join(s, "customer_basic.csv"))
    cards = pd.read_csv(os.path.join(s, "credit_card.csv"))
    crm = pd.read_csv(os.path.join(s, "crm_customer.csv"))
    consent = pd.read_csv(os.path.join(s, "customer_consent.csv"))
    bills = pd.read_csv(os.path.join(s, "bill_record.csv"))

    # 收入→月收入映射
    income_monthly = {"H": 60000, "M": 18000, "L": 6000}

    # 卡等级→消费乘数
    card_mult = {"无限卡": 3.0, "钻石卡": 2.5, "白金卡": 1.8, "金卡": 1.2, "普卡": 0.8, "校园卡": 0.3}

    # 生命周期→活跃乘数
    lifecycle_mult = {"新户": 1.2, "成长期": 1.3, "成熟期": 1.0, "沉睡期": 0.2}

    # 每客户主卡等级
    primary = cards[cards["is_primary"] == True].set_index("cust_id")
    crm_idx = crm.set_index("cust_id")
    consent_idx = consent.set_index("cust_id")

    rows = []
    for _, row in cust.iterrows():
        cid = row["cust_id"]
        inc = row["income_level"]
        monthly_inc = income_monthly.get(inc, 10000)

        # 主卡等级
        card_lvl = primary.loc[cid, "card_level"] if cid in primary.index else "金卡"
        cm = card_mult.get(card_lvl, 1.0)

        # 生命周期
        lfs = crm_idx.loc[cid, "lifecycle_stage"] if cid in crm_idx.index else "成熟期"
        lm = lifecycle_mult.get(lfs, 1.0)

        # 收入用于消费的比例 (20%~70%)
        spend_ratio = np.random.triangular(0.20, 0.40, 0.70)

        # === VALUE ===
        annual_consumption = monthly_inc * spend_ratio * 12 * cm * lm * np.random.uniform(0.6, 1.4)
        monthly_avg = annual_consumption / 12
        max_single = annual_consumption * np.random.uniform(0.05, 0.30)
        txn_count = int(annual_consumption / np.random.uniform(200, 1500))
        installment = annual_consumption * np.random.uniform(0.05, 0.15)

        # === RISK ===
        risk_lvl = consent_idx.loc[cid, "risk_level"] if cid in consent_idx.index else "low"
        churn = crm_idx.loc[cid, "churn_risk_score"] if cid in crm_idx.index else 0

        if risk_lvl == "high" or churn > 50:
            overdue_count = np.random.choice([0,1,2,3], p=[0.3, 0.3, 0.25, 0.15])
            minpay_count = np.random.choice([0,1,2,3,4], p=[0.4, 0.3, 0.15, 0.1, 0.05])
        elif risk_lvl == "medium":
            overdue_count = np.random.choice([0,1,2], p=[0.6, 0.3, 0.1])
            minpay_count = np.random.choice([0,1,2], p=[0.6, 0.3, 0.1])
        else:
            overdue_count = np.random.choice([0,1], p=[0.9, 0.1])
            minpay_count = np.random.choice([0,1], p=[0.85, 0.15])

        if overdue_count >= 3: ol = "M3+"
        elif overdue_count >= 2: ol = "M2"
        elif overdue_count >= 1: ol = "M1"
        else: ol = "M0"

        # === DYNAMIC MEMORY ===
        # 90天窗口
        cons_90d = annual_consumption * 0.25 * lm * np.random.uniform(0.6, 1.4)
        txn_90d = int(txn_count * 0.25 * lm)
        active_days_90d = int(min(txn_90d * 0.6, 90))

        # 活跃度评分
        day_score = min(active_days_90d / 90 * 40, 40)
        count_score = min(txn_90d / 100 * 30, 30)
        amount_score = min(cons_90d / 50000 * 30, 30)
        activity = int(day_score + count_score + amount_score)

        if activity < 20: dormancy = "high"
        elif activity < 50: dormancy = "medium"
        else: dormancy = "low"

        # 30天窗口 + 趋势
        cons_30d = cons_90d * 0.35 * np.random.uniform(0.7, 1.3)
        txn_30d = int(txn_90d * 0.35)
        active_30d = int(active_days_90d * 0.35)
        prev_30d = cons_30d * np.random.uniform(0.8, 1.2)
        if prev_30d > 0:
            trend_pct = (cons_30d - prev_30d) / prev_30d * 100
        else:
            trend_pct = 0
        if trend_pct > 15: trend = "up"
        elif trend_pct < -20: trend = "down"
        else: trend = "stable"

        # 降级信号
        signals = []
        if trend == "down" and abs(trend_pct) > 30:
            signals.append("消费降级")
        if activity < 30:
            signals.append("活跃度骤降")
        if dormancy == "high":
            signals.append("沉睡预警")

        # 7天窗口
        cons_7d = cons_30d * 0.25 * np.random.uniform(0.7, 1.3)
        txn_7d = int(txn_30d * 0.25)
        active_7d = int(active_30d * 0.25)

        # === 实时信号 (模拟) ===
        realtime_count = np.random.choice([0,0,0,0,1,1,2], p=[0.5,0.15,0.1,0.1,0.08,0.05,0.02])
        has_high = np.random.random() < 0.05

        rows.append({
            "cust_id": cid,
            # Value
            "value_annual_consumption": round(annual_consumption, 2),
            "value_monthly_avg_consumption": round(monthly_avg, 2),
            "value_max_single_transaction": round(max_single, 2),
            "value_transaction_count_12m": txn_count,
            "value_installment_contribution_12m": round(installment, 2),
            # Risk
            "risk_overdue_status": ol,
            "risk_history_overdue_count_6m": overdue_count,
            "risk_min_payment_frequency_6m": minpay_count,
            # Dynamic - 90d
            "long_term_90d_total_consumption": round(cons_90d, 2),
            "long_term_90d_txn_count": txn_90d,
            "long_term_90d_max_single": round(max_single * 0.25, 2),
            "long_term_90d_active_days": active_days_90d,
            "long_term_90d_activity_score": activity,
            "long_term_90d_dormancy_risk": dormancy,
            "long_term_90d_significant_signals": ",".join(signals) if signals else "",
            "long_term_90d_monthly_avg_90d": round(cons_90d / 3, 2),
            # Dynamic - 30d
            "mid_term_30d_total_consumption": round(cons_30d, 2),
            "mid_term_30d_txn_count": txn_30d,
            "mid_term_30d_max_single": round(max_single * 0.10, 2),
            "mid_term_30d_active_days": active_30d,
            "mid_term_30d_consumption_trend": trend,
            "mid_term_30d_trend_change_pct": round(trend_pct, 1),
            # Dynamic - 7d
            "short_term_7d_total_consumption": round(cons_7d, 2),
            "short_term_7d_txn_count": txn_7d,
            "short_term_7d_active_days": active_7d,
            "short_term_7d_avg_daily_spend": round(cons_7d / 7, 2),
            # Real-time
            "realtime_signal_count": realtime_count,
            "realtime_has_high_value_txn": has_high,
        })

    df = pd.DataFrame(rows)
    # 保存
    out = os.path.join(s, "customer_finance.csv")
    df.to_csv(out, index=False, encoding="utf-8-sig")
    print(f"Generated {len(df)} customer finance records -> {out}")

    # 统计
    print(f"\nValue stats:")
    print(f"  Annual consumption: mean={df['value_annual_consumption'].mean():,.0f}, median={df['value_annual_consumption'].median():,.0f}")
    print(f"  Zero consumption: {(df['value_annual_consumption']==0).sum()}")
    print(f"Dynamic stats:")
    print(f"  Mean activity score: {df['long_term_90d_activity_score'].mean():.0f}/100")
    print(f"  Dormancy: {dict(df['long_term_90d_dormancy_risk'].value_counts())}")
    return df

if __name__ == "__main__":
    generate_finance_metrics()
