# Marketing Agent 系统启动说明文档

## 📋 1. 项目概述

项目三「C端智能交互与触达执行」是营销闭环的"手脚与感官"，负责将项目二（策略优化系统）生成的策略包转化为客户可感知的营销内容与交互服务。

**架构分层**:
- **接入与策略解析层**: 接收并解析策略包（支持自动从 strategy_agent 推送）
- **核心决策与调度层**: 任务分解、Agent路由与协作、会话状态管理
- **执行与交互层**: 文案生成、渠道分发、C端智能对话
- **反馈与回流层**: 采集行为数据并回流至项目一、项目二

**服务组成**:
| 服务 | 端口 | 说明 |
|------|------|------|
| marketing_agent（主服务） | 8080 | C端交互与触达执行 |
| strategy_agent（策略生成） | 8765 | AI营销策略生成引擎（自动推送策略到主服务） |

## 🛠️ 2. 环境依赖与准备

### 2.1 基础依赖

| 依赖 | 版本 | 说明 | MVP状态 |
|------|------|------|---------|
| Python | ≥ 3.9 | 运行环境 | **必需** |
| Redis | ≥ 7.0 | 会话状态存储 | 可选（内存兜底） |
| PostgreSQL | ≥ 14 | 持久化存储 | 可选（内存兜底） |
| LLM服务 | OpenAI/Ollama | 文案生成与对话 | 可选（Mock兜底） |
| Node.js | ≥ 18 | 前端构建（可选） | 可选 |

### 2.2 Python依赖安装

```bash
cd d:\库文件\桌面\Summer_Intern\c_marketing_agent
pip install -r requirements.txt
```

**说明**: strategy_agent 使用纯 Python 标准库实现，无需额外依赖。

### 2.3 环境配置

复制 `.env.example` 为 `.env`，根据实际情况修改配置：

```bash
copy .env.example .env
```

**关键配置项说明**:

| 配置项 | 说明 | 默认值 |
|--------|------|--------|
| APP_ENV | 运行环境 | development |
| APP_HOST | 服务绑定地址 | 0.0.0.0 |
| APP_PORT | 服务端口 | 8080 |
| LLM_PROVIDER | LLM提供者 | ollama/openai |
| LLM_API_KEY | OpenAI API密钥 | (空) |
| OLLAMA_HOST | Ollama服务地址 | http://localhost:11434 |
| KE_API_BASE | knowledge_engine地址 | http://localhost:8000 |
| SA_API_BASE | strategy_agent地址 | http://localhost:8765 |

## 🚀 3. 系统启动步骤

### 3.1 启动顺序

```
1. 启动 knowledge_engine（可选，端口 8000）
2. 启动 strategy_agent（端口 8765）→ 自动推送策略到 marketing_agent
3. 启动 marketing_agent（端口 8080）→ 自动从 strategy_agent 拉取策略
```

### 3.2 启动 strategy_agent

```bash
cd d:\库文件\桌面\Summer_Intern\c_marketing_agent\strategy_agent
python app.py
```

**启动验证**:
```bash
curl http://localhost:8765/health
# 预期响应: {"status": "ok"}
```

**strategy_agent 配置环境变量**:

| 环境变量 | 说明 | 默认值 |
|----------|------|--------|
| SA_CALLBACK_ENABLED | 是否自动推送策略到 marketing_agent | 1（开启） |
| SA_CALLBACK_URL | marketing_agent 的策略接收接口 | http://localhost:8080/api/v3/strategy/receive |
| SA_CALLBACK_TIMEOUT | 推送超时时间（秒） | 10 |

### 3.3 启动 marketing_agent

```bash
cd d:\库文件\桌面\Summer_Intern\c_marketing_agent
uvicorn api_server.main:app --host 0.0.0.0 --port 8080 --reload
```

或使用 Python 直接启动：
```bash
cd d:\库文件\桌面\Summer_Intern\c_marketing_agent
python -m api_server.main
```

### 3.4 启动验证

#### 健康检查

```bash
curl http://localhost:8080/health
curl http://localhost:8080/api/v3/health
```

**预期响应**:
```json
{
    "status": "healthy",
    "service": "marketing_agent",
    "websocket_connections": 0
}
```

