# 阶段 2 最终交付：营销准入与渠道可达性

## 1. 这一阶段在做什么

阶段 2 是策略生成前的“准入闸门”。它不负责决定客群价值或生成文案，而是先回答：这个客户能不能参与本次营销？如果能，具体哪些渠道可以投放？

输出会成为策略生成、渠道预算分配和 C 端执行智能体的共同约束。

## 2. 已完成能力

### 2.1 三层规则目录

| 规则层 | 例子 | 是否可调 | 责任方 |
| --- | --- | --- | --- |
| 合规规则 | 未同意营销、风险等级高、渠道授权撤销 | 否 | 合规、风控 |
| 产品准入规则 | 已持有目标分期产品 | 否 | 产品管理 |
| 业务策略规则 | 投诉风险高、渠道不可用、频控 | 是 | 运营、渠道运营 |

规则在 `services/strategy-agent/config/` 的三个 JSON 文件中分别维护，并且共用规则版本号。新增法规改合规目录，调整频控阈值改业务策略目录，职责不会混在一起。

### 2.2 客户级和渠道级的两次判断

```text
客户数据
  -> 客户级合规/产品/策略判断
  -> 每个渠道单独检查授权、可用性、能力、频控
  -> 形成客户可投渠道清单
  -> 只有合格客户和合格渠道进入策略优化
```

客户级规则决定“这个人整体是否可营销”；渠道级规则决定“这个人通过哪个渠道可触达”。客户撤销短信授权时，短信被拦截，但 App Push 可以保留。

### 2.3 最终决策状态

| 状态 | 含义 | 示例 |
| --- | --- | --- |
| `BLOCK` | 客户级合规或产品硬排除 | 未授权营销、风险客户、已持有产品 |
| `BLOCK_ALL_CHANNELS` | 客户整体不违规，但全部渠道被合规规则封住 | 三个渠道授权均撤销 |
| `SUPPRESS` | 业务策略压制，或没有可用的非合规原因渠道 | 投诉风险高、渠道系统不可用 |
| `ALLOW_WITH_LIMITS` | 可以营销，但只有部分渠道可用 | 短信频控，App Push 可用 |
| `ALLOW` | 所有候选渠道都可用 | 正常可投放客户 |

单渠道合规限制不会被误写成客户级 `BLOCK`；只有全部渠道都被合规封住时，才会产生 `BLOCK_ALL_CHANNELS`。

### 2.4 频控数据安全处理

渠道频控只接受两类数据：

1. `contact_history`：逐条营销触达历史，系统按渠道和时间窗口精确计算。
2. `recent_contact_count_by_channel`：A 模块提供的分渠道汇总次数，例如 `{"sms": 2, "app_push": 0}`。

旧字段 `recent_contact_count` 是全渠道总数，不能用来判断某一个渠道是否超频。现在它不再参与渠道频控判断。

如果上述两类分渠道数据都缺失，系统采用保守处理：该渠道标为 `frequency_data_missing`，不投放该渠道，并在 `data_quality_warnings` 输出告警。这样不会因数据不足而误触达客户。

## 3. 对外输出重点字段

每位客户的结果包含：

```json
{
  "final_decision": "ALLOW_WITH_LIMITS",
  "eligible_channels": ["app_push"],
  "blocked_channels": {"sms": ["channel_consent_revoked"]},
  "channel_compliance_blocks": {"sms": ["channel_consent_revoked"]},
  "channel_policy_blocks": {},
  "data_quality_warnings": []
}
```

批量报告额外包含：

| 字段 | 给谁用 | 用途 |
| --- | --- | --- |
| `global_exclusion_by_layer` | 运营、合规 | 区分不可调整的硬排除和可调整的业务策略 |
| `channel_block_by_layer` | 渠道运营 | 查看各渠道为什么不可投放 |
| `channel_coverage` | 策略优化器 | 只在真正可投的渠道中分配预算 |
| `data_quality_warning_summary` | A/B 数据负责人 | 发现缺失的频控明细数据 |
| `customer_channel_constraints` | C 端执行智能体 | 每位客户只走允许的渠道 |

保留了 `exclusion_summary` 和 `blocked_channel_summary` 以兼容旧调用；新增分层字段用于正确分析和调参。

## 4. A、B、C 如何衔接

```text
A 基座/知识模块
  提供：客户画像、授权、风险、产品持有、触达历史、渠道状态、规则目录
  ->
B 策略模块（当前负责）
  输出：准入报告、可投客户、每客可投渠道、客群优先级、渠道策略、策略包
  ->
C 客户交互模块
  执行：只向 B 允许的客户走允许的渠道；回传曝光、点击、转化、投诉、退订
  ->
B 复盘优化
  用效果调整可调业务阈值、客群和渠道策略；合规规则不由 B 修改
```

目前 A 的真实字段还未最终确定，因此没有提前修改 `docs/api_contracts.md`。A 完成接口后，至少应确认：`marketing_consent`、`channel_consents`、`risk_level`、`owned_products`、`complaint_risk`、`contact_history` 或 `recent_contact_count_by_channel`、渠道状态。

## 5. 已验证场景

1. 客户未授权营销：`BLOCK`。
2. 短信授权撤销：客户为 `ALLOW_WITH_LIMITS`，仅短信被合规拦截。
3. 短信达到频控：仅短信被业务规则拦截，其他渠道可用。
4. 投诉风险高：`SUPPRESS`，属于可调业务策略，不是合规硬排除。
5. 全部渠道授权撤销：`BLOCK_ALL_CHANNELS`，不会误记成 `SUPPRESS`。
6. 只有全渠道触达总数、没有分渠道频控数据：产生数据质量告警，不会把总数错误套到每个渠道。
7. 策略优化器仅在阶段 2 允许的渠道中生成投放方案。

## 6. 如何演示和验收

在 `services/strategy-agent` 目录运行：

```powershell
python app.py
```

浏览器打开 `http://127.0.0.1:8765` 查看策略生成页。准入接口可用 PowerShell 调用：

```powershell
$body = Get-Content -Raw "../../mock_data/eligibility_customer_insight.json"
Invoke-RestMethod `
  -Uri "http://127.0.0.1:8765/api/strategy/eligibility" `
  -Method Post `
  -ContentType "application/json; charset=utf-8" `
  -Body $body | ConvertTo-Json -Depth 10
```

观察 `final_decision_summary`、`global_exclusion_by_layer`、`channel_block_by_layer`、`channel_coverage` 和每个客户的 `eligible_channels`。这就是阶段 2 的验收证据。

## 7. 完成标准与下一步

阶段 2 的 MVP 已完成：规则分层、客户/渠道双层准入、频控安全处理、可解释输出、下游渠道约束和自动化测试都已具备。

下一步是接入 A 的正式数据字段，并把 B 的客群、渠道和策略包进一步接给 C 做实际触达与效果回流。
