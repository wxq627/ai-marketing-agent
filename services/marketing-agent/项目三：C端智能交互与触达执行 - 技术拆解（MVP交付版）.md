# 项目三：C端智能交互与触达执行 - 技术拆解（MVP交付版）

## 🧭 1. 总体技术架构

项目三作为营销闭环的“手脚与感官”，负责将项目二生成的策略包转化为客户可感知的营销内容与交互服务。考虑到敏捷交付节奏，**本次MVP版本聚焦单用户仿真演示**，核心模块均采用**适配器模式（Adapter Pattern）**设计，所有依赖项先行通过Mock数据驱动，同时为后续对接真实服务预留标准化接口。

技术架构延续四层设计，并明确MVP阶段的实现策略：

| 架构分层             | 核心职责                                | MVP实现策略                                           |
| :------------------- | :-------------------------------------- | :---------------------------------------------------- |
| **接入与策略解析层** | 接收并解析项目二下发的策略包            | 使用Mock策略包（JSON文件），预留API接口               |
| **核心决策与调度层** | 任务分解、Agent路由与协作、会话状态管理 | 完整实现调度逻辑，外部依赖通过Mock适配器注入          |
| **执行与交互层**     | 文案生成、渠道分发、C端智能对话         | 文案生成调用轻量级LLM；渠道分发仅模拟（Log+状态回写） |
| **反馈与回流层**     | 采集行为数据并回流至项目一、项目二      | 采集逻辑完整实现，回流传入异步队列并打印Mock日志      |


## ⚙️ 2. 核心模块技术拆解

### A. 接入与策略解析层：定义契约，Mock填充

策略包是驱动项目三执行的指令集。MVP阶段我们使用本地`strategy_package_example.json`作为数据源，但**接口契约已预先定义**，后续项目二上线即可无缝切换。

**标准化策略包接口契约（Schema）**：

```json
{
  "$schema": "https://json-schema.org/draft/2020-12/schema",
  "$id": "strategy_to_marketing.schema.json",
  "title": "Strategy Agent to Marketing Agent Campaign Package",
  "type": "object",
  "required": ["campaign_metadata", "audience_segments", "channel_routing", "content_brief", "compliance_guard"],
  "properties": {
    "campaign_metadata": {
      "type": "object",
      "required": ["campaign_id", "objective", "product", "budget"],
      "properties": {
        "campaign_id": {"type": "string"},
        "objective": {"type": "string"},
        "product": {"type": "string"},
        "budget": {"type": "number"},
        "start_time": {"type": "string"},
        "end_time": {"type": "string"}
      }
    },
    "audience_segments": {
      "type": "array",
      "items": {
        "type": "object",
        "required": ["segment_id", "segment_name", "size", "priority"],
        "properties": {
          "segment_id": {"type": "string"},
          "segment_name": {"type": "string"},
          "size": {"type": "integer"},
          "priority": {"type": "number"},
          "features": {"type": "array", "items": {"type": "string"}},
          "expected_conversion_rate": {"type": "number"},
          "expected_roi": {"type": "number"}
        }
      }
    },
    "benefit_rule": {"type": "object"},
    "channel_routing": {
      "type": "array",
      "items": {
        "type": "object",
        "required": ["channel", "budget_ratio"],
        "properties": {
          "channel": {"type": "string"},
          "budget_ratio": {"type": "number"},
          "contact_order": {"type": "integer"},
          "retry_rule": {"type": "string"}
        }
      }
    },
    "content_brief": {"type": "object"},
    "compliance_guard": {"type": "object"},
    "experiment_plan": {"type": "object"},
    "callback_config": {"type": "object"}
  }
}
```

**策略包示例：**

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
    {"channel": "app_push", "budget_ratio": 0.5, "contact_order": 1, "retry_rule": "24小时未点击后切换短信"},
    {"channel": "sms", "budget_ratio": 0.2, "contact_order": 2, "retry_rule": "命中频控则跳过"},
    {"channel": "wechat", "budget_ratio": 0.3, "contact_order": 3, "retry_rule": "仅高价值客户触达"}
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

**技术实现**：

- 定义策略包和**JSON Schema校验器**，确保结构完整性。
- 封装`StrategyLoader`组件，支持从**本地Mock文件**或**HTTP远程接口**加载策略。

---

### B. 核心决策与调度层：完整Agent协作框架

调度中枢是项目三的“大脑”，在MVP阶段即完整实现。

