"""
Mock数据一键生成主脚本
========================
按依赖顺序执行所有生成步骤:

  1. config          - 配置(自动加载)
  2. products        - 产品/权益/活动(无依赖, 先跑)
  3. customers       - 客户+信用卡(依赖products.product_id)
  4. transactions    - 交易+账单(依赖信用卡)
  5. crm             - CRM(依赖客户+信用卡)
  6. app_events      - APP事件(依赖客户)
  7. asr             - 客服对话(依赖客户)
  8. docs            - 文档+海报(独立)

用法: python run_all.py
"""

import sys, os, time

# 确保脚本目录在path中
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import pandas as pd
from config import *


def main():
    start_time = time.time()
    print("\n" + "=" * 60)
    print("  XX银行信用卡 Mock 数据生成系统")
    print("  项目一: 企业知识引擎与记忆中心 (Knowledge Agent)")
    print("=" * 60)
    print(f"  随机种子: {RANDOM_SEED}")
    print(f"  参考日期: {REFERENCE_DATE.strftime('%Y-%m-%d')}")
    print(f"  目标客户: {N_CUSTOMERS}")
    print("=" * 60)

    # ================================================================
    # Step 1: 产品/权益/活动 (无依赖)
    # ================================================================
    print("\n" + "▸" * 30)
    print("  [1/7] 生成产品&权益&活动数据 ...")
    print("▸" * 30)
    from generate_products import generate_all_products
    df_prod, df_ben, df_map, df_camp = generate_all_products()

    # ================================================================
    # Step 2: 客户基础信息 + 信用卡
    # ================================================================
    print("\n" + "▸" * 30)
    print("  [2/7] 生成客户基础信息 & 信用卡 ...")
    print("▸" * 30)
    from generate_customers import generate_all_customers_and_cards
    df_cust, df_cards = generate_all_customers_and_cards()

    # ================================================================
    # Step 3: 交易流水 + 账单
    # ================================================================
    print("\n" + "▸" * 30)
    print("  [3/7] 生成交易流水 & 账单记录 ...")
    print("▸" * 30)
    from generate_transactions import generate_all_transactions_and_bills
    df_txn, df_bill = generate_all_transactions_and_bills(df_cards)

    # ================================================================
    # Step 4: CRM 客户关系
    # ================================================================
    print("\n" + "▸" * 30)
    print("  [4/7] 生成 CRM 客户关系数据 ...")
    print("▸" * 30)
    from generate_crm import generate_all_crm
    df_crm = generate_all_crm(df_cust, df_cards)

    # ================================================================
    # Step 5: APP 埋点事件
    # ================================================================
    print("\n" + "▸" * 30)
    print("  [5/7] 生成 APP 埋点事件 ...")
    print("▸" * 30)
    from generate_app_events import generate_all_app_events
    df_app = generate_all_app_events(df_cust, df_cards)

    # ================================================================
    # Step 6: 客服 ASR 对话
    # ================================================================
    print("\n" + "▸" * 30)
    print("  [6/7] 生成客服 ASR 对话文本 ...")
    print("▸" * 30)
    from generate_asr import generate_all_asr
    asr_records = generate_all_asr(df_cust)

    # ================================================================
    # Step 7: 非结构化文档 & 海报
    # ================================================================
    print("\n" + "▸" * 30)
    print("  [7/7] 生成产品文档 & 活动海报描述 ...")
    print("▸" * 30)
    from generate_docs import generate_all_docs_and_posters
    doc_index = generate_all_docs_and_posters()

    # ================================================================
    # 汇总报告
    # ================================================================
    elapsed = time.time() - start_time
    print("\n" + "=" * 60)
    print("  ✅ 全部 Mock 数据生成完毕!")
    print("=" * 60)
    print(f"""
  总耗时: {elapsed:.1f} 秒

  📊 结构化数据 (mock_data/structured/):
     ├── customer_basic.csv          {len(df_cust):>8,} 行
     ├── credit_card.csv             {len(df_cards):>8,} 行
     ├── transaction_log.csv         {len(df_txn):>8,} 行
     ├── bill_record.csv             {len(df_bill):>8,} 行
     ├── crm_customer.csv            {len(df_crm):>8,} 行
     ├── app_events.csv              {len(df_app):>8,} 行
     ├── product_catalog.csv         {len(df_prod):>8,} 行
     ├── benefit_catalog.csv         {len(df_ben):>8,} 行
     ├── product_benefit_mapping.csv {len(df_map):>8,} 行
     └── campaign_catalog.csv        {len(df_camp):>8,} 行

  📄 非结构化数据 (mock_data/unstructured/):
     ├── asr_transcripts/            {len(asr_records):>8,} 个文件
     ├── product_docs/               {len(doc_index):>8,} 个文件
     └── posters/                    12 个文件

  输出目录: {BASE_DIR}
""")

    return 0


if __name__ == "__main__":
    sys.exit(main())
