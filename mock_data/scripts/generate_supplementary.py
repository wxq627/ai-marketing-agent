"""
补充数据生成脚本（满足项目二 Strategy Agent 数据需求）
=====================================================
生成:
  - customer_consent.csv (重写，扩展字段)
  - contact_history.csv (新建)
  - product_eligibility.csv (新建)
"""
import random, os, pandas as pd
import numpy as np
from datetime import datetime, timedelta
from config import *

random.seed(RANDOM_SEED + 7)
np.random.seed(RANDOM_SEED + 7)

STRUCTURED_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "structured")

# ============================================================
# 1. 重写 customer_consent.csv — 扩展字段
# ============================================================

def generate_customer_consent(df_customers, df_crm):
    """生成扩展版客户授权表，补全项目二所需字段。"""
    records = []
    crm = df_crm.set_index("cust_id")

    for _, row in df_customers.iterrows():
        cid = row["cust_id"]
        # 授权: 95%营销授权
        mkt = random.random() < 0.95
        per = random.random() < 0.80
        share = random.random() < 0.60
        sms = random.random() < 0.85
        phone = random.random() < 0.30
        email = random.random() < 0.70
        push = random.random() < 0.90
        wechat = random.random() < 0.75
        dnc = random.random() < 0.03

        # 退订信息 (约8%的客户退订过某些渠道)
        unsub_channels = []
        if random.random() < 0.04 and sms:    # 4%退订短信
            unsub_channels.append("短信")
            sms = False
        if random.random() < 0.02 and push:    # 2%退订Push
            unsub_channels.append("APP Push")
            push = False
        if random.random() < 0.02 and wechat:  # 2%退订微信
            unsub_channels.append("微信公众号")
            wechat = False

        unsub_at = (REFERENCE_DATE - timedelta(days=random.randint(30,365))).strftime("%Y-%m-%d") if unsub_channels else ""

        # 投诉统计 (约5%有投诉记录)
        complaint_count = 0
        if random.random() < 0.05:
            complaint_count = random.randint(1, 3) if random.random() < 0.7 else random.randint(4, 8)
        do_not_contact = (complaint_count >= 3) or dnc

        # 风险等级 (结合CRM数据)
        risk_score = crm.loc[cid]["churn_risk_score"] if cid in crm.index else 0
        if risk_score >= 70 or complaint_count >= 3 or dnc:
            risk_level = "high"
        elif risk_score >= 40:
            risk_level = "medium"
        else:
            risk_level = "low"
        blacklist = dnc or risk_score >= 85

        # 价值等级 (基于收入+卡等级推断)
        inc = row["income_level"]
        vip = crm.loc[cid]["vip_tier"] if cid in crm.index else "普通"
        if inc == "H" or vip in ("钻石", "白金"):
            value_level = "high"
        elif inc == "M" or vip == "金卡":
            value_level = "medium"
        else:
            value_level = "low"

        records.append({
            "cust_id": cid,
            "marketing_consent": mkt,
            "personalization_consent": per,
            "data_sharing_consent": share,
            "sms_consent": sms,
            "phone_consent": phone,
            "email_consent": email,
            "push_consent": push,
            "wechat_consent": wechat,
            "consent_updated_at": (REFERENCE_DATE - timedelta(days=random.randint(0,365))).strftime("%Y-%m-%d"),
            "dnc_list": dnc,
            "unsubscribe_channels": ",".join(unsub_channels) if unsub_channels else "",
            "unsubscribe_at": unsub_at,
            "complaint_count_90d": complaint_count if random.random() < 0.3 else 0,
            "do_not_contact_signal": do_not_contact,
            "risk_level": risk_level,
            "blacklist_flag": blacklist,
            "value_level": value_level,
        })

    df = pd.DataFrame(records)
    path = os.path.join(STRUCTURED_DIR, "customer_consent.csv")
    df.to_csv(path, index=False, encoding="utf-8-sig")
    print(f"[OK] customer_consent.csv: {len(df)} rows, {len(df.columns)} cols")
    stats = {
        "marketing_consent": df["marketing_consent"].mean(),
        "dnc": df["dnc_list"].mean(),
        "do_not_contact": df["do_not_contact_signal"].mean(),
        "risk_low/med/high": f"{ (df['risk_level']=='low').sum() }/{ (df['risk_level']=='medium').sum() }/{ (df['risk_level']=='high').sum() }",
        "value_low/med/high": f"{ (df['value_level']=='low').sum() }/{ (df['value_level']=='medium').sum() }/{ (df['value_level']=='high').sum() }",
    }
    for k, v in stats.items():
        print(f"   {k}: {v}")
    return df


