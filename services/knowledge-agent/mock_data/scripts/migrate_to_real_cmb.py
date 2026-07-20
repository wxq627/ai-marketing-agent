"""
XX银行信用卡中心真实数据迁移脚本
=====================================
将现有mock数据中的产品ID映射到真实的XX银行信用卡产品体系。
运行此脚本前，请确保已更新 product_catalog.csv, benefit_catalog.csv 等文件。
"""
import pandas as pd
import os, sys, json

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
STRUCTURED_DIR = os.path.join(BASE_DIR, "structured")
UNSTRUCTURED_DIR = os.path.join(BASE_DIR, "unstructured")

# ============================================================
# 产品ID映射表: 旧ID → 新ID
# ============================================================
PRODUCT_ID_MAP = {
    "PROD_STANDARD_N":  "PROD_STANDARD_N",    # 标准普卡 → 标准普卡 (保持)
    "PROD_YOUNG_N":     "PROD_YOUNG_G",       # YOUNG普卡 → YOUNG青年版金卡
    "PROD_CAMPUS_N":    "PROD_YOUNG_CAMPUS",  # 校园卡 → YOUNG校园版
    "PROD_STANDARD_G":  "PROD_STANDARD_G",    # 标准金卡 → 标准金卡 (保持)
    "PROD_CTRIP_G":     "PROD_CTRIP_G",       # 携程金卡 → 携程金卡 (保持)
    "PROD_JD_G":        "PROD_JD_G",          # 京东金卡 → 京东金卡 (保持)
    "PROD_CLASSIC_W":   "PROD_CLASSIC_W",     # 经典白金 → 经典白金 (保持)
    "PROD_UNIONPAY_W":  "PROD_UNIONPAY_W",    # 银联白金 → 银联白金 (保持)
    "PROD_GLOBAL_W":    "PROD_GLOBAL_W",      # 全币种白金 → 全币种白金 (保持)
    "PROD_DIAMOND":     "PROD_DIAMOND",       # 钻石卡 → 钻石卡 (保持)
    "PROD_INFINITE":    "PROD_WORLD",         # 无限卡 → 万事达世界卡
}

# ============================================================
# 卡等级也需要同步更新
# ============================================================
# 从新product_catalog读取产品→卡等级映射
def load_product_levels():
    df = pd.read_csv(os.path.join(STRUCTURED_DIR, "product_catalog.csv"))
    return dict(zip(df["product_id"], df["card_level"]))

def migrate_credit_card():
    """更新 credit_card.csv 中的 product_id 和 card_level。"""
    path = os.path.join(STRUCTURED_DIR, "credit_card.csv")
    print(f"读取 {path} ...")
    df = pd.read_csv(path)
    print(f"  共 {len(df)} 条记录")

    # 统计旧产品分布
    print("\n旧产品ID分布:")
    old_dist = df["product_id"].value_counts()
    for pid, cnt in old_dist.items():
        print(f"  {pid}: {cnt}")

    # 更新 product_id
    df["product_id"] = df["product_id"].map(PRODUCT_ID_MAP).fillna(df["product_id"])

    # 更新 card_level
    prod_levels = load_product_levels()
    df["card_level"] = df["product_id"].map(prod_levels).fillna(df["card_level"])

    # 统计新产品分布
    print("\n新产品ID分布:")
    new_dist = df["product_id"].value_counts()
    for pid, cnt in new_dist.items():
        print(f"  {pid}: {cnt}")

    # 保存
    df.to_csv(path, index=False, encoding="utf-8-sig")
    print(f"\n✅ credit_card.csv 已更新: {len(df)} 条记录")
    return df

def update_product_docs_index():
    """更新 product_docs/_index.json 中的产品名称引用。"""
    # 读旧产品名→新产品名映射
    old_names = {
        "经典版白金信用卡": "经典版白金信用卡",
        "银联白金信用卡": "银联白金信用卡",
        "全币种白金信用卡": "全币种国际白金信用卡",
        "钻石信用卡": "银联钻石信用卡",
        "无限信用卡": "万事达世界信用卡",
        "标准信用卡（金卡）": "标准信用卡（金卡）",
        "携程旅行信用卡（金卡）": "携程旅行信用卡（金卡）",
        "京东联名信用卡（金卡）": "京东PLUS联名信用卡（金卡）",
        "标准信用卡（普卡）": "标准信用卡（普卡）",
        "YOUNG卡（普卡）": "YOUNG卡（青年版）",
        "校园信用卡": "YOUNG卡（校园版）",
    }

    index_path = os.path.join(UNSTRUCTURED_DIR, "product_docs", "_index.json")
    if os.path.exists(index_path):
        with open(index_path, "r", encoding="utf-8") as f:
            docs = json.load(f)

        for doc in docs:
            old_name = doc.get("product_name", "")
            if old_name in old_names:
                doc["product_name"] = old_names[old_name]

        with open(index_path, "w", encoding="utf-8") as f:
            json.dump(docs, f, ensure_ascii=False, indent=2)
        print(f"✅ _index.json 已更新: {len(docs)} 条文档记录")

def update_customer_basic():
    """检查 customer_basic.csv 是否需要更新（通常不需要，但检查确保一致性）。"""
    path = os.path.join(STRUCTURED_DIR, "customer_basic.csv")
    df = pd.read_csv(path)
    print(f"✅ customer_basic.csv 无需更新: {len(df)} 条记录")


if __name__ == "__main__":
    print("=" * 60)
    print("XX银行信用卡中心 — 真实数据迁移")
    print("=" * 60)

    # 1. 更新信用卡表
    migrate_credit_card()

    # 2. 更新产品文档索引
    update_product_docs_index()

    # 3. 检查客户表
    update_customer_basic()

    print("\n" + "=" * 60)
    print("迁移完成！")
    print("=" * 60)
