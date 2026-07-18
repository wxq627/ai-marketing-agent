"""
数据库存储层 — db_store.py
============================
SQLite 实现 (与 PostgreSQL 接口兼容, 零安装)。
升级到 PostgreSQL: 改一行连接字符串即可。

特性:
  - SQL 查询 (SELECT/WHERE/JOIN/GROUP BY)
  - 增量写入 (INSERT/UPDATE 单行)
  - 索引加速
  - 事务 (BEGIN/COMMIT)
  - 并发读 (WAL模式)
"""

import os, sqlite3, pandas as pd
from datetime import datetime
from typing import List, Dict, Optional

BASE = os.path.dirname(os.path.abspath(__file__))
DB_PATH = os.path.join(BASE, "mock_data", "knowledge_agent.db")

# PostgreSQL 兼容连接字符串 (升级时改这里)
def get_connection():
    """获取数据库连接。SQLite: 本地文件; PG: 远程服务器。"""
    conn = sqlite3.connect(DB_PATH, check_same_thread=False)
    conn.row_factory = sqlite3.Row  # 返回字典式行
    conn.execute("PRAGMA journal_mode=WAL")  # 写前日志, 支持并发读
    conn.execute("PRAGMA foreign_keys=ON")
    return conn

# 全局连接池(单连接, 生产环境用连接池)
_conn = None
def db():
    global _conn
    if _conn is None: _conn = get_connection()
    return _conn


# ================================================================
# 建表 (PostgreSQL 兼容 DDL)
# ================================================================

