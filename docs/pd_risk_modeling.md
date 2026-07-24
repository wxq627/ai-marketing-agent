# PD 风险评分模型

## 目标

PD（Probability of Default）评分模型预测客户在未来 180 天内是否会出现至少一次账单逾期。它服务于策略价值计算中的信用风险损失，不用于审批或授信决策。

## 数据与标签

- 账单数据：`bill_record.csv`，通过 `credit_card.csv` 的 `card_no -> cust_id` 映射到客户。
- 标签：在观察时点后 180 天内是否出现 `payment_status = 逾期`。
- 样本：客户月度快照；使用严格早于观察时点的账单和卡片信息构造特征，避免未来信息泄漏。

## 特征

- 近 180/365 天逾期次数、近 180 天最低还款次数。
- 近 90/180 天账单金额、账单笔数、平均账单金额和额度使用代理。
- 年龄、收入等级、有效卡数量、最高额度、主卡等级。

## 模型与评估

首版使用保持自然样本先验的 `LogisticRegression`，并采用时间顺序 70% 训练、15% 验证间隔、15% 测试的拆分。产物会输出 ROC-AUC、PR-AUC、Log loss 与高风险前 10% Lift。

```powershell
cd services\strategy-agent
C:\Python314\python.exe scripts\train_pd_risk_model.py --output-dir artifacts\pd_risk_model
```

## 策略价值接入

模型可用时，信用预期损失为：

```text
P(转化) × PD_6M × 单次预期信用损失
```

模型文件缺失时，系统自动回退到原有的“风险等级 -> 固定违约概率”规则，并在策略价值拆解的 `pd_source` 中标记为 `risk_level_fallback`。

## 口径边界

该 PD 是“客户未来逾期风险”的代理评分，并非“办理某营销活动后发生违约”的因果条件概率。要训练后者，需要产品办理事实、敞口、回款与更长观察窗的关联数据。
