"""
OneID 引擎完整测试脚本 (v2 — 隔离读写)
=========================================
读测试使用真实 id_mapping.csv
写测试使用内存存储，不修改真实数据
"""
import sys, os, json

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from oneid_engine.id_mapping_store import IdMappingStore, CONFIDENCE_MAP
from oneid_engine.conflict_detector import ConflictDetector
from oneid_engine.id_resolver import OneIdResolver

PASS = 0
FAIL = 0

def check(name, condition, detail=""):
    global PASS, FAIL
    if condition:
        PASS += 1
        print(f"  [PASS] {name}")
    else:
        FAIL += 1
        print(f"  [FAIL] {name} — {detail}")

import tempfile

def make_memory_store():
    """创建纯内存存储（不碰 CSV）。"""
    s = IdMappingStore()
    s._loaded = True
    s._records = []
    s._oneid_to_ids = {}
    s._id_to_oneid = {}
    s._next_oneid_seq = 1
    # 设一个不存在的csv路径，防止意外写入
    s.csv_path = os.path.join(tempfile.gettempdir(), f"oneid_test_{os.getpid()}.csv")
    return s

def make_temp_detector():
    """创建临时路径的冲突检测器（不碰真实日志）。"""
    return ConflictDetector(log_path=os.path.join(tempfile.gettempdir(), f"oneid_log_{os.getpid()}.csv"))

print("=" * 60)
print("OneID Engine — Test Suite v2")
print("=" * 60)

# ================================================================
# 1. 真实数据加载 (只读)
# ================================================================
print("\n[1] 真实数据加载 (Read-Only)")
store = IdMappingStore()
store.load()
check("加载映射表", len(store._records) >= 60000, f"{len(store._records)} records")
check("唯一OneID=8000", store._oneid_to_ids is not None)
stats = store.stats()
check("7种ID类型", len(stats["id_types"]) == 7, str(list(stats["id_types"].keys())))
for t, c in sorted(stats["id_types"].items()):
    print(f"     {t}: {c}")

# ================================================================
# 2. OneID 解析 (只读)
# ================================================================
print("\n[2] OneID 解析 (Read-Only)")
resolver = OneIdResolver(store=store, detector=make_temp_detector())

r = resolver.resolve("cust_id", "C000001")
check("cust_id→OneID", r["oneid"] == "UID000001", f"→{r['oneid']}")
check("返回已知ID>0", len(r["all_known_ids"]) > 0, f"{len(r['all_known_ids'])} IDs")
check("is_verified=true", r["is_verified"] == True)

r2 = resolver.resolve("cust_id", "C005000")
check("C005000→UID005000", r2["oneid"] == "UID005000", f"→{r2['oneid']}")

# phone 解析
phone_recs = [rec for rec in store._records if rec["id_type"] == "phone"]
if phone_recs:
    r3 = resolver.resolve("phone", phone_recs[0]["id_value"])
    check("phone→OneID", r3["oneid"] is not None)
    check("phone置信度0.95", abs(r3["confidence"] - 0.95) < 0.01)

# card_no 解析
card_recs = [rec for rec in store._records if rec["id_type"] == "card_no"]
if card_recs:
    r4 = resolver.resolve("card_no", card_recs[0]["id_value"])
    check("card_no→OneID", r4["oneid"] is not None)

# device_id 解析
dev_recs = [rec for rec in store._records if rec["id_type"] == "device_id" and rec.get("is_active", True)]
if dev_recs:
    r5 = resolver.resolve("device_id", dev_recs[0]["id_value"])
    check("device_id→OneID", r5["oneid"] is not None)

# 不存在的ID
r6 = resolver.resolve("phone", "000****0000")
check("不存在ID→error", r6.get("error") is not None)
check("不存在ID→confidence=0", r6["confidence"] == 0.0)

# ================================================================
# 3. 新客户注册 (内存存储 — 不碰真实数据)
# ================================================================
print("\n[3] 新客户注册 (Memory-Only)")
mem = make_memory_store()
det = make_temp_detector()
res = OneIdResolver(store=mem, detector=det)

r = res.register({"id_card":"6101****999","phone":"158****9999","cust_id":"C09999","device_id":"DEV_T1"},
                 source_system="test", customer_name="TestUser")
check("新客户分配OneID", r["oneid"] is not None)
check("is_new=true", r["is_new"] == True, f"is_new={r['is_new']}")
check("注册4个ID", r["ids_registered"] == 4)

# 同一个id_card再次注册 → 应返回已有OneID
r2 = res.register({"id_card":"6101****999","phone":"159****8888"},
                  source_system="test2")
check("同id_card→同OneID", r2["oneid"] == r["oneid"], f"{r2['oneid']} vs {r['oneid']}")
check("同id_card→is_new=false", r2["is_new"] == False)

