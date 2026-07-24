# 项目一与项目二接口联调说明

## 调用方向

项目二在需要生成策略时主动调用项目一，不需要项目一再向项目二推送一份客户 CSV。

```text
项目二策略服务 -> 项目一知识服务 -> 客户画像、授权、意图、渠道上下文
项目二策略服务 -> 项目三智能体 -> 已发布策略包与客户推荐
项目三智能体 -> 项目二策略服务 -> 曝光、点击、转化、退订等反馈
```

## 项目一提供给项目二的接口

| 接口 | 用途 |
| --- | --- |
| `POST /api/v1/customer/search` | 获取批量客户画像、意图、风险与营销授权，供圈选和策略打分使用。 |
| `POST /api/v1/customer/frequency-check` | 在投放前进行频控、渠道授权与可触达渠道校验。 |
| `GET /api/v1/channels/context` | 获取渠道成本、日容量、历史打开/点击表现，供预算和渠道优化使用。 |
| `GET /api/v1/knowledge/search` | 检索产品、权益、资格与合规知识。 |
| `GET /api/v1/campaign/performance` | 获取历史活动的转化、成本、收入和 ROI。 |

## 本地启动顺序

1. 先确保项目一的 `api_server`、`db_store.py` 已合入当前代码分支；或者由 A 同学在包含这些文件的工作目录中启动项目一：

```powershell
cd C:\Users\15531\Documents\Codex\2026-07-13\ni\outputs\ai-marketing-agent
C:\Python314\python.exe -m api_server.main
```

2. 新开一个终端，启动项目二：

```powershell
cd C:\Users\15531\Documents\Codex\2026-07-13\ni\outputs\ai-marketing-agent\services\strategy-agent
C:\Python314\python.exe app.py
```

3. 检查联通状态：

```text
http://127.0.0.1:8765/api/strategy/integration-status
```

当返回中 `project1.connected` 为 `true`，项目二会使用项目一 API 的客户与渠道数据。若项目一暂未启动，项目二会自动回退到本地 CSV，以保证网页演示可继续运行；接口返回的 `source` 会明确标识为 `project1_local_csv_fallback`。

## 配置

项目二的 `.env` 可按需配置：

```env
PROJECT1_API_BASE_URL=http://127.0.0.1:8000
PROJECT1_API_TIMEOUT_SECONDS=8
```

当前历史响应模型仍使用本地的原始行为数据构建特征，保证其与已训练模型一致；客户圈选和渠道上下文优先来自项目一 API。项目一当前的客户搜索接口尚未返回逐客户的历史触达计数，因此批量策略生成后、真正下发前，应调用 `frequency-check` 做最终频控校验。后续项目一将事件流、触达明细也以批量接口提供后，可将该特征层完全切换到接口数据。