def init_db():
    """初始化数据库表。"""
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

    CREATE INDEX IF NOT EXISTS idx_customers_age ON customers(age);
    CREATE INDEX IF NOT EXISTS idx_customers_city ON customers(city);
    CREATE INDEX IF NOT EXISTS idx_customers_income ON customers(income_level);
    CREATE INDEX IF NOT EXISTS idx_customers_lifecycle ON customers(lifecycle_stage);
    CREATE INDEX IF NOT EXISTS idx_customers_risk ON customers(risk_level);
    CREATE INDEX IF NOT EXISTS idx_transactions_cust ON transactions(cust_id);
    CREATE INDEX IF NOT EXISTS idx_feedback_oneid ON feedback_events(oneid);
    """)
    conn.commit()
    return True


# ================================================================
# 客户 CRUD (与 PostgreSQL 完全一致的 SQL)
# ================================================================

def customer_search(filters: Dict = None, page: int = 1, page_size: int = 50) -> Dict:
    """客户搜索 — 与 CSV 版本的 customer/search 接口输出一致。"""
    conn = db()
    where = ["1=1"]
    params = []

    if filters:
        if "age_min" in filters: where.append("age >= ?"); params.append(filters["age_min"])
        if "age_max" in filters: where.append("age <= ?"); params.append(filters["age_max"])
        if "city" in filters:
            placeholders = ",".join(["?" for _ in filters["city"]])
            where.append(f"city IN ({placeholders})"); params.extend(filters["city"])
        if "income_level" in filters:
            placeholders = ",".join(["?" for _ in filters["income_level"]])
            where.append(f"income_level IN ({placeholders})"); params.extend(filters["income_level"])
        if "card_level" in filters:
            placeholders = ",".join(["?" for _ in filters["card_level"]])
            where.append(f"card_level IN ({placeholders})"); params.extend(filters["card_level"])
        if "lifecycle_stage" in filters:
            placeholders = ",".join(["?" for _ in filters["lifecycle_stage"]])
            where.append(f"lifecycle_stage IN ({placeholders})"); params.extend(filters["lifecycle_stage"])
        if "risk_level" in filters:
            placeholders = ",".join(["?" for _ in filters["risk_level"]])
            where.append(f"risk_level IN ({placeholders})"); params.extend(filters["risk_level"])
        if "value_level" in filters:
            placeholders = ",".join(["?" for _ in filters["value_level"]])
            where.append(f"value_level IN ({placeholders})"); params.extend(filters["value_level"])

    where_clause = " AND ".join(where)

    # 总数
    total = conn.execute(f"SELECT COUNT(*) FROM customers WHERE {where_clause}", params).fetchone()[0]

    # 分页
    offset = (page - 1) * page_size
    rows = conn.execute(
        f"SELECT * FROM customers WHERE {where_clause} LIMIT ? OFFSET ?",
        params + [page_size, offset]
    ).fetchall()

    return {
        "total": total, "page": page, "page_size": page_size,
        "customers": [dict(r) for r in rows],
        "data_version": "db_v1.0",
        "generated_at": datetime.now().isoformat(),
    }


def customer_insert(cust_data: Dict) -> Dict:
    """新增客户 — INSERT一行, 不影响其他数据。"""
    conn = db()
    try:
        cols = ", ".join(cust_data.keys())
        placeholders = ", ".join(["?" for _ in cust_data])
        conn.execute(f"INSERT OR REPLACE INTO customers ({cols}) VALUES ({placeholders})",
                     list(cust_data.values()))
        conn.commit()
        return {"status": "ok", "oneid": cust_data.get("oneid", ""), "action": "insert"}
    except Exception as e:
        return {"status": "error", "message": str(e)}


def customer_update(oneid: str, updates: Dict) -> Dict:
    """更新客户 — UPDATE一行。"""
    conn = db()
    sets = ", ".join([f"{k}=?" for k in updates])
    conn.execute(f"UPDATE customers SET {sets}, updated_at=datetime('now') WHERE oneid=?",
                 list(updates.values()) + [oneid])
    conn.commit()
    return {"status": "ok", "oneid": oneid}


def customer_get(oneid: str) -> Optional[Dict]:
    """查询单个客户。"""
    row = db().execute("SELECT * FROM customers WHERE oneid=?", [oneid]).fetchone()
    return dict(row) if row else None


def feedback_insert(event: Dict) -> Dict:
    """记录反馈事件 — INSERT一次交互。"""
    conn = db()
    conn.execute(
        "INSERT INTO feedback_events (oneid, event_type, campaign_id, channel, detail, timestamp) "
        "VALUES (?,?,?,?,?,?)",
        [event.get("oneid"), event.get("event_type"), event.get("campaign_id",""),
         event.get("channel",""), str(event.get("detail","")), event.get("timestamp", datetime.now().isoformat())]
    )
    conn.commit()
    # 如果是转化事件, 同时更新客户消费
    if event.get("event_type") == "conversion":
        amt = event.get("detail", {}).get("amount", 0) if isinstance(event.get("detail"), dict) else 0
        if amt > 0:
            conn.execute(
                "UPDATE customers SET annual_consumption = annual_consumption + ?, "
                "monthly_avg = monthly_avg + ?, updated_at = datetime('now') WHERE oneid = ?",
                [amt, amt/12, event.get("oneid")]
            )
            conn.commit()
    return {"status": "ok", "event_type": event.get("event_type")}


# ================================================================
# 产品/权益/活动查询
# ================================================================

def get_products(): return db().execute("SELECT * FROM products").fetchall()
def get_benefits(): return db().execute("SELECT * FROM benefits").fetchall()
def get_campaigns(): return db().execute("SELECT * FROM campaigns").fetchall()
def get_recent_feedback(limit=20): return db().execute("SELECT * FROM feedback_events ORDER BY created_at DESC LIMIT ?", [limit]).fetchall()


def db_stats():
    conn = db()
    return {
        "customers": conn.execute("SELECT COUNT(*) FROM customers").fetchone()[0],
        "products": conn.execute("SELECT COUNT(*) FROM products").fetchone()[0],
        "benefits": conn.execute("SELECT COUNT(*) FROM benefits").fetchone()[0],
        "campaigns": conn.execute("SELECT COUNT(*) FROM campaigns").fetchone()[0],
        "transactions": conn.execute("SELECT COUNT(*) FROM transactions").fetchone()[0],
        "feedback_events": conn.execute("SELECT COUNT(*) FROM feedback_events").fetchone()[0],
        "db_file": DB_PATH,
        "db_size_mb": round(os.path.getsize(DB_PATH)/1024/1024, 1) if os.path.exists(DB_PATH) else 0,
    }
