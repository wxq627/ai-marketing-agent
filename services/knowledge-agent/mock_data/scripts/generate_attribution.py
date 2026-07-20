"""
活动效果归因数据生成脚本
=========================
基于现有交易流水和触达历史，构建活动→触达→转化的完整归因链路。
用于后续 ROI 计算和策略效果评估。

生成:
  - campaign_performance.csv   (活动级 ROI 汇总, 25行)
  - campaign_attribution.csv   (客户级归因明细, ~50,000行)

归因逻辑:
  1. 从 contact_history 中筛选 status=clicked 的记录作为有效触达
  2. 以触达时间前后 7 天为归因窗口
  3. 如果窗口内客户有消费，则记为一次转化，消费金额为归因收入
  4. 基于渠道成本计算单次触达成本
  5. 聚合计算每个活动的 ROI
"""
import os, random, pandas as pd
import numpy as np
from datetime import datetime, timedelta

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
STRUCTURED = os.path.join(BASE, "structured")
REF_DATE = datetime(2026, 7, 15)
random.seed(42)
np.random.seed(42)

def generate():
    print("=" * 60)
    print("生成活动效果归因数据")
    print("=" * 60)

    # 读依赖数据
    camp = pd.read_csv(os.path.join(STRUCTURED, "campaign_catalog.csv"))
    ch_cfg = pd.read_csv(os.path.join(STRUCTURED, "channel_config.csv"))
    hist = pd.read_csv(os.path.join(STRUCTURED, "contact_history.csv"))
    txn = pd.read_csv(os.path.join(STRUCTURED, "transaction_log.csv"))
    cards = pd.read_csv(os.path.join(STRUCTURED, "credit_card.csv"))
    cust = pd.read_csv(os.path.join(STRUCTURED, "customer_basic.csv"))

    # 预处理
    ch_cost = dict(zip(ch_cfg["channel_name"], ch_cfg["cost_per_send"]))
    card_to_cust = dict(zip(cards["card_no"], cards["cust_id"]))
    txn["ts"] = pd.to_datetime(txn["timestamp"])
    hist["ts"] = pd.to_datetime(hist["contact_time"])

    # ================================================================
    # 1. 更新 contact_history 增加 cost 字段
    # ================================================================
    hist["cost"] = hist["channel"].map(ch_cost).fillna(0.05)
    # 重写 contact_history.csv
    hist_out = hist.drop(columns=["ts"])
    hist_out.to_csv(os.path.join(STRUCTURED, "contact_history.csv"), index=False, encoding="utf-8-sig")
    total_touch_cost = hist["cost"].sum()
    print(f"\n[1] contact_history.csv: 已添加 cost 字段")
    print(f"    总触达成本: {total_touch_cost:,.0f} 元")

    # ================================================================
    # 2. 生成 campaign_attribution (客户级归因)
    # ================================================================
    # 只取有 campaign_id 的营销触达 + status=clicked
    effective = hist[(hist["campaign_id"] != "") & (hist["status"] == "clicked")].copy()
    print(f"\n[2] 有效点击触达: {len(effective)} 条")

    attributions = []
    # 为每个有效点击匹配最近的交易（归因窗口: 点击后 0-14 天）
    for _, touch in effective.iterrows():
        cid = touch["cust_id"]
        campaign_id = touch["campaign_id"]
        touch_time = touch["ts"]
        touch_cost = touch["cost"]
        channel = touch["channel"]

        # 查该客户的卡号
        cust_cards = cards[cards["cust_id"] == cid]["card_no"].tolist()
        if not cust_cards:
            continue

        # 查找归因窗口内的交易
        window_start = touch_time
        window_end = touch_time + timedelta(days=14)
        related_txn = txn[
            (txn["card_no"].isin(cust_cards)) &
            (txn["ts"] >= window_start) &
            (txn["ts"] <= window_end)
        ]

        if len(related_txn) > 0:
            # 有转化
            txn_row = related_txn.iloc[0]
            conv_amount = abs(float(txn_row["amount"]))
            conv_time = txn_row["ts"]
            attribution_hours = (conv_time - touch_time).total_seconds() / 3600
            converted = True
        else:
            # 有点击但无转化
            conv_amount = 0
            conv_time = None
            attribution_hours = None
            converted = False

        attributions.append({
            "attribution_id": f"ATTR_{len(attributions)+1:08d}",
            "campaign_id": campaign_id,
            "cust_id": cid,
            "touch_id": touch["contact_id"],
            "channel": channel,
            "touch_time": touch_time.strftime("%Y-%m-%d %H:%M:%S"),
            "touch_cost": round(touch_cost, 4),
            "converted": converted,
            "conversion_amount": round(conv_amount, 2),
            "conversion_time": conv_time.strftime("%Y-%m-%d %H:%M:%S") if conv_time else "",
            "attribution_hours": round(attribution_hours, 1) if attribution_hours else 0,
            "attribution_window_days": 14,
        })

    df_attr = pd.DataFrame(attributions)
    attr_path = os.path.join(STRUCTURED, "campaign_attribution.csv")
    df_attr.to_csv(attr_path, index=False, encoding="utf-8-sig")
    conv_rate = df_attr["converted"].mean()
    total_conv_value = df_attr["conversion_amount"].sum()
    print(f"   生成 {len(df_attr)} 条归因记录")
    print(f"   转化率: {conv_rate:.1%}")
    print(f"   总归因收入: {total_conv_value:,.0f} 元")

    # ================================================================
    # 3. 生成 campaign_performance (活动级 ROI)
    # ================================================================
    perf_rows = []
    for _, cp in camp.iterrows():
        cid_camp = cp["campaign_id"]
        budget = cp["budget"]
        expected = cp["expected_reach"]

        # 该活动的触达统计
        camp_hist = hist[hist["campaign_id"] == cid_camp]
        touches = len(camp_hist)
        impressions = len(camp_hist[camp_hist["status"].isin(["delivered", "opened", "clicked"])])
        clicks = len(camp_hist[camp_hist["status"] == "clicked"])
        camp_cost = camp_hist["cost"].sum() if "cost" in camp_hist.columns else touches * 0.05

        # 该活动的归因转化
        camp_attr = df_attr[df_attr["campaign_id"] == cid_camp]
        conversions = camp_attr["converted"].sum() if len(camp_attr) > 0 else 0
        attr_revenue = camp_attr["conversion_amount"].sum() if len(camp_attr) > 0 else 0
        avg_attr_hours = camp_attr[camp_attr["converted"]]["attribution_hours"].mean() if conversions > 0 else 0

        # ROI 计算
        cpa = camp_cost / conversions if conversions > 0 else float('inf')
        roi = (attr_revenue - camp_cost) / camp_cost if camp_cost > 0 else 0
        # 对于大预算活动（如周三5折、9元观影），给合理的转化率
        actual_reach = min(touches, expected)
        reach_rate = actual_reach / expected if expected > 0 else 0

        perf_rows.append({
            "campaign_id": cid_camp,
            "campaign_name": cp["campaign_name"],
            "budget": budget,
            "expected_reach": expected,
            "actual_touches": touches,
            "actual_reach_rate": round(reach_rate, 4),
            "impressions": impressions,
            "clicks": clicks,
            "click_rate": round(clicks / impressions, 4) if impressions > 0 else 0,
            "conversions": conversions,
            "conversion_rate": round(conversions / clicks, 4) if clicks > 0 else 0,
            "total_cost": round(camp_cost, 2),
            "attributed_revenue": round(attr_revenue, 2),
            "roi": round(roi, 4),
            "cpa": round(cpa, 2),
            "avg_attribution_hours": round(avg_attr_hours, 1),
        })

    df_perf = pd.DataFrame(perf_rows)
    perf_path = os.path.join(STRUCTURED, "campaign_performance.csv")
    df_perf.to_csv(perf_path, index=False, encoding="utf-8-sig")

    print(f"\n[3] campaign_performance.csv: {len(df_perf)} 个活动")
    # ROI 排名
    top_roi = df_perf.nlargest(5, "roi")[["campaign_name", "roi", "conversions", "attributed_revenue"]]
    print("    ROI Top 5:")
    for _, r in top_roi.iterrows():
        print(f"      {r['campaign_name'][:20]}: ROI={r['roi']:.2f}, conversions={int(r['conversions'])}, revenue={r['attributed_revenue']:,.0f}")

    # 全局统计
    total_cost = df_perf["total_cost"].sum()
    total_rev = df_perf["attributed_revenue"].sum()
    total_conv = df_perf["conversions"].sum()
    print(f"\n    全局: 总成本={total_cost:,.0f}, 总收入={total_rev:,.0f}, 总转化={total_conv}, 总ROI={(total_rev-total_cost)/total_cost:.4f}")

    print("\n" + "=" * 60)
    print("完成!")
    print("=" * 60)
    return df_perf, df_attr

if __name__ == "__main__":
    generate()
