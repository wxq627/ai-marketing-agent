"""
APP埋点事件生成脚本
====================
生成 mock_data/structured/app_events.csv (约50万条)

字段: event_id, device_id, open_id, event_type, page_name,
      search_keyword, duration_sec, timestamp, app_version

业务逻辑:
  - 每个客户配 1~3 个设备ID
  - 活跃客户(近90天有交易)每天产生 3~15 条事件
  - 沉睡客户事件稀疏
  - 搜索关键词按6类意图分布, 用于后续意图识别
"""

import random, os, pandas as pd, numpy as np
from datetime import datetime, timedelta
from typing import List, Dict, Any
from collections import defaultdict

from config import *

random.seed(RANDOM_SEED + 3)
np.random.seed(RANDOM_SEED + 3)

# ---- 设备ID池(每个客户生成后缓存) ----
_device_pool: Dict[str, List[str]] = {}   # cust_id → [device_id, ...]
_openid_pool: Dict[str, str] = {}          # cust_id → open_id


def ensure_devices(cust_id: str) -> List[str]:
    """为一个客户分配1~3个设备ID。"""
    if cust_id in _device_pool:
        return _device_pool[cust_id]
    n = random.choices([1, 2, 3], weights=[0.55, 0.35, 0.10])[0]
    devs = []
    for _ in range(n):
        devs.append(f"DEV_{random.choice(['A','B','iOS','HW','OP','XM','VV'])}_{random.randint(100,999)}")
    _device_pool[cust_id] = devs
    _openid_pool[cust_id] = f"wx_openid_{cust_id.lower()}_{random.randint(10,99)}"
    return devs


def pick_search_keyword() -> str:
    """随机选一个搜索关键词(按意图均匀抽样)。"""
    all_kw = []
    for kws in SEARCH_KEYWORDS.values():
        all_kw.extend(kws)
    return random.choice(all_kw)


def gen_events_one_customer(cust_id: str, is_active: bool,
                             active_days: int = 300) -> List[Dict[str, Any]]:
    """为一个客户生成指定天数内的APP埋点事件。"""
    devs = ensure_devices(cust_id)
    oid  = _openid_pool[cust_id]
    events: List[Dict] = []
    seq  = 1

    # 每日事件数 - 控制总量
    if is_active:
        daily_range = (1, 5)
    else:
        daily_range = (0, 1)

    # 最多30天事件
    event_days = min(active_days, 30)
    for d in range(event_days):
        day = REFERENCE_DATE - timedelta(days=active_days - d)
        n = random.randint(*daily_range)
        if n == 0:
            continue
        for _ in range(n):
            dev = random.choice(devs)
            etype = random.choices(list(APP_EVENT_TYPES), weights=list(APP_EVENT_TYPES.values()))[0]
            page  = random.choice(APP_PAGES)
            kw    = pick_search_keyword() if (etype == "搜索" or (etype == "页面浏览" and random.random() < 0.08)) else ""
            dur   = random.randint(1, 300) if etype in ("页面浏览","停留") else random.randint(1, 15)
            ts    = day + timedelta(
                hours=random.randint(6, 23), minutes=random.randint(0, 59), seconds=random.randint(0, 59))

            events.append({
                "event_id": f"E{seq:08d}",
                "device_id": dev,
                "open_id": oid,
                "event_type": etype,
                "page_name": page,
                "search_keyword": kw,
                "duration_sec": dur,
                "timestamp": ts.strftime("%Y-%m-%d %H:%M:%S"),
                "app_version": f"{random.randint(7,9)}.{random.randint(0,5)}.{random.randint(0,9)}",
            })
            seq += 1
    return events


def generate_all_app_events(df_customers: pd.DataFrame, df_cards: pd.DataFrame):
    print("=" * 60)
    print("生成 APP 埋点事件 ...")
    print(f"  目标: ~{N_APP_EVENTS_TOTAL} 条")
    print("=" * 60)

    # 判断活跃度: 近90天有交易为活跃
    primary = df_cards[df_cards["is_primary"] == True].set_index("cust_id")
    all_events = []
    for idx, (_, row) in enumerate(df_customers.iterrows()):
        cid = row["cust_id"]
        open_dt = datetime.strptime(row["register_date"], "%Y-%m-%d")
        active_days = min(90, max(30, (REFERENCE_DATE - open_dt).days))

        # 简单判断活跃
        if cid in primary.index:
            card = primary.loc[cid]
            card_open = datetime.strptime(card["open_date"], "%Y-%m-%d") if isinstance(card, pd.Series) else datetime.strptime(card["open_date"], "%Y-%m-%d")
            months_since_open = (REFERENCE_DATE - card_open).days / 30.44
        else:
            months_since_open = (REFERENCE_DATE - open_dt).days / 30.44

        is_active = months_since_open <= 36 and random.random() < (0.9 if months_since_open <= 12 else 0.7)

        ev = gen_events_one_customer(cid, is_active, min(active_days, 365))
        all_events.extend(ev)

        if (idx + 1) % 2000 == 0:
            print(f"  {idx+1}/{len(df_customers)} 客户, {len(all_events)} 条事件")

    df = pd.DataFrame(all_events)
    path = os.path.join(STRUCTURED_DIR, "app_events.csv")
    df.to_csv(path, index=False, encoding="utf-8-sig")

    print(f"\n✅ app_events.csv : {len(df)} 条")
    print(f"   事件类型: {dict(df['event_type'].value_counts())}")
    print(f"   设备数: {df['device_id'].nunique()}")
    print(f"   含搜索关键词: {df[df['search_keyword']!='']['search_keyword'].count()} 条")
    return df


if __name__ == "__main__":
    cp = os.path.join(STRUCTURED_DIR, "customer_basic.csv")
    rp = os.path.join(STRUCTURED_DIR, "credit_card.csv")
    if os.path.exists(cp) and os.path.exists(rp):
        generate_all_app_events(pd.read_csv(cp), pd.read_csv(rp))
    else:
        print("⚠️ 请先运行 generate_customers.py")
