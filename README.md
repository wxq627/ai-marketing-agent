# AI智能营销Agent：信用卡全链路营销智能平台

这是三人协作使用的 monorepo 仓库，按“知识/数据底座 -> B端策略大脑 -> C端触达执行”的结构组织。

## 模块分工

| 模块 | 目录 | 负责人定位 | 核心职责 |
|---|---|---|---|
| 项目一 Knowledge Agent | `services/knowledge-agent` | 基座/知识/画像 | 企业知识库、客户画像、产品规则、权限规则、GraphRAG |
| 项目二 Strategy Agent | `services/strategy-agent` | B端策略大脑 | 群像刻画、客群圈选、策略生成、渠道预算、复盘优化 |
| 项目三 Marketing Agent | `services/marketing-agent` | C端触达执行 | 智能体对话、内容生成、多渠道触达、反馈回流 |

## 关键目录

```text
docs/                  项目说明与接口文档
contracts/             JSON Schema 与接口示例
mock_data/             三方联调 mock 数据
services/              三个后端服务
frontend/console/      运营控制台前端
scripts/               本地运行脚本
```

## 推荐协作流程

1. 先看 `docs/api_contracts.md`，确认三方传递字段。
2. 三个模块先基于 `mock_data/` 并行开发。
3. 字段变更先改 `contracts/` 和 `docs/api_contracts.md`，再改代码。
4. 每个人在自己的 feature 分支开发，合并到 `dev`，演示版本合并到 `main`。

## 本地运行 B 端策略大脑

```powershell
cd services/strategy-agent
python app.py
```

打开：

```text
http://127.0.0.1:8765
```

## GitHub 分支建议

```text
main                         稳定演示版本
dev                          日常集成版本
feature/knowledge-agent       项目一开发
feature/strategy-agent        项目二开发
feature/marketing-agent       项目三开发
```
