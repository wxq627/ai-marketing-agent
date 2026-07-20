"""
数据库存储层 v2 — db_store.py
============================
SQLite 实现 (与 PostgreSQL 接口兼容, 零安装)。
升级到 PostgreSQL: 改一行连接字符串即可。

v2 新增:
  - campaign_insert: 接收项目三创建的新活动
  - feedback_insert 增强: conversation事件实时更新客户动态记忆+意图
  - 实时信号追加到 customer_profile.significant_signals
"""

import os, sqlite3, pandas as pd, json
from datetime import datetime
from typing import List, Dict, Optional

BASE = os.path.dirname(os.path.abspath(__file__))
DB_PATH = os.path.join(BASE, "mock_data", "knowledge_agent.db")


def get_connection():
    conn = sqlite3.connect(DB_PATH, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA foreign_keys=ON")
    return conn


_conn = None
def db():
    global _conn
    if _conn is None: _conn = get_connection()
    return _conn


def init_db():
    conn = db()
    conn.executescript("""
    CREATE TABLE IF NOT EXISTS customers (
        oneid TEXT PRIMARY KEY, cust_id TEXT UNIQUE NOT NULL,
        name TEXT, gender TEXT, age INTEGER, city TEXT,
        occupation TEXT, income_level TEXT, education TEXT,
        lifecycle_stage TEXT, card_level TEXT, total_credit REAL,
        annual_consumption REAL, monthly_avg REAL, risk_level TEXT,
        value_level TEXT, activity_score INTEGER, dormancy_risk TEXT,
        search_keywords TEXT, browse_preferences TEXT,
        created_at TEXT DEFAULT (datetime('now')),
        updated_at TEXT DEFAULT (datetime('now'))
    );

    CREATE TABLE IF NOT EXISTS products (
        product_id TEXT PRIMARY KEY, product_name TEXT, card_level TEXT,
        annual_fee REAL, key_selling_points TEXT, target_income TEXT
    );

    CREATE TABLE IF NOT EXISTS benefits (
        benefit_id TEXT PRIMARY KEY, benefit_name TEXT,
        benefit_category TEXT, benefit_desc TEXT
    );

    CREATE TABLE IF NOT EXISTS campaigns (
        campaign_id TEXT PRIMARY KEY, campaign_name TEXT,
        start_date TEXT, end_date TEXT, budget REAL, rules TEXT
    );

    CREATE TABLE IF NOT EXISTS transactions (
        txn_id TEXT PRIMARY KEY, cust_id TEXT, card_no TEXT,
        txn_type TEXT, amount REAL, merchant_name TEXT,
        merchant_category TEXT, txn_channel TEXT,
        is_cross_border INTEGER, timestamp TEXT,
        FOREIGN KEY (cust_id) REFERENCES customers(cust_id)
    );

    CREATE TABLE IF NOT EXISTS feedback_events (
        event_id INTEGER PRIMARY KEY AUTOINCREMENT,
        oneid TEXT, event_type TEXT, campaign_id TEXT,
        channel TEXT, detail TEXT, timestamp TEXT,
        created_at TEXT DEFAULT (datetime('now'))
    );

    CREATE INDEX IF NOT EXISTS idx_feedback_oneid ON feedback_events(oneid);
    CREATE INDEX IF NOT EXISTS idx_feedback_type ON feedback_events(event_type);
    CREATE INDEX IF NOT EXISTS idx_feedback_campaign ON feedback_events(campaign_id);
    """)
    conn.commit()
    return True


# ================================================================
# 客户 CRUD
# ================================================================

def customer_search(filters: Dict = None, page: int = 1, page_size: int = 50) -> Dict:
    conn = db()
    where = ["1=1"]
    params = []
    if filters:
        for k, col in [("age_min","age"),("city","city"),("income_level","income_level"),
                       ("card_level","card_level"),("lifecycle_stage","lifecycle_stage"),
                       ("risk_level","risk_level"),("value_level","value_level")]:
            if k in filters and filters[k]:
                if isinstance(filters[k], list):
                    where.append(f"{col} IN ({','.join(['?']*len(filters[k]))})")
                    params.extend(filters[k])
    where_clause = " AND ".join(where)
    total = conn.execute(f"SELECT COUNT(*) FROM customers WHERE {where_clause}", params).fetchone()[0]
    offset = (page-1)*page_size
    rows = conn.execute(f"SELECT * FROM customers WHERE {where_clause} LIMIT ? OFFSET ?",
                        params+[page_size,offset]).fetchall()
    return {"total":total,"page":page,"page_size":page_size,
            "customers":[dict(r) for r in rows],
            "data_version":"db_v2.0","generated_at":datetime.now().isoformat()}

def customer_insert(cust_data: Dict) -> Dict:
    conn = db()
    try:
        cols = ", ".join(cust_data.keys())
        placeholders = ", ".join(["?" for _ in cust_data])
        conn.execute(f"INSERT OR REPLACE INTO customers ({cols}) VALUES ({placeholders})", list(cust_data.values()))
        conn.commit()
        return {"status":"ok","oneid":cust_data.get("oneid",""),"action":"insert"}
    except Exception as e:
        return {"status":"error","message":str(e)}

def customer_update(oneid: str, updates: Dict) -> Dict:
    conn = db()
    sets = ", ".join([f"{k}=?" for k in updates])
    conn.execute(f"UPDATE customers SET {sets}, updated_at=datetime('now') WHERE oneid=?", list(updates.values())+[oneid])
    conn.commit()
    return {"status":"ok","oneid":oneid}

def customer_get(oneid: str) -> Optional[Dict]:
    row = db().execute("SELECT * FROM customers WHERE oneid=?",[oneid]).fetchone()
    return dict(row) if row else None


# ================================================================
# 项目三回传 — 核心
# ================================================================

def campaign_insert(campaign: Dict) -> Dict:
    """接收项目三创建的新活动。"""
    conn = db()
    cid = campaign.get("campaign_id","")
    if not cid:
        return {"status":"error","message":"campaign_id is required"}
    conn.execute(
        "INSERT OR REPLACE INTO campaigns (campaign_id, campaign_name, start_date, end_date, budget, rules) "
        "VALUES (?,?,?,?,?,?)",
        [cid,
         campaign.get("campaign_name", campaign.get("name","")),
         campaign.get("start_date",""),
         campaign.get("end_date",""),
         campaign.get("budget",0),
         json.dumps(campaign.get("rules",{}), ensure_ascii=False)]
    )
    conn.commit()
    return {"status":"ok","campaign_id":cid,"action":"insert_or_update"}


def feedback_insert(event: Dict) -> Dict:
    """项目三回传统一入口 — 记录事件 + 实时更新客户动态记忆/意图。

    支持的事件类型及其效果:
      conversion    → 更新 customer_profile 年消费/月均
      click         → 记录活动点击"感兴趣"
      reject        → 记录活动点击"不感兴趣"
      conversation  → 实时更新: 搜索关键词, 浏览偏好, 关键事件, 预警信号
      browse        → 更新浏览偏好
    """
    conn = db()
    event_type = event.get("event_type", event.get("interaction_type", "unknown"))
    # oneid 兼容多种来源字段
    oneid = event.get("oneid") or event.get("session_id") or event.get("conversation_id") or ""

    # 构建 detail JSON
    detail_data = {}
    for k in ("summary","sentiment","intent","top_concerns","round_count",
              "user_response","agent_response","amount","channel_name"):
        v = event.get(k)
        if v is not None and v != "":
            detail_data[k] = v
    detail_str = json.dumps(detail_data, ensure_ascii=False) if detail_data else str(event.get("detail",""))

    # 写入 feedback_events
    conn.execute(
        "INSERT INTO feedback_events (oneid, event_type, campaign_id, channel, detail, timestamp) "
        "VALUES (?,?,?,?,?,?)",
        [oneid, event_type,
         event.get("campaign_id", event.get("campaign","")),
         event.get("channel", str(event.get("channel_name",""))),
         detail_str,
         event.get("timestamp", datetime.now().isoformat())]
    )
    conn.commit()

    # ── 实时更新 customer_profile ──
    updates = {}
    signals = []

    if event_type == "conversion":
        amt = 0
        if isinstance(event.get("detail"), dict):
            amt = event["detail"].get("amount", 0)
        elif isinstance(event.get("amount"), (int, float)):
            amt = event["amount"]
        if amt > 0:
            conn.execute(
                "UPDATE customer_profile SET value_annual_consumption=value_annual_consumption+?, "
                "value_monthly_avg_consumption=value_monthly_avg_consumption+? WHERE oneid=?",
                [amt, amt/12, oneid]
            )
            conn.commit()
            signals.append(f"实时转化+{amt}元")

    elif event_type == "conversation":
        intent = event.get("intent","")
        sentiment = event.get("sentiment","")
        concerns = event.get("top_concerns",[])
        summary = event.get("summary","")

        # 搜索关键词 (追加)
        if concerns:
            old = conn.execute("SELECT short_term_7d_top_search_keywords FROM customer_profile WHERE oneid=?",[oneid]).fetchone()
            old_str = (old[0] or "") if old else ""
            new_items = [c for c in concerns if c not in old_str]
            if new_items:
                updates["short_term_7d_top_search_keywords"] = (old_str+","+",".join(new_items)).strip(",")

        # 浏览偏好 (从intent推导)
        if intent and intent not in ("咨询","其他",""):
            old = conn.execute("SELECT mid_term_30d_browse_preferences FROM customer_profile WHERE oneid=?",[oneid]).fetchone()
            old_str = (old[0] or "") if old else ""
            tag = f"{intent}相关"
            if tag not in old_str:
                updates["mid_term_30d_browse_preferences"] = (old_str+","+tag).strip(",")

        # 关键事件
        if summary:
            old = conn.execute("SELECT key_milestones FROM customer_profile WHERE oneid=?",[oneid]).fetchone()
            old_str = (old[0] or "") if old else ""
            updates["key_milestones"] = (old_str+f"|对话:{summary[:50]}").strip("|")

        # 满意度/焦虑度 影响风险信号
        if sentiment in ("anxious","焦虑","不满","dissatisfied"):
            signals.append(f"对话负面情绪:{sentiment}")
        signals.append(f"对话:intent={intent},sentiment={sentiment}")

    elif event_type in ("click","reject"):
        campaign = event.get("campaign_id", event.get("campaign",""))
        action = "感兴趣" if event_type=="click" else "不感兴趣"
        signals.append(f"活动:{campaign[:25]}-{action}")

    # 批量 UPDATE
    if updates:
        sets = ", ".join([f"{k}=?" for k in updates])
        conn.execute(f"UPDATE customer_profile SET {sets} WHERE oneid=?", list(updates.values())+[oneid])
        conn.commit()

    # 追加实时信号
    if signals:
        old = conn.execute("SELECT long_term_90d_significant_signals FROM customer_profile WHERE oneid=?",[oneid]).fetchone()
        old_str = (old[0] or "") if old else ""
        new_sig = (old_str+"|"+"|".join(signals)).strip("|")
        conn.execute("UPDATE customer_profile SET long_term_90d_significant_signals=?, realtime_signal_count=realtime_signal_count+? WHERE oneid=?",
                     [new_sig, len(signals), oneid])
        conn.commit()

    return {
        "status":"ok",
        "event_type":event_type,
        "oneid":oneid,
        "profile_updated":list(updates.keys()),
        "signals":signals,
    }


# ================================================================
# 查询
# ================================================================

def get_products(): return db().execute("SELECT * FROM products").fetchall()
def get_benefits(): return db().execute("SELECT * FROM benefits").fetchall()
def get_campaigns(): return db().execute("SELECT * FROM campaigns").fetchall()
def get_recent_feedback(limit=20):
    return db().execute("SELECT * FROM feedback_events ORDER BY created_at DESC LIMIT ?",[limit]).fetchall()

def db_stats():
    conn = db()
    return {
        "customers": conn.execute("SELECT COUNT(*) FROM customers").fetchone()[0],
        "products": conn.execute("SELECT COUNT(*) FROM products").fetchone()[0],
        "benefits": conn.execute("SELECT COUNT(*) FROM benefits").fetchone()[0],
        "campaigns": conn.execute("SELECT COUNT(*) FROM campaigns").fetchone()[0],
        "feedback_events": conn.execute("SELECT COUNT(*) FROM feedback_events").fetchone()[0],
        "db_file": DB_PATH,
        "db_size_mb": round(os.path.getsize(DB_PATH)/1024/1024,1) if os.path.exists(DB_PATH) else 0,
    }
