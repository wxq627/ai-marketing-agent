# 三个项目之间的联系、传递数据与数据类型

## 1. 总体关系

三个项目之间是一个闭环，而不是三个孤立模块：

```text
项目一 Knowledge Agent
  -> 提供客户画像、企业知识、产品规则、权限、合规约束
项目二 Strategy Agent
  -> 进行群像刻画、客群圈选、策略生成、预算和渠道决策
项目三 Marketing Agent
  -> 与客户交互、执行触达、生成内容、收集反馈
反馈数据
  -> 回流项目一更新画像，也回流项目二优化策略
```

## 2. 项目一 -> 项目二：认知与数据供给

接口名称建议：

```text
POST /api/knowledge/customer-insight
```

作用：

项目二在生成策略前，向项目一请求客户画像、意图、事件流、产品规则、权限和合规知识。

### 传递数据类型

| 数据对象 | 类型 | 说明 |
|---|---|---|
| CustomerProfile | object | 客户画像，包括基础属性、价值等级、生命周期、风险等级、标签等 |
| IntentVector | object | 当前意图向量，包括客户近期咨询、搜索、浏览、消费变化等意图评分 |
| EventSequence | array<object> | 客户历史行为事件流，如曝光、点击、领取、拒绝、投诉、咨询 |
| DomainKnowledge | object | 企业知识、产品规则、权益规则、权限规则、合规约束 |
| ChannelContext | object | 渠道状态、渠道成本、通道可用性、频控规则 |

### 示例 JSON

```json
{
  "campaign_id": "CMP20260715001",
  "target_product": "credit_card_installment",
  "customers": [
    {
      "customer_id": "C001",
      "customer_profile": {
        "age": 29,
        "city_tier": 1,
        "lifecycle_stage": "active",
        "value_level": "high",
        "credit_limit_usage": 0.68,
        "monthly_spend": 12000,
        "tags": ["高消费", "App活跃", "分期敏感"],
        "marketing_consent": true,
        "risk_level": "low",
        "complaint_risk": 0.03,
        "recent_contact_count": 1,
        "preferred_channel": "app"
      },
      "intent_vector": {
        "top_intents": [
          {"name": "账单压力", "score": 0.82},
          {"name": "分期咨询", "score": 0.76}
        ],
        "embedding": [0.12, 0.33, 0.48],
        "updated_at": "2026-07-15T10:00:00+08:00"
      },
      "event_sequence": [
        {
          "event_type": "app_search",
          "event_name": "搜索分期费率",
          "event_time": "2026-07-14T20:31:00+08:00"
        }
      ]
    }
  ],
  "domain_knowledge": {
    "product_rules": [
      "分期活动不可承诺收益",
      "短信文案必须包含退订方式"
    ],
    "permission_rules": [
      "marketing_consent=false 的客户不可触达",
      "未授权客户不可使用个性化推荐"
    ],
    "frequency_rules": [
      "近7天触达超过2次的客户不得再次短信触达"
    ],
    "compliance_rules": [
      "不得使用稳赚、保证、省钱无忧等绝对化表述"
    ]
  },
  "channel_context": {
    "available_channels": ["app_push", "sms", "wechat"],
    "channel_cost": {
      "app_push": 0.02,
      "sms": 0.06,
      "wechat": 0.3
    },
    "channel_status": {
      "app_push": "available",
      "sms": "available",
      "wechat": "available"
    }
  }
}
```

## 3. 项目二 -> 项目三：策略下发与执行

接口名称建议：

```text
POST /api/marketing/deploy-campaign
```

作用：

项目二完成策略推理后，向项目三下发标准策略包。项目三根据策略包生成内容、选择渠道并触达客户。

### 传递数据类型

| 数据对象 | 类型 | 说明 |
|---|---|---|
| CampaignMetadata | object | 活动元数据，包括活动 ID、目标、产品、周期、预算 |
| AudienceSegment | array<object> | 目标客群及其特征、规模、优先级 |
| BenefitRule | object | 权益规则，如券、费率优惠、权益包、领取限制 |
| ChannelRouting | array<object> | 渠道路由，包括渠道、预算比例、触达顺序、重试规则 |
| BudgetAllocation | object | 预算分配 |
| ContentBrief | object | 内容生成大纲，供 C 端生成短信、Push、外呼、客服话术 |
| ComplianceGuard | object | 合规边界、禁用词、必须展示的信息 |
| ExperimentPlan | object | A/B 实验和对照组配置 |
| CallbackConfig | object | 反馈回传地址和回传频率 |

