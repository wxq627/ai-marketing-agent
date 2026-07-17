"""
客户画像 FastAPI 路由 — router_profile.py
===========================================
提供画像查询的 REST API，供项目二/三和前端大屏消费。

接口:
  GET  /api/v1/customer/{oneid}/profile     — 完整画像 (静态+动态)
  GET  /api/v1/customer/{oneid}/profile/static   — 仅静态画像
  GET  /api/v1/customer/{oneid}/profile/dynamic  — 仅动态记忆
  GET  /api/v1/customer/{oneid}/events           — 事件流 (支持时间窗口)
  POST /api/v1/customer/search              — 多条件客户搜索
"""

import os, json, pandas as pd
from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel, Field
from typing import List, Dict, Optional
from datetime import datetime

router = APIRouter(prefix="/api/v1/customer", tags=["CustomerProfile"])

# 全局数据加载
_data = None

def load_data():
    global _data
    if _data is None:
        s = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                         "mock_data", "structured")
        _data = {
            "profile": pd.read_csv(os.path.join(s, "customer_profile.csv")),
            "cards": pd.read_csv(os.path.join(s, "credit_card.csv")),
            "txn": pd.read_csv(os.path.join(s, "transaction_log.csv")),
            "app": pd.read_csv(os.path.join(s, "app_events.csv")),
            "consent": pd.read_csv(os.path.join(s, "customer_consent.csv")),
            "crm": pd.read_csv(os.path.join(s, "crm_customer.csv")),
            "attr": pd.read_csv(os.path.join(s, "campaign_attribution.csv")),
            "perf": pd.read_csv(os.path.join(s, "campaign_performance.csv")),
        }
        # 预计算索引
        _data["oneid_index"] = dict(zip(_data["profile"]["oneid"],
                                        range(len(_data["profile"]))))
    return _data


# ================================================================
# Pydantic Models
# ================================================================

class ProfileResponse(BaseModel):
    oneid: str
    cust_id: str
    static_profile: Dict
    dynamic_memory: Dict
    events: List[Dict] = []
    generated_at: str

class SearchRequest(BaseModel):
    filters: Dict = Field(default={}, description="筛选条件")
    page: int = 1
    page_size: int = 20


# ================================================================
# API-01: 完整画像
# ================================================================

@router.get("/{oneid}/profile", summary="获取客户完整画像（静态+动态）")
def get_full_profile(oneid: str):
    """返回客户的静态画像 + 动态记忆 + 近期事件。"""
    data = load_data()
    idx = data["oneid_index"].get(oneid)
    if idx is None:
        raise HTTPException(404, f"OneID not found: {oneid}")

    row = data["profile"].iloc[idx]
    cust_id = row["cust_id"]

    # 静态部分
    static = {}
    for section in ["demographics", "account", "lifecycle", "risk", "value"]:
        static[section] = {}
        for col in data["profile"].columns:
            if col.startswith(f"{section}_"):
                key = col.replace(f"{section}_", "")
                val = row[col]
                static[section][key] = val if not (isinstance(val, float) and str(val) == 'nan') else None

    # 动态部分
    dynamic = {"realtime": {}, "short_term_7d": {}, "mid_term_30d": {}, "long_term_90d": {}}
    for window in dynamic:
        for col in data["profile"].columns:
            if col.startswith(f"{window}_"):
                key = col.replace(f"{window}_", "")
                val = row[col]
                dynamic[window][key] = val if not (isinstance(val, float) and str(val) == 'nan') else None

    # 近期事件
    events = []
    txn_df = data["txn"]
    cards_df = data["cards"]
    card_to_cust = dict(zip(cards_df["card_no"], cards_df["cust_id"]))
    txn_df["cust_id_mapped"] = txn_df["card_no"].map(card_to_cust)
    cust_txn = txn_df[txn_df["cust_id_mapped"] == cust_id].tail(10)
    for _, t in cust_txn.iterrows():
        events.append({
            "type": t["txn_type"],
            "amount": float(t["amount"]),
            "merchant": str(t["merchant_name"]),
            "channel": str(t["txn_channel"]),
            "time": str(t["timestamp"]),
            "is_cross_border": bool(t["is_cross_border"]),
        })

    return {
        "oneid": oneid,
        "cust_id": cust_id,
        "static_profile": static,
        "dynamic_memory": dynamic,
        "events": events[-20:],
        "generated_at": row.get("generated_at", ""),
    }


# ================================================================
# API-02/03: 分维度查询
# ================================================================

@router.get("/{oneid}/profile/static", summary="仅静态画像")
def get_static_profile(oneid: str):
    r = get_full_profile(oneid)
    return {"oneid": oneid, "static_profile": r["static_profile"]}

@router.get("/{oneid}/profile/dynamic", summary="仅动态记忆")
def get_dynamic_memory(oneid: str):
    r = get_full_profile(oneid)
    return {"oneid": oneid, "dynamic_memory": r["dynamic_memory"]}


# ================================================================
# API-04: 事件流
# ================================================================