- **会话上下文管理**：为演示用户（如`U10001`）创建唯一的`session_id`，使用**Redis**维护对话状态，包含：
  - 当前轮次、历史消息记录、已推荐的权益列表。
  - 用户情绪标签（正面/中性/负面）。
  - 当前执行策略ID。

- **调度中枢（Orchestrator）** 采用**LangGraph**构建状态机工作流：
  1. **Init**：加载策略包并校验合规预检（如用户年龄是否满足）。
  2. **Generate**：调用营销Agent生成文案。
  3. **Dispatch**：调用渠道分发模块（Mock）。
  4. **Interact**：等待用户响应（在仿真界面中模拟点击），路由至对应Agent。
  5. **Feedback**：采集数据写入回流队列。

**技术选型（MVP适配）**：

| 组件     | 技术方案           | MVP说明                           |
| -------- | ------------------ | --------------------------------- |
| 调度框架 | LangGraph (Python) | 完整实现状态机流转                |
| 会话存储 | Redis              | MVP阶段使用内存，依赖注入预留切换 |
| 异步任务 | Celery             | 暂不启用，同步执行简化调试        |

用户消息
   ↓
IntentClassifier.classify() ←── 上下文记忆(last_agent/intent/score)
   ├─ 第一层：大类分类（加权关键词）
   ├─ 上下文增强规则：
   │   ├─ 短消息/代词 → 继承上一轮
   │   ├─ 低分回退 → 继承上一轮
   │   ├─ 得分接近 → 加分上一轮
   │   └─ 话题切换词 → 强制重新识别
   └─ 输出: (category, score, confidence)
   ↓
Agent.process(message, oneid, context)
   ├─ 第二层：细类识别（加权关键词+上下文继承）
   └─ 调用对应handler
   ↓
记录本轮意图到SessionContext

### C. 执行与交互层：三类核心Agent实现

三类Agent均具备完整的业务逻辑，但依赖的客户画像、知识库数据全部来自Mock适配器。

#### 🔍 查询类 Agent（Query Agent）
- **职责**：秒级响应标准化事实查询。
- **实现方案**：基于轻量级**意图识别模型**（BERT-tiny微调，或规则兜底）。识别为查询意图后，调用`ProfileMockAdapter`获取用户的“账单日”、“应还金额”等字段。
- **Mock数据示例**：返回“您本期账单应还金额为￥3,850.00，账单日为每月5日”。

#### 💁 服务类 Agent（Service Agent）
- **职责**：处理复杂事务（活动咨询、投诉受理、业务办理）。
- **实现方案**：采用**RAG架构**，检索器对接`KnowledgeMockAdapter`（本地向量数据库加载Mock产品文档），生成器使用LLM合成友好答复。
- **Mock知识库**：包含`benefit_catalog.csv`、`product_catalog.csv`等结构化数据文档。

#### 🤖 营销类 Agent（Marketing Agent）
- **职责**：生成个性化推送文案，并在对话中识别营销时机主动推荐。
- **实现方案**：
  1. **文案生成**：基于**Qwen2.5-7B**，通过Prompt注入用户画像（从`ProfileMockAdapter`获取）和策略规则，生成**纯文本Push/SMS文案**。
  2. **时机判断**：在对话流中，若用户询价或比较产品，Agent主动按照策略包的`key_message`进行推荐引导。

- **Mock用户画像示例**：

  ```
  oneid,cust_id,demographics_name,demographics_gender,demographics_age,demographics_city,demographics_occupation,demographics_income_level,demographics_education,account_primary_card_level,account_product_name,account_total_credit_amount,account_used_amount,account_usage_rate,account_card_count,account_active_cards,account_tenure_months,lifecycle_stage,lifecycle_months_since_open,lifecycle_vip_tier,lifecycle_customer_manager,risk_overdue_status,risk_history_overdue_count_6m,risk_min_payment_frequency_6m,risk_cash_advance_risk_score,risk_churn_risk_score,risk_risk_level,risk_blacklist_flag,risk_do_not_contact,value_annual_consumption,value_monthly_avg_consumption,value_max_single_transaction,value_transaction_count_12m,value_installment_contribution_12m,value_value_level,long_term_90d_total_consumption,long_term_90d_txn_count,long_term_90d_active_days,long_term_90d_activity_score,long_term_90d_dormancy_risk,long_term_90d_significant_signals,long_term_90d_monthly_avg_90d,mid_term_30d_total_consumption,mid_term_30d_txn_count,mid_term_30d_active_days,mid_term_30d_consumption_trend,mid_term_30d_trend_change_pct,mid_term_30d_browse_preferences,short_term_7d_total_consumption,short_term_7d_txn_count,short_term_7d_active_days,short_term_7d_top_search_keywords,short_term_7d_avg_daily_spend,realtime_signal_count,realtime_has_high_value_txn,key_milestones,generated_at,update_type
  UID000001,C000001,王丹,M,39,西安,金融/保险,M,大专,金卡,XX银行YOUNG卡（青年版）,109600.0,41747.2,0.3809,4,4,64.9,成熟期,64.9,普通,吴芳,M1,1,0,4,0,low,False,False,61039.39,5086.62,2611.17,46,5133.43,medium,17799.97,11,6,16,high,"活跃度骤降, 沉睡预警",5933.32,4437.94,3,2,down,-22.0,"新手指引(19%), 还款页面(20%), 分期计算器(1%), 额度管理(60%)",1330.79,0,0,"账单分期×3, 注销×3, 固定额度×2",190.11,0,False,,2026-07-15 15:00:00,T+1_batch_v3
  ```