### 示例 JSON

```json
{
  "campaign_metadata": {
    "campaign_id": "CMP20260715001",
    "objective": "提升信用卡分期转化",
    "product": "credit_card_installment",
    "budget": 800000,
    "start_time": "2026-07-20T09:00:00+08:00",
    "end_time": "2026-07-27T22:00:00+08:00"
  },
  "audience_segments": [
    {
      "segment_id": "SEG001",
      "segment_name": "高消费高活跃分期潜力客群",
      "size": 50000,
      "priority": 0.91,
      "features": ["月消费高", "额度使用率高", "App活跃", "分期意图强"],
      "expected_conversion_rate": 0.082,
      "expected_roi": 2.4
    }
  ],
  "benefit_rule": {
    "benefit_type": "installment_fee_coupon",
    "benefit_name": "分期手续费折扣券",
    "eligibility": ["marketing_consent=true", "risk_level != high"],
    "limit": "每客户最多领取1次"
  },
  "channel_routing": [
    {
      "channel": "app_push",
      "budget_ratio": 0.5,
      "contact_order": 1,
      "retry_rule": "24小时未点击后切换短信"
    },
    {
      "channel": "sms",
      "budget_ratio": 0.2,
      "contact_order": 2,
      "retry_rule": "命中频控则跳过"
    },
    {
      "channel": "wechat",
      "budget_ratio": 0.3,
      "contact_order": 3,
      "retry_rule": "仅高价值客户触达"
    }
  ],
  "content_brief": {
    "core_message": "账单压力缓释与分期费率优惠",
    "tone": "专业、克制、合规",
    "personalization_fields": ["customer_name", "available_benefit", "valid_period"],
    "required_disclosure": ["活动规则以页面展示为准", "短信需包含退订方式"]
  },
  "compliance_guard": {
    "blocked_words": ["稳赚", "保证", "无条件通过"],
    "must_not_claim": ["承诺一定省钱", "承诺审批通过"],
    "frequency_limit": "7天最多触达2次"
  },
  "experiment_plan": {
    "control_group_ratio": 0.1,
    "test_group_ratio": 0.9,
    "success_metrics": ["conversion_rate", "roi", "complaint_rate"]
  },
  "callback_config": {
    "feedback_url": "/api/strategy/feedback",
    "report_interval": "hourly"
  }
}
```

## 4. 项目三 -> 项目一：行为回流与画像更新

接口名称建议：

```text
POST /api/knowledge/feedback-events
```

作用：

项目三执行触达后，把客户行为事件和对话信息回传项目一，用于更新客户画像、事件流和意图标签。

### 传递数据类型

| 数据对象 | 类型 | 说明 |
|---|---|---|
| FeedbackEvent | object | 单次客户行为事件 |
| ConversationSummary | object | 对话摘要、客户意图、情绪和问题类型 |
| UpdatedIntentSignal | object | 新产生的客户意图信号 |

### 示例 JSON

```json
{
  "campaign_id": "CMP20260715001",
  "customer_id": "C001",
  "events": [
    {
      "event_type": "exposure",
      "channel": "app_push",
      "event_time": "2026-07-20T10:01:00+08:00"
    },
    {
      "event_type": "click",
      "channel": "app_push",
      "event_time": "2026-07-20T10:03:00+08:00"
    }
  ],
  "conversation_summary": {
    "conversation_id": "CHAT8899",
    "agent_type": "service_agent",
    "customer_intent": "咨询分期期数和手续费",
    "sentiment": "neutral",
    "summary": "客户询问分期期数和手续费，暂未办理"
  },
  "updated_intent_signal": {
    "intent_name": "分期咨询",
    "score_delta": 0.12
  }
}
```

## 5. 项目三 -> 项目二：效果反馈与策略复盘

接口名称建议：

```text
POST /api/strategy/feedback
```

作用：

项目三把活动执行效果回传项目二。项目二根据反馈分析策略效果，并调整下一轮客群、渠道、预算和话术。

### 传递数据类型

