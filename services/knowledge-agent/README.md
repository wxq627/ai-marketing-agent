# Knowledge Agent

项目一：企业知识引擎与记忆中心。

## 职责

- 构建客户画像与 OneID
- 维护企业知识库、产品规则、权限规则、合规规则
- 维护客户历史行为和实时意图
- 向 Strategy Agent 提供标准化客户洞察接口

## 计划接口

```text
POST /api/knowledge/customer-insight
POST /api/knowledge/feedback-events
```

## 第一版交付建议

先用 `mock_data/customer_insight_example.json` 提供模拟数据，保证 B 端可以联调。