---

### D. 执行与交互层：文案生成与渠道分发（含Mock）

#### 文案内容生成（纯文本）
- **流程**：`Marketing Agent`从`ProfileMockAdapter`获取用户偏好（如“偏爱餐饮类权益”），拼接Prompt，调用LLM生成2条备选文案（A/B测试模拟）。
- **性能指标**：单条文案生成耗时控制在**2秒以内**（MVP演示标准）。

#### 渠道分发执行（全Mock）
- **实施方案**：**不调用任何真实三方API**，仅进行逻辑模拟。
- **模拟过程**：
  1. 记录“待分发用户”及“策略包指定渠道”。
  2. 生成模拟分发结果（成功/失败），状态随机或配置预设（便于演示不同分支）。
  3. 模拟回执写入`dispatch_log.json`，并打印结构化日志供演示查阅。
- **预留接口**：已定义标准的`ChannelSenderInterface`（包含`send_push()`和`send_sms()`方法），真实上线时只需实现该接口替换Mock类即可。

**代码结构示例**：
```python
class MockPushChannel(ChannelSenderInterface):
    def send(self, user_id, content):
        # 仅模拟，不发送真实网络请求
        logger.info(f"[MOCK] Push to {user_id}: {content}")
        return DispatchResult(success=True, trace_id="mock_trace_xxx")
```

---

## 🔗 3. 数据接口契约与Mock策略

为确保项目间解耦，项目三针对上游依赖定义了两套标准接口，并内置Mock实现。

### A. 与项目一的接口（画像、知识库、回传）

### API-C1: 客户识别 (OneID解析)

**场景**: 客户通过手机号/设备ID进来，项目三需要知道他是谁。

```http
GET /api/v1/oneid/resolve?type=phone&value=138****8888
GET /api/v1/oneid/resolve?type=device_id&value=DEV_A001
```

**返回**: OneID + 所有已知ID列表 + 置信度。

---

### API-C2: 客户完整画像

**场景**: 拿到OneID后，获取客户全部信息用于个性化对话。

```http
GET /api/v1/customer/{oneid}/profile
```

**返回**: 项目三用来个性化对话的关键字段：

| 数据组               | 项目三用来做什么   | 示例                                     |
| -------------------- | ------------------ | ---------------------------------------- |
| `demographics`       | 称呼客户、了解背景 | "张先生您好！" (姓名/性别/年龄/城市)     |
| `account`            | 知道客户持什么卡   | "您的白金卡享有..." (卡等级/额度/产品名) |
| `lifecycle`          | 调整对话策略       | 新户→引导激活; 沉睡→唤醒话术             |
| `risk`               | 判断能否营销       | 高风险→仅服务; 黑名单→不可触达           |
| `value`              | 推荐匹配产品等级   | 高价值→推高端; 低价值→推入门             |
| `consent`            | 判断能否发推送     | marketing_consent + 各渠道授权           |
| `consumption`        | 了解消费习惯       | 年消费/月均/趋势/活跃度                  |
| `search_keywords`    | 了解最近关注什么   | "您最近在看分期方案?"                    |
| `browse_preferences` | 了解偏好页面       | "您常浏览权益商城?"                      |

---

### API-C3: 客户长期意图向量

**场景**: 客户说了一段话，项目三想知道他当前的需求倾向。

```http
GET /api/v1/customer/{oneid}/intent
```

**返回**: 