# ============================================================
# 2. 新建 contact_history.csv — 触达历史
# ============================================================

def generate_contact_history(df_customers, df_campaigns, n_total=120000):
    """生成近90天营销触达历史记录。"""
    campaigns = df_campaigns[df_campaigns["campaign_id"].str.startswith("CAMP_")]
    channels = ["APP Push", "短信", "微信公众号", "邮件", "掌上生活APP内消息", "电话外呼"]
    types = ["marketing", "service", "transactional"]
    statuses = ["sent", "delivered", "opened", "clicked", "bounced", "unsubscribed"]
    status_weights = [0.02, 0.10, 0.45, 0.25, 0.08, 0.10]
    cust_ids = df_customers["cust_id"].tolist()

    records = []
    for i in range(n_total):
        cid = random.choice(cust_ids)
        camp = campaigns.sample(1).iloc[0]
        ch = random.choice(channels)
        ct = "marketing" if random.random() < 0.85 else random.choice(["service", "transactional"])
        st = random.choices(statuses, weights=status_weights, k=1)[0]

        # 时间: 近90天内
        days_ago = int(np.random.exponential(scale=25))
        days_ago = min(days_ago, 89)
        contact_time = REFERENCE_DATE - timedelta(days=days_ago, hours=random.randint(0,23), minutes=random.randint(0,59))

        records.append({
            "contact_id": f"CONTACT_{i+1:08d}",
            "cust_id": cid,
            "campaign_id": camp["campaign_id"] if ct == "marketing" else "",
            "channel": ch,
            "contact_time": contact_time.strftime("%Y-%m-%d %H:%M:%S"),
            "contact_type": ct,
            "status": st,
            "response_time_sec": random.randint(60, 86400) if st in ("opened", "clicked") else 0,
        })

    df = pd.DataFrame(records)
    path = os.path.join(STRUCTURED_DIR, "contact_history.csv")
    df.to_csv(path, index=False, encoding="utf-8-sig")
    print(f"\n[OK] contact_history.csv: {len(df)} rows, {len(df.columns)} cols")
    print(f"   Date range: {df['contact_time'].min()} ~ {df['contact_time'].max()}")
    print(f"   Channels: {dict(df['channel'].value_counts())}")
    print(f"   Status: {dict(df['status'].value_counts())}")
    return df


# ============================================================
# 3. 新建 product_eligibility.csv — 产品办理资格
# ============================================================

