# 模块四：GraphRAG 企业知识图谱 — 详细说明

> Knowledge Agent | 版本 v1.0 | 代码 `graphrag/` | 361节点 1843边

---

## 目录

1. [什么是 RAG 和 GraphRAG](#1-什么是-rag-和-graphrag)
2. [为什么需要 GraphRAG 而不是普通 RAG](#2-为什么需要-graphrag-而不是普通-rag)
3. [四步检索流程](#3-四步检索流程)
4. [知识图谱 Schema](#4-知识图谱-schema)
5. [文档处理流水线](#5-文档处理流水线)
6. [代码架构](#6-代码架构)
7. [API 接口](#7-api-接口)
8. [数据规模](#8-数据规模)
9. [技术选型说明](#9-技术选型说明)
10. [输入输出示例](#10-输入输出示例)

---

## 1. 什么是 RAG 和 GraphRAG

### RAG = 检索增强生成

```
传统大模型的问题:
  Q: "白金卡在机场有哪些权益？"
  LLM: "抱歉，我没有XX银行白金卡权益的具体信息。"  ← 私有数据不在训练语料中

RAG 解决:
  Q: "白金卡在机场有哪些权益？"
    ↓
  ① 检索: 把问题转成向量 → 在知识库中搜索相关文档
    ↓
  ② 找到: 《白金卡权益说明》第3页:
     "机场贵宾厅全年无限次使用，覆盖全球超过1000间贵宾厅"
    ↓
  ③ 增强: 原文片段 + 问题 → 喂给大模型
    ↓
  ④ 生成: "白金卡持卡人可全年无限次使用全球超过1000间机场贵宾厅..."
```

### GraphRAG = 知识图谱 + RAG

```
普通 RAG 的问题:
  问"张*明为什么收到这么多分期推送？"
  → 搜到"分期条款PDF"的片段
  → 但不知道张*明是谁、持有什么卡、最近消费多少
  → 回答空洞

GraphRAG 的改进:
  知识图谱把实体和关系连成一张网
  → 从"张*明"节点出发 → [持有]→白金卡 → [关联]→白金权益 → [INCLUDES]→机场贵宾厅
  → 回答"他是白金卡客户，本期账单18500元，额度使用率78%，因此系统推分期方案"
```

---

## 2. 为什么需要 GraphRAG 而不是普通 RAG

| 对比维度 | 普通 RAG | GraphRAG |
|------|------|------|
| **知识组织** | 扁平文档向量 | 实体+关系图 |
| **多跳推理** | ❌ 无法"张*明→白金卡→权益" | ✅ 沿图遍历关系链 |
| **客户个性化** | ❌ 只能搜通用文档 | ✅ 结合客户节点+画像 |
| **产品关系** | ❌ 不知产品关联哪些权益 | ✅ 产品-[INCLUDES]-权益 |
| **合规约束** | ❌ 可能推荐不符合资格的客户 | ✅ 检查 eligibility 关系 |

**结论**: 信用卡业务知识高度结构化（产品-权益-活动-规则有明确关系），用图表达最自然。

---

## 3. 四步检索流程

```
用户问: "张*明适合推荐什么分期方案？"
    │
    ▼
┌─ 第一步: 图谱检索 (graph_retrieve) ────────────────────────┐
│  从"张*明"节点出发:                                          │
│  → [HOLDS] → 白金信用卡 (额度200k)                           │
│  → [PARTICIPATES_IN] → 双十一分期活动                        │
│  → 白金信用卡 [BELONGS_TO] → 经典版白金信用卡                 │
│  → 经典版白金信用卡 [GOVERNED_BY] → 12期分期条款(0.45%/期)   │
│                                                              │
│  图谱返回: 白金卡客户, 当前有分期活动, 可办12期分期            │
└──────────────────────────────────────────────────────────────┘
    │
    ▼
┌─ 第二步: 向量检索 (vector_retrieve) ───────────────────────┐
│  将"分期方案推荐"转TF-IDF向量 → 搜索162个文档片段             │
│                                                              │
│  返回:                                                       │
│  · 《分期条款》片段: "12期手续费 0.45%/期"                    │
│  · 《双十一活动规则》片段: "满3000享3期免息"                  │
│  · 《白金卡权益》片段: "白金卡专享分期优惠费率"               │
└──────────────────────────────────────────────────────────────┘
    │
    ▼
┌─ 第三步: 融合排序 (fusion_rank) ───────────────────────────┐
│  · 相关性打分 (向量相似度)                                    │
│  · 新鲜度加权 (活动是否在有效期内)                            │
│  · 权威性加权 (合规条款 > 产品文档 > 活动海报)                │
│  · 去重合并 → Top-K                                          │
└──────────────────────────────────────────────────────────────┘
    │
    ▼
┌─ 第四步: 生成答案 (Mock: 拼接上下文, 生产: Qwen3-8B) ──────┐
│  输入 = 问题 + 融合上下文 + 客户画像                          │
│                                                              │
│  → "张*明先生是白金卡持卡人，本期账单¥18,500。               │
│     当前推荐12期分期方案，手续费仅0.45%/期，                  │
│     每期约还¥1,652。同时您正处于双十一活动覆盖范围，          │
│     可享前3期免息，预估节省手续费约¥333。"                    │
└──────────────────────────────────────────────────────────────┘
```

---

## 4. 知识图谱 Schema

### 4.1 实体节点类型 (7类, 361个)

| 节点类型 | Label | 数量 | 主要属性 | 数据来源 |
|:--:|------|:--:|------|------|
| 客户 | Customer | 200(抽样) | oneid, name, age, city, income_level, lifecycle | customer_profile.csv |
| 信用卡 | CreditCard | ~1200 | card_no, card_level, credit_amount | credit_card.csv |
| 产品 | Product | 15 | product_id, name, card_level, annual_fee | product_catalog.csv |
| 权益 | Benefit | 90 | benefit_id, name, category | benefit_catalog.csv |
| 营销活动 | Campaign | 25 | campaign_id, name, start, end, budget | campaign_catalog.csv |
| 分期条款 | InstallmentRule | 5 | periods, fee_rate | 业务规则 |
| 文档 | Document | 20 | doc_id, title, doc_type, product_name | product_docs |

### 4.2 关系类型 (7种, 1843条)

| 关系 | 方向 | 说明 | 示例 |
|:--:|------|------|------|
| `HOLDS` | Customer → CreditCard | 客户持有信用卡 | 张*明 → 白金卡 |
| `BELONGS_TO` | CreditCard → Product | 卡片属于某产品 | 白金卡 → 经典版白金卡 |
| `INCLUDES` | Product → Benefit | 产品包含权益 | 经典版白金卡 → 机场贵宾厅 |
| `PARTICIPATES_IN` | Customer → Campaign | 客户参与活动 | 张*明 → 双十一活动 |
| `APPLIES_TO` | Campaign → Product | 活动适用产品 | 双十一活动 → 经典版白金卡 |
| `GOVERNED_BY` | Product → InstallmentRule | 产品受条款约束 | 经典版白金卡 → 12期分期 |
| `RELATES_TO` | Document → Product | 文档关联产品 | 白金卡权益说明 → 经典版白金卡 |

---

## 5. 文档处理流水线

```
┌──────────────────────────────────────────────────────────┐
│              文档处理流水线                                 │
├──────────────────────────────────────────────────────────┤
│                                                           │
│  产品文档TXT (20份) + CSV (产品/权益/活动)                 │
│       │                                                   │
│       ▼                                                   │
│  ① 文档解析: 读取TXT全文 + CSV字段拼接为描述文本           │
│       │                                                   │
│       ▼                                                   │
│  ② 文本切片: 按段落+字符边界智能切分                       │
│     chunk_size=800, overlap=100                           │
│     → 162个文档片段                                       │
│       │                                                   │
│       ▼                                                   │
│  ③ 向量化: TF-IDF (ngram 1-2, 2000维)                    │
│     生产环境: Qwen3-Embedding-0.6B (1024维)               │
│       │                                                   │
│       ▼                                                   │
│  ④ 存储: 内存 (生产环境: Milvus)                          │
│                                                           │
└──────────────────────────────────────────────────────────┘
```

### Mock vs 生产对比

| 组件 | Mock (当前) | 生产 |
|------|------|------|
| 图数据库 | NetworkX (内存) | Neo4j |
| 向量化 | TF-IDF | Qwen3-Embedding-0.6B |
| 向量存储 | 内存矩阵 | Milvus |
| 文档加载 | Python文件读取 | pdfplumber + python-docx |
| 答案生成 | 拼接上下文 | Qwen3-8B-Instruct |

---

## 6. 代码架构

```
graphrag/
├── __init__.py              # 模块入口
├── kg_builder.py            # 知识图谱构建 (NetworkX, 361节点/1843边)
│   ├── KnowledgeGraph.build()      # 从CSV数据全量建图
│   ├── get_subgraph(id, depth)     # BFS遍历子图
│   ├── traverse_relations(id,rel) # 沿特定关系遍历
│   └── find_path(from, to)        # 最短路径
│
├── doc_pipeline.py          # 文档处理流水线
│   ├── DocPipeline.load_and_process() # 加载→切片→TF-IDF向量化
│   └── DocPipeline.search(query,k)    # 向量相似检索
│
├── retrieval.py             # 检索与融合
│   ├── graph_retrieve()     # 第一步: 图谱遍历
│   ├── vector_retrieve()    # 第二步: TF-IDF文档匹配
│   ├── compliance_retrieve()# 合规规则检索
│   ├── fusion_rank()        # 第三步: 融合排序(相关性+新鲜度+权威性)
│   └── full_search()        # 完整四步检索入口
│
├── router_knowledge.py      # FastAPI 路由 (3端点)
│   ├── POST /search         # 完整GraphRAG检索
│   ├── GET  /graph/{id}     # 查询子图
│   └── POST /path           # 两实体最短路径
│
└── test_graphrag.py         # 测试 (15/18 PASS)
```

---

## 7. API 接口

| # | 方法 | 路径 | 输入 | 输出 |
|:--:|:--:|------|------|------|
| 1 | POST | `/api/v1/knowledge/search` | query + 可选 customer_oneid | 图谱+向量+合规融合结果 |
| 2 | GET | `/api/v1/knowledge/graph/{entity_id}?depth=2` | 实体ID | 子图(nodes+edges) |
| 3 | POST | `/api/v1/knowledge/path` | {from_id, to_id} | 最短路径+关系链 |
| 4 | GET | `/api/v1/knowledge/stats` | — | 图谱统计 |

### 请求示例

```http
POST /api/v1/knowledge/search
{
  "query": "白金卡有哪些机场权益",
  "customer_oneid": "UID000001",
  "top_k": 5,
  "include_graph": true,
  "include_vector": true
}
```

---

## 8. 数据规模

| 指标 | 数值 |
|------|:--:|
| 知识图谱节点 | **361** (7种类型) |
| 知识图谱边 | **1,843** (7种关系) |
| 文档片段 | **162** chunks |
| TF-IDF 维度 | **1,945** |
| 抽样客户节点 | 200 (全量8000) |

---

## 9. 技术选型说明

### 为什么用 NetworkX 而不是 Neo4j

| 对比 | NetworkX (Mock) | Neo4j (生产) |
|------|------|------|
| 安装 | `pip install networkx` | Docker + Java环境 |
| 查询语言 | Python遍历 | Cypher |
| 性能 | 单机内存, 适合万级节点 | 分布式, 亿级节点 |
| 可视化 | 无 | Neo4j Browser |

> 当前阶段: NetworkX 足够展示图结构、验证检索逻辑。生产环境将图数据导出为 Cypher 脚本, 直接导入 Neo4j。

### 为什么用 TF-IDF 而不是 Qwen-Embedding

| 对比 | TF-IDF (Mock) | Qwen3-Embedding (生产) |
|------|------|------|
| 依赖 | scikit-learn (轻量) | GPU + 模型下载 |
| 维度 | 2000 | 1024 |
| 语义理解 | 关键词匹配 | 深层语义 |
| 中文 | ngram可以处理 | 中文C-MTEB榜单领先 |

> TF-IDF 的局限: 无法理解"便宜"和"优惠"是近义词。生产环境替换为 Qwen3-Embedding 后, 语义匹配准确率显著提高。

---

## 10. 输入输出示例

### 输入

```json
{
  "query": "白金卡有哪些机场权益",
  "customer_oneid": "UID000001",
  "top_k": 5
}
```

### 输出

```json
{
  "query": "白金卡有哪些机场权益",
  "customer_id": "UID000001",
  "results": [
    {
      "rank": 1,
      "source_type": "graph",
      "content": "机场贵宾厅服务 (benefit) — 出行",
      "source_doc": "knowledge_graph/benefit",
      "relevance_score": 0.85,
      "entity_type": "benefit"
    },
    {
      "rank": 2,
      "source_type": "graph",
      "content": "经典版白金信用卡 (product) — 白金卡",
      "source_doc": "knowledge_graph/product",
      "relevance_score": 0.85,
      "entity_type": "product"
    },
    {
      "rank": 3,
      "source_type": "vector",
      "content": "白金卡持卡人每年享有6次免费使用机场贵宾厅权益, 可携带1人...",
      "source_doc": "doc_01.txt",
      "relevance_score": 0.246
    },
    {
      "rank": 4,
      "source_type": "graph",
      "content": "接送机服务 (benefit) — 出行",
      "source_doc": "knowledge_graph/benefit",
      "relevance_score": 0.85,
      "entity_type": "benefit"
    },
    {
      "rank": 5,
      "source_type": "graph",
      "content": "航班延误险 (benefit) — 出行",
      "source_doc": "knowledge_graph/benefit",
      "relevance_score": 0.85,
      "entity_type": "benefit"
    }
  ],
  "graph_context": {
    "related_entities": [
      {"type": "product", "name": "百夫长白金卡 (product) —  白金卡"},
      {"type": "product", "name": "精致版白金信用卡 (product) —  白金卡"}
    ]
  },
  "total_sources": {
    "graph": 2,
    "vector": 1,
    "compliance": 0,
    "fused": 5
  }
}
```

---

## 11. 三个核心问题的直接答案

### Q1: 这个可以理解成知识问答引擎吗？

**是的。** 就是"客户问 → 查知识库 → 找答案"。

```
客户问智能体: "白金卡在机场有什么权益？"
        │
        ▼
项目三的对话智能体收到问题
        │
        ▼
调用项目一的 GraphRAG API: POST /api/v1/knowledge/search
  {"query": "白金卡机场权益"}
        │
        ▼
GraphRAG 引擎:
  ① 图检索: 找到 Product(白金卡) → [INCLUDES] → Benefit(机场贵宾厅/接送机/延误险)
  ② 向量检索: 找到文档片段 "白金卡持卡人每年6次免费机场贵宾厅..."
  ③ 融合排序 → Top-K
        │
        ▼
返回: [{机场贵宾厅}, {接送机}, {航班延误险}, {文档原文}]
        │
        ▼
项目三的对话智能体拿到这些信息 → 组织成自然语言回答客户
  "白金卡有3项机场权益: ①全年6次贵宾厅 ②6次接送机 ③航班延误险最高赔2000元"
```

### Q2: 知识图谱具体展现形式是什么？

**本质是一个数据结构，但可以多种方式展现。**

```
1. 存储层面: NetworkX 图数据结构 (节点+边)
   
   节点: Product(经典版白金卡)  边: INCLUDES  节点: Benefit(机场贵宾厅)
   
2. 查询层面: 通过 API 返回 JSON
   
   POST /api/v1/knowledge/graph/PROD_CLASSIC_W?depth=2
   → {
       "nodes": [
         {"id":"PROD_CLASSIC_W","label":"Product","name":"经典版白金信用卡"},
         {"id":"BEN_TRV_001","label":"Benefit","name":"机场贵宾厅服务"},
         ...
       ],
       "edges": [
         {"from":"PROD_CLASSIC_W","to":"BEN_TRV_001","label":"INCLUDES"},
         ...
       ]
     }

3. 可视化层面: JSON可渲染为力导向图 (生产环境用Neo4j Browser直接看)
```

### Q3: 项目三做对话智能体时，是不是直接调用这个？

**是的。这就是项目一为项目三提供的知识服务。**

```
项目三的对话智能体架构:

客户发消息 "白金卡有什么权益"
    │
    ▼
对话智能体 (项目三)
    │
    ├─→ 调用 项目一 GraphRAG API    ← 查产品/权益/规则
    │   POST /api/v1/knowledge/search
    │   {"query": "白金卡权益"}
    │
    ├─→ 调用 项目一 意图识别 API     ← 判断客户意图
    │   POST /api/v1/intent/classify
    │   {"conversation_text": "白金卡有什么权益"}
    │
    ├─→ 调用 项目一 客户画像 API     ← 查该客户信息
    │   GET /api/v1/customer/{oneid}/profile
    │
    └─→ 综合以上信息 → LLM 生成回复 → 发给客户
        "您好！您持有的白金卡包含以下权益: ..."
```

**项目三不需要在自己的代码里存产品信息、权益条款、活动规则。这些全在项目一的知识图谱里，通过API调用即可。**

> 一句话: 项目三是"对话外壳"，项目一是"知识大脑"。项目三负责和客户聊天，项目一负责告诉它该聊什么内容。

---