#### 获取当前策略

```bash
curl http://localhost:8080/api/v3/strategy/current
```

**预期响应**: 返回 strategy_agent 生成的最新策略（campaign_id 形如 `MKT-XXXXX`）

#### 查看OpenAPI文档

访问 http://localhost:8080/docs 查看完整API文档

## 🔌 4. API接口文档

### 4.1 策略管理接口

| 接口 | 方法 | 描述 |
|------|------|------|
| `/api/v3/strategy/receive` | POST | 接收策略包（strategy_agent 自动推送） |
| `/api/v3/strategy/generate` | POST | 手动触发策略生成（调用 strategy_agent） |
| `/api/v3/strategy/current` | GET | 获取当前策略 |
| `/api/v3/strategy/list` | GET | 列出所有已缓存策略 |
| `/api/v3/strategy/cached` | GET | 获取 adapter 缓存的策略 |
| `/api/v3/strategy/switch` | POST | 切换当前使用的策略 |
| `/api/v3/strategy/validate` | POST | 校验策略包 |

**策略生成示例**:
```bash
curl -X POST http://localhost:8080/api/v3/strategy/generate \
  -H "Content-Type: application/json" \
  -d '{
    "goal": "提升信用卡分期转化",
    "product": "installment",
    "channel_mode": "omni",
    "budget_wan": 80,
    "risk_level": 2,
    "frequency_level": 2
  }'
```

**响应示例**:
```json
{
  "success": true,
  "campaign_id": "MKT-C68E6C5F",
  "message": "策略生成成功",
  "strategy": {
    "campaign_metadata": {...},
    "audience_segments": [...],
    "channel_routing": [...],
    "content_brief": {...},
    "compliance_guard": {...}
  }
}
```

### 4.2 对话交互接口

| 接口 | 方法 | 描述 |
|------|------|------|
| `/api/v3/chat/start` | POST | 开始对话（自动根据策略生成推送内容） |
| `/api/v3/chat/message` | POST | 发送消息 |
| `/api/v3/chat/end` | POST | 结束对话 |
| `/api/v3/chat/session/{session_id}` | GET | 获取会话详情 |

**对话开始示例**:
```bash
curl -X POST http://localhost:8080/api/v3/chat/start \
  -H "Content-Type: application/json" \
  -d '{"oneid": "UID004008"}'
```

### 4.3 触达管理接口

| 接口 | 方法 | 描述 |
|------|------|------|
| `/api/v3/reach/single` | POST | 单客触达（根据最新策略推送） |
| `/api/v3/reach/channels` | GET | 获取渠道列表 |
| `/api/v3/reach/dispatch-logs` | GET | 获取分发日志 |

### 4.4 监控统计接口

| 接口 | 方法 | 描述 |
|------|------|------|
| `/api/v3/monitor/stats` | GET | 获取统计信息 |
| `/api/v3/monitor/workflows` | GET | 获取工作流列表 |
| `/api/v3/monitor/feedback` | GET | 获取反馈数据 |

### 4.5 WebSocket接口

| 接口 | 描述 |
|------|------|
| `ws://localhost:8080/ws/logs` | 实时日志推送 |

## 🔗 5. 与项目一（知识引擎）联动说明

### 5.1 已实现的联动

项目三通过 `agents/adapters.py` 中的适配器调用项目一（knowledge_engine）的接口：

| 适配器 | 接口 | 说明 |
|--------|------|------|
| `ProfileAPIAdapter` | `/api/v1/profile/{oneid}` | 获取客户画像 |
| `KnowledgeAPIAdapter` | `/api/v1/knowledge/search` | 知识全文检索 |
| `IntentAPIAdapter` | `/api/v1/intent/classify` | 意图分类 |
| `FrequencyAPIAdapter` | `/api/v1/frequency/check` | 频控检查 |

**配置**: 在 `.env` 中设置 `KE_API_BASE=http://localhost:8000`

**降级机制**: 当 knowledge_engine 不可用时，自动回退到 Mock 数据。

### 5.2 反馈数据回传（已实现）

**反馈事件类型**:

