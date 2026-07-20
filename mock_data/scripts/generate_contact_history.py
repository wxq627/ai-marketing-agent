"""
历史营销触达结果生成脚本 v3 — 渠道策略优化
============================================
按项目二要求:
  一、合规规则过滤可用渠道 (consent + unsubscribed)
  二、contact_preference 作为客户既有属性 (从profile读取)
  三、80%倾向投放 + 20%随机探索
  四、渠道真正影响打开/点击/转化/退订概率
  五、保存 assigned_channel / assignment_probability / assignment_policy
  六、支持后续渠道模型训练

生成: contact_history.csv (120,000条) + campaign_attribution.csv
"""
import os, sys, random, pandas as pd, numpy as np, json
from datetime import datetime, timedelta

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
BASE_DIR = os.path.dirname(SCRIPT_DIR)
STRUCTURED = os.path.join(BASE_DIR, "structured")

REFERENCE_DATE = datetime(2026, 7, 17)
random.seed(42); np.random.seed(42)
POLICY_VERSION = "v3_feature_driven_20260720"

def clamp(v, lo=0.0, hi=0.95):
    return min(max(v, lo), hi)

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

CAMPAIGN_INTENT_MAP = {
    "分期":"分期/借贷需求","免息":"分期/借贷需求",
    "境外":"跨境/出行需求","出行":"跨境/出行需求","跨境":"跨境/出行需求","旅行":"跨境/出行需求",
    "升级":"额度/升级需求","白金":"额度/升级需求",
    "优惠":"权益/优惠需求","返现":"权益/优惠需求","折扣":"权益/优惠需求",
    "积分":"权益/优惠需求","饭票":"权益/优惠需求","观影":"权益/优惠需求",
    "唤醒":"沉睡/流失风险","沉睡":"沉睡/流失风险",
    "新户":"新户/激活引导","开卡":"新户/激活引导","校园":"新户/激活引导",
}
def campaign_intent(name):
    for kw, intent in CAMPAIGN_INTENT_MAP.items():
        if kw in name: return intent
    return "分期/借贷需求"

ALL_CHANNELS = ["APP Push", "短信", "微信公众号", "邮件", "电话外呼"]

def get_eligible_channels(consent_row, profile_row):
    """一、合规规则: 根据授权+退订+勿扰 筛选可用渠道"""
    if consent_row is None:
        return ALL_CHANNELS.copy()

    eligible = []
    push_ok  = bool(consent_row.get("push_consent", True))
    sms_ok   = bool(consent_row.get("sms_consent", True))
    wechat_ok = bool(consent_row.get("wechat_consent", True))
    email_ok = bool(consent_row.get("email_consent", True))
    do_not = bool(profile_row.get("risk_do_not_contact", False))
    blacklist = bool(profile_row.get("risk_blacklist_flag", False))

    if do_not or blacklist:
        return []  # 黑名单/勿扰, 无可用渠道

    if push_ok:   eligible.append("APP Push")
    if sms_ok:    eligible.append("短信")
    if wechat_ok: eligible.append("微信公众号")
    if email_ok:  eligible.append("邮件")
    # 电话外呼: 仅非黑名单且非高风险
    risk = str(profile_row.get("risk_risk_level","low"))
    if risk != "high":
        eligible.append("电话外呼")
    return eligible

def choose_channel(customer, eligible_channels):
    """三、80%倾向投放 + 20%随机探索"""
    if not eligible_channels:
        return None, 0.0, "no_eligible_channel"

    pref = str(customer.get("contact_preference", ""))
    app_active = float(customer.get("long_term_90d_active_days", 10) or 10)

    base_weights = {c: 0.25 for c in eligible_channels}
    normalized = {c: 1.0 / len(eligible_channels) for c in eligible_channels}

    # 高活跃→APP Push+
    if app_active > 20 and "APP Push" in normalized:
        normalized["APP Push"] += 0.20
    elif app_active > 10 and "APP Push" in normalized:
        normalized["APP Push"] += 0.10

    # 偏好渠道+
    if pref in normalized:
        normalized[pref] += 0.20

    # 20%随机探索
    if random.random() < 0.20:
        channel = random.choice(eligible_channels)
        prob = 1.0 / len(eligible_channels)
        policy = "exploration"
    else:
        channels = list(normalized.keys())
        w = [normalized[c] for c in channels]
        total = sum(w)
        channel = random.choices(channels, weights=w, k=1)[0]
        prob = normalized[channel] / total
        policy = "exploitation"

    return channel, prob, policy


