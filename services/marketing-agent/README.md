# Marketing Agent

项目三：C端智能交互与触达执行。

## 职责

- 接收 Strategy Agent 下发的策略包
- 生成短信、App Push、客服话术等内容
- 实现查询类、服务类、营销类智能体
- 执行客户触达并收集反馈
- 向 Knowledge Agent 和 Strategy Agent 回流行为与效果数据

## 计划接口

```text
POST /api/marketing/deploy-campaign
POST /api/marketing/chat
POST /api/marketing/feedback-events
```

## 第一版交付建议

先读取 `contracts/examples/strategy_package_example.json`，完成 C 端触达展示和反馈 mock。