| 事件类型 | 触发时机 | 说明 | 映射到KE |
|----------|----------|------|----------|
| `impression` | 触达消息曝光 | 用户看到推送内容 | `impression` |
| `user_click` | 用户点击感兴趣 | 用户对推送卡片点击感兴趣 | `click` |
| `user_reject` | 用户反馈不感兴趣 | 用户对推送卡片点击不感兴趣 | `dismiss` |
| `conversation` | 对话结束 | 对话摘要和情绪分析 | `conversation` |
| `conversion` | 用户完成转化 | 如分期办理、绑卡等 | `conversion` |

**回流接口**:
- `POST /api/v1/feedback/events` — 逐条回传事件数据
- `POST /api/v1/feedback/batch` — 批量回传事件数据

**配置**: 在 `.env` 中设置 `KE_FEEDBACK_URL=http://localhost:8000`

**事件回流流程**:
```
1. 曝光事件: dispatch → impression → 回流至 KE
2. 交互事件: 用户点击感兴趣/不感兴趣 → user_click/user_reject → 回流至 KE
3. 对话摘要: 对话结束 → conversation → 回流至 KE
4. 活动指标: 对话结束 → 策略反馈 → 回流至 strategy_agent
```

### 5.3 数据回流队列

`feedback_collector/data_reflow.py` 实现了异步数据回流队列：

- **队列机制**: 使用线程安全队列，支持异步处理
- **重试机制**: 失败时自动重试（最多3次）
- **持久化回退**: 重试失败后写入本地文件，下次启动时重新处理
- **事件类型映射**: 将项目三事件类型映射为知识引擎支持的类型

**事件类型映射表**:
```python
event_type_mapping = {
    "user_click": "click",
    "user_reject": "dismiss",
    "interaction": "click"
}
```

## 🔗 6. 与项目二（策略优化系统/strategy_agent）联动说明

### 6.1 自动推送机制（已实现）

**策略流转链路**:
```
strategy_agent (8765)
       │ 用户在前端点击"生成"或调用 /api/generate
       ▼
  generate_plan() 生成 MarketingPlan
       │
       ▼ 自动回调（urllib.request）
marketing_agent (8080)
       │ POST /api/v3/strategy/receive
       ▼
  StrategyPackage 格式校验 + 缓存
       │
       ▼ 后续工作流自动使用最新策略
  chat/start → 使用新策略生成文案
  reach/single → 使用新策略推送
```

### 6.2 strategy_agent 回调配置

在 strategy_agent 启动时可通过环境变量配置：

```bash
set SA_CALLBACK_ENABLED=1
set SA_CALLBACK_URL=http://localhost:8080/api/v3/strategy/receive
set SA_CALLBACK_TIMEOUT=10
cd strategy_agent
python app.py
```

### 6.3 策略加载优先级

marketing_agent 的 `StrategyLoader.load_latest()` 按以下顺序加载策略：

1. **内存缓存**（最近保存的策略）→ 优先使用
2. **自动生成**（调用 strategy_agent 的 `/api/generate`）→ 无缓存时自动生成默认策略
3. **Mock文件**（`contracts/examples/strategy_package_example.json`）→ 最后兜底

### 6.5 反馈回流机制（已实现）

**反馈回流链路**:
```
marketing_agent (8080)
  ├─ _dispatch_node → impression 事件 → 回流至 KE
  ├─ _feedback_node → interaction 事件 → 回流至 KE
  └─ _end_node → 对话摘要 → 回流至 KE
               → 活动指标 → 回流至 strategy_agent
```

**strategy_agent 反馈接口**:

| 接口 | 方法 | 描述 |
|------|------|------|
| `/api/feedback` | POST | 接收营销活动反馈数据 |
| `/api/feedback/list` | GET | 获取所有反馈记录列表 |
| `/api/feedback/{id}` | GET | 获取单个反馈记录详情 |

**配置**: 在 `.env` 中设置 `SA_FEEDBACK_URL=http://localhost:8765`

### 7.1 marketing_agent 前端

**访问地址**: http://localhost:8080

