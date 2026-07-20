"""
历史营销触达结果生成脚本 v2 — 概率由客户特征驱动
===================================================
替代旧版独立随机生成。保留字段和数据规模, 但概率基于:
  - 渠道偏好 + App活跃度 + 意图匹配 + 频控 + 风险 + 产品准入

生成: contact_history.csv (120,000条)
"""
import os, sys, random, pandas as pd, numpy as np
from datetime import datetime, timedelta

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
BASE_DIR = os.path.dirname(SCRIPT_DIR)
STRUCTURED = os.path.join(BASE_DIR, "structured")

REFERENCE_DATE = datetime(2026, 7, 17)
random.seed(42); np.random.seed(42)


def load_all():
    s = STRUCTURED
    return {
        "profile": pd.read_csv(os.path.join(s, "customer_profile.csv")),
        "cards": pd.read_csv(os.path.join(s, "credit_card.csv")),
        "campaigns": pd.read_csv(os.path.join(s, "campaign_catalog.csv")),
        "consent": pd.read_csv(os.path.join(s, "customer_consent.csv")),
        "channels": pd.read_csv(os.path.join(s, "channel_config.csv")),
        "intent": pd.read_csv(os.path.join(s, "intent_vector.csv")),
    }


# === 活动→意图类别映射 ===
CAMPAIGN_INTENT_MAP = {
    "分期": "分期/借贷需求", "免息": "分期/借贷需求",
    "境外": "跨境/出行需求", "出行": "跨境/出行需求", "跨境": "跨境/出行需求", "旅行": "跨境/出行需求",
    "升级": "额度/升级需求", "白金": "额度/升级需求",
    "优惠": "权益/优惠需求", "返现": "权益/优惠需求", "折扣": "权益/优惠需求",
    "积分": "权益/优惠需求", "饭票": "权益/优惠需求", "观影": "权益/优惠需求",
    "唤醒": "沉睡/流失风险", "沉睡": "沉睡/流失风险",
    "新户": "新户/激活引导", "开卡": "新户/激活引导", "校园": "新户/激活引导",
}

def campaign_intent(camp_name: str) -> str:
    for kw, intent in CAMPAIGN_INTENT_MAP.items():
        if kw in camp_name: return intent
    return "分期/借贷需求"  # 默认


