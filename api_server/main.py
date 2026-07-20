"""
项目一 Knowledge Agent — API服务 (可直接运行)
================================================
为项目二 Strategy Agent 提供5个核心接口, 全部基于真实CSV数据。

启动: cd XX银行 && python -m api_server.main
文档: http://localhost:8000/docs (Swagger UI)
"""
import os, sys, json, math, pandas as pd
from datetime import datetime
from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field
from typing import List, Dict, Optional

def safe_val(v, default=None):
    """清理NaN/Inf值,确保JSON可序列化"""
    if v is None: return default
    if isinstance(v, float):
        if math.isnan(v) or math.isinf(v): return default
    return v

def clean_json(obj):
    """递归清理对象中的NaN/Inf"""
    if isinstance(obj, dict):
        return {k: clean_json(v) for k, v in obj.items()}
    elif isinstance(obj, list):
        return [clean_json(v) for v in obj]
    elif isinstance(obj, float):
        if math.isnan(obj) or math.isinf(obj): return 0.0
        return obj
    return obj

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA = os.path.join(BASE, "mock_data", "structured")
sys.path.insert(0, BASE)
from db_store import (customer_search as db_search, customer_insert, customer_update, customer_get,
                      feedback_insert, get_products, get_benefits, get_campaigns, get_recent_feedback, db_stats)

app = FastAPI(title="Knowledge Agent API", version="1.0.0",
              description="项目一 -> 项目二 数据供给接口。所有数据基于XX银行信用卡中心真实体系。")
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])

# ================================================================
# 启动时加载数据到内存
# ================================================================
_data = {}

@app.on_event("startup")
def load():
    s = DATA
    _data["snapshot"] = pd.read_csv(os.path.join(s, "customer_snapshot.csv"))
    _data["intent"] = pd.read_csv(os.path.join(s, "intent_vector.csv"))
    _data["events"] = pd.read_csv(os.path.join(s, "event_sequence_per_customer.csv"))
    _data["consent"] = pd.read_csv(os.path.join(s, "customer_consent.csv"))
    _data["contact"] = pd.read_csv(os.path.join(s, "contact_history.csv"))
    _data["products"] = pd.read_csv(os.path.join(s, "product_catalog.csv"))
    _data["benefits"] = pd.read_csv(os.path.join(s, "benefit_catalog.csv"))
    _data["eligibility"] = pd.read_csv(os.path.join(s, "product_eligibility.csv"))
    _data["channels"] = pd.read_csv(os.path.join(s, "channel_config.csv"))
    _data["attr"] = pd.read_csv(os.path.join(s, "campaign_attribution.csv"))
    _data["perf"] = pd.read_csv(os.path.join(s, "campaign_performance.csv"))
    _data["id_map"] = pd.read_csv(os.path.join(s, "id_mapping.csv"))
    # 加载频控规则
    freq_path = os.path.join(BASE, "mock_data", "unstructured", "frequency_rules.json")
    with open(freq_path, "r", encoding="utf-8") as f:
        _data["freq_rules"] = json.load(f)
    # 构建索引
    _data["snap_idx"] = dict(zip(_data["snapshot"]["cust_id"], range(len(_data["snapshot"]))))
    # 手机号->cust_id
    mp = _data["id_map"]
    _data["phone_to_cust"] = dict(zip(mp[mp["id_type"]=="phone"]["id_value"],
                                       mp[mp["id_type"]=="phone"]["oneid"]))
    print(f"API服务启动完成: {len(_data['snapshot'])} 客户已加载")

# ================================================================
# Pydantic Models
# ================================================================
class SearchRequest(BaseModel):
    cust_ids: Optional[List[str]] = None
    oneids: Optional[List[str]] = None
    age_min: Optional[int] = None
    age_max: Optional[int] = None
    city: Optional[List[str]] = None
    income_level: Optional[List[str]] = None
    lifecycle_stage: Optional[List[str]] = None
    card_level: Optional[List[str]] = None
    risk_level: Optional[List[str]] = None
    value_level: Optional[List[str]] = None
    marketing_consent: Optional[bool] = None
    exclude_dnc: bool = True
    exclude_blacklist: bool = True
    intent_type: Optional[str] = None
    intent_score_min: Optional[int] = None
    page: int = 1
    page_size: int = 50