**界面功能**:
- **策略看板**: 展示当前加载的策略包详情，包括客群、渠道、文案、合规检查等
- **仿真手机交互区**: 模拟智能手机界面，支持对话交互（发送消息、接收回复）
- **推送消息记录**: 展示触达推送的卡片列表，支持点击"👍感兴趣"或"👎不感兴趣"交互
- **回流监控**: 实时展示回流事件统计、事件列表、全链路时间线、回流详情弹窗
- **实时日志监控**: 实时滚动显示后端执行日志

**回流监控面板**:

| 组件 | 功能 |
|------|------|
| **统计卡片** | 回流成功/失败/等待/总数实时展示 |
| **回流事件列表** | 表格展示所有回流事件，支持类型/渠道/状态筛选 |
| **全链路时间线** | 可视化展示 `初始化 → 合规检查 → 内容生成 → 渠道分发 → 用户交互 → 数据回流 → 策略优化` |
| **回流详情弹窗** | 点击事件可查看完整回流数据（JSON格式化展示） |

### 7.2 strategy_agent 前端

**访问地址**: http://localhost:8765

**界面功能**:
- **策略生成表单**: 输入活动目标、产品类型、渠道模式、预算等参数
- **策略方案展示**: 展示生成的客群、渠道、文案、合规检查结果
- **效果预测图表**: 展示 CTR、转化率、投诉率预测

### 7.3 演示流程

**完整流程（推荐）**:

1. **启动 knowledge_engine**（端口 8000）:
   ```bash
   cd knowledge_engine && uvicorn api_server.main:app --host 0.0.0.0 --port 8000
   ```

2. **启动 strategy_agent**（端口 8765）:
   ```bash
   cd strategy_agent && python app.py
   ```

3. **打开 strategy_agent 界面**:
   - 访问 http://localhost:8765
   - 修改参数（如选择 "installment" 产品）
   - 点击"生成方案"按钮

4. **启动 marketing_agent**（端口 8080）:
   ```bash
   cd .. && uvicorn api_server.main:app --host 0.0.0.0 --port 8080 --reload
   ```

5. **打开 marketing_agent 界面**:
   - 访问 http://localhost:8080
   - 策略看板应自动显示最新策略

6. **触发触达并交互**:
   - 输入客户 OneID（如 `UID004008`）或留空随机选择
   - 点击"触发触达"按钮 → 推送卡片显示在推送消息记录区
   - 点击推送卡片的"👍感兴趣"或"👎不感兴趣"按钮 → 触发交互事件回流

7. **对话交互**:
   - 在仿真手机界面输入消息（如"账单"、"额度"、"利息"）
   - Agent 根据意图分类返回对应查询结果

8. **查看回流监控**:
   - 切换到"回流监控"Tab
   - 查看事件统计、事件列表和全链路时间线
   - 点击事件可查看回流详情

9. **结束对话**:
   - 点击"结束对话"按钮 → 对话摘要和策略反馈回流

### 7.4 典型演示场景

| 场景 | 操作 | 预期结果 |
|------|------|----------|
| 分期策略 | strategy_agent 选择 installment 产品 | 推送"分期手续费折扣券"文案 |
| 消费券策略 | strategy_agent 选择 coupon 产品 | 推送"消费券包"文案 |
| 商旅策略 | strategy_agent 选择 travel 产品 | 推送"商旅权益包"文案 |
| 单客触达 | 输入 OneID 点击"触发触达" | 推送卡片显示，曝光事件回流 |
| 用户点击感兴趣 | 点击推送卡片"👍感兴趣"按钮 | user_click 事件回流成功 |
| 用户反馈不感兴趣 | 点击推送卡片"👎不感兴趣"按钮 | user_reject 事件回流成功 |
| 账单查询 | 输入"账单" | 返回账单金额、账单日、还款日 |
| 额度查询 | 输入"额度" | 返回可用额度、总授信额度 |
| 利息查询 | 输入"利息" | 返回透支利息和分期费率 |
| 频控限制 | 同一客户短时间多次触达 | 后续触达被拦截 |
| 合规校验 | 输入高风险词策略 | 内容合规检查拦截 |
| 对话结束 | 点击"结束对话" | 对话摘要和策略反馈回流 |

## 🐛 8. 常见问题排查