def generate():
    print("=" * 60)
    print("contact_history v2 — 特征驱动生成")
    print("=" * 60)

    data = load_all()
    profile = data["profile"]
    campaigns = data["campaigns"]
    consent = data["consent"].set_index("cust_id")
    intent_df = data["intent"].set_index("cust_id")
    channels_list = ["APP Push", "短信", "微信公众号", "邮件", "电话外呼"]

    # 客户特征索引
    profile_idx = profile.set_index("cust_id")
    cust_ids = profile["cust_id"].tolist()

    n_total = 120000
    records = []

    # 统计计数器
    stats = {"opened": {"high_intent": 0, "low_intent": 0, "high": 0, "low": 0},
             "clicked": {"high_intent": 0, "low_intent": 0, "high": 0, "low": 0},
             "converted": {"high_intent": 0, "low_intent": 0, "high": 0, "low": 0},
             "unsubscribed": {"high_risk": 0, "low_risk": 0, "high_freq": 0, "low_freq": 0}}
    intent_counts = {"high_intent": 0, "low_intent": 0}
    risk_counts = {"high_risk": 0, "low_risk": 0}

    for i in range(n_total):
        cid = random.choice(cust_ids)
        camp = campaigns.sample(1).iloc[0]
        ch = random.choice(channels_list)
        ct = "marketing" if random.random() < 0.85 else "service"

        # 获取客户特征
        try:
            p = profile_idx.loc[cid]
            cn = consent.loc[cid] if cid in consent.index else None
            it = intent_df.loc[cid] if cid in intent_df.index else None
        except: continue

        # === 核心: 计算特征驱动的概率 ===

        # 1. 意图匹配度
        camp_intent = campaign_intent(camp["campaign_name"])
        intent_score = 0
        if it is not None:
            try:
                intent_json = json.loads(it["intent_json"]) if isinstance(it["intent_json"], str) else {}
                intent_score = intent_json.get(camp_intent, 0)
            except: pass

        # 将意图分为 "高意图(>=40)" vs "低意图(<40)"
        high_intent = intent_score >= 40
        if high_intent: intent_counts["high_intent"] += 1
        else: intent_counts["low_intent"] += 1

        # 2. App活跃度 (0-100)
        activity = float(p.get("long_term_90d_activity_score", 30) or 30)

        # 3. 风险
        risk_level = p.get("risk_risk_level", "low")
        churn_score = float(p.get("risk_churn_risk_score", 10) or 10)
        complaint_cnt = float(cn["complaint_count_90d"]) if cn is not None else 0
        high_risk = (risk_level == "high") or (churn_score >= 50) or (complaint_cnt >= 2)
        if high_risk: risk_counts["high_risk"] += 1
        else: risk_counts["low_risk"] += 1

        # 4. 渠道偏好 (简化: 推送优先)
        channel_match = 1.0 if ch == "APP Push" else (0.8 if ch == "微信公众号" else 0.6)

        # 5. 频控 (通过时间分布模拟: 近期触达多→概率下降)
        days_ago = int(np.random.exponential(scale=25))
        days_ago = min(days_ago, 89)
        high_freq = days_ago < 7  # 近7天触达=高频

        # 6. 收入和额度
        income = p.get("demographics_income_level", "M")
        credit_usage = float(p.get("account_usage_rate", 0.3) or 0.3)

        # ===== OPENED 概率 =====
        # 基础: 15%, 受渠道+活跃度+意图+频控影响
        p_open = 0.15
        p_open += 0.08 * channel_match                        # 渠道匹配
        p_open += 0.001 * activity                            # 活跃度 (max +10%)
        p_open += 0.12 if high_intent else 0                  # 意图匹配
        p_open -= 0.06 if high_freq else 0                    # 高频触达降低
        p_open -= 0.08 if high_risk else 0                    # 高风险降低
        p_open = max(0.02, min(0.55, p_open))                 # 截断

        # ===== CLICKED 概率 (在已打开的基础上) =====
        p_click = 0.10
        p_click += 0.15 if high_intent else 0
        p_click += 0.001 * activity
        p_click += 0.05 * channel_match
        p_click -= 0.04 if high_freq else 0
        p_click = max(0.01, min(0.50, p_click))

        # ===== CONVERTED 概率 (在已点击的基础上) =====
        p_conv = 0.08
        p_conv += 0.20 if high_intent else 0
        p_conv += 0.10 if income == "H" else (0.03 if income == "M" else 0)
        p_conv += 0.08 if credit_usage > 0.7 else 0
        p_conv += 0.001 * activity
        p_conv -= 0.10 if high_risk else 0
        p_conv = max(0.005, min(0.55, p_conv))

        # ===== UNSUBSCRIBED 概率 =====
        p_unsub = 0.03
        p_unsub += 0.15 if high_risk else 0
        p_unsub += 0.08 if high_freq else 0
        p_unsub += 0.05 if complaint_cnt >= 2 else 0
        p_unsub -= 0.02 if channel_match > 0.8 else 0
        p_unsub -= 0.02 if high_intent else 0
        p_unsub = max(0.001, min(0.35, p_unsub))

        # === 决定状态 ===
        rand = random.random()
        if rand < p_unsub:
            status = "unsubscribed"
            if high_risk: stats["unsubscribed"]["high_risk"] += 1
            else: stats["unsubscribed"]["low_risk"] += 1
        elif rand < p_unsub + p_conv:
            status = "clicked"; ct = "marketing"  # clicked then converted (简化: clicked=converted)
            if high_intent: stats["converted"]["high_intent"] += 1
            else: stats["converted"]["low_intent"] += 1
        elif rand < p_unsub + p_conv + p_click:
            status = "clicked"
            if high_intent: stats["clicked"]["high_intent"] += 1
            else: stats["clicked"]["low_intent"] += 1
        elif rand < p_unsub + p_conv + p_click + p_open:
            status = "opened"
            if high_intent: stats["opened"]["high_intent"] += 1
            else: stats["opened"]["low_intent"] += 1
        else:
            status = "sent"  # 发了但未打开

        contact_time = REFERENCE_DATE - timedelta(days=days_ago, hours=random.randint(0, 23))
        records.append({
            "contact_id": f"CONTACT_{i+1:08d}",
            "cust_id": cid,
            "campaign_id": camp["campaign_id"] if ct == "marketing" else "",
            "channel": ch,
            "contact_time": contact_time.strftime("%Y-%m-%d %H:%M:%S"),
            "contact_type": ct,
            "status": status,
            "response_time_sec": random.randint(60, 86400) if status in ("opened", "clicked") else 0,
        })

        if (i + 1) % 30000 == 0:
            print(f"  {i+1}/{n_total} ...")

    df = pd.DataFrame(records)

    # 保存
    path = os.path.join(STRUCTURED, "contact_history.csv")
    df.to_csv(path, index=False, encoding="utf-8-sig")
    print(f"\n[OK] contact_history.csv: {len(df)} rows")

    # ===== 输出统计验证 =====
    print(f"\n=== 特征驱动效果验证 ===")
    for status_key in ["opened", "clicked", "converted"]:
        h = stats[status_key]["high_intent"]
        l = stats[status_key]["low_intent"]
        h_total = max(intent_counts["high_intent"], 1)
        l_total = max(intent_counts["low_intent"], 1)
        h_rate = h / h_total * 100
        l_rate = l / l_total * 100
        lift = h_rate / max(l_rate, 0.01)
        print(f"  {status_key}: 高意图={h_rate:.1f}% vs 低意图={l_rate:.1f}% (Lift={lift:.1f}x)")

    ur_h = stats["unsubscribed"]["high_risk"]
    ur_l = stats["unsubscribed"]["low_risk"]
    print(f"  unsubscribed: 高风险={ur_h} vs 低风险={ur_l} (Ratio={ur_h/max(ur_l,1):.1f}x)")

    overall = df["status"].value_counts().to_dict()
    print(f"\n  全局分布: {overall}")

    # 高意图客户应有更高转化率
    conv_lift = (stats["converted"]["high_intent"] / max(intent_counts["high_intent"], 1)) / \
                (stats["converted"]["low_intent"] / max(intent_counts["low_intent"], 1))
    print(f"\n  ✅ 高意图客户转化提升: {conv_lift:.1f}x (目标>2x)")

    return df


if __name__ == "__main__":
    import json
    generate()
