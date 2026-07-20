"""
意图规则评分引擎 — rule_scorer.py
===================================
第一层: 纯Python规则引擎。可控、可解释、低延迟。

基于 intent_rules.yaml 中6类意图×多条触发规则, 加权求和输出0-100分。
每条规则输出 sub_signals 数组, 包含 signal/value/weight/threshold 四元组,
确保完全可解释(evidence_summary)。
"""

import os, yaml, re, numpy as np
from typing import Dict, List, Any, Optional

# 加载规则配置
_RULES_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "intent_rules.yaml")
with open(_RULES_PATH, "r", encoding="utf-8") as f:
    RULES = yaml.safe_load(f)


class RuleScorer:
    """第一层: 规则评分引擎。"""

    def __init__(self):
        self.intents = RULES["intents"]
        self.confidence_cfg = RULES["confidence"]
        self.trend_cfg = RULES["trend"]
        self.sentiment_cfg = RULES["sentiment"]

    # ================================================================
    # 评分主入口
    # ================================================================
    def score_all(self, profile: Dict, events: Dict) -> Dict:
        """
        对6类意图全部打分。

        profile: 客户画像(从customer_snapshot取)
        events:  客户行为事件 {search_keywords: [], browse_pages: [], overdue_count: int, ...}
        """
        results = {}
        for key, cfg in self.intents.items():
            score, sub_signals = self._score_one(cfg, profile, events)
            confidence = self._get_confidence(score, cfg)
            results[key] = {
                "type": cfg["label"],
                "score": score,
                "confidence": confidence["label"],
                "sub_signals": sub_signals,
                "evidence_summary": self._build_evidence(sub_signals),
            }
        # 找主意图
        primary = max(results, key=lambda k: results[k]["score"])
        return {
            "intents": list(results.values()),
            "primary_intent": results[primary]["type"],
        }

    # ================================================================
    # 单意图评分
    # ================================================================
    def _score_one(self, cfg: Dict, profile: Dict, events: Dict) -> tuple:
        """对一条意图的所有规则评分, 返回(总分, sub_signals)"""
        total = 0
        sub_signals = []
        for rule in cfg["rules"]:
            triggered, value = self._eval_rule(rule, profile, events)
            if triggered:
                total += rule["weight"]
                sub_signals.append({
                    "signal": rule["signal"],
                    "value": value,
                    "weight": rule["weight"],
                    "threshold": f"{rule['operator']} {rule['threshold']}",
                    "description": rule.get("description", ""),
                })
        return min(total, 100), sub_signals

    # ================================================================
    # 规则评估
    # ================================================================
    def _eval_rule(self, rule: Dict, profile: Dict, events: Dict) -> tuple:
        """评估单条规则: 返回(触发?, 实际值描述)"""
        op = rule["operator"]
        threshold = rule["threshold"]

        # ---- 类型1: 基于 profile 字段 ----
        if "field_map" in rule:
            # 如账单/额度比
            actual = self._calc_ratio(profile, rule)
            triggered = self._compare(actual, op, threshold)
            return triggered, f"{actual:.0%}"

        # ---- 类型2: 基于搜索关键词 ----
        if "keywords" in rule:
            keywords = events.get("search_keywords", "")
            if isinstance(keywords, list):
                keywords = " ".join(keywords)
            if isinstance(keywords, str):
                count = sum(1 for kw in rule["keywords"] if kw in keywords)
            else:
                count = 0
            triggered = self._compare(count, op, threshold)
            return triggered, f"匹配{count}个关键词"

        # ---- 类型3: 基于浏览页面 ----
        if "pages" in rule:
            pages = events.get("browse_pages", "")
            if isinstance(pages, list):
                pages = " ".join(pages)
            if isinstance(pages, str):
                count = sum(1 for p in rule["pages"] if p in pages)
            else:
                count = 0
            triggered = self._compare(count, op, threshold)
            return triggered, f"浏览{count}次"

        # ---- 类型4: 基于生命周期 ----
        if "lifecycle_stages" in rule:
            stage = str(profile.get("lifecycle_stage", ""))
            triggered = stage in rule["lifecycle_stages"]
            return triggered, f"生命周期={stage}"

        # ---- 类型5: 基于逾期/最低还款 ----
        if "overdue" in rule.get("signal", ""):
            count = events.get("overdue_count", 0)
            triggered = self._compare(count, op, threshold)
            return triggered, f"{count}次"

        if "最低还款" in rule.get("signal", ""):
            count = events.get("min_payment_count", 0)
            triggered = self._compare(count, op, threshold)
            return triggered, f"{count}次"

        # ---- 类型6: 跨境交易 ----
        if "is_cross_border" in rule.get("source", ""):
            count = events.get("cross_border_count", 0)
            triggered = self._compare(count, op, threshold)
            return triggered, f"{count}笔"

        # ---- 类型7: 投诉 ----
        if "客服" in rule.get("signal", "") or "投诉" in rule.get("signal", ""):
            count = events.get("complaint_count", 0)
            triggered = self._compare(count, op, threshold)
            return triggered, f"{count}次"

        # ---- 类型8: 销户/注销搜索 ----
        if any(kw in str(rule.get("keywords", [])) for kw in ["销户", "注销"]):
            keywords = events.get("search_keywords", "")
            count = sum(1 for kw in rule["keywords"] if kw in str(keywords))
            triggered = self._compare(count, op, threshold)
            return triggered, f"{count}次"

        # ---- 默认: 用events中的数值字段 ----
        val = events.get(rule["signal"], 0)
        if isinstance(val, (int, float)):
            triggered = self._compare(val, op, threshold)
            return triggered, str(val)

        return False, "0"

    # ================================================================
    # 工具方法
    # ================================================================
    def _compare(self, actual, op: str, threshold) -> bool:
        if op == "gt": return actual > threshold
        if op == "gte": return actual >= threshold
        if op == "lt": return actual < threshold
        if op == "lte": return actual <= threshold
        return False

    def _calc_ratio(self, profile: Dict, rule: Dict) -> float:
        """计算账单/额度比"""
        # 从profile中近似获取
        usage = float(profile.get("usage_rate", 0))
        return usage

    def _get_confidence(self, score: int, cfg: Dict) -> Dict:
        th = cfg.get("thresholds", {})
        high_th = th.get("high", 70)
        medium_th = th.get("medium", 40)
        if score >= high_th:
            return {"label": "high", "description": "高置信度, 建议优先触达"}
        elif score >= medium_th:
            return {"label": "medium", "description": "中等置信度, 需持续观察"}
        return {"label": "low", "description": "低置信度, 暂无显著需求"}

    def _build_evidence(self, sub_signals: List) -> str:
        if not sub_signals:
            return "暂无显著信号"
        parts = []
        for s in sub_signals[:3]:
            parts.append(f"{s['signal']}({s['value']}, 权重{s['weight']})")
        return "; ".join(parts)

    # ================================================================
    # 趋势判断
    # ================================================================
    def compute_trend(self, current_score: int, previous_score: int) -> str:
        if previous_score == 0:
            return "stable"
        change_pct = (current_score - previous_score) / previous_score * 100
        if change_pct > self.trend_cfg["rising"]["change_pct"]:
            return "rising"
        elif change_pct < self.trend_cfg["falling"]["change_pct"]:
            return "falling"
        return "stable"