### 8.1 服务启动失败

**问题**: `ModuleNotFoundError`
**解决方案**: 确保已安装所有依赖
```bash
pip install -r requirements.txt
```

**问题**: `Port 8080 is already in use`
**解决方案**: 更换端口或关闭占用进程
```bash
netstat -ano | findstr :8080
taskkill /F /PID <进程ID>
```

### 8.2 策略加载失败

**问题**: `[StrategyLoader] 无已保存策略，回退到 mock 文件`
**解决方案**: 
1. 确认 strategy_agent 已启动（端口 8765）
2. 在 strategy_agent 界面生成策略（会自动推送到 marketing_agent）
3. 或手动调用 `POST /api/v3/strategy/generate`

**问题**: `策略接收失败: 'dict' object has no attribute 'valid'`
**解决方案**: 已修复，确保使用最新代码

### 8.3 strategy_agent 推送失败

**问题**: `[callback] 推送 HTTP 错误: 500`
**解决方案**: 
1. 确认 marketing_agent 已启动
2. 检查 `SA_CALLBACK_URL` 配置正确
3. 查看 marketing_agent 日志定位具体错误

### 8.4 WebSocket连接失败

**问题**: 日志面板不更新
**解决方案**: 
1. 检查浏览器控制台是否有错误
2. 确认WebSocket地址正确（`ws://localhost:8080/ws/logs`）
3. 检查防火墙是否阻止WebSocket连接

### 8.5 LLM调用失败

**问题**: `LLM生成失败`
**解决方案**: 
1. 检查LLM配置
2. 确认Ollama服务已启动（如果使用Ollama）
3. 确认OpenAI API密钥有效（如果使用OpenAI）
4. 系统会自动降级到Mock模式

### 8.6 knowledge_engine 不可用

**问题**: `[KE API] 调用失败`
**解决方案**: 
1. 确认 knowledge_engine 已启动（端口 8000）
2. 检查 `KE_API_BASE` 配置
3. 系统会自动回退到 Mock 数据

### 8.7 数据回流失败

**问题**: `项目一回流失败: HTTP错误: 422`
**根因**: 回流数据字段不符合知识引擎接口要求（如 `channel` 为 `null`）
**解决方案**: 
1. 确认 knowledge_engine 已启动并正常运行
2. 检查回流数据格式是否正确
3. 查看日志确认具体错误字段

**问题**: `项目一回流失败: <urlopen error [WinError 10061]>`
**根因**: knowledge_engine 服务未启动或端口错误
**解决方案**: 
1. 确认 knowledge_engine 已启动（端口 8000）
2. 检查 `KE_API_BASE` 配置是否正确
3. 确认网络连通性

### 8.8 对话回复问题

**问题**: 发送"账单"、"额度"、"利息"等关键词始终回复"请问您想查询什么信息？"
**根因**: 工作流在处理第一条消息后直接结束，无法继续接收后续消息
**解决方案**: 
1. 确认工作流边配置包含 `feedback → interact` 边
2. 检查 `continue_workflow` 方法的循环逻辑
3. 确认状态缓存正确维护

### 8.9 前端回流监控不更新

**问题**: 回流监控面板数据不实时更新
**解决方案**: 
1. 检查浏览器控制台是否有错误
2. 确认 `fetchReflowEvents` 定时任务正常执行
3. 检查后端 `/api/v3/monitor/reflow-events` 接口是否正常

## ✅ 9. MVP交付标准检查清单

### 9.1 代码交付

- [x] FastAPI后端服务完整实现
- [x] Vue3前端源码完整实现
- [x] strategy_agent 独立服务实现（纯标准库）
- [x] 模块化设计，代码结构清晰
- [x] 统一异常处理机制
- [x] JSON格式日志输出

### 9.2 接口契约

- [x] 策略接收接口 (`/api/v3/strategy/receive`)
- [x] 策略生成接口 (`/api/v3/strategy/generate`)
- [x] 单客触达接口 (`/api/v3/reach/single`)
- [x] 对话交互接口 (`/api/v3/chat/*`)
- [x] 健康检查接口 (`/api/v3/health`)
- [x] WebSocket实时日志接口 (`/ws/logs`)