class FreqCheckRequest(BaseModel):
    cust_ids: List[str]
    planned_channel: str = ""

# ================================================================
# API-01: 客户搜索 & 批量洞察
# ================================================================
@app.post("/api/v1/customer/search", summary="客户搜索与批量洞察快照")
def search_customers(req: SearchRequest):
    df = _data["snapshot"].copy()
    intent_df = _data["intent"].copy()

    # 过滤
    if req.cust_ids: df = df[df["cust_id"].isin(req.cust_ids)]
    if req.oneids: df = df[df["oneid"].isin(req.oneids)]
    if req.age_min is not None: df = df[df["age"] >= req.age_min]
    if req.age_max is not None: df = df[df["age"] <= req.age_max]
    if req.city: df = df[df["city"].isin(req.city)]
    if req.income_level: df = df[df["income_level"].isin(req.income_level)]
    if req.lifecycle_stage: df = df[df["lifecycle_stage"].isin(req.lifecycle_stage)]
    if req.card_level: df = df[df["card_level"].isin(req.card_level)]
    if req.risk_level: df = df[df["risk_level"].isin(req.risk_level)]
    if req.value_level: df = df[df["value_level"].isin(req.value_level)]
    if req.marketing_consent is not None: df = df[df["marketing_consent"] == req.marketing_consent]
    if req.exclude_dnc: df = df[df["dnc_list"] == False]
    if req.exclude_blacklist: df = df[df["blacklist_flag"] == False]

    total = len(df)
    start = (req.page - 1) * req.page_size
    page_df = df.iloc[start:start + req.page_size]

    # 关联意图
    cust_ids = page_df["cust_id"].tolist()
    rel_intent = intent_df[intent_df["cust_id"].isin(cust_ids)]

    customers = []
    for _, row in page_df.iterrows():
        cid = row["cust_id"]
        it = rel_intent[rel_intent["cust_id"]==cid]
        intent_data = {}
        if len(it) > 0:
            ir = it.iloc[0]
            intent_data = {"primary_intent": ir["primary_intent"],
                           "intents": json.loads(ir["intent_json"]) if isinstance(ir["intent_json"], str) else ir["intent_json"]}

        customers.append({
            "cust_id": cid, "oneid": row["oneid"],
            "profile": {
                "age": int(row["age"]), "city": row["city"],
                "income_level": row["income_level"], "lifecycle_stage": row["lifecycle_stage"],
                "vip_tier": row["vip_tier"],
            },
            "account": {
                "card_level": row["card_level"], "product_name": row["product_name"],
                "total_credit_amount": safe_val(float(row["total_credit_amount"]),0),
                "card_count": int(row["card_count"]), "usage_rate": float(row["usage_rate"]),
            },
            "consumption": {
                "annual": float(row["annual_consumption"]),
                "monthly_avg": float(row["monthly_avg_consumption"]),
                "cons_90d": float(row["cons_90d"]), "cons_30d": float(row["cons_30d"]),
                "cons_7d": float(row["cons_7d"]),
                "trend": row["consumption_trend"],
                "active_days_90d": int(row["active_days_90d"]),
                "activity_score": int(row["activity_score"]),
            },
            "risk": {
                "overdue_status": row["overdue_status"],
                "churn_risk_score": int(row["churn_risk_score"]),
                "risk_level": row["risk_level"],
                "dormancy_risk": row["dormancy_risk"],
            },
            "tags": {
                "value_level": row["value_level"],
                "significant_signals": row["significant_signals"],
                "search_keywords_7d": row["search_keywords_7d"],
            },
            "consent": {
                "marketing_consent": bool(row["marketing_consent"]),
                "dnc_list": bool(row["dnc_list"]),
                "do_not_contact": bool(row["do_not_contact"]),
                "blacklist_flag": bool(row["blacklist_flag"]),
                "push_consent": bool(row["push_consent"]),
                "sms_consent": bool(row["sms_consent"]),
                "wechat_consent": bool(row["wechat_consent"]),
                "phone_consent": bool(row["phone_consent"]),
                "complaint_count_90d": int(row["complaint_count_90d"]),
            },
            "intent": intent_data,
        })

    return clean_json({
        "total": total, "page": req.page, "page_size": req.page_size,
        "data_version": "v1.0",
        "generated_at": datetime.now().strftime("%Y-%m-%dT%H:%M:%S+08:00"),
        "customers": customers,
    })

