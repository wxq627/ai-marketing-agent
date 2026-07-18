"""
数据动态更新模块 — data_updater.py
====================================
提供轻量级数据增量更新, 使大屏无需重启即可看到新数据。

CSV 模式(当前): 写入增量日志 → 大屏轮询检测 → 合并显示
PG 模式(生产): INSERT INTO → 大屏直接查询最新数据

架构对比:
  CSV: Add → append to delta.json → dashboard reads delta + merges → display
  PG:  Add → INSERT INTO customers → dashboard SELECT → display
"""

import os, json, time, pandas as pd
from datetime import datetime
from typing import Dict, List

BASE = os.path.dirname(os.path.abspath(__file__))
DELTA_FILE = os.path.join(BASE, "mock_data", "structured", "data_delta.json")
PROFILE_CSV = os.path.join(BASE, "mock_data", "structured", "customer_profile.csv")


# ================================================================
# 增量更新 API
# ================================================================

def add_customer(customer_data: Dict) -> Dict:
    """新增客户: 写入增量日志, 返回状态。"""
    delta = _load_delta()

    # 生成 OneID
    existing_ids = [int(r.get("oneid","UID000000").replace("UID","")) for r in delta.get("new_customers", [])]
    next_id = max(existing_ids) + 1 if existing_ids else 8001
    oneid = f"UID{next_id:06d}"

    record = {
        "oneid": oneid,
        "cust_id": customer_data.get("cust_id", f"C{next_id:06d}"),
        "data": customer_data,
        "added_at": datetime.now().isoformat(),
        "source": "manual_input",
    }

    if "new_customers" not in delta: delta["new_customers"] = []
    delta["new_customers"].append(record)

    # 如果是"转化事件"类更新, 同时追加到交易日志
    if customer_data.get("event_type") == "conversion":
        txn = {
            "oneid": oneid,
            "amount": customer_data.get("amount", 0),
            "merchant": customer_data.get("merchant", ""),
            "category": customer_data.get("category", "购物"),
            "time": datetime.now().isoformat(),
        }
        if "new_transactions" not in delta: delta["new_transactions"] = []
        delta["new_transactions"].append(txn)

    _save_delta(delta)
    return {"status": "ok", "oneid": oneid, "total_new": len(delta.get("new_customers", []))}


def add_document(doc_data: Dict) -> Dict:
    """新增产品文档/权益/活动。"""
    delta = _load_delta()
    record = {**doc_data, "added_at": datetime.now().isoformat()}
    if "new_documents" not in delta: delta["new_documents"] = []
    delta["new_documents"].append(record)
    _save_delta(delta)
    return {"status": "ok", "type": doc_data.get("type", "unknown")}


def get_updates_since(timestamp: str = None) -> Dict:
    """获取自某时间后的所有增量更新。"""
    delta = _load_delta()
    if timestamp is None:
        return delta

    filtered = {"new_customers": [], "new_transactions": [], "new_documents": []}
    for cat in filtered:
        for r in delta.get(cat, []):
            if r.get("added_at", "") > timestamp:
                filtered[cat].append(r)
    return filtered


def get_delta_stats() -> Dict:
    """获取增量统计。"""
    delta = _load_delta()
    return {
        "new_customers": len(delta.get("new_customers", [])),
        "new_transactions": len(delta.get("new_transactions", [])),
        "new_documents": len(delta.get("new_documents", [])),
        "last_updated": delta.get("last_updated", ""),
    }


def clear_delta():
    """清空增量(模拟T+1批量: 将增量合并到CSV后清空)。"""
    delta = _load_delta()
    # 实际生产: 将delta中的数据INSERT INTO PostgreSQL, 然后清空delta
    _save_delta({"last_updated": datetime.now().isoformat(), "last_cleared": datetime.now().isoformat()})
    return {"status": "cleared", "message": "增量已清空(T+1批量完成)"}


# ================================================================
# 内部
# ================================================================

def _load_delta() -> Dict:
    if os.path.exists(DELTA_FILE):
        with open(DELTA_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    return {"last_updated": datetime.now().isoformat()}

def _save_delta(delta: Dict):
    delta["last_updated"] = datetime.now().isoformat()
    os.makedirs(os.path.dirname(DELTA_FILE), exist_ok=True)
    with open(DELTA_FILE, "w", encoding="utf-8") as f:
        json.dump(delta, f, ensure_ascii=False, indent=2)


# ================================================================
# 生产环境 PostgreSQL 示例 (不真正连接, 仅展示代码)
# ================================================================

PG_SCHEMA_EXAMPLE = """
-- 生产环境 PostgreSQL 建表语句

CREATE TABLE customers (
    oneid VARCHAR(32) PRIMARY KEY,
    cust_id VARCHAR(32) UNIQUE NOT NULL,
    name VARCHAR(64), gender CHAR(1), age INT,
    city VARCHAR(32), occupation VARCHAR(32),
    income_level VARCHAR(8), education VARCHAR(16),
    -- ... 其他画像字段
    created_at TIMESTAMP DEFAULT NOW(),
    updated_at TIMESTAMP DEFAULT NOW()
);

CREATE INDEX idx_customers_age ON customers(age);
CREATE INDEX idx_customers_city ON customers(city);
CREATE INDEX idx_customers_income ON customers(income_level);

-- 增量插入 (一行, 不影响其他数据)
INSERT INTO customers (oneid, cust_id, name, age, city, ...)
VALUES ('UID008001', 'C008001', '新客户', 30, '深圳', ...)
ON CONFLICT (oneid) DO UPDATE SET ...;

-- 大屏直接查询最新数据
SELECT * FROM customers WHERE updated_at > '2026-07-18 00:00:00';
"""

if __name__ == "__main__":
    # 测试
    r = add_customer({"name": "测试客户", "age": 30, "city": "深圳", "amount": 5000, "event_type": "conversion", "merchant": "星巴克"})
    print(f"新增客户: {r}")
    print(f"增量统计: {get_delta_stats()}")
    print()
    print("=== PostgreSQL Schema ===")
    print(PG_SCHEMA_EXAMPLE)