@router.get("/{oneid}/events", summary="客户事件流（支持时间窗口）")
def get_events(oneid: str, window: str = "30d", limit: int = 50):
    data = load_data()
    idx = data["oneid_index"].get(oneid)
    if idx is None:
        raise HTTPException(404, f"OneID not found: {oneid}")
    cust_id = data["profile"].iloc[idx]["cust_id"]

    cards_df = data["cards"]
    card_to_cust = dict(zip(cards_df["card_no"], cards_df["cust_id"]))
    txn_df = data["txn"].copy()
    txn_df["cust_id_mapped"] = txn_df["card_no"].map(card_to_cust)

    # 时间窗口
    ref = datetime(2026, 7, 15)
    days = {"7d": 7, "30d": 30, "90d": 90}.get(window, 30)
    cutoff = (ref - pd.Timedelta(days=days)).strftime("%Y-%m-%d")

    cust_txn = txn_df[(txn_df["cust_id_mapped"] == cust_id) & (txn_df["timestamp"] >= cutoff)]

    events = []
    for _, t in cust_txn.tail(limit).iterrows():
        events.append({
            "type": t["txn_type"],
            "amount": float(t["amount"]),
            "merchant": str(t["merchant_name"]),
            "category": str(t["merchant_category"]),
            "channel": str(t["txn_channel"]),
            "time": str(t["timestamp"]),
        })

    return {"oneid": oneid, "window": window, "total": len(cust_txn), "events": events}


# ================================================================
# API-05: 搜索
# ================================================================

@router.post("/search", summary="客户搜索与圈选")
def search_customers(req: SearchRequest):
    data = load_data()
    df = data["profile"].copy()
    filters = req.filters

    if "age_min" in filters:
        df = df[df["demographics_age"] >= filters["age_min"]]
    if "age_max" in filters:
        df = df[df["demographics_age"] <= filters["age_max"]]
    if "city" in filters:
        df = df[df["demographics_city"].isin(filters["city"])]
    if "income_level" in filters:
        df = df[df["demographics_income_level"].isin(filters["income_level"])]
    if "lifecycle_stage" in filters:
        df = df[df["lifecycle_stage"].isin(filters["lifecycle_stage"])]
    if "risk_level" in filters:
        df = df[df["risk_risk_level"].isin(filters["risk_level"])]
    if "value_level" in filters:
        df = df[df["value_value_level"].isin(filters["value_level"])]
    if "card_level" in filters:
        df = df[df["account_primary_card_level"].isin(filters["card_level"])]

    total = len(df)
    start = (req.page - 1) * req.page_size
    end = start + req.page_size
    page_data = df.iloc[start:end]

    return {
        "total": total,
        "page": req.page,
        "page_size": req.page_size,
        "customers": page_data[["oneid", "cust_id", "demographics_name", "demographics_city",
                                  "account_primary_card_level", "lifecycle_stage",
                                  "risk_risk_level", "value_value_level"]].to_dict(orient="records"),
    }


# ================================================================
# C→A 反馈接口 (项目三回传)
# ================================================================

class FeedbackEvent(BaseModel):
    oneid: str
    event_type: str = Field(..., description="conversation_summary|click_event|conversion_event|impression_event|complaint_event|unsubscribe_event")
    campaign_id: str = ""
    channel: str = ""
    detail: Dict = Field(default={}, description="事件详情")
    timestamp: str = ""

class FeedbackResponse(BaseModel):
    status: str
    oneid: str
    profile_updates: Dict
    intent_update: Dict = {}
    triggered_alerts: List[str] = []


@router.post("/feedback/simulate", response_model=FeedbackResponse,
             summary="项目三反馈模拟 — C→A 回传接口",
             description="模拟项目三 Marketing Agent 回传客户行为事件。支持对话摘要/点击/转化/投诉/退订。")
def simulate_feedback(event: FeedbackEvent):
    """接收项目三回传的客户行为事件, 模拟画像实时更新。"""
    data = load_data()
    profile = data["profile"]
    oneid = event.oneid
    idx = data["oneid_index"].get(oneid)
    if idx is None:
        raise HTTPException(404, f"OneID not found: {oneid}")

    row = profile.iloc[idx]
    updates = {}
    alerts = []

    etype = event.event_type

    if etype == "click_event":
        updates["realtime_signal_count"] = "+1"
        updates["short_term_engagement"] = "1h内微批更新"
    elif etype == "conversion_event":
        amount = event.detail.get("amount", 0)
        updates["realtime_signal_count"] = "+2 (含大额标记)"
        updates["value_monthly_avg"] = f"下次T+1批量更新纳入 ¥{amount}"
        updates["intent_rescore"] = "意图评分-30 (需求被满足)"
        alerts.append("B端感知: 该客户转化成功, 可推送升级/交叉销售")
    elif etype == "impression_event":
        updates["realtime_impression_count"] = "+1"
        updates["frequency_counter"] = "触达频控计数+1"
    elif etype == "complaint_event":
        updates["risk_churn_risk_score"] = "+25"
        updates["risk_level"] = "重新评估: 可能升至medium/high"
        updates["channel_block"] = "自动降频: 暂停该渠道30天"
        alerts.append("投诉预警: churn_risk+25, 自动降频")
        alerts.append("DNC候选: 如累计投诉≥3次, 标记do_not_contact")
    elif etype == "unsubscribe_event":
        channel = event.detail.get("channel", event.channel)
        updates["consent_update"] = f"{channel}_consent → false"
        updates["channel_block"] = f"永久禁止{channel}"
        alerts.append(f"退订: 永久禁止{channel}触达")
    elif etype == "conversation_summary":
        updates["intent_vector"] = "LLM重算意图向量"
        updates["sentiment"] = event.detail.get("sentiment", "neutral")
        updates["event_timeline"] = "对话摘要已追加"

    return {
        "status": "accepted",
        "oneid": oneid,
        "profile_updates": updates,
        "intent_update": {"primary_intent": "分期/借贷需求", "score_delta": -15} if etype == "conversation_summary" else {},
        "triggered_alerts": alerts,
    }


@router.get("/feedback/log",
            summary="查看反馈更新日志")
def get_feedback_log(limit: int = 20):
    """返回最近的反馈更新记录。"""
    data = load_data()
    return {"total": 0, "log": [], "note": "实时日志在Streamlit session中, API层面下次实现持久化"}
