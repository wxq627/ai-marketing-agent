# 项目一 -> 项目二: 数据供给清单 & 接口说明

> A(Knowledge Agent) -> B(Strategy Agent)

---

## 一、你现在能直接拿到的数据 (P0全部就绪)

### 1. 客户决策快照 `customer_snapshot.csv`

**一个文件包含B端需要的全部客户级字段**, 不需要B端逐条解析76万交易。

| 字段组 | 字段数 | 内容 |
|------|:--:|------|
| 标识 | 2 | `cust_id`, `oneid` |
| 基础画像 | 5 | age, city, income_level, lifecycle_stage, vip_tier |
| 卡与账户 | 5 | card_level, product_name, total_credit_amount, card_count, usage_rate |
| 价值消费 | 12 | annual_consumption, monthly_avg, cons_90d/30d/7d, txn_count_90d/30d/7d, active_days_90d/30d/7d, trend, installment |
| 风险 | 6 | overdue_status, history_overdue_count, min_payment_count, churn_risk_score, cash_advance_risk, risk_level |
| 画像标签 | 5 | value_level, activity_score, dormancy_risk, significant_signals, search_keywords_7d, browse_preferences_30d, milestones |
| 营销授权 | 13 | marketing_consent, personalization_consent, dnc_list, do_not_contact, blacklist_flag, push/sms/wechat/email/phone_consent, unsubscribe_channels, complaint_count_90d |
| 元数据 | 2 | data_version, generated_at |

**文件**: `mock_data/structured/customer_snapshot.csv` (8000行 × 52列)

### 2. 意图向量 `intent_vector.csv`

每个客户6类意图的评分(0-100), 主键: `cust_id` + `oneid`。

| 意图类型 | 字段名 |
|------|------|
| 分期/借贷需求 | `intent_分期_借贷需求` |
| 跨境/出行需求 | `intent_跨境_出行需求` |
| 额度/升级需求 | `intent_额度_升级需求` |
| 权益/优惠需求 | `intent_权益_优惠需求` |
| 沉睡/流失风险 | `intent_沉睡_流失风险` |
| 新户/激活引导 | `intent_新户_激活引导` |
| 主要意图 | `primary_intent` |

**文件**: `mock_data/structured/intent_vector.csv` (8000行 × 8列)

### 3. 事件序列 `event_sequence_per_customer.csv`

每个客户近30天的聚合关键事件(已去重+排序), 主键: `cust_id`。

| 字段 | 说明 |
|------|------|
| `event_type` | search / transaction / browse / service / campaign_click |
| `event_detail` | 搜索"分期费率" / 消费 5000元 / 浏览权益商城 |
| `event_time` | ISO 8601格式 |

**文件**: `mock_data/structured/event_sequence_per_customer.csv` (24,076条)

---

## 二、B端五个接口均已有数据支撑

| 接口 | 数据文件 | 状态 |
|------|------|:--:|
| `POST /api/v1/customer/search` | customer_snapshot.csv + intent_vector.csv | 🟢 |
| `POST /api/v1/customer/frequency-check` | contact_history.csv + frequency_rules.json + customer_consent.csv | 🟢 |
| `POST /api/v1/knowledge/search` | product_catalog.csv + benefit_catalog.csv + product_eligibility.csv + compliance_rules.json | 🟢 |
| `GET /api/v1/channels/context` | channel_config.csv | 🟢 |
| `POST /api/v1/campaign/performance/query` | campaign_attribution.csv + campaign_performance.csv | 🟢 |

---

## 三、字段规范确认

| 规范 | 我们的实现 |
|------|------|
| ID用字符串 | cust_id=C000001, oneid=UID000001 ✅ |
| 时间ISO 8601 | 2026-07-17T10:30:00+08:00 ✅ |
| 布尔true/false | 所有consent字段均为Python bool ✅ |
| 金额单位元 | 所有金额均以元为单位 ✅ |
| device_id->oneid映射 | id_mapping.csv已完成 ✅ |
| data_version+generated_at | customer_snapshot中已包含 ✅ |

---

## 四、仍需完善的内容 (后续迭代)

| 项目 | 当前状态 | 计划 |
|------|:--:|------|
| `frequency-check` API实现 | 接口已定义, 数据就绪 | 下一步实现FastAPI端点 |
| `campaign/performance/query` API | 接口已定义, 数据就绪 | 下一步实现 |
| 意图向量LLM评分 | 当前用规则模拟 | 生产环境接入Qwen3-8B |
| 实时事件流 | 当前用CSV批量 | 生产环境接入Kafka |