### 9.3 策略联动（核心功能）

- [x] strategy_agent 自动推送策略到 marketing_agent
- [x] marketing_agent 自动从 strategy_agent 拉取策略
- [x] MarketingPlan → StrategyPackage 格式转换
- [x] 策略缓存机制（内存）
- [x] 策略加载优先级（缓存 → 自动生成 → Mock）

### 9.4 知识引擎联动

- [x] 客户画像获取（ProfileAPIAdapter）
- [x] 知识检索（KnowledgeAPIAdapter）
- [x] 意图分类（IntentAPIAdapter）
- [x] 频控检查（FrequencyAPIAdapter）
- [x] Mock回退机制

### 9.5 Mock数据

- [x] 用户画像Mock数据（`agents/adapters.py`）
- [x] 知识库Mock数据（`agents/adapters.py`）
- [x] 策略包样例（`contracts/examples/strategy_package_example.json`）
- [x] LLM Mock响应（`common/llm_client.py`）

### 9.6 仿真演示

- [x] Web端智能助手交互界面
- [x] 策略看板展示
- [x] 仿真手机交互区
- [x] 实时日志监控
- [x] WebSocket实时日志推送

### 9.7 合规与安全

- [x] 策略包合规校验（年龄限制、敏感词检测）
- [x] 频控校验
- [x] 全链路trace_id追踪
- [x] CORS跨域配置

### 9.8 反馈与回流

- [x] 曝光事件采集（impression）→ 回流至知识引擎
- [x] 交互事件采集（user_click/user_reject）→ 回流至知识引擎
- [x] 对话摘要采集（conversation）→ 回流至知识引擎
- [x] 活动指标聚合 → 回流至策略引擎
- [x] strategy_agent 反馈接收接口（`/api/feedback`）
- [x] 数据回流队列（DataReflowQueue）
- [x] 本地文件持久化回退机制
- [x] 事件类型映射（user_click→click, user_reject→dismiss）
- [x] 回流数据字段 null 值保护

### 9.9 单客触达与交互

- [x] 单客触达接口（`/api/v3/reach/single`）
- [x] 推送卡片交互按钮（👍感兴趣/👎不感兴趣）
- [x] 交互事件 API（`/api/v3/feedback/interaction`）
- [x] 工作流多轮对话支持（interact → feedback → interact）
- [x] 意图识别与路由（query/service/marketing）
- [x] 查询 Agent 实现（账单/额度/利息/积分/账户）
- [x] 对话上下文记忆

### 9.10 回流可视化

- [x] 回流监控面板（事件统计、列表、时间线）
- [x] 全链路时间线可视化
- [x] 回流详情弹窗（JSON格式化展示）
- [x] 实时数据刷新

### 9.11 可扩展性

- [x] 适配器模式设计（便于替换Mock为真实服务）
- [x] 标准化接口契约（与项目一、项目二）
- [x] 配置化管理（`pydantic-settings`）
- [x] 优雅降级机制（Redis/PostgreSQL/LLM/策略均有Mock兜底）

## 📊 10. 升级建议

### 10.1 立即升级项

| 项 | 说明 | 优先级 |
|----|------|--------|
| 真实LLM集成 | 配置Ollama或OpenAI API密钥，获得真实AI对话体验 | 高 |
| Redis集成 | 启用Redis会话存储，支持多实例部署 | 中 |
| 数据库持久化 | 启用PostgreSQL，持久化日志和反馈数据 | 中 |

### 10.2 中期优化项

| 项 | 说明 | 优先级 |
|----|------|--------|
| 异步任务队列 | 引入Celery处理异步分发任务 | 中 |
| 负载均衡 | 部署多个服务实例，通过Nginx负载均衡 | 中 |
| 缓存优化 | 引入Redis缓存策略包和用户画像 | 中 |

### 10.3 长期改进项

| 项 | 说明 | 优先级 |
|----|------|--------|
| 多租户支持 | 支持多个品牌/产品线独立配置 | 低 |
| A/B测试平台 | 独立的A/B测试管理和分析平台 | 低 |
| 实时监控告警 | 集成Prometheus+Grafana监控 | 低 |
