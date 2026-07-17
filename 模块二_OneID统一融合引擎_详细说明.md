# 模块二：OneID 统一融合引擎 — 详细说明

> **所属项目**: 项目一 — 企业知识引擎与记忆中心 (Knowledge Agent)  
> **负责人**: A（偏大数据、RAG 底层）  
> **版本**: v1.0 | **日期**: 2026-07-16  
> **代码位置**: `oneid_engine/`

---

## 目录

1. [这个模块要解决什么问题](#1-这个模块要解决什么问题)
2. [为什么需要 OneID](#2-为什么需要-oneid)
3. [ID 分级策略](#3-id-分级策略)
4. [数据库表设计](#4-数据库表设计)
5. [核心算法：OneID 生成与解析](#5-核心算法oneid-生成与解析)
6. [冲突检测与去重合并](#6-冲突检测与去重合并)
7. [代码架构](#7-代码架构)
8. [API 接口清单](#8-api-接口清单)
9. [数据规模](#9-数据规模)
10. [测试结果](#10-测试结果)
11. [使用示例](#11-使用示例)
12. [与项目二/三的关系](#12-与项目二项目三的关系)

---

## 1. 这个模块要解决什么问题

### 一句话概括

> **同一个客户在银行的不同系统里用着不同的 ID，OneID 引擎把这些 ID 全部串联起来，让你知道"这其实是一个人"。**

### 现实场景

```text
客户「张*明」在XX银行的各个系统中，分别使用着完全不同的标识符：

┌──────────────────────────────────────────────────────────────┐
│                        同一个人 = 张*明                        │
├──────────────┬───────────────────┬────────────────────────────┤
│   银行核心系统  │   cust_id         │  C000001                   │
│   信用卡系统   │   card_no         │  6225****01 (主卡)          │
│              │   card_no         │  6225****02 (副卡)          │
│   CRM系统     │   crm_id          │  CRM030511                 │
│   APP埋点     │   device_id       │  DEV_A001 (主力手机)        │
│              │   device_id       │  DEV_B003 (iPad)           │
│              │   open_id          │  wx_openid_zhang           │
│   客服ASR     │   来电手机号        │  138****8888               │
│              │   身份证号          │  4403****001               │
└──────────────┴───────────────────┴────────────────────────────┘

如果没有 OneID，你想查"张*明最近做了什么"？
  → 你需要在 6 张表里用不同的 ID 分别去查，然后手工拼凑。

有了 OneID 之后：
  → 无论你手里有什么 ID，一键解析出 OneID，然后通过 OneID 拉取所有数据。
```

---

## 2. 为什么需要 OneID

### 在三个项目中的位置

```text
项目一 Knowledge Agent（我们）
  │
  ├── 模块一: Mock 数据体系      ← 造出多源异构数据
  ├── 模块二: OneID 融合引擎     ← 把这堆数据串起来  ← 你现在在这里
  ├── 模块三: 客户画像引擎        ← 基于 OneID 构建画像
  ├── 模块四: GraphRAG 知识图谱   ← 基于 OneID 关联产品/权益
  ├── 模块五: 意图识别引擎        ← 基于 OneID 聚合行为信号
  ├── 模块六: 统一 API 服务      ← 通过 OneID 对外提供数据
  └── 模块七: 数据基座大屏        ← 通过 OneID 展示客户360视图
                                    │
                                    ▼
项目二 Strategy Agent  ← 通过 OneID 查询客户画像、做策略决策
                                    │
                                    ▼
项目三 Marketing Agent ← 通过 OneID 找到客户、执行触达
```

**OneID 是整个系统的"身份证号"**，三个项目之间的所有数据传递都通过 OneID 来定位同一个客户。

---

## 3. ID 分级策略

不是所有 ID 都"一样可靠"。我们根据业务特性把 ID 分为三个等级：

| 级别 | ID 类型 | 置信度 | 确定性 | 说明 |
|:--:|---------|:--:|:--:|------|
| **强 ID** | `id_card` (身份证号) | **1.00** | 100% | 一个身份证绝对对应一个自然人。是 OneID 的**锚点** |
| **中 ID** | `cust_id` (银行客户号) | 1.00 | 100% | 银行核心系统的客户 ID，与身份证强绑定 |
| **中 ID** | `card_no` (卡号) | 1.00 | 100% | 每张卡通过银行核心系统绑定到唯一客户 |
| **中 ID** | `crm_id` (CRM编号) | 1.00 | 100% | CRM 系统与银行核心系统共享客户主数据 |
| **中 ID** | `phone` (手机号) | **0.95** | ~95% | 可能换号（旧号被回收后分配给新客户） |
| **弱 ID** | `device_id` (设备ID) | **0.90** | ~90% | 可能换手机、多人共用设备（如家庭 iPad） |
| **弱 ID** | `open_id` (微信OpenID) | **0.90** | ~90% | 微信账户通常与自然人一一对应，但也可能切换账户 |

### 分级的实际作用

```text
场景 1：通过身份证号查 OneID
  → 置信度 1.00，直接返回，100% 可信。

场景 2：通过 device_id 查 OneID  
  → 置信度 0.90，返回结果，但标记 is_verified=false
  → 项目二收到后知道这个结果"不够确定"，做决策时会保守一些。

场景 3：同一个 device_id 查到两个不同的 OneID
  → 可能是家庭共享 iPad，系统检测为冲突
  → 自动判断：如果两个关联的置信度都低 → 不自动合并，标记人工确认
```

---

## 4. 数据库表设计

### 表 A：`id_mapping` — ID 映射主表

存储**每一个 ID 到 OneID 的映射关系**。

```text
┌─────────┬──────────┬──────────┬──────────────┬────────────┬───────────────┬──────────────────┬──────────────────┬───────────┐
│   id    │  oneid   │ id_type  │   id_value   │ confidence │ source_system │    first_seen    │   last_updated   │ is_active │
├─────────┼──────────┼──────────┼──────────────┼────────────┼───────────────┼──────────────────┼──────────────────┼───────────┤
│    1    │UID000001 │ id_card  │ 4403****001  │    1.00    │    银行核心    │ 2026-07-15 00:00 │ 2026-07-15 00:00 │   true    │
│    2    │UID000001 │  phone   │ 138****8888  │    0.95    │    银行核心    │ 2026-07-15 00:00 │ 2026-07-15 00:00 │   true    │
│    3    │UID000001 │ cust_id  │  C000001     │    1.00    │    银行核心    │ 2026-07-15 00:00 │ 2026-07-15 00:00 │   true    │
│    4    │UID000001 │ card_no  │6225****01    │    1.00    │    银行核心    │ 2026-07-15 00:00 │ 2026-07-15 00:00 │   true    │
│    5    │UID000001 │ card_no  │6225****02    │    1.00    │    银行核心    │ 2026-07-15 00:00 │ 2026-07-15 00:00 │   true    │
│    6    │UID000001 │ crm_id   │ CRM030511    │    1.00    │     CRM       │ 2026-07-15 00:00 │ 2026-07-15 00:00 │   true    │
│    7    │UID000001 │device_id │ DEV_A001     │    0.90    │   APP埋点     │ 2026-07-15 00:00 │ 2026-07-15 00:00 │   true    │
│    8    │UID000001 │device_id │ DEV_B003     │    0.85    │   APP埋点     │ 2026-07-15 00:00 │ 2026-07-15 00:00 │   true    │
│    9    │UID000001 │ open_id  │wx_openid_zh  │    0.90    │   APP埋点     │ 2026-07-15 00:00 │ 2026-07-15 00:00 │   true    │
└─────────┴──────────┴──────────┴──────────────┴────────────┴───────────────┴──────────────────┴──────────────────┴───────────┘
```

| 字段 | 类型 | 说明 |
|------|------|------|
| `id` | BIGINT | 自增主键 |
| `oneid` | VARCHAR(32) | 全局唯一客户 ID，格式 `UID` + 6位序号，如 `UID000001` |
| `id_type` | VARCHAR(16) | ID 类型：`id_card` / `phone` / `card_no` / `device_id` / `open_id` / `crm_id` / `cust_id` |
| `id_value` | VARCHAR(128) | ID 值（已脱敏） |
| `confidence` | DECIMAL(3,2) | 映射置信度：1.00 = 确定，0.90 = 高，<0.85 = 低 |
| `source_system` | VARCHAR(32) | 来源系统：银行核心 / CRM / APP埋点 / ASR系统 |
| `first_seen` | DATETIME | 首次发现此 ID 的时间 |
| `last_updated` | DATETIME | 最后更新时间 |
| `is_active` | BOOLEAN | 是否仍有效（旧设备/退订的ID可标记 false） |

### 表 B：`id_mapping_log` — 映射变更日志

记录**每次 ID 映射的冲突和变更**，用于审计追溯。

| 字段 | 类型 | 说明 |
|------|------|------|
| `log_id` | VARCHAR(32) | 日志 ID |
| `id_value` | VARCHAR(128) | 发生冲突的 ID 值 |
| `old_oneid` | VARCHAR(32) | 原来的 OneID |
| `new_oneid` | VARCHAR(32) | 新的 OneID |
| `conflict_reason` | VARCHAR(256) | 冲突原因描述 |
| `resolution` | VARCHAR(32) | 解决方式：`自动合并` / `人工确认` / `保留原映射` |
| `resolved_at` | DATETIME | 解决时间 |

**模拟的 3 条冲突日志**（来自真实测试数据）：

| 日志ID | 场景 | 解决方式 |
|--------|------|:--:|
| LOG_001 | 旧手机号被新客户使用，系统检测到同号异人 | 人工确认 |
| LOG_002 | 疑似家庭共享 iPad，一个 device_id 被多人使用 | 保留原映射 |
| LOG_003 | 客户更换设备，旧 device_id 超过30天未活跃 | 自动合并 |

---

## 5. 核心算法：OneID 生成与解析

### 5.1 算法流程图

```text
                    输入: 一条客户记录，携带多个 ID
                    如: {id_card: "4403****001", phone: "138****8888",
                          cust_id: "C000001", device_id: "DEV_A001"}
                                  │
                                  ▼
          ┌────────────────────────────────────────────┐
          │  步骤 1: 检查强 ID（身份证号）               │
          │                                            │
          │  id_card 是否已在 id_mapping 表中？          │
          │    ├── 是 → 直接返回已有的 oneid             │
          │    └── 否 → 分配新 OneID: UID000042         │
          └──────────────────┬─────────────────────────┘
                             │
                             ▼
          ┌────────────────────────────────────────────┐
          │  步骤 2: 逐个处理所有 ID                     │
          │                                            │
          │  按置信度从高到低:                            │
          │    id_card → cust_id → card_no → crm_id    │
          │    → phone → device_id → open_id           │
          │                                            │
          │  对每个 ID:                                 │
          │    ├── 新 ID（表中不存在）→ 建立映射          │
          │    ├── 已存在且同一 OneID → 跳过              │
          │    └── 已存在但不同 OneID → 冲突！→ 步骤 3    │
          └──────────────────┬─────────────────────────┘
                             │
                             ▼
          ┌────────────────────────────────────────────┐
          │  步骤 3: 冲突检测与处理                      │
          │                                            │
          │  弱 ID (device_id/open_id) 冲突:            │
          │    置信度 < 0.85 → 自动迁移到新 OneID        │
          │    置信度 ≥ 0.85 → 双映射 + 标记人工确认      │
          │                                            │
          │  中/强 ID (phone/id_card) 冲突:              │
          │    → 记录日志，标记人工确认，不自动修改        │
          └──────────────────┬─────────────────────────┘
                             │
                             ▼
          ┌────────────────────────────────────────────┐
          │  输出:                                      │
          │  {                                         │
          │    "oneid": "UID000001",                    │
          │    "is_new": false,                         │
          │    "all_known_ids": [...],     ← 该客户全部ID│
          │    "conflicts": [...]          ← 冲突详情   │
          │  }                                         │
          └────────────────────────────────────────────┘
```

### 5.2 关键设计决策

**为什么以身份证号作为锚点？**

身份证号是中国大陆唯一、终身不变的自然人标识。银行开户时必须实名认证，所以 `customer_basic` 表中的 `cust_id ↔ id_card` 是一一对应的。

**如果客户记录中没有身份证号怎么办？**

算法会自动降级：先查 `cust_id` → 再查 `card_no` → 再查 `crm_id`。只要有一个中 ID 命中，就能找到 OneID。

**为什么 phone 的置信度是 0.95 而不是 1.00？**

因为手机号可能被回收。比如客户 A 注销了手机号，运营商半年后把这个号分配给了客户 B。如果 phone 置信度是 1.00，系统就会错误地把 B 关联到 A 的 OneID。0.95 的置信度意味着"大概率对，但需要其他证据交叉验证"。

---

## 6. 冲突检测与去重合并

### 6.1 冲突的类型

```text
类型 1: 弱 ID 被多个人使用
  例: 家庭 iPad (device_id=DEV_SHARED) 被 3 个家庭成员使用
  处理: 弱ID + 低置信度 → 可以多映射，但标记置信度低

类型 2: 中 ID 冲突（严重）
  例: 手机号被回收后分配给新客户，导致一个 phone 映射到两个 OneID
  处理: 记录日志 → 标记人工确认 → 不自动修改

类型 3: 两个 OneID 实际是同一个人（数据错误）
  例: 系统升级时同一个客户被创建了两次，有两个 OneID 但共享同一个身份证号
  处理: 定时任务检测到 → 自动合并 → 所有 ID 迁移到最早的 OneID
```

### 6.2 自动 vs 人工决策矩阵

| 冲突类型 | 示例 | 自动处理？ | 逻辑 |
|---------|------|:--:|------|
| 弱ID + 低置信度(<0.85) | 共享设备 | ✅ 自动 | 迁移到强ID锚定的OneID |
| 弱ID + 高置信度(≥0.85) | 设备疑似换人 | ❌ 人工 | 双映射 + 人工确认 |
| 中ID (phone) | 手机号回收 | ❌ 人工 | 记录日志 |
| 强ID (id_card) | 两个OneID同身份证 | ✅ 自动 | 定时去重任务自动合并 |

---

## 7. 代码架构

```text
oneid_engine/
│
├── __init__.py                   # 模块入口，版本号
│
├── id_mapping_store.py           # 【数据层】映射存储
│   │                              #  - 内存 + CSV 双后端
│   │                              #  - resolve() / add_mapping() / update_mapping()
│   │                              #  - find_conflicts() / stats()
│   │                              #  - 生产环境可替换为 PostgreSQL 后端
│   │
├── conflict_detector.py          # 【业务层】冲突检测
│   │                              #  - detect() 扫描冲突
│   │                              #  - resolve_conflict() 解决冲突
│   │                              #  - merge_duplicates() 合并重复 OneID
│   │                              #  - save_log() / load_log() 日志持久化
│   │
├── id_resolver.py                # 【核心引擎】OneID 解析
│   │                              #  - resolve() 查询 OneID（主入口）
│   │                              #  - register() 注册新客户 ID（4步算法）
│   │                              #  - register_batch() 批量注册
│   │                              #  - find_duplicates() 定期去重
│   │
├── router_id.py                  # 【接口层】FastAPI REST API
│   │                              #  - GET /resolve   → resolve_oneid()
│   │                              #  - POST /register → register_ids()
│   │                              #  - POST /merge    → merge_oneids()
│   │                              #  - GET /stats     → get_stats()
│   │                              #  - ...共 7 个接口
│   │
├── generate_id_mapping.py        # 【数据工具】从 mock 数据生成映射表
│   │                              #  - 读取所有结构化 CSV
│   │                              #  - 提取每个客户的跨系统 ID
│   │                              #  - 生成 id_mapping.csv + id_mapping_log.csv
│   │
└── test_oneid.py                 # 【测试】36 项测试全覆盖
                                   #  - 真实数据加载测试
                                   #  - OneID 解析测试（5种ID类型）
                                   #  - 新客户注册测试
                                   #  - 冲突检测 + 自动合并测试
                                   #  - ID 分级策略验证
                                   #  - 冲突日志读写测试
                                   #  - 存储层 CRUD 测试
```

### 调用关系

```text
router_id.py (FastAPI)
    │
    ▼
id_resolver.py (OneIdResolver)
    ├──→ id_mapping_store.py (IdMappingStore)
    │       └──→ id_mapping.csv (读写)
    │
    └──→ conflict_detector.py (ConflictDetector)
            └──→ id_mapping_log.csv (读写)
```

---

## 8. API 接口清单

### 8.1 核心接口

#### API-01: OneID 解析

```http
GET /api/v1/oneid/resolve?type=cust_id&value=C000001
```

**支持 7 种 ID 类型**：`id_card` / `phone` / `card_no` / `device_id` / `open_id` / `crm_id` / `cust_id`

**响应**：

```json
{
  "oneid": "UID000001",
  "resolved_from": {"type": "cust_id", "value": "C000001"},
  "confidence": 1.00,
  "all_known_ids": [
    {"type": "id_card",   "value": "3401****20", "confidence": 1.00, "source_system": "银行核心"},
    {"type": "phone",     "value": "136****0838","confidence": 0.95, "source_system": "银行核心"},
    {"type": "cust_id",   "value": "C000001",    "confidence": 1.00, "source_system": "银行核心"},
    {"type": "crm_id",    "value": "CRM030511",  "confidence": 1.00, "source_system": "CRM"},
    {"type": "card_no",   "value": "6225****61", "confidence": 1.00, "source_system": "银行核心"},
    {"type": "card_no",   "value": "6226****13", "confidence": 1.00, "source_system": "银行核心"},
    {"type": "card_no",   "value": "6214****27", "confidence": 1.00, "source_system": "银行核心"},
    {"type": "card_no",   "value": "6225****37", "confidence": 1.00, "source_system": "银行核心"},
    {"type": "device_id", "value": "DEV_A001",   "confidence": 0.90, "source_system": "APP埋点"},
    {"type": "open_id",   "value": "wx_openid_001","confidence": 0.90,"source_system": "APP埋点"}
  ],
  "customer_name": null,
  "is_verified": true
}
```

#### API-02: 注册新客户 ID

```http
POST /api/v1/oneid/register
Content-Type: application/json

{
  "ids": {
    "id_card": "6101****999",
    "phone": "158****9999",
    "cust_id": "C009999",
    "device_id": "DEV_TEST_001"
  },
  "source_system": "银行核心",
  "customer_name": "测试用户"
}
```

**响应**：

```json
{
  "oneid": "UID008001",
  "is_new": true,
  "ids_registered": 4,
  "conflicts": [],
  "all_known_ids": [...]
}
```

#### API-05: 合并重复 OneID

```http
POST /api/v1/oneid/merge
Content-Type: application/json

{
  "oneid_a": "UID000001",
  "oneid_b": "UID000042"
}
```

### 8.2 全部 7 个接口一览

| # | 方法 | 路径 | 功能 | 读/写 |
|:--:|:--:|------|------|:--:|
| 1 | GET | `/api/v1/oneid/resolve` | 根据任意ID查询OneID | 读 |
| 2 | POST | `/api/v1/oneid/register` | 注册新客户ID映射 | 写 |
| 3 | POST | `/api/v1/oneid/batch-register` | 批量注册 | 写 |
| 4 | GET | `/api/v1/oneid/{oneid}/ids` | 获取某OneID的所有ID | 读 |
| 5 | POST | `/api/v1/oneid/merge` | 手动合并重复OneID | 写 |
| 6 | GET | `/api/v1/oneid/stats` | 引擎统计信息 | 读 |
| 7 | GET | `/api/v1/oneid/conflicts` | 查看冲突日志 | 读 |

---

## 9. 数据规模

### 当前 Mock 数据集

| 指标 | 数值 |
|------|------|
| 总映射记录 | **64,776 条** |
| 唯一 OneID | **8,000 个**（= 8,000 个客户） |
| 平均每人 ID 数 | **8.1 个** |

### 各 ID 类型分布

| ID 类型 | 记录数 | 置信度 | 来源系统 |
|---------|:---:|:--:|------|
| `card_no` | 19,939 | 1.00 | 银行核心 |
| `cust_id` | 8,000 | 1.00 | 银行核心 |
| `id_card` | 8,000 | 1.00 | 银行核心 |
| `crm_id` | 8,000 | 1.00 | CRM |
| `phone` | 8,000 | 0.95 | 银行核心 |
| `open_id` | 8,000 | 0.90 | APP埋点 |
| `device_id` | 4,837 | 0.90 | APP埋点 |

> 每人有 1-4 张卡（平均 2.5 张），所以 `card_no` 数量 > 客户数。  
> 部分客户（校园卡用户）只有 1 台设备，所以 `device_id` < 客户数。

---

## 10. 测试结果

### 测试套件：36 项全部通过

```text
============================================================
Result: 36 PASS, 0 FAIL
ALL TESTS PASSED!
============================================================
```

### 测试覆盖详情

| 测试块 | 数量 | 验证内容 |
|--------|:--:|------|
| **真实数据加载** | 3 | 64,776条映射成功加载，8,000唯一OneID，7种ID类型全覆盖 |
| **OneID 解析** | 10 | cust_id/phone/card_no/device_id/open_id 五种ID类型解析 |
| | | C000001→UID000001，C005000→UID005000 确定性验证 |
| | | 不存在ID返回 error + confidence=0 |
| | | is_verified 状态正确 |
| **新客户注册** | 5 | 新id_card分配新OneID |
| | | 同id_card二次注册返回同一OneID |
| | | is_new 标记正确 |
| | | 4个ID全部注册成功 |
| **冲突检测与处理** | 3 | 共享device_id冲突被检测 |
| | | 同id_card映射到2个OneID被检测 |
| | | 自动合并成功 |
| **ID 分级策略** | 7 | 7种ID类型的置信度全部验证 |
| **冲突日志** | 4 | 3条模拟冲突全部加载 |
| | | 自动合并/人工确认/保留原映射 三种解决方式齐全 |
| **存储层CRUD** | 4 | add_mapping / resolve / get_all_ids / update_mapping |
| **合计** | **36** | **全部通过** |

---

## 11. 使用示例

### Python 代码示例

```python
from oneid_engine.id_resolver import OneIdResolver
from oneid_engine.id_mapping_store import IdMappingStore
from oneid_engine.conflict_detector import ConflictDetector

# 初始化引擎（自动加载 id_mapping.csv）
store = IdMappingStore()
detector = ConflictDetector()
resolver = OneIdResolver(store=store, detector=detector)

# ---- 示例 1: 查客户 ----
result = resolver.resolve("cust_id", "C000001")
print(f"OneID: {result['oneid']}")              # UID000001
print(f"已知ID数: {len(result['all_known_ids'])}")  # ~10
print(f"验证状态: {result['is_verified']}")       # True

# ---- 示例 2: 通过手机号查 ----
result = resolver.resolve("phone", "138****8888")
print(f"置信度: {result['confidence']}")          # 0.95

# ---- 示例 3: 注册新客户 ----
result = resolver.register(
    ids={
        "id_card": "6101****999",
        "phone": "158****9999",
        "cust_id": "C009999",
    },
    source_system="银行核心",
    customer_name="测试用户"
)
print(f"新OneID: {result['oneid']}")             # UID008001
print(f"是否新客户: {result['is_new']}")          # True

# ---- 示例 4: 查看统计 ----
stats = resolver.stats()
print(stats["mapping"])   # 总映射数、OneID数等
print(stats["conflicts"]) # 冲突日志统计
```

---

## 12. 与项目二/三的关系

### 在整体数据流中的位置

```text
项目三 (Marketing Agent)                   项目二 (Strategy Agent)
       │                                         │
       │  C→A 回流传入:                            │  A→B 查询:
       │  POST /api/v1/feedback/events              │  GET /api/v1/oneid/resolve?type=phone&value=...
       │  {                                         │
       │    "phone": "138****8888",    ──→  项目一   │  项目一 OneID 引擎
       │    "event_type": "click"        ←──  OneID │       │
       │  }                              引擎解析   │       ▼
       │                                  ↓        │  "UID000001" → 项目二拿到 OneID
       │                            "UID000001"    │       │
       │                                           │       ▼
       │                                           │  项目二用 OneID 查询画像
       │                                           │  GET /api/v1/customer/UID000001/profile
```

### 项目二如何使用 OneID

```text
场景: B端要给"最近搜索过分期费率的客户"推送分期优惠

1. B端从 APP 埋点数据中拿到一批 device_id 和 open_id
2. B端调用 resolve(device_id=DEV_A001) → 得到 UID000001
3. B端调用 resolve(open_id=wx_openid_zhang) → 也得到 UID000001  ← 去重！
4. B端调用 GET /customer/UID000001/profile → 获取完整画像
5. B端检查 consent: marketing_consent=true, push_consent=true ✅
6. B端做策略决策: 该客户适合推送12期分期免息
7. B端把决策发给 C 端，携带 oneid=UID000001
```

> **关键价值**: 没有 OneID，步骤 2 和 3 返回的是两个不同的 ID，B 端会以为是两个不同的人，导致重复触达。有了 OneID 之后，自动去重。

---

> **文档版本**: v1.1 | **下次更新**: 与项目二/三联调后根据反馈修订  
> **代码位置**: `oneid_engine/` | **数据位置**: `mock_data/structured/id_mapping*.csv`

---

## 13. OneID + 活动归因：完整效果追踪 🆕

### 为什么活动归因需要 OneID

```text
问题场景：评估"双十一分期大促"活动的效果

没有 OneID 时:
  项目二: 这个客户(cust_id=C001689)被推送了双十一活动
  项目三: 这个设备(device_id=DEV_B_770)在活动后消费了50元
  → 这俩是同一个人吗？无法确定！归因断裂！

有 OneID 时:
  项目二: cust_id=C001689 → OneID=UID001689
  项目三: device_id=DEV_B_770 → OneID=UID001689
  → 确认是同一个人！归因成功！此人因双十一活动消费50元。
```

### 归因链路全景

```text
┌─────────────────────────────────────────────────────────────────────┐
│              活动效果归因完整链路 (OneID 串联)                         │
├─────────────────────────────────────────────────────────────────────┤
│                                                                      │
│  campaign_catalog          campaign_performance                     │
│  ┌──────────────┐          ┌──────────────────────────────┐        │
│  │ 活动定义      │          │ 活动ROI汇总                   │        │
│  │ 25个活动      │          │ · ROI: 1857x                 │        │
│  │ 预算/规则     │          │ · CPA: ¥1.71-1.88            │        │
│  └──────┬───────┘          │ · 25,450 次转化              │        │
│         │                  └──────────────▲───────────────┘        │
│         │                                 │ 聚合                     │
│         ▼                                 │                         │
│  contact_history          campaign_attribution                      │
│  ┌──────────────┐         ┌──────────────────────────────┐         │
│  │ 触达记录      │────────→│ 归因明细                      │         │
│  │ 120,000条     │ touch_id│ 25,583条                     │         │
│  │ · 渠道        │         │ · touch_cost (单次成本)       │         │
│  │ · cost (成本) │         │ · converted (是否转化)        │         │
│  │ · status      │         │ · conversion_amount (金额)   │         │
│  └──────┬───────┘         │ · attribution_hours (时效)    │         │
│         │                  └──────────────┬───────────────┘         │
│         │                                 │                          │
│         ▼                                 ▼                          │
│       cust_id ──────────→  OneID 引擎  ←────────── cust_id          │
│                           ┌──────────┐                              │
│                           │ UIDXXXXXX │                              │
│                           └────┬─────┘                              │
│                                │                                     │
│                  ┌─────────────┼─────────────┐                      │
│                  ▼             ▼             ▼                      │
│           客户画像        客户授权        交易流水                    │
│           (profile)     (consent)       (transaction)               │
│                                                                      │
│  完整问题可回答:                                                      │
│  · "双十一活动给UID001689发了推送(cost=¥0.02)"                       │
│  · "UID001689 在推送后 3.5 小时打开并点击"                            │
│  · "UID001689 在推送后 128 小时产生了 ¥12,500 消费"                   │
│  · "该客户贡献 ROI: (12500-0.02)/0.02 = 624,999x"                   │
│  · "UID001689 是 high-value + low-risk 客户，可加大触达"              │
└─────────────────────────────────────────────────────────────────────┘
```

### 归因数据规模

| 数据层 | 记录数 | 说明 |
|--------|:---:|------|
| campaign_catalog | 25 | 活动定义 |
| contact_history | 120,000 | 触达记录 (含 cost 字段) |
| campaign_attribution | 25,583 | 归因明细 (点击→转化) |
| campaign_performance | 25 | 活动级ROI汇总 |
| id_mapping | 64,776 | OneID 映射 (串联全部) |

### 实操示例：追踪一个客户的完整活动效果

```python
from oneid_engine.id_resolver import OneIdResolver
import pandas as pd

resolver = OneIdResolver()
attr = pd.read_csv("mock_data/structured/campaign_attribution.csv")
perf = pd.read_csv("mock_data/structured/campaign_performance.csv")

# 1. 查客户 OneID
r = resolver.resolve("cust_id", "C001689")
oneid = r["oneid"]           # UID001689

# 2. 查该客户参与的所有活动
cust_attr = attr[attr["cust_id"] == "C001689"]
for _, row in cust_attr.iterrows():
    name = perf[perf["campaign_id"]==row["campaign_id"]]["campaign_name"].values[0]
    print(f"活动: {name}")
    print(f"  渠道: {row['channel']}, 触达成本: {row['touch_cost']}")
    print(f"  是否转化: {row['converted']}, 金额: {row['conversion_amount']}")
    print(f"  从触达到转化: {row['attribution_hours']}小时")

# 3. 查全平台 ROI
total_cost = perf["total_cost"].sum()
total_rev = perf["attributed_revenue"].sum()
print(f"\n全局ROI: {(total_rev-total_cost)/total_cost:.2f}x")
print(f"CPA均值: ¥{perf['cpa'].mean():.2f}")
```

### 一致性保证

| 检查项 | 状态 |
|--------|:--:|
| 归因表 cust_id 100% 可映射到 OneID | ✅ 7,833/7,833 |
| 归因表 campaign_id 100% 有效 | ✅ 25/25 |
| 性能表 conversions = 归因表 converted 之和 | ✅ 25,450 = 25,450 |
| contact_history 中 cost 与 channel_config 一致 | ✅ 8/8 渠道 |
| consent/cards/crm 中 cust_id 100% 可映射 | ✅ 8,000/8,000 |
