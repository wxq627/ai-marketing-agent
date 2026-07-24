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

import os, re, sqlite3, pandas as pd, json
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
    """新增客户 — 完全新用户(从未办卡, 无历史记录) → customer_profile 表。

    强制默认:
      - lifecycle_stage = '新户' (刚开户)
      - 所有历史字段为空/零 (无搜索/浏览/消费/逾期记录)
      - 开户时长=0, 活跃度=初始值10
    """
    conn = db()
    # 新用户强制默认值
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    defaults = {
        "lifecycle_stage": "新户", "lifecycle_months_since_open": 0,
        "account_tenure_months": 0, "account_card_count": 1, "account_active_cards": 1,
        "account_usage_rate": 0.0, "account_used_amount": 0,
        "value_annual_consumption": 0, "value_monthly_avg_consumption": 0,
        "value_max_single_transaction": 0, "value_transaction_count_12m": 0,
        "value_installment_contribution_12m": 0, "value_value_level": "low",
        "risk_risk_level": "low", "risk_overdue_status": "M0",
        "risk_history_overdue_count_6m": 0, "risk_min_payment_frequency_6m": 0,
        "risk_churn_risk_score": 0, "risk_blacklist_flag": 0, "risk_do_not_contact": 0,
        "risk_cash_advance_risk_score": 0,
        "long_term_90d_total_consumption": 0, "long_term_90d_txn_count": 0,
        "long_term_90d_active_days": 0, "long_term_90d_activity_score": 10,
        "long_term_90d_dormancy_risk": "low", "long_term_90d_significant_signals": "新户开户",
        "long_term_90d_monthly_avg_90d": 0,
        "mid_term_30d_total_consumption": 0, "mid_term_30d_txn_count": 0,
        "mid_term_30d_active_days": 0, "mid_term_30d_consumption_trend": "stable",
        "mid_term_30d_trend_change_pct": 0, "mid_term_30d_browse_preferences": "",
        "short_term_7d_total_consumption": 0, "short_term_7d_txn_count": 0,
        "short_term_7d_active_days": 0, "short_term_7d_top_search_keywords": "",
        "short_term_7d_avg_daily_spend": 0,
        "realtime_signal_count": 0, "realtime_has_high_value_txn": 0,
        "key_milestones": "新户开户",
        "generated_at": now, "update_type": "manual_new",
        "lifecycle_vip_tier": "普通", "lifecycle_customer_manager": "",
        "demographics_gender": "M", "demographics_education": "本科",
        "demographics_occupation": "其他", "account_product_name": "",
    }
    final = {**defaults, **cust_data}
    # 强制锁死: 新用户必须是新户
    for k in ("lifecycle_stage","lifecycle_months_since_open","account_tenure_months",
              "risk_overdue_status","risk_risk_level"):
        final[k] = defaults[k]
    final["key_milestones"] = "新户开户"
    final["long_term_90d_significant_signals"] = "新户开户"

    try:
        cols = ", ".join(final.keys())
        placeholders = ", ".join(["?" for _ in final])
        conn.execute(f"INSERT OR REPLACE INTO customer_profile ({cols}) VALUES ({placeholders})",
                     list(final.values()))
        conn.commit()
        return {"status":"ok","oneid":final.get("oneid",""),"action":"insert_new_customer"}
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
    """接收项目三创建/更新的活动。支持全部9个字段。"""
    conn = db()
    cid = campaign.get("campaign_id","")
    if not cid:
        return {"status":"error","message":"campaign_id is required"}
    # 安全序列化JSON字段
    def _safe_json(v, default="{}"):
        if v is None:
            return default
        if isinstance(v, str):
            return v  # 已经是JSON字符串
        return json.dumps(v, ensure_ascii=False)
    conn.execute(
        "INSERT OR REPLACE INTO campaigns "
        "(campaign_id, campaign_name, start_date, end_date, target_segment, rules, budget, expected_reach, campaign_poster_path) "
        "VALUES (?,?,?,?,?,?,?,?,?)",
        [cid,
         campaign.get("campaign_name", campaign.get("name","")),
         campaign.get("start_date",""),
         campaign.get("end_date",""),
         _safe_json(campaign.get("target_segment")),
         _safe_json(campaign.get("rules")),
         campaign.get("budget",0),
         campaign.get("expected_reach",0),
         campaign.get("campaign_poster_path","")]
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
            # 更新年消费即可, 不写signals（年消费在静态画像Tab显示）

    elif event_type == "conversation":
        intent = event.get("intent","")
        sentiment = event.get("sentiment","")
        concerns = event.get("top_concerns",[])
        summary = event.get("summary","")

        # 搜索关键词: top_concerns中的话题追加到搜索意图
        if concerns:
            old = conn.execute("SELECT short_term_7d_top_search_keywords FROM customer_profile WHERE oneid=?",[oneid]).fetchone()
            old_str = (old[0] or "") if old else ""
            new_items = [c for c in concerns if c not in old_str]
            if new_items:
                updates["short_term_7d_top_search_keywords"] = (old_str+","+",".join(new_items)).strip(",")

        # 浏览偏好: intent映射为内容偏好
        intent_browse_map = {
            "分期需求":"分期计算器","权益咨询":"权益商城","额度升级":"额度管理",
            "账户问题":"账单详情","销户咨询":"还款页面","跨境出行":"境外消费专区",
            "新户引导":"新手指引",
        }
        browse_tag = intent_browse_map.get(intent, "")
        if browse_tag:
            old = conn.execute("SELECT mid_term_30d_browse_preferences FROM customer_profile WHERE oneid=?",[oneid]).fetchone()
            old_str = (old[0] or "") if old else ""
            if browse_tag not in old_str:
                updates["mid_term_30d_browse_preferences"] = (old_str+f",{browse_tag}({intent})").strip(",")

        # -- Key events: conversations do NOT auto-write --
        # Key events are only triggered by actual system-detected milestone behaviors
        # (actual card cancellation, installment signup, credit limit change, etc.),
        # NOT by consultation/inquiry in Project 3 conversations.
        # Conversation content goes to search intent (handled by top_concerns above).
        # If Project 3 reports an explicit milestone event (e.g. conversion + large amount),
        # it is handled by the corresponding event type.

        # -- Conversation summary -> search intent enrichment --
        # The topic of the conversation is itself a search intent signal
        if summary:
            old = conn.execute("SELECT short_term_7d_top_search_keywords FROM customer_profile WHERE oneid=?",[oneid]).fetchone()
            old_str = (old[0] or "") if old else ""
            # Extract keywords from summary (split by commas or spaces, max 3 words)
            summary_words = re.split(r'[，,、\s]+', summary)
            summary_kw = [w for w in summary_words if len(w) >= 2 and w not in old_str][:3]
            if summary_kw:
                existing = updates.get("short_term_7d_top_search_keywords", old_str)
                base = existing
                new_items = [w for w in summary_kw if w not in base]
                if new_items:
                    updates["short_term_7d_top_search_keywords"] = (base + "," + ",".join(new_items)).strip(",")

        # -- Sentiment: stored in feedback_events, NOT in warning signals --
        # Sentiment from Project 3 conversations is read by Dashboard Tab 3
        # (Intent Recognition -> Sentiment Analysis) from the feedback_events table,
        # and combined with overdue/churn/risk data to compute anxiety & satisfaction.
        # Only severe negative + high-risk combinations trigger warnings via other event types.

    elif event_type == "impression":
        # P3曝光: 仅记录在feedback_events中(活动效果Tab展示)
        pass

    elif event_type == "browse":
        # P3浏览(客户感兴趣): 活跃度+1, 记录到浏览偏好
        conn.execute("UPDATE customer_profile SET long_term_90d_activity_score=MIN(long_term_90d_activity_score+1,100) WHERE oneid=?",[oneid])
        conn.commit()
        detail = event.get("detail",{})
        if isinstance(detail, str):
            try: detail = json.loads(detail)
            except: detail = {}
        page = detail.get("page","") or event.get("channel_name","")
        if page:
            old = conn.execute("SELECT mid_term_30d_browse_preferences FROM customer_profile WHERE oneid=?",[oneid]).fetchone()
            old_str = (old[0] or "") if old else ""
            if page not in old_str:
                updates["mid_term_30d_browse_preferences"] = (old_str+f",{page}").strip(",")

    elif event_type == "ignore":
        # P3忽略(不感兴趣): 不更新画像, 仅记录
        pass

    elif event_type == "unsubscribe":
        # P3退订: 活跃度-5, 更新渠道退订标记, 流失风险增加
        conn.execute("UPDATE customer_profile SET long_term_90d_activity_score=MAX(long_term_90d_activity_score-5,0) WHERE oneid=?",[oneid])
        channel = event.get("channel","") or event.get("channel_name","")
        # 标记渠道退订
        if channel:
            ch_map = {"APP Push":"push_consent","短信":"sms_consent","邮件":"email_consent",
                      "微信公众号":"wechat_consent","电话":"phone_consent"}
            col = ch_map.get(channel)
            if col:
                conn.execute(f"UPDATE customer_profile SET {col}=FALSE WHERE oneid=?",[oneid])
            # 追加退订渠道记录
            old = conn.execute("SELECT unsubscribe_channels FROM customer_profile WHERE oneid=?",[oneid]).fetchone()
            old_str = (old[0] or "") if old else ""
            if channel not in old_str:
                conn.execute("UPDATE customer_profile SET unsubscribe_channels=? WHERE oneid=?",
                            [(old_str+","+channel).strip(","), oneid])
        conn.commit()

    elif event_type in ("click","reject"):
        # 旧版兼容: 点击/拒绝不写入signals
        pass

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
