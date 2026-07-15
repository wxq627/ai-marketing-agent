# 模块拆分说明

## 项目一：Knowledge Agent

输入：

- 企业知识
- 产品信息
- 权限规则
- 合规规则
- 客户历史行为
- 客户实时事件

输出：

- CustomerProfile
- IntentVector
- EventSequence
- DomainKnowledge

## 项目二：Strategy Agent

输入：

- 项目一输出的客户画像、意图、事件和规则
- 运营人员自然语言目标
- 项目三回传的效果反馈

输出：

- 群像刻画
- 客群圈选
- 策略包
- 渠道预算
- 内容大纲
- 合规边界
- 复盘建议

## 项目三：Marketing Agent

输入：

- 项目二输出的策略包
- 客户实时对话输入

输出：

- 客户触达内容
- 智能体回复
- 曝光、点击、转化、拒绝、投诉等反馈

## 联调优先级

1. 先跑通项目二 Strategy Agent 的策略生成页面。
2. 项目一先用 mock 数据提供客户洞察。
3. 项目三先读取策略包示例生成触达内容。
4. 最后接入真实 REST API。