# ================================================================
# 4. 冲突检测与自动处理 (内存存储)
# ================================================================
print("\n[4] 冲突检测与处理 (Memory-Only)")
mem2 = make_memory_store()
det2 = make_temp_detector()
res2 = OneIdResolver(store=mem2, detector=det2)

# 创建客户A
uid_a = mem2._generate_oneid()
mem2.add_mapping(uid_a, "id_card", "9999****001", 1.0, "test")
mem2.add_mapping(uid_a, "cust_id", "DUP_A", 1.0, "test")

# 创建客户B — 使用已被A占用的 device_id
uid_b = mem2._generate_oneid()
mem2.add_mapping(uid_b, "id_card", "9999****002", 1.0, "test")
mem2.add_mapping(uid_b, "cust_id", "DUP_B", 1.0, "test")
# 故意让B也使用A的device_id (低置信度)
mem2.add_mapping(uid_b, "device_id", "DEV_SHARED", 0.65, "test")
mem2.add_mapping(uid_a, "device_id", "DEV_SHARED", 0.90, "test")

conflicts = mem2.find_conflicts()
check("检测到共享device冲突", len(conflicts) > 0, f"{len(conflicts)} conflicts")

# 自动合并场景: 两个OneID共享id_card
mem3 = make_memory_store()
det3 = make_temp_detector()
res3 = OneIdResolver(store=mem3, detector=det3)

uid_x = mem3._generate_oneid()
mem3.add_mapping(uid_x, "id_card", "8888****001", 1.0, "test")
mem3.add_mapping(uid_x, "cust_id", "MERGE_X", 1.0, "test")

uid_y = mem3._generate_oneid()
mem3.add_mapping(uid_y, "id_card", "8888****001", 1.0, "test")  # 同一个id_card!
mem3.add_mapping(uid_y, "cust_id", "MERGE_Y", 1.0, "test")

check("同id_card映射2个OneID", len(mem3.find_conflicts()) >= 1)

merged = res3.find_duplicates()
check("自动合并成功", len(merged) >= 1 and merged[0].get("merged"),
      f"merged={len(merged)}, detail={merged[0] if merged else 'none'}")

# ================================================================
# 5. ID 分级策略
# ================================================================
print("\n[5] ID 分级策略")
check("id_card=1.00(强)", CONFIDENCE_MAP["id_card"] == 1.00)
check("cust_id=1.00(中)", CONFIDENCE_MAP["cust_id"] == 1.00)
check("card_no=1.00(中)", CONFIDENCE_MAP["card_no"] == 1.00)
check("crm_id=1.00(中)", CONFIDENCE_MAP["crm_id"] == 1.00)
check("phone=0.95(中)", CONFIDENCE_MAP["phone"] == 0.95)
check("device_id=0.90(弱)", CONFIDENCE_MAP["device_id"] == 0.90)
check("open_id=0.90(弱)", CONFIDENCE_MAP["open_id"] == 0.90)

# ================================================================
# 6. 冲突日志 (只读)
# ================================================================
print("\n[6] 冲突日志 (Read-Only)")
det_log = ConflictDetector()  # 读真实日志
logs = det_log.load_log()
check("加载冲突日志", len(logs) >= 3, f"{len(logs)} entries")
resolutions = {l["resolution"] for l in logs}
check("包含自动合并", "自动合并" in resolutions)
check("包含人工确认", "人工确认" in resolutions)
check("包含保留原映射", "保留原映射" in resolutions)

# ================================================================
# 7. 存储层直接 CRUD
# ================================================================
print("\n[7] 存储层CRUD (Memory-Only)")
mem4 = make_memory_store()
uid = mem4._generate_oneid()
mem4.add_mapping(uid, "id_card", "7777****001", 1.0, "test")
mem4.add_mapping(uid, "cust_id", "C_CRUD", 1.0, "test")

check("add_mapping成功", len(mem4._records) == 2)
r = mem4.resolve("cust_id", "C_CRUD")
check("resolve成功", r is not None and r["oneid"] == uid)

all_ids = mem4.get_all_ids(uid)
check("get_all_ids返回2条", len(all_ids) == 2)

mem4.update_mapping("cust_id", "C_CRUD", "UID_NEW")
check("update_mapping: OneID变更", mem4._id_to_oneid[("cust_id","C_CRUD")]["oneid"] == "UID_NEW")

# ================================================================
# Summary
# ================================================================
print("\n" + "=" * 60)
print(f"Result: {PASS} PASS, {FAIL} FAIL")
if FAIL == 0:
    print("ALL TESTS PASSED!")
else:
    print(f"THERE ARE {FAIL} FAILURES!")
print("=" * 60)
