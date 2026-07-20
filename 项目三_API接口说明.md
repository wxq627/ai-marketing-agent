# 项目三 → 项目一 API 接口说明

> **版本**: v2.0 | **更新**: 2026-07-20 | **Base URL**: `http://<host>:8000`

---

## 接口概览

| 接口 | 方法 | 用途 |
|------|------|------|
| `/api/v1/db/feedback/import` | POST | 回传事件(点击/拒绝/对话/转化) — **最常用** |
| `/api/v1/db/campaign/import` | POST | 新建/更新活动 |
| `/api/v1/db/feedback/recent` | GET | 查询最近回传记录 |

Swagger 文档: `http://<host>:8000/docs`

---

## 一、回传事件 (最常用)

```
POST /api/v1/db/feedback/import
Content-Type: application/json
```

### 请求体: 事件数组

```json
[
  {
    "oneid": "UID000001",
    "event_type": "click",
    "campaign_id": "CAMP_2026_DOUBLE11",
    "channel": "APP Push",
    "timestamp": "2026-07-20T14:30:00"
  }
]
```

### 事件类型说明

#### 1. click — 用户点击"感兴趣"

```json
{
  "oneid": "UID000001",
  "event_type": "click",
  "campaign_id": "CAMP_2026_DOUBLE11",
  "channel": "APP Push",
  "timestamp": "2026-07-20T14:30:00"
}
```

| 字段 | 必填 | 说明 |
|------|------|------|
| oneid | ✅ | 客户唯一标识 (UID开头) |
| event_type | ✅ | 固定 `"click"` |
| campaign_id | ✅ | 活动ID |
| channel | - | 渠道: APP Push / 邮件 / 微信 |
| timestamp | - | ISO 8601 时间 |

#### 2. reject — 用户点击"不感兴趣"

```json
{
  "oneid": "UID000001",
  "event_type": "reject",
  "campaign_id": "CAMP_2026_DOUBLE11",
  "channel": "APP Push",
  "timestamp": "2026-07-20T14:30:00"
}
```

#### 3. conversation — 对话交互 (实时更新动态记忆)

```json
{
  "oneid": "UID000001",
  "event_type": "conversation",
  "conversation_id": "3cc87fa2-4e2d-4b",
  "summary": "用户咨询白金卡机场权益和分期费率",
  "intent": "权益咨询",
  "sentiment": "中性",
  "top_concerns": ["机场贵宾厅", "分期费率", "白金卡权益"],
  "round_count": 3,
  "timestamp": "2026-07-20T14:30:00"
}
```

| 字段 | 必填 | 说明 | 实时更新 |
|------|------|------|---------|
| oneid | ✅ | 客户唯一标识 | - |
| event_type | ✅ | 固定 `"conversation"` | - |
| summary | ✅ | 对话摘要 | → `key_milestones` 关键事件 |
| intent | ✅ | 意图: 权益咨询/分期需求/额度升级/账户问题/销户等 | → `browse_preferences` 浏览偏好 |
| sentiment | ✅ | 情感: 中性/满意/焦虑/不满 | → `significant_signals` 预警信号 |
| top_concerns | ✅ | 用户关注的话题列表 | → `search_keywords` 搜索关键词 |
| conversation_id | - | 对话会话ID (用于去重) | - |
| round_count | - | 对话轮数 | - |

**实时更新效果**: 对话数据写入后, 客户360大屏的「动态记忆」Tab 立即显示更新后的搜索关键词/浏览偏好/关键事件/预警信号。

#### 4. conversion — 消费转化

```json
{
  "oneid": "UID000001",
  "event_type": "conversion",
  "campaign_id": "CAMP_2026_DOUBLE11",
  "amount": 5000,
  "channel": "APP Push",
  "timestamp": "2026-07-20T14:30:00"
}
```

| 字段 | 必填 | 说明 | 实时更新 |
|------|------|------|---------|
| oneid | ✅ | 客户唯一标识 | - |
| event_type | ✅ | 固定 `"conversion"` | - |
| campaign_id | ✅ | 归因活动ID | - |
| amount | ✅ | 消费金额(元) | → `value_annual_consumption` + `value_monthly_avg` |

