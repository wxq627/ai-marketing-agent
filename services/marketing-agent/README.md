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
<<<<<<< HEAD


## 最终验证步骤
```bash
# 1. cmd中启动redis
redis-server.exe redis.windows.conf

# 2. 启动服务
uvicorn app.main:app --reload --host 0.0.0.0 --port 8000

# 3. 打开浏览器访问
http://localhost:8000
```

## 仿真工作台操作指南
| 操作 | 说明 |
| :--- | :--- |
| 🚀 部署营销活动 | 将内置策略包投递至 Celery，观察左侧日志确认任务分发 |
| 💬 发送消息 | 在仿真手机中输入"分期费率""我想办理分期"等，体验 Agent 意图识别与内容生成 |
| 📊 模拟反馈回流 | 一键生成随机反馈数据，右侧看板实时更新，同时触发 `/feedback/aggregate` 接口 |
| 🗑️ 清空对话 | 重置 LangGraph 对话状态 |

## 交付物总览
| 阶段 | 核心产出 | 验证方式 |
| :--- | :--- | :--- |
| 一 | Config + Pydantic 契约模型 | `pytest tests/test_models.py` |
| 二 | ContentGen + Frequency + LangGraph Agent | `pytest tests/test_services.py` |
| 三 | Channel Adapter + Celery 异步任务 | `pytest tests/test_phase3.py` |
| 四 | FastAPI 路由 + 仿真 App 界面 | 浏览器访问 `localhost:8000` |

=======
>>>>>>> origin/feature/project1-knowledge-agent