# ================================================================
# API-02: 频控检查
# ================================================================
@app.post("/api/v1/customer/frequency-check", summary="批量频控状态检查")
def freq_check(req: FreqCheckRequest):
    contact = _data["contact"]
    consent = _data["consent"].set_index("cust_id")
    freq_rules = _data["freq_rules"]
    contact["contact_time"] = pd.to_datetime(contact["contact_time"])
    ref = pd.Timestamp("2026-07-17")

    results = []
    for cid in req.cust_ids:
        cn = consent.loc[cid] if cid in consent.index else None
        if cn is None:
            results.append({"cust_id": cid, "can_send": True, "available_channels": [], "error": "customer not found"})
            continue

        # 硬门槛
        if not bool(cn["marketing_consent"]) or bool(cn["blacklist_flag"]) or bool(cn["do_not_contact_signal"]):
            results.append({
                "cust_id": cid, "can_send": False,
                "block_reason": "marketing_consent=false" if not bool(cn["marketing_consent"])
                    else "blacklist" if bool(cn["blacklist_flag"]) else "do_not_contact",
                "available_channels": [],
            })
            continue

        # 频控统计
        cust_contact = contact[contact["cust_id"]==cid]
        cnt_1d = len(cust_contact[cust_contact["contact_time"] >= ref - pd.Timedelta(days=1)])
        cnt_7d = len(cust_contact[cust_contact["contact_time"] >= ref - pd.Timedelta(days=7)])
        cnt_30d = len(cust_contact[cust_contact["contact_time"] >= ref - pd.Timedelta(days=30)])

        defaults = freq_rules["default_rules"]
        can_send_global = cnt_1d < defaults["global_max_per_day"] and cnt_7d < defaults["global_max_per_week"]

        # 可用渠道
        avail = []
        if bool(cn["push_consent"]): avail.append("APP Push")
        if bool(cn["sms_consent"]): avail.append("短信")
        if bool(cn["wechat_consent"]): avail.append("微信公众号")
        if bool(cn["email_consent"]): avail.append("邮件")
        if bool(cn["phone_consent"]): avail.append("电话外呼")

        # 退订渠道
        unsub = str(cn.get("unsubscribe_channels","")).split(",") if cn.get("unsubscribe_channels") else []
        unsub = [u.strip() for u in unsub if u.strip()]
        blocked = [u for u in unsub]

        results.append({
            "cust_id": cid,
            "can_send": can_send_global,
            "available_channels": [c for c in avail if c not in blocked],
            "blocked_channels": blocked,
            "contact_count": {"1d": cnt_1d, "7d": cnt_7d, "30d": cnt_30d},
            "limits": defaults,
        })

    return {"checked_at": datetime.now().strftime("%Y-%m-%dT%H:%M:%S+08:00"), "results": results}

# ================================================================
# API-03: 知识检索
# ================================================================
@app.get("/api/v1/knowledge/search", summary="知识检索: 产品/权益/资格/合规")
def knowledge_search(q: str = Query("", description="搜索关键词, 如'白金卡'或'分期'"), top_k: int = 10):
    products = _data["products"]
    benefits = _data["benefits"]
    eligibility = _data["eligibility"]

    # 简单关键词匹配
    results = []
    # 产品匹配
    for _, p in products.iterrows():
        if q.lower() in str(p["product_name"]).lower() or q in str(p["card_level"]):
            results.append({"type": "product", "id": p["product_id"],
                           "name": p["product_name"], "card_level": p["card_level"],
                           "annual_fee": int(p["annual_fee"]), "selling_points": p["key_selling_points"]})
    # 权益匹配
    for _, b in benefits.iterrows():
        if q.lower() in str(b["benefit_name"]).lower() or q in str(b["benefit_category"]):
            results.append({"type": "benefit", "id": b["benefit_id"],
                           "name": b["benefit_name"], "category": b["benefit_category"],
                           "desc": str(b["benefit_desc"])[:100]})

    return {"query": q, "total": len(results), "results": results[:top_k]}

