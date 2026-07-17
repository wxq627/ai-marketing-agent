"""
意图识别 API 路由 — router_intent.py
=======================================
提供意图向量查询接口, 供项目二/三调用。

接口:
  GET /api/v1/customer/{oneid}/intent    — 完整意图向量
  POST /api/v1/intent/classify           — 对话文本意图分类
  POST /api/v1/intent/batch              — 批量意图查询
"""

import os, sys, json, random, pandas as pd
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field
from typing import List, Dict, Optional
from datetime import datetime

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from intent_engine.rule_scorer import RuleScorer
from intent_engine.llm_classifier import LLMClassifier, SentimentAnalyzer

router = APIRouter(prefix="/api/v1", tags=["Intent"])
_scorer = None
_classifier = None
_analyzer = None
_data = None

def get_scorer():
    global _scorer
    if _scorer is None: _scorer = RuleScorer()
    return _scorer

def get_classifier():
    global _classifier
    if _classifier is None: _classifier = LLMClassifier(mock_mode=True)
    return _classifier

def get_analyzer():
    global _analyzer
    if _analyzer is None: _analyzer = SentimentAnalyzer(mock_mode=True)
    return _analyzer

def load_data():
    global _data
    if _data is None:
        s = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                         "mock_data", "structured")
        _data = {
            "snapshot": pd.read_csv(os.path.join(s, "customer_snapshot.csv")),
            "intent": pd.read_csv(os.path.join(s, "intent_vector.csv")),
            "events": pd.read_csv(os.path.join(s, "event_sequence_per_customer.csv")),
            "profile": pd.read_csv(os.path.join(s, "customer_profile.csv")),
        }
    return _data

class ClassifyRequest(BaseModel):
    conversation_text: str
    oneid: Optional[str] = None

class BatchRequest(BaseModel):
    oneids: List[str]

# ================================================================
# API-01: 意图向量查询
# ================================================================
@router.get("/customer/{oneid}/intent", summary="查询客户意图向量")
def get_intent(oneid: str):
    """返回完整 IntentVector: 6类意图评分 + 子信号 + 情感 + 趋势"""
    data = load_data()
    profile = data["profile"]
    if oneid not in profile.index:
        raise HTTPException(404, f"OneID not found: {oneid}")

    # 从预生成的intent_vector读取
    intent_df = data["intent"]
    profile_df = data["profile"]
    # 通过oneid找行
    p_row = profile_df[profile_df["oneid"] == oneid]
    if len(p_row) == 0:
        raise HTTPException(404, f"OneID not found: {oneid}")
    cid = p_row.iloc[0]["cust_id"]

    # 找到该客户的intent记录
    intent_rows = intent_df[intent_df["cust_id"] == cid]
    intent_row = intent_rows.iloc[0] if len(intent_rows) > 0 else None

    if intent_row is not None:
        scores = json.loads(intent_row["intent_json"]) if isinstance(intent_row["intent_json"], str) else {}
        intents = []
        for itype, score in scores.items():
            conf = "high" if score >= 70 else ("medium" if score >= 40 else "low")
            intents.append({"type": itype, "score": score, "confidence": conf, "trend": "stable"})

        analyzer = get_analyzer()
        sentiment = analyzer.analyze("中性", f"基于画像数据的综合评估")

        return {
            "oneid": oneid,
            "cust_id": cid,
            "updated_at": datetime.now().strftime("%Y-%m-%dT%H:%M:%SZ"),
            "intents": intents,
            "primary_intent": intent_row["primary_intent"] if isinstance(intent_row, pd.Series) else "",
            "sentiment": {
                "overall": "neutral",
                "confidence": 0.75,
                "anxiety_score": random.randint(10, 60),
                "satisfaction_score": random.randint(30, 70),
                "key_evidence": "基于搜索关键词和生命周期综合评估",
            },
        }

    # 如果没有预生成数据, 用规则引擎实时计算
    scorer = get_scorer()
    p_dict = p_row.iloc[0].to_dict()
    events_data = {
        "search_keywords": str(p_dict.get("search_keywords_7d", "")),
        "browse_pages": str(p_dict.get("browse_preferences_30d", "")),
        "overdue_count": int(p_dict.get("history_overdue_count", 0)),
        "min_payment_count": int(p_dict.get("min_payment_count", 0)),
        "complaint_count": int(p_dict.get("complaint_count_90d", 0)),
        "cross_border_count": 0,
    }
    result = scorer.score_all(p_dict, events_data)
    return {"oneid": oneid, "updated_at": datetime.now().strftime("%Y-%m-%dT%H:%M:%SZ"), **result}

# ================================================================
# API-02: 对话文本意图分类
# ================================================================
@router.post("/intent/classify", summary="对话文本意图分类 (LLM/Mock)")
def classify_text(req: ClassifyRequest):
    """输入对话文本, 输出意图+情感分类"""
    classifier = get_classifier()
    analyzer = get_analyzer()

    llm_result = classifier.classify(req.conversation_text)
    sentiment = analyzer.analyze(llm_result["sentiment"], "对话关键词: " + ", ".join(llm_result.get("key_phrases", [])))

    return {
        "primary_intent": llm_result["primary_intent"],
        "intent_score": llm_result["intent_score"],
        "all_intents": llm_result.get("all_intents", {}),
        "sentiment": sentiment,
        "urgency": llm_result.get("urgency", "中"),
        "key_phrases": llm_result.get("key_phrases", []),
    }

# ================================================================
# API-03: 批量意图查询
# ================================================================
@router.post("/intent/batch", summary="批量意图查询")
def batch_intent(req: BatchRequest):
    results = {}
    for oid in req.oneids:
        try:
            results[oid] = get_intent(oid)
        except:
            results[oid] = {"error": "not found"}
    return {"total": len(req.oneids), "results": results}