def generate():
    print("=" * 60)
    print("contact_history v3 — 渠道策略优化 (项目二要求)")
    print("=" * 60)

    data = load_all()
    profile = data["profile"]
    campaigns = data["campaigns"]
    consent = data["consent"].set_index("cust_id")
    intent_df = data["intent"].set_index("cust_id")
    ch_df = data["channels"]
    channel_cost = dict(zip(ch_df["channel_name"], ch_df["cost_per_send"]))

    profile_idx = profile.set_index("cust_id")
    cust_ids = profile["cust_id"].tolist()

    n_total = 120000
    records = []
    attributions = []

    empty_ch = {"APP Push":0,"短信":0,"微信公众号":0,"邮件":0,"电话外呼":0}
    stats = {"opened": empty_ch.copy(), "clicked": empty_ch.copy(),
             "converted": empty_ch.copy(), "sent": empty_ch.copy(),
             "total": empty_ch.copy(),
             "policy": {"exploitation":0, "exploration":0},
             "high_active_push": {"open":0,"click":0,"conv":0,"total":0},
             "pref_match": {"open":0,"click":0,"conv":0,"total":0},
             }

    for i in range(n_total):
        cid = random.choice(cust_ids)
        camp = campaigns.sample(1).iloc[0]
        ct_contact = "marketing" if random.random() < 0.85 else "service"

        try:
            p = profile_idx.loc[cid]
            cn = consent.loc[cid] if cid in consent.index else None
            it = intent_df.loc[cid] if cid in intent_df.index else None
        except: continue

        # === 一、合规过滤可用渠道 ===
        eligible = get_eligible_channels(cn, p)
        if not eligible:
            continue  # 无可投渠道, 跳过

        # === 二、读取客户既有属性 ===
        cust_pref = str(p.get("contact_preference", "APP Push"))
        app_active = float(p.get("long_term_90d_active_days", 10) or 10)
        activity = float(p.get("long_term_90d_activity_score", 30) or 30)

        # === 三、渠道选择 (80%倾向+20%探索) ===
        ch, ch_prob, ch_policy = choose_channel(p, eligible)
        if ch is None:
            continue

        stats["total"][ch] = stats["total"].get(ch, 0) + 1
        stats["policy"][ch_policy] = stats["policy"].get(ch_policy, 0) + 1

        # === 意图匹配度 (驱动基础概率) ===
        camp_intent = campaign_intent(camp["campaign_name"])
        intent_score = 0
        if it is not None:
            try:
                intent_json = json.loads(it["intent_json"]) if isinstance(it["intent_json"], str) else {}
                intent_score = intent_json.get(camp_intent, 0)
            except: pass
        high_intent = intent_score >= 40

        # 风险/频控
        risk_level = str(p.get("risk_risk_level", "low"))
        churn_score = float(p.get("risk_churn_risk_score", 10) or 10)
        complaint_cnt = float(cn["complaint_count_90d"]) if cn is not None else 0
        high_risk = (risk_level == "high") or (churn_score >= 50) or (complaint_cnt >= 2)
        days_ago = int(np.random.exponential(scale=25))
        days_ago = min(days_ago, 89)
        high_freq = days_ago < 7
        income = str(p.get("demographics_income_level", "M"))
        credit_usage = float(p.get("account_usage_rate", 0.3) or 0.3)

        # === 基础概率 ===
        p_open = clamp(0.15)
        p_open += 0.001 * activity
        p_open += 0.12 if high_intent else 0
        p_open -= 0.06 if high_freq else 0
        p_open -= 0.08 if high_risk else 0

        p_click = clamp(0.10)
        p_click += 0.15 if high_intent else 0
        p_click += 0.001 * activity
        p_click -= 0.04 if high_freq else 0

        p_conv = clamp(0.08)
        p_conv += 0.20 if high_intent else 0
        p_conv += 0.10 if income == "H" else (0.03 if income == "M" else 0)
        p_conv += 0.08 if credit_usage > 0.7 else 0
        p_conv += 0.001 * activity
        p_conv -= 0.10 if high_risk else 0

        p_unsub = clamp(0.03)
        p_unsub += 0.15 if high_risk else 0
        p_unsub += 0.08 if high_freq else 0
        p_unsub += 0.05 if complaint_cnt >= 2 else 0
        p_unsub -= 0.02 if high_intent else 0

        # === 四、渠道影响结果概率 (沿漏斗体现) ===
        # APP Push × 高活跃
        if ch == "APP Push" and app_active > 20:
            p_open  += 0.08
            p_click += 0.05
            p_conv  += 0.06
            stats["high_active_push"]["total"] += 1
            pref_match = True
        else:
            pref_match = False

        # 偏好短信 × 短信
        if ch == "短信" and cust_pref == "短信":
            p_open  += 0.06
            p_click += 0.04
            p_conv  += 0.05
            pref_match = True

        # 偏好公众号 × 公众号
        if ch == "微信公众号" and cust_pref == "微信公众号":
            p_open  += 0.05
            p_click += 0.04
            p_conv  += 0.04
            pref_match = True

        if pref_match:
            stats["pref_match"]["total"] += 1

        # 截断
        p_open  = clamp(p_open)
        p_click = clamp(p_click)
        p_conv  = clamp(p_conv)
        p_unsub = clamp(p_unsub)

        # === 状态判定 ===
        is_converted = False
        rand = random.random()
        if rand < p_unsub:
            status = "unsubscribed"
        elif rand < p_unsub + p_conv:
            status = "clicked"; ct_contact = "marketing"; is_converted = True
            if pref_match: stats["pref_match"]["conv"] += 1
            if ch == "APP Push" and app_active > 20: stats["high_active_push"]["conv"] += 1
        elif rand < p_unsub + p_conv + p_click:
            status = "clicked"
            if pref_match: stats["pref_match"]["click"] += 1
            if ch == "APP Push" and app_active > 20: stats["high_active_push"]["click"] += 1
        elif rand < p_unsub + p_conv + p_click + p_open:
            status = "opened"
            if pref_match: stats["pref_match"]["open"] += 1
            if ch == "APP Push" and app_active > 20: stats["high_active_push"]["open"] += 1
        else:
            status = "sent"

        if status in stats and ch in stats[status]:
            stats[status][ch] += 1

        contact_time = REFERENCE_DATE - timedelta(days=days_ago, hours=random.randint(0, 23))
        touch_id = f"CONTACT_{i+1:08d}"

        # === 五、保存渠道分配字段 ===
        records.append({
            "contact_id": touch_id,
            "cust_id": cid,
            "campaign_id": camp["campaign_id"] if ct_contact == "marketing" else "",
            "channel": ch,
            "assigned_channel": ch,
            "assignment_probability": round(ch_prob, 4),
            "assignment_policy": ch_policy,
            "assignment_policy_version": POLICY_VERSION,
            "contact_preference": cust_pref,
            "app_active_days": int(app_active),
            "contact_time": contact_time.strftime("%Y-%m-%d %H:%M:%S"),
            "contact_type": ct_contact,
            "status": status,
            "response_time_sec": random.randint(60, 86400) if status in ("opened","clicked") else 0,
        })

        # === 归因记录 ===
        if is_converted and ct_contact == "marketing":
            touch_cost = channel_cost.get(ch, 0.05)
            if high_intent and income == "H":
                conv_amount = random.randint(3000, 30000)
            elif high_intent:
                conv_amount = random.randint(1000, 15000)
            else:
                conv_amount = random.randint(200, 5000)
            attr_hours = round(random.uniform(0.5, 168), 1)
            conv_time = contact_time + timedelta(hours=attr_hours)
            attributions.append({
                "attribution_id": f"ATTR_{len(attributions)+1:08d}",
                "campaign_id": camp["campaign_id"],
                "cust_id": cid,
                "touch_id": touch_id,
                "channel": ch,
                "touch_time": contact_time.strftime("%Y-%m-%d %H:%M:%S"),
                "touch_cost": round(touch_cost, 4),
                "converted": True,
                "conversion_amount": conv_amount,
                "conversion_time": conv_time.strftime("%Y-%m-%d %H:%M:%S"),
                "attribution_hours": attr_hours,
                "attribution_window_days": 14,
            })

        if (i+1) % 30000 == 0:
            print(f"  {i+1}/{n_total} ...")

    df = pd.DataFrame(records)
    df_attr = pd.DataFrame(attributions)

    # 保存
    path = os.path.join(STRUCTURED, "contact_history.csv")
    df.to_csv(path, index=False, encoding="utf-8-sig")
    print(f"\n[OK] contact_history.csv: {len(df)} rows, {len(df.columns)} cols")

    attr_path = os.path.join(STRUCTURED, "campaign_attribution.csv")
    df_attr.to_csv(attr_path, index=False, encoding="utf-8-sig")
    print(f"[OK] campaign_attribution.csv: {len(df_attr)} rows")

    # === 七、验收统计 ===
    print(f"\n{'='*60}")
    print("验收统计")
    print(f"{'='*60}")
    print(f"\n1. 各渠道投放比例:")
    total_all = sum(stats["total"].values())
    for ch in ALL_CHANNELS:
        cnt = stats["total"].get(ch,0)
        print(f"  {ch:10s}: {cnt:6d} ({cnt/max(total_all,1)*100:5.1f}%)")

    print(f"\n2. 高App活跃客户中APP Push效果:")
    ha = stats["high_active_push"]
    if ha["total"] > 0:
        print(f"  样本={ha['total']} | 打开率={ha['open']/ha['total']*100:.1f}% | 点击率={ha['click']/ha['total']*100:.1f}% | 转化率={ha['conv']/ha['total']*100:.1f}%")

    print(f"\n3. 偏好匹配客户效果:")
    pm = stats["pref_match"]
    if pm["total"] > 0:
        print(f"  样本={pm['total']} | 打开率={pm['open']/pm['total']*100:.1f}% | 点击率={pm['click']/pm['total']*100:.1f}% | 转化率={pm['conv']/pm['total']*100:.1f}%")

    print(f"\n4. 探索/利用比例:")
    print(f"  exploitation={stats['policy']['exploitation']} ({stats['policy']['exploitation']/max(n_total,1)*100:.1f}%)")
    print(f"  exploration={stats['policy']['exploration']} ({stats['policy']['exploration']/max(n_total,1)*100:.1f}%)")

    print(f"\n5. 全局状态分布:")
    overall = df["status"].value_counts().to_dict()
    print(f"  {overall}")

    print(f"\n6. 渠道分配策略版本: {POLICY_VERSION}")
    return df

if __name__ == "__main__":
    generate()
