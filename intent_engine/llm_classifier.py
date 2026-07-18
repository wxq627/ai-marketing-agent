"""
LLM语义分类 + 情感分析 — llm_classifier.py
=============================================
第二层: 对ASR对话文本等需深度理解的信号, 用DeepSeek做语义分析。

DeepSeek可用时: 调用 classify_intent() / analyze_sentiment()
DeepSeek不可用时: 降级为本地关键词规则匹配
"""

import os, sys, json, re, random
from typing import Dict, List, Any
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from llm_client import classify_intent as deepseek_classify, analyze_sentiment as deepseek_sentiment, is_available


class LLMClassifier:
    """第二层: LLM语义分类器 (DeepSeek优先, 降级关键词规则)。"""

    def __init__(self, mock_mode: bool = None):
        if mock_mode is None:
            mock_mode = not is_available()
        self.mock_mode = mock_mode
        self.intent_keywords = {
            "分期/借贷需求": ["分期", "手续费", "账单", "还不上", "压力", "最低还款", "12期"],
            "跨境/出行需求": ["境外", "出国", "汇率", "海淘", "免税", "签证", "机票", "酒店", "东京", "巴黎"],
            "额度/升级需求": ["提额", "额度不够", "升级", "白金卡", "钻石卡"],
            "权益/优惠需求": ["积分", "兑换", "优惠", "折扣", "里程", "5折", "星巴克", "贵宾厅"],
            "沉睡/流失风险": ["销户", "注销", "投诉", "取消", "年费太高"],
            "新户/激活引导": ["开卡", "激活", "怎么用", "新手"],
        }
        self.sentiment_keywords = {
            "焦虑": ["压力", "还不上", "太高", "怎么办", "担心"],
            "不满": ["投诉", "凭什么", "太差", "骗人", "乱收费"],
            "满意": ["谢谢", "好的", "明白了", "很方便", "不错"],
            "好奇": ["有什么", "怎么办理", "介绍一下", "多少钱"],
        }

    def classify(self, conversation_text: str) -> Dict:
        """
        分析客服对话/智能体对话, 识别意图和情感。
        DeepSeek可用→直接调用API; 不可用→关键词规则降级。
        """
        if not self.mock_mode:
            try:
                result = deepseek_classify(conversation_text)
                # 标准化输出格式
                return {
                    "primary_intent": result.get("primary_intent", "分期借贷需求"),
                    "intent_score": result.get("intent_score", 50),
                    "sentiment": result.get("sentiment", "中性"),
                    "urgency": result.get("urgency", "中"),
                    "key_phrases": result.get("key_phrases", []),
                    "all_intents": result.get("all_intents", {}),
                }
            except:
                pass
        return self._mock_classify(conversation_text)

    def _mock_classify(self, text: str) -> Dict:
        """Mock: 基于关键词规则模拟LLM分类"""
        scores = {}
        for intent, keywords in self.intent_keywords.items():
            count = sum(1 for kw in keywords if kw in text)
            # 模拟: 匹配到的关键词越多, 意图越强
            base = min(count * 15 + random.randint(-5, 20), 100)
            scores[intent] = max(0, base)

        # 如果没有匹配, 给一个默认低分分布
        if max(scores.values()) < 10:
            scores["分期/借贷需求"] = random.randint(10, 30)
            scores["跨境/出行需求"] = random.randint(5, 20)

        primary = max(scores, key=scores.get)

        # 情感
        sentiment_scores = {}
        for sent, kws in self.sentiment_keywords.items():
            sentiment_scores[sent] = sum(1 for kw in kws if kw in text)
        overall = max(sentiment_scores, key=sentiment_scores.get) if max(sentiment_scores.values()) > 0 else "中性"

        # 关键短语提取
        key_phrases = []
        for kw in ["分期", "手续费", "12期", "账单", "压力", "还不上", "提额"]:
            if kw in text:
                key_phrases.append(kw)

        return {
            "primary_intent": primary,
            "intent_score": scores[primary],
            "all_intents": scores,
            "sentiment": overall,
            "urgency": "高" if scores[primary] > 70 else ("中" if scores[primary] > 40 else "低"),
            "key_phrases": key_phrases[:5] if key_phrases else [text[:15]],
        }

    def _llm_classify(self, text: str) -> Dict:
        """生产环境: 调用 Qwen3-8B API"""
        # TODO: 实现真实的LLM API调用
        prompt = self._load_prompt("intent_classify.txt")
        # response = call_qwen_api(prompt + text)
        # return parse_json(response)
        return self._mock_classify(text)  # fallback

    def _load_prompt(self, name: str) -> str:
        path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "prompts", name)
        if os.path.exists(path):
            with open(path, "r", encoding="utf-8") as f:
                return f.read()
        return ""


class SentimentAnalyzer:
    """情感分析器"""

    def __init__(self, mock_mode: bool = True):
        self.mock_mode = mock_mode
        self.sentiment_map = {
            "满意": {"satisfaction_score": 80, "anxiety_score": 10, "description": "客服评价高, 持续活跃"},
            "中性": {"satisfaction_score": 60, "anxiety_score": 30, "description": "日常正常使用"},
            "焦虑": {"satisfaction_score": 30, "anxiety_score": 75, "description": "表达还款压力"},
            "不满": {"satisfaction_score": 15, "anxiety_score": 60, "description": "投诉记录"},
            "好奇": {"satisfaction_score": 55, "anxiety_score": 20, "description": "多次浏览新产品"},
        }

    def analyze(self, sentiment_label: str, key_evidence: str = "") -> Dict:
        info = self.sentiment_map.get(sentiment_label, self.sentiment_map["中性"])
        return {
            "overall": sentiment_label,
            "confidence": round(random.uniform(0.70, 0.90), 2) if self.mock_mode else 0.85,
            "anxiety_score": info["anxiety_score"],
            "satisfaction_score": info["satisfaction_score"],
            "key_evidence": key_evidence or info["description"],
            "b_strategy_impact": {
                "满意": "可推送升级/高端权益, 话术可积极",
                "中性": "按标准策略执行",
                "焦虑": "优先推荐低门槛分期, 话术需温和关怀",
                "不满": "避免频繁营销, 先推送安抚/补偿方案",
                "好奇": "推送详细介绍、对比优势, 引导转化",
            }.get(sentiment_label, "按标准策略执行"),
        }