```json
{
  "primary_intent": "分期/借贷需求",
  "intents": [
    {"type": "分期/借贷需求", "score": 85, "confidence": "high"},
    {"type": "跨境/出行需求", "score": 45, "confidence": "medium"},
    {"type": "权益/优惠需求", "score": 30, "confidence": "low"}
  ],
  "sentiment": {
    "overall": "anxious",
    "anxiety_score": 65,
    "satisfaction_score": 40
  }
}
```

**项目三使用逻辑**:

```
if primary_intent == "分期/借贷需求" and score >= 70:
    → 主动提分期方案
if primary_intent == "沉睡/流失风险" and score >= 50:
    → 优先推送唤醒红包, 不要营销
if sentiment == "焦虑":
    → 话术温和, "不着急, 我们慢慢看"
```

---

### API-C4: 知识全文检索

**场景**: 客户问产品问题，项目三需要查知识库来回答。

```http
GET /api/v1/knowledge/search?q=白金卡机场权益&top_k=5
```

**返回**: 产品文档+产品描述+权益说明+活动规则+合规条款的匹配片段。

```
客户: "白金卡有什么权益"
  → 智能体调此接口
  → 得到: 机场贵宾厅(全年60次) + 接送机(12次/年) + 延误险(2000元) + ...
  → LLM组织语言回复客户
```

---

### API-C5: 客户事件流

**场景**: 项目三想知道客户最近做了什么，用于个性化对话。

```http
GET /api/v1/customer/{oneid}/events?window=30d&limit=20
```

**返回**: 近30天交易/浏览/搜索/客服事件列表。

**项目三使用**: "您上周在星巴克消费了3次，我们有个咖啡优惠券..." / "您最近在看分期计算器，需要了解分期方案吗?"

```http
POST /api/v1/feedback/conversation
Content-Type: application/json

{
  "oneid": "UID000001",
  "conversation_id": "CHAT_20260717_001",
  "summary": {
    "topic": "分期办理咨询",
    "customer_intent": "分期/借贷需求",
    "intent_confidence": 0.92,
    "sentiment": "neutral_to_satisfied",
    "resolution": "成功办理12期分期",
    "key_phrases": ["12期","手续费0.45%","每月1652元"],
    "customer_concerns": ["手续费是否划算","能否提前还款"]
  },
  "updated_intent_signals": [
    {"intent_type": "分期/借贷需求", "score_delta": -0.30, "reason": "需求已被满足"},
    {"intent_type": "额度/升级需求", "score_delta": 0.15, "reason": "分期后额度使用率上升"}
  ]
}
```

### API-CA1: 反馈事件回传

每次客户交互后回传。

```http
POST /api/v1/feedback/events
Content-Type: application/json

{
  "oneid": "UID000001",
  "event_type": "conversion",       ← impression|click|dismiss|conversion|browse|search|unsubscribe
  "campaign_id": "CAMP_2026_DOUBLE11",
  "channel": "APP Push",
  "detail": {
    "amount": 5000,                  ← 转化金额
    "stay_sec": 45,                  ← 停留时长
    "page": "分期计算器",            ← 浏览页面
    "keyword": "分期费率"            ← 搜索词
  },
  "timestamp": "2026-07-17T10:30:00+08:00"
}
```

### API-CA2: 对话摘要回传

对话结束后回传对话摘要。

```http
POST /api/v1/feedback/conversation
Content-Type: application/json

{
  "oneid": "UID000001",
  "conversation_id": "CHAT_20260717_001",
  "summary": {
    "topic": "分期办理咨询",
    "customer_intent": "分期/借贷需求",
    "intent_confidence": 0.92,
    "sentiment": "neutral_to_satisfied",
    "resolution": "成功办理12期分期",
    "key_phrases": ["12期","手续费0.45%","每月1652元"],
    "customer_concerns": ["手续费是否划算","能否提前还款"]
  },
  "updated_intent_signals": [
    {"intent_type": "分期/借贷需求", "score_delta": -0.30, "reason": "需求已被满足"},
    {"intent_type": "额度/升级需求", "score_delta": 0.15, "reason": "分期后额度使用率上升"}
  ]
}
```

---

### B. 与项目二的接口（策略包下发）

项目三对外暴露策略接收端点，当前由Mock数据驱动。

| 接口端点                  | 协议      | 功能描述               | MVP输入源                               |
| :------------------------ | :-------- | :--------------------- | :-------------------------------------- |
| `/api/v1/strategy/assign` | HTTP REST | 接收项目二下发的策略包 | 读取本地`strategy_package_example.json` |
| `/api/v1/strategy/status` | HTTP      | 回传策略执行状态       | 实时计算并返回Mock响应                  |