ELIGIBILITY_RULES = [
    {"product_id": "PROD_STANDARD_N", "required_income": "L,M,H", "min_age": 21, "max_age": 65,
     "required_card_level": "-", "min_credit": 0, "special_conditions": "无"},
    {"product_id": "PROD_HELLOKITTY_N", "required_income": "L,M,H", "min_age": 18, "max_age": 60,
     "required_card_level": "-", "min_credit": 0, "special_conditions": "限女性申请(男性可办理附属卡)"},
    {"product_id": "PROD_YOUNG_CAMPUS", "required_income": "L", "min_age": 18, "max_age": 28,
     "required_card_level": "-", "min_credit": 0, "special_conditions": "需提供在校学生证明(学信网验证)"},
    {"product_id": "PROD_STANDARD_G", "required_income": "L,M,H", "min_age": 21, "max_age": 65,
     "required_card_level": "普卡及以上", "min_credit": 10000, "special_conditions": "已有普卡客户可直接升级"},
    {"product_id": "PROD_YOUNG_G", "required_income": "L,M,H", "min_age": 21, "max_age": 30,
     "required_card_level": "-", "min_credit": 5000, "special_conditions": "限30周岁(含)以下非学生客户申请"},
    {"product_id": "PROD_JD_G", "required_income": "L,M,H", "min_age": 21, "max_age": 60,
     "required_card_level": "-", "min_credit": 5000, "special_conditions": "京东PLUS会员可享额外权益加成"},
    {"product_id": "PROD_CTRIP_G", "required_income": "M,H", "min_age": 21, "max_age": 60,
     "required_card_level": "-", "min_credit": 10000, "special_conditions": "近6个月有出行记录的客户优先审批"},
    {"product_id": "PROD_CLASSIC_W", "required_income": "M,H", "min_age": 25, "max_age": 60,
     "required_card_level": "金卡及以上", "min_credit": 50000, "special_conditions": "需年消费满8万元或10000永久积分兑换年费; 2025年4月起暂停新户申请"},
    {"product_id": "PROD_FREELIFE_W", "required_income": "M,H", "min_age": 23, "max_age": 55,
     "required_card_level": "-", "min_credit": 30000, "special_conditions": "首年免年费，适合白金入门"},
    {"product_id": "PROD_UNIONPAY_W", "required_income": "M,H", "min_age": 23, "max_age": 60,
     "required_card_level": "-", "min_credit": 30000, "special_conditions": "需年消费满5万元免次年年费"},
    {"product_id": "PROD_GLOBAL_W", "required_income": "M,H", "min_age": 23, "max_age": 60,
     "required_card_level": "-", "min_credit": 30000, "special_conditions": "有效期内免年费; 适合有境外消费需求的客户"},
    {"product_id": "PROD_REFINED_W", "required_income": "M,H", "min_age": 23, "max_age": 55,
     "required_card_level": "-", "min_credit": 30000, "special_conditions": "新户达标赠饮品券(星巴克/喜茶/奈雪三选一)"},
    {"product_id": "PROD_CENTURION_W", "required_income": "H", "min_age": 28, "max_age": 60,
     "required_card_level": "金卡及以上", "min_credit": 80000, "special_conditions": "刚性年费3600元; 需邀请或满足高净值条件"},
    {"product_id": "PROD_DIAMOND", "required_income": "H", "min_age": 30, "max_age": 60,
     "required_card_level": "白金卡及以上", "min_credit": 100000, "special_conditions": "刚性年费3600元; 亲子家庭优先(含儿童机票权益)"},
    {"product_id": "PROD_WORLD", "required_income": "H", "min_age": 30, "max_age": 60,
     "required_card_level": "白金卡及以上", "min_credit": 200000, "special_conditions": "刚性年费3600元; 邀请制，需私行或高净值客户"},
]

def generate_product_eligibility():
    """生成产品办理资格表。"""
    df = pd.DataFrame(ELIGIBILITY_RULES)
    path = os.path.join(STRUCTURED_DIR, "product_eligibility.csv")
    df.to_csv(path, index=False, encoding="utf-8-sig")
    print(f"\n[OK] product_eligibility.csv: {len(df)} rows, {len(df.columns)} cols")
    return df


# ============================================================
# 主入口
# ============================================================

if __name__ == "__main__":
    print("=" * 60)
    print("生成项目二所需补充数据")
    print("=" * 60)

    # 读依赖数据
    df_cust = pd.read_csv(os.path.join(STRUCTURED_DIR, "customer_basic.csv"))
    df_crm = pd.read_csv(os.path.join(STRUCTURED_DIR, "crm_customer.csv"))
    df_camp = pd.read_csv(os.path.join(STRUCTURED_DIR, "campaign_catalog.csv"))

    # 1. 扩展客户授权表
    generate_customer_consent(df_cust, df_crm)

    # 2. 触达历史表
    generate_contact_history(df_cust, df_camp, 120000)

    # 3. 产品资格表
    generate_product_eligibility()

    print("\n" + "=" * 60)
    print("完成!")
    print("=" * 60)
