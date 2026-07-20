"""
动态记忆引擎 — dynamic_memory.py
=================================
四时间窗口计算: 实时(≤1h) / 短期(7d) / 中期(30d) / 长期(90d)

数据来源:
  实时窗口: app_events + transaction_log (近1小时)
  短期窗口: app_events搜索 + 交易流水 (近7天)
  中期窗口: app_events浏览 + 交易流水 (近30天, 天级聚合)
  长期窗口: 交易流水 (近90天, 天级聚合)

更新机制:
  实时: 事件驱动 (模拟: 每次查询时计算最近1小时)
  短期: 每小时微批 (模拟: 按小时聚合)
  中期: 每日T+1 (模拟: 按天聚合)
  长期: 每日T+1 (模拟: 按天聚合)
"""

import os, pandas as pd, numpy as np
from datetime import datetime, timedelta
from collections import Counter
from typing import Dict, Any, List, Optional

REF_DATE = datetime(2026, 7, 15, 15, 0, 0)  # 模拟"现在"时刻


class DynamicMemoryEngine:
    """四窗口动态记忆计算引擎。"""

    def __init__(self, data_dir: str = None):
        if data_dir is None:
            data_dir = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                                    "mock_data", "structured")
        self.data_dir = data_dir
        self._loaded = False

    def load(self):
        """加载数据源。"""
        if self._loaded:
            return self
        s = self.data_dir
        cards = pd.read_csv(os.path.join(s, "credit_card.csv"))
        card_to_cust = dict(zip(cards["card_no"], cards["cust_id"]))

        self.txn = pd.read_csv(os.path.join(s, "transaction_log.csv"))
        self.txn["ts"] = pd.to_datetime(self.txn["timestamp"])
        self.txn["cust_id"] = self.txn["card_no"].map(card_to_cust)
        self.txn = self.txn[self.txn["cust_id"].notna()]

        self.app = pd.read_csv(os.path.join(s, "app_events.csv"))
        self.app["ts"] = pd.to_datetime(self.app["timestamp"])

        self.asr_dir = os.path.join(os.path.dirname(s), "unstructured", "asr_transcripts")
        self._loaded = True
        return self

    # ================================================================
    # 四个时间窗口计算
    # ================================================================

    def realtime(self, cust_id: str) -> Dict[str, Any]:
        """实时窗口 (≤1小时) — 事件级。"""
        self.load()
        cutoff = REF_DATE - timedelta(hours=1)

        # 近1小时交易
        txn1h = self.txn[(self.txn["cust_id"] == cust_id) & (self.txn["ts"] >= cutoff)]
        # 近1小时APP事件
        app1h = self.app[(self.app["device_id"].notna())]  # 简化: 无法直接关联cust_id到app_events
        # 实际生产环境通过 OneID + device_id 映射关联

        signals = []
        for _, t in txn1h.iterrows():
            if t["txn_type"] == "消费" and t["amount"] > 5000:
                signals.append({"type": "大额消费", "detail": f"{t['merchant_name']} ¥{t['amount']:.0f}",
                                "time": str(t["ts"]), "significance": "high"})
            elif t["is_cross_border"]:
                signals.append({"type": "境外交易", "detail": f"{t['merchant_name']} {t['currency']} {t['amount']:.0f}",
                                "time": str(t["ts"]), "significance": "high"})

        return {
            "window": "realtime_1h",
            "updated_at": REF_DATE.strftime("%Y-%m-%d %H:%M:%S"),
            "recent_signals": signals[-5:],  # 最近5条
            "signal_count": len(signals),
            "has_high_value_txn": any(s["significance"] == "high" for s in signals),
        }

    def short_term_7d(self, cust_id: str) -> Dict[str, Any]:
        """短期窗口 (7天) — 小时级聚合。"""
        self.load()
        cutoff = REF_DATE - timedelta(days=7)
        txn7 = self.txn[(self.txn["cust_id"] == cust_id) & (self.txn["ts"] >= cutoff)]
        consumption = txn7[txn7["txn_type"] == "消费"]["amount"].sum()
        count = len(txn7[txn7["txn_type"] == "消费"])

        # 搜索关键词 (简化: 取该客户关联的 device_id 对应的搜索)
        # 实际用 OneID → device_id 映射，这里用采样
        search_kw = ["分期费率", "出境游", "汇率", "提额"]  # 模拟: 实际从app_events提取
        active_days = txn7["ts"].dt.date.nunique()

        return {
            "window": "short_7d",
            "updated_at": REF_DATE.strftime("%Y-%m-%d %H:%M:%S"),
            "total_consumption": round(float(consumption), 2),
            "transaction_count": int(count),
            "active_days": int(active_days),
            "top_search_keywords": search_kw[:5],
            "avg_daily_spend": round(float(consumption) / 7, 2),
        }

    def mid_term_30d(self, cust_id: str) -> Dict[str, Any]:
        """中期窗口 (30天) — 天级聚合。"""
        self.load()
        cutoff = REF_DATE - timedelta(days=30)
        prev_cutoff = cutoff - timedelta(days=30)  # 前30天用于对比

        txn30 = self.txn[(self.txn["cust_id"] == cust_id) & (self.txn["ts"] >= cutoff)]
        txn_prev30 = self.txn[(self.txn["cust_id"] == cust_id) &
                               (self.txn["ts"] >= prev_cutoff) & (self.txn["ts"] < cutoff)]

        curr_cons = txn30[txn30["txn_type"] == "消费"]["amount"].sum()
        prev_cons = txn_prev30[txn_prev30["txn_type"] == "消费"]["amount"].sum()

        # 趋势判断
        if prev_cons > 0:
            change_pct = (curr_cons - prev_cons) / prev_cons
        else:
            change_pct = 0 if curr_cons == 0 else 1.0

        if change_pct > 0.15:
            trend = "up"
        elif change_pct < -0.20:
            trend = "down"
        else:
            trend = "stable"

        # 浏览偏好 (模拟: 实际从 app_events page_name 聚合)
        browse = [{"category": "权益商城", "ratio": 0.45},
                   {"category": "分期计算器", "ratio": 0.30},
                   {"category": "账单详情", "ratio": 0.15},
                   {"category": "境外消费专区", "ratio": 0.10}]

        # 商户类别Top3
        cats = txn30[txn30["txn_type"] == "消费"]["merchant_category"].value_counts()
        top_merchants = [{"category": k, "count": int(v)} for k, v in cats.head(3).items()]

        return {
            "window": "mid_30d",
            "updated_at": REF_DATE.strftime("%Y-%m-%d %H:%M:%S"),
            "total_consumption": round(float(curr_cons), 2),
            "consumption_trend": trend,
            "trend_change_pct": round(float(change_pct * 100), 1),
            "top_merchant_categories": top_merchants,
            "top_browse_categories": browse,
        }

    def long_term_90d(self, cust_id: str) -> Dict[str, Any]:
        """长期窗口 (90天) — 天级聚合。"""
        self.load()
        cutoff = REF_DATE - timedelta(days=90)
        txn90 = self.txn[(self.txn["cust_id"] == cust_id) & (self.txn["ts"] >= cutoff)]
        consumption = txn90[txn90["txn_type"] == "消费"]["amount"].sum()
        count = len(txn90[txn90["txn_type"] == "消费"])
        active_days = txn90["ts"].dt.date.nunique()

        # 活跃度评分 (0-100)
        # = 交易天数/90 * 40 + 交易笔数归一化*30 + 消费金额归一化*30
        day_score = min(active_days / 90 * 40, 40)
        count_score = min(count / 100 * 30, 30) if count > 0 else 0
        amount_score = min(consumption / 50000 * 30, 30) if consumption > 0 else 0
        activity_score = int(day_score + count_score + amount_score)

        # 沉睡风险
        if activity_score < 20:
            dormancy = "high"
        elif activity_score < 50:
            dormancy = "medium"
        else:
            dormancy = "low"

        # 降级信号
        mid_cutoff = REF_DATE - timedelta(days=60)
        recent60 = txn90[txn90["ts"] >= mid_cutoff]["amount"].sum()
        early30 = txn90[txn90["ts"] < mid_cutoff]["amount"].sum()
        downgrade_signal = (recent60 < early30 * 0.6) if early30 > 0 else False

        signals = []
        if downgrade_signal:
            signals.append("消费降级")
        if activity_score < 30:
            signals.append("活跃度骤降")
        if dormancy == "high":
            signals.append("沉睡预警")

        return {
            "window": "long_90d",
            "updated_at": REF_DATE.strftime("%Y-%m-%d %H:%M:%S"),
            "total_consumption": round(float(consumption), 2),
            "transaction_count": int(count),
            "active_days": int(active_days),
            "activity_score": activity_score,
            "dormancy_risk": dormancy,
            "significant_signals": signals,
            "monthly_avg_90d": round(float(consumption) / 3, 2),
        }

    # ================================================================
    # 全量动态记忆 (四个窗口打包)
    # ================================================================

    def build_full(self, cust_id: str) -> Dict[str, Any]:
        """构建一个客户的完整动态记忆（四个窗口合并）。"""
        return {
            "cust_id": cust_id,
            "realtime": self.realtime(cust_id),
            "short_term_7d": self.short_term_7d(cust_id),
            "mid_term_30d": self.mid_term_30d(cust_id),
            "long_term_90d": self.long_term_90d(cust_id),
            "generated_at": REF_DATE.strftime("%Y-%m-%d %H:%M:%S"),
        }

    def build_all(self, cust_ids: List[str]) -> pd.DataFrame:
        """批量构建动态记忆 — 使用分组聚合（快）。"""
        self.load()
        ref = pd.Timestamp(REF_DATE)

        # 预过滤交易数据
        txn = self.txn.copy()
        txn_90d = txn[txn["ts"] >= ref - pd.Timedelta(days=90)]
        txn_30d = txn_90d[txn_90d["ts"] >= ref - pd.Timedelta(days=30)]
        txn_7d = txn_30d[txn_30d["ts"] >= ref - pd.Timedelta(days=7)]

        # 按 cust_id 聚合
        def agg_txn(df, prefix):
            cons = df[df["txn_type"]=="消费"]
            g = cons.groupby("cust_id")["amount"].agg(["sum","count","max"])
            g.columns = [f"{prefix}_total_consumption", f"{prefix}_txn_count", f"{prefix}_max_single"]
            # 活跃天数
            days = cons.groupby("cust_id")["ts"].apply(lambda x: x.dt.date.nunique()).rename(f"{prefix}_active_days")
            return pd.concat([g, days], axis=1)

        agg_90d = agg_txn(txn_90d, "long_term_90d")
        agg_30d = agg_txn(txn_30d, "mid_term_30d")
        agg_7d = agg_txn(txn_7d, "short_term_7d")

        # 消费趋势 (30d vs 前30d)
        prev_30d = txn[(txn["ts"] >= ref - pd.Timedelta(days=60)) &
                        (txn["ts"] < ref - pd.Timedelta(days=30))]
        prev_cons = prev_30d[prev_30d["txn_type"]=="消费"].groupby("cust_id")["amount"].sum().rename("prev_30d_cons")

        # 合并
        df = pd.DataFrame({"cust_id": cust_ids}).set_index("cust_id")
        for agg in [agg_90d, agg_30d, agg_7d]:
            df = df.join(agg, how="left")
        df = df.join(prev_cons, how="left")
        df = df.fillna(0).reset_index()

        # 计算衍生字段
        df["mid_term_30d_trend_change_pct"] = df.apply(
            lambda r: round((r["mid_term_30d_total_consumption"] - r["prev_30d_cons"]) /
                            r["prev_30d_cons"] * 100, 1) if r["prev_30d_cons"] > 0 else 0, axis=1)
        df["mid_term_30d_consumption_trend"] = df["mid_term_30d_trend_change_pct"].apply(
            lambda x: "up" if x > 15 else ("down" if x < -20 else "stable"))

        # 活跃度评分
        df["long_term_90d_activity_score"] = df.apply(
            lambda r: min(int(r["long_term_90d_active_days"]/90*40 +
                              min(r["long_term_90d_txn_count"]/100*30, 30) +
                              min(r["long_term_90d_total_consumption"]/50000*30, 30)), 100), axis=1)
        df["long_term_90d_dormancy_risk"] = df["long_term_90d_activity_score"].apply(
            lambda x: "high" if x < 20 else ("medium" if x < 50 else "low"))

        # 降级信号
        df["long_term_90d_significant_signals"] = df.apply(
            lambda r: "消费降级" if (r["prev_30d_cons"] > 0 and
                r["mid_term_30d_total_consumption"] < r["prev_30d_cons"] * 0.6) else "", axis=1)

        # 实时窗口 (简化为0或1标记)
        df["realtime_signal_count"] = 0
        df["realtime_has_high_value_txn"] = False
        df["realtime_updated_at"] = REF_DATE.strftime("%Y-%m-%d %H:%M:%S")

        # 短期窗口
        df["short_term_7d_updated_at"] = REF_DATE.strftime("%Y-%m-%d %H:%M:%S")
        df["short_term_7d_top_search_keywords"] = "[]"
        df["short_term_7d_avg_daily_spend"] = (df["short_term_7d_total_consumption"] / 7).round(2)

        # 中期窗口
        df["mid_term_30d_updated_at"] = REF_DATE.strftime("%Y-%m-%d %H:%M:%S")
        df["mid_term_30d_top_merchant_categories"] = "[]"
        df["mid_term_30d_top_browse_categories"] = "[]"

        # 长期窗口
        df["long_term_90d_updated_at"] = REF_DATE.strftime("%Y-%m-%d %H:%M:%S")
        df["long_term_90d_monthly_avg_90d"] = (df["long_term_90d_total_consumption"] / 3).round(2)

        print(f"  动态记忆: {len(df)} 个客户完成")
        return df