# ================================================================
# API-04: 渠道上下文
# ================================================================
@app.get("/api/v1/channels/context", summary="渠道成本/容量/效果")
def channel_context():
    ch = _data["channels"]
    channels = []
    for _, c in ch.iterrows():
        channels.append({
            "code": c["channel_code"], "name": c["channel_name"],
            "cost_per_send": float(c["cost_per_send"]),
            "daily_capacity": int(c["daily_capacity"]),
            "monthly_capacity": int(c["monthly_capacity"]),
            "avg_open_rate": float(c["avg_open_rate"]),
            "avg_click_rate": float(c["avg_click_rate"]),
            "requires_consent": bool(c["requires_consent"]),
            "status": c["status"],
        })
    return {"channels": channels, "updated_at": datetime.now().strftime("%Y-%m-%dT%H:%M:%S+08:00")}

# ================================================================
# API-05: 活动效果查询
# ================================================================
@app.get("/api/v1/campaign/performance", summary="历史活动ROI/转化/归因")
def campaign_performance(campaign_id: str = ""):
    perf = _data["perf"]
    if campaign_id:
        perf = perf[perf["campaign_id"]==campaign_id]
    results = []
    for _, r in perf.iterrows():
        results.append({
            "campaign_id": r["campaign_id"], "campaign_name": r["campaign_name"],
            "budget": int(r["budget"]), "actual_touches": int(r["actual_touches"]),
            "clicks": int(r["clicks"]), "conversions": int(r["conversions"]),
            "total_cost": float(r["total_cost"]),
            "attributed_revenue": float(r["attributed_revenue"]),
            "roi": float(r["roi"]), "cpa": float(r["cpa"]),
        })
    return {"total": len(results), "results": results}

# ================================================================
# 健康检查
# ================================================================
# ---- 集成意图引擎 + 知识图谱路由 ----
sys.path.insert(0, os.path.dirname(BASE))
from intent_engine.router_intent import router as intent_router
from graphrag.router_knowledge import router as knowledge_router
app.include_router(intent_router)
app.include_router(knowledge_router)

# ================================================================
# DB 持久化端点 (SQLite, 升级PG改连接字符串即可)
# ================================================================

@app.get("/api/v1/db/stats", summary="DB统计 (8000客户已持久化)")
def db_statistics():
    return db_stats()

@app.post("/api/v1/db/customer/search", summary="DB客户搜索 (SQL查询, 增量快)")
def db_customer_search(req: SearchRequest):
    filters = {}
    if req.age_min is not None: filters["age_min"] = req.age_min
    if req.age_max is not None: filters["age_max"] = req.age_max
    if req.city: filters["city"] = req.city
    if req.income_level: filters["income_level"] = req.income_level
    if req.card_level: filters["card_level"] = req.card_level
    if req.lifecycle_stage: filters["lifecycle_stage"] = req.lifecycle_stage
    if req.risk_level: filters["risk_level"] = req.risk_level
    if req.value_level: filters["value_level"] = req.value_level
    return db_search(filters, req.page, req.page_size)

@app.post("/api/v1/db/customer/import", summary="批量导入客户 (INSERT增量)")
def db_customer_import(customers: List[Dict]):
    results = []
    for c in customers:
        r = customer_insert(c)
        results.append(r)
    return {"imported": len(results), "results": results}

@app.post("/api/v1/db/feedback/import", summary="导入项目二三回传数据 (INSERT增量+实时更新画像)")
def db_feedback_import(events: List[Dict]):
    results = []
    for e in events:
        r = feedback_insert(e)
        results.append(r)
    return {"imported": len(results), "results": results, "note": "转化事件自动更新客户年消费/月均"}

@app.get("/api/v1/db/feedback/recent", summary="查询最近回传记录")
def db_feedback_recent(limit: int = 20):
    return {"events": [dict(r) for r in get_recent_feedback(limit)]}


@app.get("/api/v1/health")
def health():
    stats = db_stats() if os.path.exists(os.path.join(BASE, "mock_data", "knowledge_agent.db")) else {}
    return {"status": "ok", "customers_loaded": stats.get("customers", 8000),
            "db_size_mb": stats.get("db_size_mb", 0),
            "version": "2.0.0", "backend": "SQLite (PG兼容)", "time": datetime.now().isoformat()}

if __name__ == "__main__":
    import uvicorn
    uvicorn.run("api_server.main:app", host="0.0.0.0", port=8000, reload=False)