| 数据对象 | 类型 | 说明 |
|---|---|---|
| FeedbackMetrics | object | 曝光、点击、转化、拒绝、投诉等指标 |
| ChannelAttribution | array<object> | 各渠道贡献与成本 |
| SegmentPerformance | array<object> | 各客群表现 |
| ConversationOutcome | object | 客户对话结果和营销反馈 |

### 示例 JSON

```json
{
  "campaign_id": "CMP20260715001",
  "feedback_metrics": {
    "exposure_count": 50000,
    "click_count": 6200,
    "conversion_count": 820,
    "reject_count": 1300,
    "complaint_count": 8,
    "cost": 260000,
    "revenue": 650000,
    "roi": 2.5
  },
  "channel_attribution": [
    {
      "channel": "app_push",
      "exposure_count": 30000,
      "conversion_count": 520,
      "cost": 60000,
      "roi": 3.1
    },
    {
      "channel": "sms",
      "exposure_count": 12000,
      "conversion_count": 140,
      "cost": 72000,
      "roi": 1.2
    }
  ],
  "segment_performance": [
    {
      "segment_id": "SEG001",
      "conversion_rate": 0.082,
      "complaint_rate": 0.00016,
      "recommendation": "保留并扩大"
    }
  ],
  "conversation_outcome": {
    "positive_intent_count": 2200,
    "negative_intent_count": 360,
    "top_customer_questions": ["分期费率", "活动有效期", "提前还款规则"]
  }
}
```

## 6. 项目二 <-> 项目三：实时策略调整

接口名称建议：

```text
POST /api/strategy/replan
```

作用：

当项目三在触达或对话中发现异常情况，例如客户强烈反感、投诉率升高、某渠道转化异常下降，可以实时回调项目二，请求调整策略。

### 示例 JSON

```json
{
  "campaign_id": "CMP20260715001",
  "trigger_type": "complaint_rate_alert",
  "trigger_detail": "短信渠道投诉率超过阈值",
  "current_channel": "sms",
  "affected_segment": "SEG001",
  "recommended_action": "降低短信触达频次，切换为 App 内提醒"
}
```

项目二返回：

```json
{
  "campaign_id": "CMP20260715001",
  "action": "update_strategy",
  "new_channel_routing": [
    {
      "channel": "app_push",
      "budget_ratio": 0.7
    },
    {
      "channel": "wechat",
      "budget_ratio": 0.3
    }
  ],
  "disabled_channel": "sms",
  "reason": "短信渠道投诉风险超过阈值，临时降级"
}
```

## 7. 你们组最小可落地接口清单

如果时间有限，建议先实现下面 4 个接口：

| 方向 | 接口 | 负责人 | 作用 |
|---|---|---|---|
| 项目一 -> 项目二 | `/api/knowledge/customer-insight` | A 提供，B 调用 | 获取客户画像、意图、事件、规则 |
| 项目二 -> 项目三 | `/api/marketing/deploy-campaign` | B 提供，C 调用或接收 | 下发活动策略包 |
| 项目三 -> 项目二 | `/api/strategy/feedback` | B 提供，C 调用 | 回传执行效果给 B 端复盘 |
| 项目二 <-> 项目三 | `/api/strategy/replan` | B 提供，C 调用 | 触发实时策略调整 |

## 8. 字段类型约定

| 字段类型 | 推荐格式 | 示例 |
|---|---|---|
| ID | string | `"C001"`, `"CMP20260715001"` |
| 时间 | ISO 8601 string | `"2026-07-15T10:00:00+08:00"` |
| 金额 | number，单位元 | `800000` |
| 比例 | number，0 到 1 | `0.35` |
| 分数 | number，0 到 1 | `0.87` |
| 标签 | array<string> | `["高消费", "App活跃"]` |
| 状态 | enum string | `"available"`, `"blocked"`, `"pending"` |
| 规则 | array<string> | `["不得承诺收益"]` |
| 事件 | object | 包含 event_type、event_time、channel |

## 9. 三方对齐建议

1. 先把 JSON 字段定下来，再写代码。
2. 每个接口都准备一份 mock JSON，三个人可以先用假数据联调。
3. 项目二优先保证输入输出稳定，不要一开始就追求模型复杂。
4. 项目一字段可以逐步丰富，但必须稳定提供 customer_id、tags、risk、consent、events、rules。
5. 项目三执行反馈必须包含 exposed、clicked、converted、rejected、complaint，否则项目二无法复盘。