---

## 二、新建活动

```
POST /api/v1/db/campaign/import
Content-Type: application/json
```

```json
[
  {
    "campaign_id": "CAMP_2026_NEW_CAMPAIGN",
    "campaign_name": "新活动名称",
    "start_date": "2026-08-01",
    "end_date": "2026-08-31",
    "budget": 500000,
    "rules": {
      "返现比例": 0.05,
      "适用商户": ["天猫", "京东"],
      "最低消费": 500
    }
  }
]
```

| 字段 | 必填 | 说明 |
|------|------|------|
| campaign_id | ✅ | 活动唯一ID |
| campaign_name | ✅ | 活动名称 |
| start_date | - | 开始日期 YYYY-MM-DD |
| end_date | - | 结束日期 |
| budget | - | 预算(元) |
| rules | - | 活动规则 (任意JSON) |

---

## 三、查询回传记录

```
GET /api/v1/db/feedback/recent?limit=20
```

---

## 四、oneid 获取方式

如果只知道 `cust_id` 或 `phone`，可以先查客户获取 `oneid`:

```
GET /api/v1/customer/search?q=手机号或cust_id
```

---

## 五、完整示例: Python 调用

```python
import requests

BASE = "http://localhost:8000"

# 1. 回传对话事件
events = [{
    "oneid": "UID000001",
    "event_type": "conversation",
    "summary": "用户咨询白金卡机场权益",
    "intent": "权益咨询",
    "sentiment": "满意",
    "top_concerns": ["机场贵宾厅", "接送机", "酒店权益"],
    "round_count": 5
}]
r = requests.post(f"{BASE}/api/v1/db/feedback/import", json=events)
print(r.json())
# → {"imported": 1, "results": [{"status":"ok","event_type":"conversation","oneid":"UID000001","profile_updated":["short_term_7d_top_search_keywords","mid_term_30d_browse_preferences","key_milestones"],"signals":["对话:intent=权益咨询,sentiment=满意"]}]}

# 2. 新建活动
campaigns = [{
    "campaign_id": "CAMP_2026_TEST",
    "campaign_name": "测试活动",
    "start_date": "2026-08-01",
    "end_date": "2026-08-31",
    "budget": 100000
}]
r = requests.post(f"{BASE}/api/v1/db/campaign/import", json=campaigns)
print(r.json())
# → {"imported": 1, "results": [{"status":"ok","campaign_id":"CAMP_2026_TEST","action":"insert_or_update"}]}

# 3. 回传点击事件
events = [{
    "oneid": "UID000001",
    "event_type": "click",
    "campaign_id": "CAMP_2026_TEST"
}]
r = requests.post(f"{BASE}/api/v1/db/feedback/import", json=events)
print(r.json())
```

---

## 六、实时更新链路

```
项目三 POST /feedback/import
         │
    ┌────▼────────────────────────────────────┐
    │ db_store.feedback_insert()              │
    │                                         │
    │ ① INSERT feedback_events (记录事件)      │
    │ ② UPDATE customer_profile (实时更新)     │
    │    - conversation→搜索词/浏览偏好/关键事件│
    │    - conversion→年消费/月均              │
    │    - click/reject→预警信号               │
    └────┬────────────────────────────────────┘
         │
    ┌────▼────────────────────────────────────┐
    │ 客户360大屏 (dashboard_customer360)      │
    │                                         │
    │ 清空缓存(Clear Cache) → 立即可见更新     │
    │ 自动刷新: @st.cache_data(ttl=15)         │
    └─────────────────────────────────────────┘
```

---

## 七、注意事项

1. **oneid 必须正确**: 传错则更新不到正确的客户画像
2. **conversation 的 summary/intent/sentiment/top_concerns 尽量填**: 这四个字段直接影响大屏的动态记忆和意图识别
3. **campaign_id 需要先注册**: 新活动先调 `/campaign/import` 再回传事件
4. **大屏刷新**: 回传后点「清空缓存」按钮或等15秒自动刷新
