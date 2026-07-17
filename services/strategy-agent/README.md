# AI全链路智能营销决策系统 MVP

这是一个可本地运行的课题 MVP，用模拟信用卡客户画像跑通“AI理解 + AI决策 + AI生成”的营销闭环。

## 已实现能力

1. 自然语言运营目标输入。
2. 产品识别与营销意图解析。
3. 模拟客户画像、响应概率、转化概率和投诉风险预测。
4. 智能客群推荐与推荐理由。
5. 渠道、预算和触达策略生成。
6. App、短信、企微话术生成。
7. 授权、频控、投诉风险和内容合规校验。
8. 效果预测、A/B 实验建议和活动记录落库。

## 运行方式

```powershell
cd C:\Users\15531\Documents\Codex\2026-07-13\ni\outputs\ai_marketing_mvp
C:\Users\15531\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe app.py
```

打开：

```text
http://127.0.0.1:8765
```

## 目录结构

```text
ai_marketing_mvp/
  app.py                         # 标准库 HTTP 服务
  ai_marketing/
    intent.py                    # 运营目标理解
    predictor.py                 # 响应/转化/价值预测
    recommender.py               # 客群筛选与解释
    optimizer.py                 # 渠道与效果优化
    content.py                   # 营销内容生成
    compliance.py                # 合规与频控校验
    orchestrator.py              # 全链路编排
    storage.py                   # 本地活动记录
  web/
    index.html                   # 前端驾驶舱
    styles.css
    app.js
  schema_mysql.sql               # 后续 MySQL 化表结构
  tests/test_pipeline.py         # 核心链路测试
```

## 后续升级路线

1. 将 `predictor.py` 替换为 LightGBM/XGBoost/uplift model，并接入真实脱敏样本。
2. 将 `content.py` 替换为 LLM 调用，增加提示词模板、内容审查和人工确认。
3. 将营销 SOP、合规规范、历史活动案例接入向量库，形成 RAG。
4. 将当前 SQLite 存储替换为 MySQL，对接活动、客群、实验和复盘表。
5. 增加离线训练、在线推理、AB 实验回流、模型监控和审计日志。
