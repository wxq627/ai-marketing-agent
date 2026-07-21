# B-C 策略服务交互协议

## 1. 协议目的

本协议规定策略运营端（B 端）与客户智能体（C 端）之间如何传递策略。

B 端网页是运营人员生成、审核和发布策略的工作台；C 端不访问该网页，也不读取“最近一次点击生成”的临时结果。C 端只能通过策略服务接口，读取已经发布、仍在有效期内，并且适用于当前客户的策略版本。

这样可以保证：

- 运营人员可以同时维护多场活动，不会相互覆盖。
- 已生成但未审核的草稿不会被 C 端误用。
- 同一策略可以追溯到明确的版本号、活动和生效时间。
- 策略下线后，C 端能够立即停止使用。

## 2. 整体流程

```text
运营输入目标
  -> B 端生成策略草稿
  -> 保存策略包
  -> 运营确认发布
  -> 生成策略版本 strategy_version
  -> C 端按 oneid 查询客户可用策略
  -> C 端推荐/对话
  -> C 端回传曝光、点击、转化等反馈
```

策略状态及含义：

| 状态 | 含义 | C 端是否可读取 |
|---|---|---|
| 草稿 | B 端刚生成，仍可由运营审核 | 否 |
| 已发布 | 具有版本号且处于有效期内 | 是 |
| 已归档 | 已下线或被运营停止 | 否 |

## 3. 核心概念

### 3.1 活动 ID 与策略版本

- `campaign_id`：一次运营活动的标识，例如一次分期促活活动。
- `strategy_version`：活动发布后的不可变版本标识，例如 `STR_MKT-XXXX_001`。
- 同一 `campaign_id` 可以发布多个版本，便于留存版本历史、复盘和回滚。

### 3.2 有效期

- `effective_from`：策略开始生效时间；不传时默认发布当刻生效。
- `effective_to`：策略结束生效时间；不传表示没有预设结束时间。
- C 端只能获得当前时间落在有效期内的策略。

### 3.3 客户范围

策略包保存了 B 端完成圈选后的客户约束信息，包括客户所属群像、可触达渠道和策略分群。C 端查询时，系统仅返回与当前 `oneid` 对应客户匹配的策略上下文，不会返回完整客群名单或运营侧原始数据。

## 4. B 端运营接口

### 4.1 发布已生成的策略

```text
POST /api/strategy/publications
```

请求示例：

```json
{
  "campaign_id": "MKT-BF14E483",
  "effective_from": "2026-07-20 10:00:00",
  "effective_to": "2026-08-20 23:59:59"
}
```

字段说明：

| 字段 | 必填 | 说明 |
|---|---|---|
| `campaign_id` | 是 | 已在 B 端生成并保存的活动 ID |
| `effective_from` | 否 | 生效时间，默认为当前发布时刻 |
| `effective_to` | 否 | 失效时间，必须晚于生效时间 |

响应示例：

```json
{
  "publication": {
    "strategy_version": "STR_MKT-BF14E483_001",
    "campaign_id": "MKT-BF14E483",
    "product": "credit_card_installment",
    "status": "published",
    "effective_from": "2026-07-20 10:00:00",
    "effective_to": "2026-08-20 23:59:59",
    "published_at": "2026-07-20 10:05:00"
  }
}
```

### 4.2 查看已发布策略

```text
GET /api/strategy/publications?status=published&limit=50
```

该接口供运营端查看当前已发布版本。返回内容只包含策略元数据，不直接返回完整策略包。

### 4.3 归档策略

```text
POST /api/strategy/publications/archive
```

请求示例：

```json
{
  "strategy_version": "STR_MKT-BF14E483_001"
}
```

归档后，该策略不会再被 C 端查询接口返回。

## 5. C 端获取完整策略包

完整策略包用于 C 端在收到新活动后校验、缓存活动级规则和生成执行计划。它与“某一位客户当前是否命中策略”是两类不同数据，不能互相替代。

### 5.1 查询已发布版本列表

```text
GET /api/strategy/publications?status=published&limit=50
```

C 端先获得已发布的 `strategy_version`，只同步新版本或尚未缓存的版本。该接口只返回元数据，不返回完整策略包。

### 5.2 下载某个已发布的完整策略包

```text
GET /api/strategy/publications/{strategy_version}/package
```

示例：

```text
GET /api/strategy/publications/STR_CAMP_2026_WEDDING5_001/package
```

返回值是标准 `StrategyPackage`，可直接交给 C 端的 `/api/v3/strategy/receive` 校验和缓存；额外的 `publication` 字段用于记录版本、状态和有效期。草稿、归档版本或不存在的版本返回 `404`。

```text
GET B /api/strategy/publications?status=published
GET B /api/strategy/publications/{strategy_version}/package
POST C /api/v3/strategy/receive   body: {"strategy": <下载到的策略包>}
```

C 端现有代码中调用的旧接口 `POST /api/generate` 已被移除，不能再作为策略包来源。C 端应改为上述“版本列表 -> 下载策略包 -> receive”的流程。

### 5.3 C 端改造清单

