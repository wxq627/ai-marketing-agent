"""
从 Mock 数据生成 OneID 映射表
===============================
读取所有结构化数据，提取每个客户的跨系统 ID，生成:
  - mock_data/structured/id_mapping.csv      (ID 映射主表)
  - mock_data/structured/id_mapping_log.csv  (映射变更日志, 含模拟冲突)

模拟的冲突场景 (用于测试冲突检测和人工确认流程):
  1. 旧手机号被回收，重新分配给新客户
  2. 客户更换设备，device_id 变更
  3. 共享设备 (家庭共用 iPad) — 一个 device_id 关联多人
"""

import os, sys, random, pandas as pd
from datetime import datetime, timedelta

# 路径
BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
STRUCTURED = os.path.join(BASE, "mock_data", "structured")

REFERENCE_DATE = datetime(2026, 7, 15)
random.seed(42)


def generate_id_mapping():
    """从现有 mock 数据生成 OneID 映射表和冲突日志。"""
    print("=" * 60)
    print("OneID 映射表生成")
    print("=" * 60)

    # ---- 读数据 ----
    cust = pd.read_csv(os.path.join(STRUCTURED, "customer_basic.csv"))
    card = pd.read_csv(os.path.join(STRUCTURED, "credit_card.csv"))
    crm = pd.read_csv(os.path.join(STRUCTURED, "crm_customer.csv"))
    app = pd.read_csv(os.path.join(STRUCTURED, "app_events.csv"))
    consent = pd.read_csv(os.path.join(STRUCTURED, "customer_consent.csv"))

    # ---- 构建 cust_id → OneID 映射 ----
    # OneID = UID + 自增6位序号
    cust_ids = cust["cust_id"].tolist()
    id_to_oneid = {cid: f"UID{i+1:06d}" for i, cid in enumerate(cust_ids)}
    oneid_to_name = dict(zip(cust["cust_id"], cust["name"]))
    oneid_to_name = {id_to_oneid[cid]: name for cid, name in oneid_to_name.items()}

    print(f"  客户数: {len(cust_ids)} → {len(set(id_to_oneid.values()))} 唯一 OneID")

    # ---- 生成 id_mapping 记录 ----
    records = []
    now = REFERENCE_DATE.strftime("%Y-%m-%d %H:%M:%S")

    def add(oneid, id_type, id_value, confidence, source):
        records.append({
            "id": len(records) + 1,
            "oneid": oneid,
            "id_type": id_type,
            "id_value": id_value,
            "confidence": confidence,
            "source_system": source,
            "first_seen": now,
            "last_updated": now,
            "is_active": True,
        })

    # 每个客户: cust_id + id_card + phone + crm_id
    for _, row in cust.iterrows():
        cid = row["cust_id"]
        uid = id_to_oneid[cid]
        add(uid, "cust_id", cid, 1.00, "银行核心")
        add(uid, "id_card", str(row["id_card"]), 1.00, "银行核心")
        add(uid, "phone", str(row["phone"]), 0.95, "银行核心")

    # CRM ID
    for _, row in crm.iterrows():
        cid = row["cust_id"]
        uid = id_to_oneid[cid]
        add(uid, "crm_id", row["crm_id"], 1.00, "CRM")

    # 信用卡号 (一人多卡)
    for _, row in card.iterrows():
        cid = row["cust_id"]
        uid = id_to_oneid[cid]
        add(uid, "card_no", row["card_no"], 1.00, "银行核心")

    # 设备 ID 和 OpenID (从 app_events 抽样)
    # 每个客户从 app_events 中选取 1-3 个 device_id + 1 open_id
    app_devices = app[["device_id", "open_id"]].drop_duplicates()
    device_pool = app_devices["device_id"].dropna().unique().tolist()
    openid_pool = app_devices["open_id"].dropna().unique().tolist()

    # 为每个客户分配设备 ID (模拟 1-3 个设备)
    used_devices = set()
    for cid in cust_ids:
        uid = id_to_oneid[cid]
        n_devices = random.choices([1, 2, 3], weights=[0.6, 0.3, 0.1])[0]
        for _ in range(n_devices):
            if device_pool:
                dev = random.choice(device_pool)
                if dev not in used_devices:
                    used_devices.add(dev)
                    add(uid, "device_id", dev, 0.90, "APP埋点")

    # 为每个客户分配 1 个 OpenID
    for cid in cust_ids:
        uid = id_to_oneid[cid]
        if openid_pool:
            oid = random.choice(openid_pool)
            add(uid, "open_id", oid, 0.90, "APP埋点")

    # ---- 模拟冲突场景 ----
    print("\n  注入模拟冲突...")
    conflict_logs = []

    # 场景1: 旧手机号回收 (2个客户)
    # 选取两个客户，让它们共享同一个手机号
    if len(records) > 10:
        # 客户A的手机号记录
        phone_records = [r for r in records if r["id_type"] == "phone"]
        if len(phone_records) >= 2:
            r1, r2 = phone_records[0], phone_records[1]
            old_phone = r2["id_value"]
            old_oneid = r2["oneid"]
            # 把 r2 的 phone 也映射到 r1 的 oneid (模拟换号)
            conflict_logs.append({
                "log_id": "LOG_CONFLICT_001",
                "id_value": old_phone,
                "old_oneid": old_oneid,
                "new_oneid": r1["oneid"],
                "conflict_reason": "旧手机号被新客户使用, 系统检测到同号异人",
                "resolution": "人工确认",
                "resolved_at": "",
            })

    # 场景2: 共享设备 (家庭 iPad) — 一个 device_id 映射到 2 个 OneID
    dev_records = [r for r in records if r["id_type"] == "device_id"]
    if len(dev_records) >= 3:
        d1, d2, d3 = dev_records[0], dev_records[1], dev_records[2]
        shared_dev = d1["id_value"]
        # d2 也使用这个设备
        conflict_logs.append({
            "log_id": "LOG_CONFLICT_002",
            "id_value": shared_dev,
            "old_oneid": d1["oneid"],
            "new_oneid": d2["oneid"],
            "conflict_reason": f"疑似共享设备(家庭iPad), device_id={shared_dev}被多人使用",
            "resolution": "保留原映射",
            "resolved_at": REFERENCE_DATE.strftime("%Y-%m-%d %H:%M:%S"),
        })
        # 允许 d2 也用这个设备 (低置信度)
        add(d2["oneid"], "device_id", shared_dev, 0.65, "APP埋点")

    # 场景3: 客户投诉后更换 device_id, 旧 device_id 标记为 inactive
    if len(dev_records) >= 5:
        d5 = dev_records[4]
        # 模拟旧设备标记为 inactive
        for r in records:
            if r["id_type"] == "device_id" and r["id_value"] == d5["id_value"]:
                r["is_active"] = False
                r["last_updated"] = (REFERENCE_DATE - timedelta(days=30)).strftime("%Y-%m-%d %H:%M:%S")
                conflict_logs.append({
                    "log_id": "LOG_CONFLICT_003",
                    "id_value": d5["id_value"],
                    "old_oneid": d5["oneid"],
                    "new_oneid": d5["oneid"],
                    "conflict_reason": "客户更换设备, 旧device_id超过30天未活跃, 自动标记inactive",
                    "resolution": "自动合并",
                    "resolved_at": REFERENCE_DATE.strftime("%Y-%m-%d %H:%M:%S"),
                })
                break

    # ---- 保存 ----
    df_map = pd.DataFrame(records)
    df_map = df_map.sort_values(["oneid", "id_type"]).reset_index(drop=True)
    # 重新赋值 id
    df_map["id"] = range(1, len(df_map) + 1)

    map_path = os.path.join(STRUCTURED, "id_mapping.csv")
    df_map.to_csv(map_path, index=False, encoding="utf-8-sig")
    print(f"\n  [OK] id_mapping.csv: {len(df_map)} 条映射")

    # ID 类型分布
    for t in ["id_card", "phone", "cust_id", "crm_id", "card_no", "device_id", "open_id"]:
        cnt = len(df_map[df_map["id_type"] == t])
        active = len(df_map[(df_map["id_type"] == t) & (df_map["is_active"] == True)])
        print(f"    {t}: {cnt} 条 (活跃: {active})")

    # 冲突日志
    if conflict_logs:
        df_log = pd.DataFrame(conflict_logs)
        log_path = os.path.join(STRUCTURED, "id_mapping_log.csv")
        df_log.to_csv(log_path, index=False, encoding="utf-8-sig")
        print(f"\n  [OK] id_mapping_log.csv: {len(df_log)} 条冲突日志")
        for _, l in df_log.iterrows():
            print(f"    {l['log_id']}: {l['conflict_reason'][:50]}... → {l['resolution']}")

    # 验证
    print(f"\n  验证: {df_map['oneid'].nunique()} 唯一 OneID")
    print(f"  每人平均 ID 数: {len(df_map) / df_map['oneid'].nunique():.1f}")

    return df_map


if __name__ == "__main__":
    generate_id_mapping()
