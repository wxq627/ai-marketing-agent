# 三项目接口对接规范 — Knowledge Agent (项目一)

> **文档目的**: 定义项目一(Knowledge Agent)对外暴露的全部接口契约，供项目二(Strategy Agent)和项目三(Marketing Agent)联调使用。
> **版本**: v1.0  
> **更新日期**: 2026-07-16  
> **数据基础**: XX银行信用卡中心真实产品/权益/活动体系

---

## 目录

- [一、三项目数据流全景](#一三项目数据流全景)
- [二、数据资产清单（项目一能提供什么）](#二数据资产清单项目一能提供什么)
- [三、A→B 接口：认知与数据供给](#三ab-接口认知与数据供给)
  - [API-01: 客户全景洞察](#api-01-客户全景洞察)
  - [API-02: 客户搜索与圈选](#api-02-客户搜索与圈选)
  - [API-03: GraphRAG 知识检索](#api-03-graphrag-知识检索)
  - [API-04: 渠道上下文查询](#api-04-渠道上下文查询)
  - [API-05: 频控状态查询](#api-05-频控状态查询)
- [四、C→A 接口：行为反馈与画像更新](#四ca-接口行为反馈与画像更新)
  - [API-06: 反馈事件回传](#api-06-反馈事件回传)
  - [API-07: 对话摘要回传](#api-07-对话摘要回传)
- [五、数据补充说明](#五数据补充说明)
- [六、Mock 数据现状与接口覆盖度矩阵](#六mock-数据现状与接口覆盖度矩阵)

---

## 一、三项目数据流全景

```text
┌──────────────────────────────────────────────────────────────────┐
│                      端到端数据与控制流闭环                         │
├──────────────────────────────────────────────────────────────────┤
│                                                                   │
│  ┌──────────────┐          ┌──────────────┐          ┌──────────┐│
│  │   项目一       │  A → B  │   项目二       │  B → C  │  项目三   ││
│  │  Knowledge    │────────→│  Strategy     │────────→│ Marketing ││
│  │  Agent (A)    │ 画像/意图 │  Agent (B)    │ 策略包   │  Agent (C)││
│  │               │←────────│               │←────────│          ││
│  └──────────────┘ 反馈回流  └──────────────┘ 效果归因  └──────────┘│
│       │                                                            │
│       │ ① 提供客户画像、意图、事件流                                  │
│       │ ② 提供企业知识、产品规则、权益、合规约束                       │
│       │ ③ 提供渠道状态、成本、频控规则                                │
│       │ ④ 接收C端反馈，更新画像与事件流                               │
│       │                                                            │
└──────────────────────────────────────────────────────────────────┘
```

### 三条核心集成流

| 流向 | 协议 | 触发时机 | 频率 |
|------|------|---------|:--:|
| **A → B** | REST API (同步) | B端开启策略决策前 | 按需 |
| **B → C** | REST API (同步) | B端完成策略推理后 | 按需 |
| **C → A** | REST API (异步) | C端监测到客户行为后 | 实时/准实时 |

> 本文档覆盖 **A→B** 和 **C→A** 两条流。B→C 流定义在项目二的项目文档中。

---

## 二、数据资产清单（项目一能提供什么）

### 2.1 结构化数据 (10张表 + 2张补充表)

| 数据表 | 行数 | 核心信息 | 接口使用 |
|--------|:---:|------|:------:|
| `customer_basic.csv` | 8,000 | 人口属性、城市、职业、收入等级 | Profile |
| `credit_card.csv` | 19,939 | 卡等级、授信额度、产品ID | Profile |
| `crm_customer.csv` | 8,000 | 生命周期、VIP等级、流失风险 | Profile |
| `customer_consent.csv` | 8,000 | **营销授权、渠道授权、免打扰标识** | 权限校验 |
| `transaction_log.csv` | 760,718 | 消费金额、商户类别、境外标识 | 事件流/意图 |
| `bill_record.csv` | 189,194 | 账单金额、还款状态、最低还款 | 事件流/意图 |
| `app_events.csv` | 369,497 | 页面浏览、搜索关键词、停留时长 | 事件流/意图 |
| `product_catalog.csv` | 15 | 产品名称、年费、卡等级、卖点 | 知识检索 |
| `benefit_catalog.csv` | 90 | 权益名称、类别、描述 | 知识检索 |
| `product_benefit_mapping.csv` | 711 | 产品-权益关联 | 知识检索 |
| `campaign_catalog.csv` | 25 | 活动名称、规则、目标客群 | 知识检索 |
| `channel_config.csv` | 8 | **渠道成本、可用性、容量、转化率** | 渠道上下文 |

### 2.2 非结构化数据

| 数据 | 数量 | 核心信息 | 接口使用 |
|------|:---:|------|:------:|
| ASR对话 | 956 | 客服对话记录+意图标注+情感标注 | 意图识别 |
| 产品文档 | 20 | 权益说明、分期条款、章程等 | GraphRAG检索 |
| 活动海报 | 12 | 活动规则、视觉描述、目标客群 | 知识检索 |
| `frequency_rules.json` | — | **各渠道频控上限、客户分层频控、负反馈升级** | 频控查询 |
| `compliance_rules.json` | — | **营销合规、隐私授权、内容规范、渠道规范** | 合规校验 |

### 2.3 关键业务指标（8000客户总体）

| 指标 | 数值 |
|------|------|
| 客户总数 | 8,000 |
| 持卡总数 | 19,939 (平均2.5张/人) |
| 卡等级分布 | 金卡56.3% / 校园卡17.8% / 白金卡14.3% / 普卡9.1% / 钻石卡1.7% / 无限卡0.9% |
| 收入分布 | M-47.0% / L-37.2% / H-15.8% |
| 生命周期 | 成熟期66.7% / 成长期15.4% / 沉睡期11.6% / 新户6.3% |
| 营销授权率 | 95.0% (7,601/8,000) |
| 免打扰(DNC)率 | 2.9% (229/8,000) |

---

## 三、A→B 接口：认知与数据供给

### API-01: 客户全景洞察

> B端调用此接口，一次获取策略决策所需的全部客户信息。

```http
POST /api/v1/customer/insight
```

**请求体**:

```json
{
  "oneids": ["UID000001", "UID000003"],
  "include_profile": true,
  "include_intent": true,
  "include_events": true,
  "include_consent": true,
  "event_window": "30d",
  "event_limit": 20
}
```

| 参数 | 类型 | 必填 | 说明 |
|------|------|:--:|------|
| `oneids` | string[] | 是 | OneID列表, 最多200个 |
| `include_profile` | bool | 否 | 是否返回画像 (默认true) |
| `include_intent` | bool | 否 | 是否返回意图向量 (默认true) |
| `include_events` | bool | 否 | 是否返回事件流 (默认true) |
| `include_consent` | bool | 否 | 是否返回授权状态 (默认true) |
| `event_window` | string | 否 | 事件时间窗口: 7d/30d/90d (默认30d) |
| `event_limit` | int | 否 | 每人最多返回事件数 (默认20) |

**响应体** (基于真实数据示例):

```json
{
  "request_id": "req_20260716_001",
  "generated_at": "2026-07-16T10:30:00+08:00",
  "customers": [
    {
      "oneid": "UID000001",
      "static_profile": {
        "gender": "M",
        "age": 32,
        "city": "深圳",
        "occupation": "IT/互联网",
        "income_level": "M",
        "education": "本科",
        "lifecycle_stage": "成熟期",
        "customer_since": "2021-03-13",
        "cards": [
          {
            "card_no": "6225**********61",
            "card_level": "金卡",
            "credit_amount": 28700.00,
            "product_id": "PROD_YOUNG_G",
            "product_name": "XX银行YOUNG卡（青年版）",
            "is_primary": true
          },
          {
            "card_no": "6214**********27",
            "card_level": "校园卡",
            "credit_amount": 29900.00,
            "product_id": "PROD_YOUNG_CAMPUS",
            "product_name": "XX银行YOUNG卡（校园版）",
            "is_primary": false
          }
        ],
        "risk_tags": {
          "churn_risk_score": 0,
          "vip_tier": "普通",
          "dnc_list": false
        },
        "value_tags": {
          "primary_card_level": "金卡",
          "total_credit_amount": 28700.00
        }
      },
      "dynamic_memory": {
        "consumption_30d": {"total": 8500.00, "count": 15},
        "consumption_trend_90d": "up",
        "browse_preferences": ["权益商城", "分期计算器", "账单详情"],
        "search_keywords_7d": ["分期费率", "出境游"]
      },
      "intent_vector": {
        "primary_intent": "分期/借贷需求",
        "intents": [
          {"type": "分期/借贷需求", "score": 85, "confidence": "high", "trend": "rising"},
          {"type": "跨境/出行需求", "score": 45, "confidence": "medium", "trend": "rising"},
          {"type": "权益/优惠需求", "score": 30, "confidence": "low", "trend": "stable"}
        ],
        "sentiment": {"overall": "neutral", "anxiety_score": 35, "satisfaction_score": 60}
      },
      "recent_events": [
        {
          "event_type": "search",
          "detail": "搜索'分期费率'",
          "timestamp": "2026-07-15T14:20:00+08:00",
          "channel": "app"
        },
        {
          "event_type": "transaction",
          "detail": "境外消费 $500.00 at Apple US",
          "timestamp": "2026-07-14T10:30:00+08:00",
          "channel": "Apple Pay"
        },
        {
          "event_type": "browse",
          "detail": "浏览'权益商城'页面 停留45秒",
          "timestamp": "2026-07-13T20:15:00+08:00",
          "channel": "app"
        }
      ],
      "consent": {
        "marketing_consent": true,
        "personalization_consent": true,
        "sms_consent": true,
        "phone_consent": false,
        "push_consent": true,
        "wechat_consent": true,
        "email_consent": true,
        "dnc_list": false,
        "available_channels": ["APP Push", "短信", "微信公众号", "邮件", "手机银行APP内消息"]
      },
      "contact_preference": "APP Push",
      "customer_manager": "吴芳"
    },
    {
      "oneid": "UID000003",
      "static_profile": {
        "gender": "F",
        "age": 28,
        "city": "北京",
        "occupation": "金融/保险",
        "income_level": "H",
        "education": "硕士",
        "lifecycle_stage": "新户",
        "customer_since": "2026-05-13",
        "cards": [
          {
            "card_no": "6225**********22",
            "card_level": "白金卡",
            "credit_amount": 223000.00,
            "product_id": "PROD_GLOBAL_W",
            "product_name": "XX银行全币种国际白金信用卡",
            "is_primary": true
          }
        ],
        "risk_tags": {
          "churn_risk_score": 10,
          "vip_tier": "金卡",
          "dnc_list": false
        },
        "value_tags": {
          "primary_card_level": "白金卡",
          "total_credit_amount": 223000.00
        }
      },
      "intent_vector": {
        "primary_intent": "新户/激活引导",
        "intents": [
          {"type": "新户/激活引导", "score": 72, "confidence": "high", "trend": "stable"},
          {"type": "权益/优惠需求", "score": 55, "confidence": "medium", "trend": "rising"}
        ]
      },
      "consent": {
        "marketing_consent": true,
        "personalization_consent": false,
        "available_channels": ["APP Push", "短信", "微信公众号", "手机银行APP内消息"],
        "dnc_list": false
      },
      "contact_preference": "短信",
      "customer_manager": "陈晓燕"
    }
  ]
}
```

---

### API-02: 客户搜索与圈选

> B端基于多条件筛选目标客群，获取符合条件的OneID列表用于策略投放。

```http
POST /api/v1/customer/search
```

**请求体**:

```json
{
  "filters": {
    "age_range": [25, 45],
    "city": ["深圳", "上海", "北京", "广州", "杭州"],
    "card_level": ["金卡", "白金卡", "钻石卡"],
    "lifecycle_stage": ["成长期", "成熟期"],
    "income_level": ["M", "H"],
    "intent": {"type": "分期/借贷需求", "score_min": 50},
    "marketing_consent": true,
    "exclude_dnc": true,
    "vip_tier": ["金卡", "白金", "钻石"]
  },
  "pagination": {"page": 1, "page_size": 50},
  "return_fields": ["oneid", "city", "card_level", "primary_intent", "intent_score"]
}
```

**响应体**:

```json
{
  "total_count": 3847,
  "page": 1,
  "page_size": 50,
  "customers": [
    {
      "oneid": "UID000005",
      "city": "深圳",
      "card_level": "白金卡",
      "primary_intent": "分期/借贷需求",
      "intent_score": 72
    }
  ]
}
```

**支持的筛选维度**（全部基于项目一现有数据）:

| 筛选维度 | 数据来源 | 示例值 |
|---------|---------|--------|
| `age_range` | customer_basic.age | `[25, 45]` |
| `city` | customer_basic.city | `["深圳","上海"]` |
| `income_level` | customer_basic.income_level | `["M","H"]` |
| `card_level` | credit_card.card_level | `["白金卡","钻石卡"]` |
| `lifecycle_stage` | crm_customer.lifecycle_stage | `["成熟期"]` |
| `vip_tier` | crm_customer.vip_tier | `["白金"]` |
| `churn_risk_max` | crm_customer.churn_risk_score | `50` |
| `intent.type` | intent_vector | `"分期/借贷需求"` |
| `intent.score_min` | intent_vector | `60` |
| `marketing_consent` | customer_consent | `true` |
| `exclude_dnc` | customer_consent.dnc_list | `true` |
| `has_cross_border` | transaction_log | `true` |

---

### API-03: GraphRAG 知识检索

> B端查询企业知识（产品规则、权益条款、合规约束）、C端查询权益说明等。

```http
POST /api/v1/knowledge/search
```

**请求体**:

```json
{
  "query": "白金卡有哪些机场权益？分期的合规要求是什么？",
  "customer_oneid": "UID000001",
  "top_k": 5,
  "include_graph": true,
  "include_vector": true,
  "knowledge_types": ["product", "benefit", "campaign", "compliance"]
}
```

**响应体**:

```json
{
  "query": "白金卡有哪些机场权益？分期的合规要求是什么？",
  "results": [
    {
      "rank": 1,
      "source_type": "graph",
      "content": "经典版白金信用卡 → 关联 → 机场贵宾厅服务(全年6次) → 含北京首都、上海浦东、深圳宝安等100余间",
      "source_doc": "product_docs/doc_01.txt",
      "entity_path": ["经典版白金信用卡", "出行权益", "机场贵宾厅服务"],
      "relevance_score": 0.95
    },
    {
      "rank": 2,
      "source_type": "vector",
      "content": "机场贵宾厅服务覆盖全球超过1000间机场贵宾厅。白金卡持卡人每年享有6次免费使用权益，可携带1人（扣减1次）。超次使用需3000积分/人次...",
      "source_doc": "product_docs/doc_01.txt",
      "relevance_score": 0.92
    },
    {
      "rank": 3,
      "source_type": "compliance",
      "content": "[合规规则 CMP-002] 所有涉及分期产品的营销文案必须明确标注年化利率(APR)",
      "source_doc": "compliance_rules.json",
      "relevance_score": 0.88
    }
  ],
  "graph_context": {
    "related_entities": [
      {"type": "Product", "id": "PROD_CLASSIC_W", "name": "经典版白金信用卡"},
      {"type": "Benefit", "id": "BEN_TRV_001", "name": "机场贵宾厅服务"},
      {"type": "Benefit", "id": "BEN_TRV_002", "name": "接送机服务"},
      {"type": "ComplianceRule", "id": "CMP-002", "name": "必须标注年化利率"}
    ]
  }
}
```

---

### API-04: 渠道上下文查询

> B端在决策触达渠道时，获取各渠道成本、可用性、容量等实时上下文。

```http
GET /api/v1/channels/context
```

**响应体** (基于 `channel_config.csv`):

```json
{
  "updated_at": "2026-07-16T00:00:00+08:00",
  "channels": [
    {
      "channel_code": "CH_PUSH",
      "channel_name": "APP Push",
      "channel_type": "owned",
      "cost_per_send": 0.02,
      "availability": "always",
      "daily_capacity": 500000,
      "monthly_capacity": 10000000,
      "today_used": 125000,
      "month_used": 3200000,
      "avg_open_rate": 0.18,
      "avg_click_rate": 0.06,
      "requires_consent": true,
      "supported_content": ["text", "image", "deeplink"],
      "status": "active"
    },
    {
      "channel_code": "CH_SMS",
      "channel_name": "短信",
      "channel_type": "owned",
      "cost_per_send": 0.06,
      "availability": "always",
      "daily_capacity": 200000,
      "monthly_capacity": 5000000,
      "today_used": 85000,
      "month_used": 2100000,
      "avg_open_rate": 0.08,
      "avg_click_rate": 0.02,
      "requires_consent": true,
      "supported_content": ["text", "shortlink"],
      "status": "active"
    },
    {
      "channel_code": "CH_PHONE",
      "channel_name": "电话外呼",
      "channel_type": "owned",
      "cost_per_send": 2.50,
      "availability": "business_hours",
      "daily_capacity": 5000,
      "today_used": 3200,
      "requires_consent": true,
      "supported_content": ["voice"],
      "status": "active"
    }
  ],
  "optimal_channel_ranking": {
    "by_cost": ["手机银行APP内消息", "APP Push", "邮件", "微信公众号", "短信", "彩信", "电话外呼"],
    "by_conversion": ["电话外呼", "手机银行APP内消息", "APP Push", "微信公众号", "短信", "邮件"],
    "by_reach": ["APP Push", "手机银行APP内消息", "短信", "微信公众号", "邮件", "电话外呼"]
  }
}
```

---

### API-05: 频控状态查询

> B端在策略决策前查询指定客户的触达频控状态，避免超频。

```http
POST /api/v1/customer/frequency-check
```

**请求体**:

```json
{
  "oneids": ["UID000001", "UID000007"],
  "planned_channel": "短信"
}
```

**响应体** (基于 `frequency_rules.json`):

```json
{
  "checked_at": "2026-07-16T10:30:00+08:00",
  "results": [
    {
      "oneid": "UID000001",
      "planned_channel": "短信",
      "can_send": true,
      "available_channels": ["APP Push", "短信", "微信公众号", "邮件", "手机银行APP内消息"],
      "frequency_status": {
        "today_sent": 1,
        "week_sent": 2,
        "month_sent": 5,
        "channel_today_sent": 0,
        "channel_week_sent": 1
      },
      "limits": {
        "channel_max_per_day": 1,
        "channel_max_per_week": 2,
        "global_max_per_day": 2,
        "global_max_per_week": 5,
        "cooldown_hours": 24
      },
      "customer_type": "normal",
      "blocked_channels": []
    },
    {
      "oneid": "UID000007",
      "planned_channel": "短信",
      "can_send": false,
      "available_channels": [],
      "frequency_status": {
        "today_sent": 0,
        "week_sent": 0,
        "month_sent": 0
      },
      "limits": {},
      "customer_type": "complaint_risk",
      "blocked_channels": ["电话外呼", "短信"],
      "block_reason": "客户在DNC名单中 (marketing_consent=false)"
    }
  ],
  "negative_feedback_rules": [
    "连续3次推送未点击 → 暂停72小时",
    "短信回复TD退订 → 永久禁止短信营销",
    "客户投诉营销骚扰 → 全局禁止主动营销"
  ]
}
```

---

## 四、C→A 接口：行为反馈与画像更新

### API-06: 反馈事件回传

> 项目三执行触达后，将客户行为事件回流项目一，更新画像和意图。

```http
POST /api/v1/feedback/events
```

**请求体**:

```json
{
  "batch_id": "batch_20260716_001",
  "campaign_id": "CAMP_2026_DOUBLE11",
  "events": [
    {
      "oneid": "UID000001",
      "event_type": "impression",
      "channel": "APP Push",
      "content_id": "push_20260716_double11_001",
      "event_time": "2026-07-16T10:01:00+08:00",
      "traffic_flag": "A",
      "metadata": {
        "device_id": "DEV_A001",
        "app_version": "9.4.4"
      }
    },
    {
      "oneid": "UID000001",
      "event_type": "click",
      "channel": "APP Push",
      "content_id": "push_20260716_double11_001",
      "event_time": "2026-07-16T10:03:00+08:00",
      "traffic_flag": "A",
      "metadata": {
        "deeplink_page": "分期计算器",
        "stay_sec": 67
      }
    },
    {
      "oneid": "UID000001",
      "event_type": "conversion",
      "channel": "APP Push",
      "content_id": "push_20260716_double11_001",
      "event_time": "2026-07-16T12:30:00+08:00",
      "traffic_flag": "A",
      "conversion_detail": {
        "conversion_type": "分期申请",
        "conversion_amount": 12500.00,
        "installment_periods": 12,
        "fee_rate": 0.0045
      }
    },
    {
      "oneid": "UID000001",
      "event_type": "dismiss",
      "channel": "APP Push",
      "content_id": "push_20260716_double11_003",
      "event_time": "2026-07-16T18:00:00+08:00",
      "traffic_flag": "A",
      "metadata": {
        "dismiss_reason": "用户滑动关闭"
      }
    }
  ]
}
```

**响应体**:

```json
{
  "status": "accepted",
  "batch_id": "batch_20260716_001",
  "received_events": 4,
  "queued_for_processing": true,
  "estimated_update_at": "2026-07-16T13:00:00+08:00"
}
```

**回流后项目一的处理逻辑**:

| 事件类型 | 画像更新动作 | 更新窗口 |
|---------|------------|:------:|
| `impression` | 累计曝光次数, 触达频控计数+1 | 实时 |
| `click` | 标记高意向, 活跃度加分, 渠道偏好更新 | 实时 |
| `conversion` | LTV加分, 意图下调(需求被满足), 转化标签 | 实时 |
| `dismiss` | 推送疲劳计数+1, 连续3次dismiss触发频控升级 | 实时 |
| `complaint` | churn_risk+30, VIP降级审查, DNC标记候选 | 实时 |
| `unsubscribe` | 对应渠道consent置false, 永久禁止该渠道 | 实时 |

---

### API-07: 对话摘要回传

> 项目三的对话Agent完成客户互动后，将对话摘要回传项目一，更新意图标签。

```http
POST /api/v1/feedback/conversation
```

**请求体**:

```json
{
  "oneid": "UID000001",
  "conversation_id": "CHAT_20260716_8899",
  "agent_type": "marketing_agent",
  "timestamp": "2026-07-16T14:30:00+08:00",
  "campaign_id": "CAMP_2026_DOUBLE11",
  "summary": {
    "topic": "分期办理咨询",
    "customer_intent": "分期/借贷需求",
    "intent_confidence": 0.92,
    "sentiment": "neutral_to_satisfied",
    "resolution": "成功办理12期分期，客户表示满意",
    "key_phrases": ["12期", "手续费0.45%", "每月1652元"],
    "customer_concerns": ["手续费是否划算", "能否提前还款"],
    "next_best_action": "3个月后推送提额邀请"
  },
  "updated_intent_signals": [
    {"intent_type": "分期/借贷需求", "score_delta": -0.30, "reason": "需求已被满足"},
    {"intent_type": "额度/升级需求", "score_delta": 0.15, "reason": "分期后额度使用率将上升"}
  ]
}
```

**响应体**:

```json
{
  "status": "accepted",
  "conversation_id": "CHAT_20260716_8899",
  "profile_updates": {
    "intent_updated": true,
    "events_appended": 3,
    "sentiment_updated": true
  }
}
```

---

## 五、数据补充说明

### 5.1 为支持三项目对接，新增的补充数据

| 新增文件 | 说明 | 用途 |
|---------|------|------|
| `structured/channel_config.csv` | 8个渠道的成本、容量、转化率、状态 | API-04 渠道上下文查询 |
| `structured/customer_consent.csv` | 8,000客户的营销授权、渠道授权、DNC标识 | API-01/02/05 权限校验 |
| `unstructured/frequency_rules.json` | 全局+分渠道+分客群的频控规则 | API-05 频控状态查询 |
| `unstructured/compliance_rules.json` | 产品营销/隐私/内容/渠道的合规规则 | API-03 知识检索 |

### 5.2 关键字段的数据来源映射

| 接口字段 | 数据来源 | 计算/取值方式 |
|---------|---------|-------------|
| `static_profile.*` | customer_basic + credit_card + crm_customer | 直接映射+JOIN |
| `value_tags` | credit_card + transaction_log 聚合 | 取主卡等级、总额度、近12月消费 |
| `risk_tags.churn_risk_score` | crm_customer.churn_risk_score | 直接映射 (0-100) |
| `risk_tags.dnc_list` | customer_consent.dnc_list | 直接映射 |
| `intent_vector` | app_events.search_keyword + ASR intent_label + 规则评分 | 规则引擎+LLM融合计算 |
| `recent_events` | transaction_log + app_events | 按timestamp倒序取窗口内数据 |
| `consent.*` | customer_consent | 直接映射 |
| `frequency_status` | 从C端回流事件累计 + frequency_rules | 实时聚合+规则判定 |
| `domain_knowledge` | product_catalog + benefit_catalog + compliance_rules | GraphRAG检索 |

### 5.3 需要项目二/三配合的数据

| 需要对方提供 | 由谁提供 | 何时提供 |
|------------|:------:|---------|
| `campaign_id` + 策略包JSON | 项目二 → 项目一 | B端完成策略推理后 |
| 客户反馈事件 (曝光/点击/转化/投诉) | 项目三 → 项目一 | 触达后实时 |
| 对话摘要 + 意图信号更新 | 项目三 → 项目一 | 对话完成后 |
| 策略效果归因数据 | 项目二 → 项目一 | T+1批量 |

---

## 六、Mock 数据现状与接口覆盖度矩阵

| 接口 | 数据支撑度 | 说明 |
|------|:--:|------|
| **API-01** 客户全景洞察 | 🟢 完整 | 画像、意图、事件、授权数据均就绪，可直接联调 |
| **API-02** 客户搜索圈选 | 🟢 完整 | 15个筛选维度均有数据支撑 |
| **API-03** GraphRAG知识检索 | 🟢 完整 | 15产品+90权益+25活动+20文档+合规规则 |
| **API-04** 渠道上下文查询 | 🟢 完整 | 8渠道的成本/容量/转化率数据就绪 |
| **API-05** 频控状态查询 | 🟢 完整 | 频控规则+分层策略+负反馈升级规则就绪 |
| **API-06** 反馈事件回传 | 🟡 接口就绪 | Schema已定义，需项目三对接测试 |
| **API-07** 对话摘要回传 | 🟡 接口就绪 | Schema已定义，需项目三对接测试 |

> 🟢 = 数据完整, 可直接联调 | 🟡 = 接口已定义, 待对方对接 | 🔴 = 待补充

---

> **文档版本**: v1.0 | **下次更新**: 与项目二/三联调后根据反馈修订
