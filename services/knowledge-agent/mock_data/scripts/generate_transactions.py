"""
交易流水与账单记录生成脚本 (高效批处理版)
==========================================
策略: 不逐月逐卡循环, 而是先算好每张卡的年度交易配额,
然后批量生成日期和属性, 最后按卡号+月份聚合出账单。
"""

import random, os, pandas as pd, numpy as np
from datetime import datetime, timedelta
from typing import Dict, List
from collections import defaultdict

from config import *

random.seed(RANDOM_SEED + 1)
np.random.seed(RANDOM_SEED + 1)

# ---- 查表 ----
MC_NAMES = list(MERCHANT_CATEGORIES)
MC_WTS   = [MERCHANT_CATEGORIES[c]["prob"] for c in MC_NAMES]
TXN_TYPES = list(TRANSACTION_TYPES)
TXN_WTS   = list(TRANSACTION_TYPES.values())
CH_NAMES  = list(TRANSACTION_CHANNELS)
CH_WTS    = list(TRANSACTION_CHANNELS.values())


def generate_all_transactions_and_bills(df_cards: pd.DataFrame):
    print("=" * 60)
    print("生成交易流水 & 账单记录 (批处理模式)...")
    print(f"  卡片数: {len(df_cards)}")
    print("=" * 60)

    all_txns: List[Dict] = []
    all_bills: List[Dict] = []
    txn_seq = 1
    bill_seq = 1

    # 每卡年交易额度 (目标总交易量≈600k, 19000张卡 → 均30笔/年/卡)
    lvl_annual = {"校园卡": (15, 40), "普卡": (20, 60), "金卡": (30, 90),
                  "白金卡": (40, 120), "钻石卡": (50, 140), "无限卡": (60, 160)}
    lvl_mult = {"校园卡": 0.4, "普卡": 0.7, "金卡": 1.0,
                "白金卡": 1.5, "钻石卡": 2.5, "无限卡": 4.0}

    for idx, (_, card) in enumerate(df_cards.iterrows()):
        card_no = card["card_no"]
        level   = card["card_level"]
        credit  = card["credit_amount"]
        open_dt = datetime.strptime(card["open_date"], "%Y-%m-%d")
        status  = card["card_status"]
        lvl_m   = lvl_mult.get(level, 1.0)
        lo_yr, hi_yr = lvl_annual.get(level, (80, 240))

        # 活跃月数
        if status == "销卡":
            alive_months = random.randint(6, min(48, int((REFERENCE_DATE - open_dt).days / 30.44)))
        elif status == "冻结":
            alive_months = int((REFERENCE_DATE - timedelta(days=random.randint(30,180)) - open_dt).days / 30.44)
        else:
            alive_months = int((REFERENCE_DATE - open_dt).days / 30.44)
        alive_months = max(1, min(alive_months, 12))  # 最多12个月历史交易

        # 总交易笔数
        monthly_txn = np.random.randint(lo_yr // 12, hi_yr // 12 + 1, size=alive_months)
        # 季节性调整
        now_m_idx = alive_months - 1
        for mi in range(alive_months):
            actual_m = (REFERENCE_DATE.month - (alive_months - 1 - mi) - 1) % 12 + 1
            if actual_m in (11, 12, 1):
                monthly_txn[mi] = int(monthly_txn[mi] * random.uniform(1.1, 1.4))
            elif actual_m in (2, 6):
                monthly_txn[mi] = int(monthly_txn[mi] * random.uniform(0.75, 0.9))

        total_txn = monthly_txn.sum()

        if total_txn == 0:
            continue

        # 批量属性
        ttypes = np.random.choice(TXN_TYPES, size=total_txn, p=[w/sum(TXN_WTS) for w in TXN_WTS])
        cats   = np.random.choice(MC_NAMES, size=total_txn, p=[w/sum(MC_WTS) for w in MC_WTS])
        chans  = np.random.choice(CH_NAMES, size=total_txn, p=[w/sum(CH_WTS) for w in CH_WTS])

        card_txns = []
        start_dt = open_dt
        if alive_months > 0:
            start_dt = REFERENCE_DATE - timedelta(days=alive_months * 30)
        start_dt = max(start_dt, open_dt)

        txn_idx = 0
        for mi in range(alive_months):
            n = monthly_txn[mi]
            if n <= 0:
                continue
            m_start = start_dt + timedelta(days=mi * 30)
            m_end   = min(m_start + timedelta(days=30), REFERENCE_DATE)
            if m_start >= m_end:
                continue

            days_span = max(1, (m_end - m_start).days)
            offsets   = np.random.randint(0, days_span, size=n)
            for j in range(n):
                ts = m_start + timedelta(days=int(offsets[j]),
                                         hours=random.randint(6, 23),
                                         minutes=random.randint(0, 59))
                ttype = ttypes[txn_idx]
                cat   = cats[txn_idx]
                merchant = random.choice(MERCHANT_CATEGORIES[cat]["typical_merchants"])
                xb = (cat == "境外") or (cat == "商旅" and random.random() < 0.2)

                # 金额
                lo_amt, hi_amt = MERCHANT_CATEGORIES[cat]["amount_range"]
                amt = round(np.clip(np.random.lognormal(np.log(max(lo_amt,1)*lvl_m), 0.75),
                                    lo_amt * 0.5, hi_amt * lvl_m * 2.0), 2)
                if ttype == "取现":
                    amt = round(random.uniform(100, min(5000, credit * 0.3)), 2)
                elif ttype == "还款":
                    amt = round(random.uniform(500, credit * 0.5), 2)
                elif ttype == "退款":
                    amt = -round(random.uniform(20, 500), 2)
                elif ttype == "分期":
                    amt = round(random.uniform(1000, credit * 0.3), 2)
                if ttype == "消费" and random.random() < 0.05:
                    amt *= random.uniform(3, 8)

                currency = "CNY"
                if xb and random.random() < 0.55:
                    currency = random.choices(["USD","EUR","JPY","HKD","GBP"], weights=[0.4,0.2,0.2,0.15,0.05])[0]

                card_txns.append({
                    "txn_id": f"T{txn_seq:08d}", "card_no": card_no,
                    "txn_type": ttype, "amount": amt, "currency": currency,
                    "merchant_category": cat, "merchant_name": merchant,
                    "is_cross_border": xb, "txn_channel": chans[txn_idx],
                    "timestamp": ts.strftime("%Y-%m-%d %H:%M:%S"),
                })
                txn_idx += 1

        txn_seq += len(card_txns)
        all_txns.extend(card_txns)

        # ---- 账单 ----
        by_month: Dict[str, List] = defaultdict(list)
        for t in card_txns:
            m = datetime.strptime(t["timestamp"], "%Y-%m-%d %H:%M:%S").strftime("%Y-%m")
            by_month[m].append(t)

        for mk, mt in by_month.items():
            bill = round(sum(t["amount"] for t in mt if t["txn_type"] in ("消费","取现","退款")), 2)
            if bill < 0: bill = 0.0
            min_pay = max(round(bill * 0.10, 2), 100.0) if bill > 0 else 0.0
            is_min = (bill > credit * 0.3 and random.random() < 0.12)
            ym = datetime.strptime(mk, "%Y-%m")
            due = ym + timedelta(days=random.randint(23, 35))
            ps = "已还清"
            if bill == 0:           ps = "无欠款"
            elif is_min:            ps = "最低还款"
            elif random.random() < 0.015: ps = "逾期"

            all_bills.append({
                "bill_id": f"B{bill_seq:08d}", "card_no": card_no, "bill_month": mk,
                "bill_amount": bill, "min_payment": min_pay, "is_min_payment": is_min,
                "due_date": due.strftime("%Y-%m-%d"), "payment_status": ps,
            })
            bill_seq += 1

        if (idx + 1) % 2000 == 0:
            print(f"  {idx+1}/{len(df_cards)} cards, {len(all_txns)} txns")

    # 保存
    df_txn = pd.DataFrame(all_txns)
    df_bill = pd.DataFrame(all_bills)
    df_txn.to_csv(os.path.join(STRUCTURED_DIR, "transaction_log.csv"), index=False, encoding="utf-8-sig")
    df_bill.to_csv(os.path.join(STRUCTURED_DIR, "bill_record.csv"), index=False, encoding="utf-8-sig")

    print(f"\n[OK] transaction_log.csv : {len(df_txn)} rows")
    print(f"   types: {dict(df_txn['txn_type'].value_counts())}")
    print(f"   cross-border: {df_txn['is_cross_border'].mean()*100:.1f}%")
    print(f"[OK] bill_record.csv : {len(df_bill)} rows")
    print(f"   status: {dict(df_bill['payment_status'].value_counts())}")
    return df_txn, df_bill


if __name__ == "__main__":
    p = os.path.join(STRUCTURED_DIR, "credit_card.csv")
    if os.path.exists(p):
        generate_all_transactions_and_bills(pd.read_csv(p))
    else:
        print("[WARN] Run generate_customers.py first")
