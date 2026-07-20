"""
CSV → SQLite 迁移脚本
=======================
一次性导入所有 CSV 数据到 SQLite 数据库。
升级到 PostgreSQL: 改 db_store.py 中的连接字符串即可, SQL 不变。
"""
import os, sys, pandas as pd, time
from db_store import init_db, db, DB_PATH, customer_insert

BASE = os.path.dirname(os.path.abspath(__file__))
CSV_DIR = os.path.join(BASE, "mock_data", "structured")

def migrate():
    print("=" * 60)
    print("CSV → SQLite 数据迁移")
    print("=" * 60)

    init_db()
    conn = db()
    t0 = time.time()

    # 1. 客户画像
    print("\n[1/5] 导入客户画像...")
    df = pd.read_csv(os.path.join(CSV_DIR, "customer_profile.csv"))
    # 映射列名到数据库字段
    col_map = {
        "oneid": "oneid", "cust_id": "cust_id",
        "demographics_name": "name", "demographics_gender": "gender",
        "demographics_age": "age", "demographics_city": "city",
        "demographics_occupation": "occupation", "demographics_income_level": "income_level",
        "demographics_education": "education",
        "lifecycle_stage": "lifecycle_stage", "account_primary_card_level": "card_level",
        "account_total_credit_amount": "total_credit",
        "value_annual_consumption": "annual_consumption",
        "value_monthly_avg_consumption": "monthly_avg",
        "risk_risk_level": "risk_level", "value_value_level": "value_level",
        "long_term_90d_activity_score": "activity_score",
        "long_term_90d_dormancy_risk": "dormancy_risk",
        "short_term_7d_top_search_keywords": "search_keywords",
        "mid_term_30d_browse_preferences": "browse_preferences",
    }
    df_db = df[list(col_map.keys())].rename(columns=col_map)
    df_db = df_db.where(pd.notnull(df_db), None)
    df_db.to_sql("customers", conn, if_exists="replace", index=False)
    n = conn.execute("SELECT COUNT(*) FROM customers").fetchone()[0]
    print(f"  导入客户: {n}")

    # 2. 产品
    print("\n[2/5] 导入产品...")
    df = pd.read_csv(os.path.join(CSV_DIR, "product_catalog.csv"))
    df.to_sql("products", conn, if_exists="replace", index=False)
    print(f"  导入产品: {len(df)}")

    # 3. 权益
    print("\n[3/5] 导入权益...")
    df = pd.read_csv(os.path.join(CSV_DIR, "benefit_catalog.csv"))
    df.to_sql("benefits", conn, if_exists="replace", index=False)
    print(f"  导入权益: {len(df)}")

    # 4. 活动
    print("\n[4/5] 导入活动...")
    df = pd.read_csv(os.path.join(CSV_DIR, "campaign_catalog.csv"))
    df.to_sql("campaigns", conn, if_exists="replace", index=False)
    print(f"  导入活动: {len(df)}")

    # 5. 交易 (采样10万条)
    print("\n[5/5] 导入交易(采样)...")
    df = pd.read_csv(os.path.join(CSV_DIR, "transaction_log.csv"))
    # 添加 card_no → cust_id 映射
    cards = pd.read_csv(os.path.join(CSV_DIR, "credit_card.csv"))
    card_to_cust = dict(zip(cards["card_no"], cards["cust_id"]))
    df["cust_id"] = df["card_no"].map(card_to_cust)
    sample = df.sample(min(100000, len(df)), random_state=42)
    sample.to_sql("transactions", conn, if_exists="replace", index=False)
    n = conn.execute("SELECT COUNT(*) FROM transactions").fetchone()[0]
    print(f"  导入交易: {n}")

    # 建索引
    conn.executescript("""
    CREATE INDEX IF NOT EXISTS idx_customers_age ON customers(age);
    CREATE INDEX IF NOT EXISTS idx_customers_city ON customers(city);
    CREATE INDEX IF NOT EXISTS idx_customers_income ON customers(income_level);
    CREATE INDEX IF NOT EXISTS idx_transactions_cust ON transactions(cust_id);
    """)
    conn.commit()

    # 统计
    elapsed = time.time() - t0
    stats = {}
    for t in ["customers","products","benefits","campaigns","transactions"]:
        stats[t] = conn.execute(f"SELECT COUNT(*) FROM {t}").fetchone()[0]

    print(f"\n迁移完成! 耗时 {elapsed:.1f}s")
    print(f"数据库: {DB_PATH} ({os.path.getsize(DB_PATH)/1024/1024:.1f}MB)")
    for t, c in stats.items():
        print(f"  {t}: {c}")
    print("\n升级到 PostgreSQL: 修改 db_store.py 中 get_connection() 即可, SQL 不变。")

if __name__ == "__main__":
    migrate()