1. 删除 `StrategyAgentAdapter` 中对 `http://localhost:8765/api/generate` 的调用和“MarketingPlan 二次转换”逻辑。
2. 调用版本列表接口，选取尚未缓存的 `strategy_version`。
3. 调用下载接口，得到的响应可直接作为 `StrategyPackage` 校验；`publication` 是附加元数据，可忽略。
4. 将完整包提交至 C 端已有的 `POST /api/v3/strategy/receive`，或在 C 服务内部直接执行同样的校验和缓存。
5. 用户进入会话、展示卡片或准备营销推荐时，再调用第 6 节的单客接口，不能仅凭 C 的“最新活动缓存”判断该客户是否命中。

## 6. C 端单客户策略查询接口

### 6.1 获取客户当前可用的已发布策略

```text
GET /api/strategy/customers/{oneid}/published-context?product=installment
```

调用时机：

- 用户进入智能体首页，需要展示个性化推荐时。
- 用户在对话中咨询某个产品或权益时。
- C 端准备给出营销推荐前，需要确认该客户是否命中已发布策略时。

路径参数：

| 参数 | 说明 |
|---|---|
| `oneid` | 项目 A 提供的客户唯一标识符 |

查询参数：

| 参数 | 必填 | 说明 |
|---|---|---|
| `product` | 否 | 产品场景，可传 `installment`、`coupon` 或 `travel` |
| `as_of` | 否 | 指定查询时点，用于测试有效期，格式为 ISO 时间 |

响应示例：

```json
{
  "oneid": "UID000001",
  "strategy_context": [
    {
      "strategy_version": "STR_MKT-BF14E483_001",
      "campaign_id": "MKT-BF14E483",
      "product": "credit_card_installment",
      "objective": "提升分期转化",
      "effective_from": "2026-07-20 10:00:00",
      "effective_to": "2026-08-20 23:59:59",
      "segment_id": "SEG003",
      "persona_name": "数据驱动群像-C3",
      "allowed_channels": ["app_push", "sms"],
      "strategy": {
        "offer_direction": "突出适用场景与费用优惠",
        "content_direction": "先解释规则和费用，再引导客户测算"
      },
      "benefit_rule": {
        "benefit_type": "installment_fee_coupon"
      },
      "compliance_guard": {
        "frequency_limit": "7天最多触达2次",
        "must_not_claim": ["承诺一定省钱", "承诺审批通过"]
      }
    }
  ]
}
```

这里的返回是脱敏后的单客策略上下文，不是完整策略包：它不会包含其他客户的名单、预算明细或全部客群约束。返回为空数组 `strategy_context: []` 时，代表该客户当前没有命中的已发布策略。C 端应继续提供正常的查询或服务能力，不应主动输出营销推荐。

## 7. C 端已有接口的联动方式

以下两个接口的响应中，也会自动增加 `published_strategy_context` 字段，因此 C 端可以少调用一次接口：

### 7.1 智能体首页推荐

```text
GET /api/strategy/customers/{oneid}/recommendations?scene=agent_home
```

该接口返回基础个性化推荐列表，并附带当前客户命中的已发布策略上下文。C 端展示推荐卡片时，应优先使用策略上下文中的权益方向、内容方向和合规要求。

### 7.2 对话中的推荐决策

```text
POST /api/strategy/decision
```

请求示例：

```json
{
  "oneid": "UID000001",
  "scene": "chat",
  "user_intent": "我想了解账单分期怎么收费",
  "product_id": "INSTALLMENT",
  "conversation_summary": "客户正在比较分期期数和费用",
  "touchpoint": "in_app"
}
```

响应中的 `published_strategy_context` 用于约束 C 端回答：

- 是否存在当前有效的营销策略。
- 推荐哪类权益和内容表达方向。
- 哪些渠道、频率和合规措辞需要遵守。

C 端仍负责生成自然语言回答；B 端提供的是“推荐什么、如何推荐、是否应推荐”的策略约束，而不是替代对话本身。

## 8. C 端使用规则

1. C 端不得通过页面抓取或读取 SQLite 文件获取策略，必须调用服务接口。
2. C 端不得使用 `draft` 或 `archived` 状态的策略。
3. 当存在多个命中策略时，C 端应按返回顺序优先使用最新发布的策略；若策略产品与用户问题不匹配，则不主动营销。
4. C 端输出任何营销内容前，应遵守 `compliance_guard` 中的频控和禁止承诺要求。
5. 当用户明确拒绝营销、取消授权或表达投诉时，C 端应停止营销推荐，并将事件回传给 B 端复盘模块。

## 9. 反馈回传约定

C 端在用户发生关键行为后，应调用反馈接口：

```text
POST /api/strategy/feedback
```

建议至少回传以下信息：

```json
{
  "strategy_version": "STR_MKT-BF14E483_001",
  "campaign_id": "MKT-BF14E483",
  "oneid": "UID000001",
  "feedback_metrics": {
    "exposure_count": 1,
    "click_count": 1,
    "conversion_count": 0,
    "complaint_count": 0,
    "roi": 0
  }
}
```

Demo 当前会汇总 CTR、转化率、投诉率和优化建议。后续可将反馈按 `strategy_version`、客群、渠道、产品和时间窗口沉淀，用于模型重训、A/B 实验和预算再分配。

## 9. Demo 实现边界

- 当前策略库使用 SQLite：`services/strategy-agent/data/marketing_demo.sqlite3`。
- 策略包保存为 JSON，适合本项目演示与三人协作开发。
- 生产环境应替换为受控数据库，并补充鉴权、权限隔离、审计日志、加密存储、限流和接口签名。
- C 端只接收客户级策略上下文，不应接触运营端完整客群、原始行为数据或模型训练数据。