---

## 🖥️ 4. MVP交付：仿真智能助手交互界面

本次MVP的核心交付物是一个**Web端仿真智能助手界面**，用于完整演示“策略下发 → 触达 → 用户响应 → 多轮对话 → 反馈闭环”全流程。

### A. 界面功能模块

界面包含三大区域，协同演示单个用户（`U10001`）的营销交互过程：

1.  **策略看板（左侧）**：
    - 展示当前加载的Mock策略包详情（客群、权益、预算、频控规则）。
    - 显示渠道分发Mock结果（“已向用户发送App Push模拟推送”）。
    - 提供“触发策略执行”按钮，模拟项目二下发指令。

2.  **仿真手机交互区（中间/核心）**：
    - 模拟智能手机界面，呈现App Push通知栏弹窗。
    - **用户点击Push**后，界面切换至聊天窗口（模拟App内客服/营销会话）。
    - 支持**文本输入框**，供演示人员模拟客户回复（如“利率多少？”“我不需要”“怎么办理？”）。
    - Agent根据输入实时响应，展示三类Agent的协同工作（查询/服务/营销）。

3.  **决策执行流水线（右侧）**：
    - 实时滚动显示**后端执行日志**（JSON格式），包括：
      - 策略解析记录。
      - 调用的Mock画像数据。
      - LLM生成的Prompt与回复。
      - 渠道分发模拟记录（Mock回执）。
      - 反馈回流记录（模拟写入项目一、项目二的数据包）。

### B. 技术栈选型（MVP快速构建）

| 组件      | 技术选型                           | 说明                                           |
| :-------- | :--------------------------------- | :--------------------------------------------- |
| 后端服务  | Python FastAPI                     | 轻量级、高性能、天然支持异步和OpenAPI          |
| Agent框架 | LangGraph + LangChain              | 完整实现多Agent协作流程                        |
| LLM推理   | 本地Qwen2.5-7B（Ollama）或 云端API | 确保纯文本生成质量与响应速度                   |
| 向量检索  | Chroma (本地持久化)                | 支撑知识库Mock检索                             |
| 前端界面  | Vue3 + Element Plus                | 构建左侧策略看板、中间仿真手机、右侧日志流水线 |
| 实时通信  | WebSocket                          | 实现演示操作与后端日志的实时联动推送           |

---

## 🔒 5. 合规与安全机制（贯穿全链路）

虽然处于MVP阶段，合规与可解释性机制完整实现，不缩水。

- **策略包硬约束**：`StrategyLoader`加载策略时，强制校验`compliance_rules.min_age`与Mock画像中用户年龄，若不符则在生成前直接终止后续动作并提示。
- **实时合规防火墙**：在文案生成后、渠道分发前，遍历`prohibited_words`进行敏感词检测，若命中则拦截该条文案并标记为“合规驳回”。
- **频控校验**：基于`user_id`在内存缓存中维护触达计数，若当日次数已达`frequency_control`上限，则跳过本次触达并输出日志。
- **全链路追踪**：每个策略包生成唯一的`trace_id`，在各组件间透传。右侧流水线面板可清晰展示每一步的输入、输出和决策依据，满足验收要求的“可解释性”。

---

## 💎 6. MVP交付物总结

| 交付维度     | 具体内容                                            | 验收标准                                                     |
| :----------- | :-------------------------------------------------- | :----------------------------------------------------------- |
| **代码交付** | FastAPI后端服务 + Vue3前端源码                      | 本地一键启动，完成端到端演示                                 |
| **接口契约** | OpenAPI                                             | 清晰定义与项目一、项目二的输入输出格式                       |
| **Mock数据** | 用户画像、企业知识库、策略包样例                    | 覆盖信用卡分期典型场景，数据符合业务逻辑                     |
| **仿真演示** | Web端智能助手交互界面                               | 演示人员可在界面内模拟用户点击Push、输入对话，观察Agent实时响应及日志流水线 |
| **验证用例** | 提供3个典型交互脚本（正常办理、拒绝投诉、条件不符） | 一键切换演示场景，闭环链路清晰可见                           |

通过以上细化设计，项目三在MVP阶段既保证了演示效果与业务逻辑的完整性，又通过**适配器模式**和**标准化接口契约**为后续与项目一、项目二的真实集成铺平了道路，最大化复用前期开发投入。