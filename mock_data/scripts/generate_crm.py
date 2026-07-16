"""
CRM客户关系数据生成脚本
=========================
生成 mock_data/structured/crm_customer.csv

字段: crm_id, cust_id, lifecycle_stage, customer_manager, vip_tier,
      churn_risk_score, last_contact_date, contact_preference

业务规则:
  - lifecycle_stage 基于开户日期 + 近期是否有交易推算
  - vip_tier 与卡等级和收入等级正相关
  - churn_risk_score 由交易活跃度和投诉历史决定
"""

import random, os, pandas as pd, numpy as np
from datetime import datetime, timedelta
from typing import Dict, Any

from config import *

random.seed(RANDOM_SEED + 2)
np.random.seed(RANDOM_SEED + 2)


def determine_lifecycle(open_date: datetime, has_recent_90d: bool) -> str:
    months = max(0, (REFERENCE_DATE - open_date).days / 30.44)
    if months <= 3:       return "新户"
    elif months <= 12:    return "成长期"
    elif months <= 36:    return "成熟期"
    else:
        return "沉睡期" if not has_recent_90d else "成熟期"


def compute_churn_risk(lifecycle: str, has_complaint: bool, has_recent: bool,
                        income_level: str, card_level: str) -> int:
    """综合计算流失风险评分(0-100)。"""
    score = 0
    if lifecycle == "沉睡期":    score += 40
    elif lifecycle == "新户":    score += 10
    if not has_recent:          score += 25
    if has_complaint:           score += 20
    if income_level == "H" and card_level in ("钻石卡","无限卡"):
        score -= 10  # 高端客户粘性高
    # 加噪声
    score += random.randint(-10, 10)
    return max(0, min(100, score))


def assign_vip_tier(card_level: str, income_level: str) -> str:
    """根据卡等和收入分配VIP等级。"""
    if card_level in ("无限卡","钻石卡"):   return random.choices(["钻石","白金"], weights=[0.7,0.3])[0]
    if card_level == "白金卡":
        if income_level == "H":  return random.choices(["白金","钻石","金卡"], weights=[0.5,0.2,0.3])[0]
        return random.choices(["白金","金卡"], weights=[0.4,0.6])[0]
    if card_level == "金卡":    return random.choices(["金卡","白金","普通"], weights=[0.5,0.15,0.35])[0]
    return random.choices(["普通","金卡"], weights=[0.8,0.2])[0]


# ---- 客户经理姓名池 ----
MANAGERS = ["王建国","李娟","张伟","陈晓燕","刘志强","赵敏","周涛","吴芳",
            "孙磊","钱丽华","郑刚","马晓雯","黄海波","林雪梅","何志明","罗玲"]


def gen_one_crm(cust_id: str, primary_card: Dict, register_dt: datetime) -> Dict[str, Any]:
    """为一个客户生成CRM记录。"""
    # 是否有近90天交易
    has_90d = REFERENCE_DATE - register_dt < timedelta(days=90) or random.random() < 0.75
    stage = determine_lifecycle(register_dt, has_90d)

    # 是否有投诉(5%概率)
    has_complaint = random.random() < 0.05

    card_lvl = primary_card.get("card_level", "金卡")
    inc_lvl  = random.choices(["H","M","L"], weights=[0.15,0.50,0.35])[0]  # 从card关联角度简化

    risk = compute_churn_risk(stage, has_complaint, has_90d, inc_lvl, card_lvl)
    vip  = assign_vip_tier(card_lvl, inc_lvl)

    # 最近联系日期
    if has_90d:
        last_contact = REFERENCE_DATE - timedelta(days=random.randint(1, 60))
    else:
        last_contact = REFERENCE_DATE - timedelta(days=random.randint(90, 365))

    return {
        "crm_id": f"CRM{str(random.randint(1,999999)).zfill(6)}",
        "cust_id": cust_id,
        "lifecycle_stage": stage,
        "customer_manager": random.choice(MANAGERS),
        "vip_tier": vip,
        "churn_risk_score": risk,
        "last_contact_date": last_contact.strftime("%Y-%m-%d"),
        "contact_preference": random.choices(CONTACT_PREFERENCES, weights=CONTACT_PREF_WEIGHTS)[0],
    }


def generate_all_crm(df_customers: pd.DataFrame, df_cards: pd.DataFrame):
    print("=" * 60)
    print("生成 CRM 客户关系数据 ...")
    print("=" * 60)

    # 取每人的主卡
    primary = df_cards[df_cards["is_primary"] == True].set_index("cust_id")
    records = []
    for _, row in df_customers.iterrows():
        cid = row["cust_id"]
        card = primary.loc[cid].to_dict() if cid in primary.index else {"card_level": "金卡"}
        reg  = datetime.strptime(row["register_date"], "%Y-%m-%d")
        records.append(gen_one_crm(cid, card, reg))

    df = pd.DataFrame(records)
    path = os.path.join(STRUCTURED_DIR, "crm_customer.csv")
    df.to_csv(path, index=False, encoding="utf-8-sig")
    print(f"✅ crm_customer.csv : {len(df)} 条")
    print(f"   生命周期: {dict(df['lifecycle_stage'].value_counts())}")
    print(f"   VIP分布:  {dict(df['vip_tier'].value_counts())}")
    print(f"   流失风险均值: {df['churn_risk_score'].mean():.1f}")
    return df


if __name__ == "__main__":
    cp = os.path.join(STRUCTURED_DIR, "customer_basic.csv")
    rp = os.path.join(STRUCTURED_DIR, "credit_card.csv")
    if os.path.exists(cp) and os.path.exists(rp):
        generate_all_crm(pd.read_csv(cp), pd.read_csv(rp))
    else:
        print("⚠️ 请先运行 generate_customers.py")
