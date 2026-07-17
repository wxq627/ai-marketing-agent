# Mock 数据字典 — 项目一：企业知识引擎与记忆中心

> **数据基础**: XX银行信用卡中心真实产品/权益/活动体系  
> **生成日期**: 2026-07-16  
> **数据规模**: 8,000客户 × 12个月历史数据  
> **随机种子**: 42 (可复现)

---

## 目录结构

```
mock_data/
├── README.md                          ← 本文件
├── structured/                         ← 结构化数据 (CSV)
│   ├── customer_basic.csv              # 客户基础信息 (8,000行)
│   ├── credit_card.csv                 # 信用卡信息 (19,939行)
│   ├── transaction_log.csv             # 交易流水 (760,718行)
│   ├── bill_record.csv                 # 账单记录 (189,194行)
│   ├── crm_customer.csv                # CRM客户关系 (8,000行)
│   ├── app_events.csv                  # APP埋点事件 (369,497行)
│   ├── product_catalog.csv             # 产品目录 (15款)
│   ├── benefit_catalog.csv             # 权益目录 (90项)
│   ├── product_benefit_mapping.csv     # 产品-权益关联 (711条)
│   ├── campaign_catalog.csv            # 营销活动 (25个)
│   ├── channel_config.csv              # 触达渠道配置 (8个渠道) 🆕
│   ├── customer_consent.csv            # 客户营销授权+退订+风险+价值 (8,000行) 🆕
│   ├── contact_history.csv             # 近90天触达历史含成本 (120,000行) 🆕
│   ├── product_eligibility.csv         # 产品办理资格规则 (15条) 🆕
│   ├── campaign_attribution.csv        # 活动归因明细 (30,092条) 🆕
│   └── campaign_performance.csv        # 活动ROI汇总 (25个) 🆕
├── unstructured/                       ← 非结构化数据
│   ├── asr_transcripts/                # 客服ASR对话 (956个JSON文件)
│   ├── product_docs/                   # 产品说明书/条款 (20个TXT + _index.json)
│   ├── posters/                        # 活动海报描述 (12个JSON)
│   ├── frequency_rules.json            # 营销触达频控规则 🆕
│   └── compliance_rules.json           # 营销合规规则 🆕
└── scripts/                            ← 生成 + 运维脚本
    ├── config.py                       # 全局配置
    ├── generate_products.py            # 产品/权益/活动 (基于招行真实体系)
    ├── generate_customers.py           # 客户+信用卡
    ├── generate_transactions.py        # 交易+账单
    ├── generate_crm.py                 # CRM数据
    ├── generate_app_events.py          # APP埋点
    ├── generate_asr.py                 # ASR对话
    ├── generate_docs.py                # 文档+海报
    ├── generate_supplementary.py       # 项目二所需补充数据 🆕
    ├── generate_attribution.py         # 活动效果归因数据生成 🆕
    ├── migrate_to_real_cmb.py          # 数据迁移脚本
    ├── sync_names.py                   # 非结构化数据名称同步
    ├── check_all.py                    # 数据完整性全量检查
    └── run_all.py                      # 一键生成
```

---

## 一、XX银行信用卡产品体系 (15款)

> 基于XX银行信用卡中心真实产品线，覆盖 6 个卡等级。

### 产品完整列表

| 卡等级 | product_id | 产品名称 | 年费 |
|:------:|-----------|------|------|
| 普卡 | `PROD_STANDARD_N` | 标准信用卡（普卡） | ¥100 |
| 普卡 | `PROD_HELLOKITTY_N` | Hello Kitty粉丝信用卡（普卡） | ¥100 |
| 校园卡 | `PROD_YOUNG_CAMPUS` | YOUNG卡（校园版） | ¥0 |
| 金卡 | `PROD_STANDARD_G` | 标准信用卡（金卡） | ¥300 |
| 金卡 | `PROD_YOUNG_G` | YOUNG卡（青年版） | ¥300 |
| 金卡 | `PROD_JD_G` | 京东PLUS联名信用卡（金卡） | ¥300 |
| 金卡 | `PROD_CTRIP_G` | 携程旅行信用卡（金卡） | ¥300 |
| 白金卡 | `PROD_CLASSIC_W` | 经典版白金信用卡 | ¥3,600 |
| 白金卡 | `PROD_FREELIFE_W` | 自由人生白金信用卡 | ¥800 |
| 白金卡 | `PROD_UNIONPAY_W` | 银联白金信用卡 | ¥1,800 |
| 白金卡 | `PROD_GLOBAL_W` | 全币种国际白金信用卡 | ¥2,600 |
| 白金卡 | `PROD_REFINED_W` | 精致版白金信用卡 | ¥800 |
| 白金卡 | `PROD_CENTURION_W` | 百夫长白金卡 | ¥3,600 |
| 钻石卡 | `PROD_DIAMOND` | 银联钻石信用卡 | ¥3,600 |
| 无限卡 | `PROD_WORLD` | 万事达世界信用卡 | ¥3,600 |

---

## 二、结构化数据 Schema

### 1. customer_basic.csv — 客户基础信息

| 序号 | 字段名 | 类型 | 说明 | 示例 |
|:--:|--------|------|------|------|
| 1 | `cust_id` | VARCHAR(32) | 银行核心系统客户ID | `C000001` |
| 2 | `name` | VARCHAR(64) | 姓名 | `张伟` |
| 3 | `gender` | CHAR(1) | 性别 | `M` / `F` |
| 4 | `age` | INT | 年龄 | `32` |
| 5 | `city` | VARCHAR(32) | 城市 | `深圳` |
| 6 | `occupation` | VARCHAR(32) | 职业 | `IT/互联网` |
| 7 | `income_level` | VARCHAR(8) | 收入等级 | `H`(高) / `M`(中) / `L`(普通) |
| 8 | `education` | VARCHAR(16) | 学历 | `本科` |
| 9 | `id_card` | VARCHAR(32) | 身份证号(脱敏) | `4403****001` |
| 10 | `phone` | VARCHAR(16) | 手机号(脱敏) | `138****8888` |
| 11 | `register_date` | DATE | 开户日期 | `2020-03-15` |

> **脱敏规则**: 身份证保留前4后2位, 手机号保留前3后4位, 中间以`*`替代。

---

### 2. credit_card.csv — 信用卡信息

| 序号 | 字段名 | 类型 | 说明 |
|:--:|--------|------|------|
| 1 | `card_no` | VARCHAR(32) | 卡号(脱敏, BIN前缀使用招行真实BIN) |
| 2 | `cust_id` | VARCHAR(32) | 客户ID (外键→customer_basic) |
| 3 | `card_level` | VARCHAR(16) | 卡等级: 校园卡 / 普卡 / 金卡 / 白金卡 / 钻石卡 / 无限卡 |
| 4 | `credit_amount` | DECIMAL(12,2) | 授信额度 |
| 5 | `open_date` | DATE | 开卡日期 |
| 6 | `card_status` | VARCHAR(16) | 卡片状态: 正常 / 冻结 / 销卡 |
| 7 | `product_id` | VARCHAR(32) | 产品ID (外键→product_catalog, 对应15款真实招行产品) |
| 8 | `is_primary` | BOOLEAN | 是否主卡 |

---

### 3. transaction_log.csv — 交易流水

| 序号 | 字段名 | 类型 | 说明 |
|:--:|--------|------|------|
| 1 | `txn_id` | VARCHAR(32) | 交易ID |
| 2 | `card_no` | VARCHAR(32) | 卡号(外键→credit_card) |
| 3 | `txn_type` | VARCHAR(16) | 类型: 消费 / 取现 / 还款 / 退款 / 分期 |
| 4 | `amount` | DECIMAL(12,2) | 金额(退款为负) |
| 5 | `currency` | VARCHAR(8) | 币种: CNY / USD / EUR / JPY / HKD / GBP |
| 6 | `merchant_category` | VARCHAR(32) | 商户类别: 餐饮 / 商旅 / 购物 / 境外 / 娱乐 / 教育 / 医疗 / 日用 / 交通 / 其他 |
| 7 | `merchant_name` | VARCHAR(64) | 商户名称 |
| 8 | `is_cross_border` | BOOLEAN | 是否境外交易 |
| 9 | `txn_channel` | VARCHAR(16) | 交易渠道: 线下刷卡 / 支付宝 / 微信支付 / 银联在线 / Apple Pay / 云闪付 |
| 10 | `timestamp` | DATETIME | 交易时间 |

---

### 4. bill_record.csv — 账单记录

| 序号 | 字段名 | 类型 | 说明 |
|:--:|--------|------|------|
| 1 | `bill_id` | VARCHAR(32) | 账单ID |
| 2 | `card_no` | VARCHAR(32) | 卡号 |
| 3 | `bill_month` | VARCHAR(7) | 账单月份 (YYYY-MM) |
| 4 | `bill_amount` | DECIMAL(12,2) | 本期账单金额 |
| 5 | `min_payment` | DECIMAL(12,2) | 最低还款额 |
| 6 | `is_min_payment` | BOOLEAN | 是否最低还款 |
| 7 | `due_date` | DATE | 到期还款日 |
| 8 | `payment_status` | VARCHAR(16) | 还款状态: 已还清 / 最低还款 / 逾期 / 无欠款 |

---

### 5. crm_customer.csv — CRM客户关系

| 序号 | 字段名 | 类型 | 说明 |
|:--:|--------|------|------|
| 1 | `crm_id` | VARCHAR(32) | CRM系统ID |
| 2 | `cust_id` | VARCHAR(32) | 客户ID |
| 3 | `lifecycle_stage` | VARCHAR(16) | 生命周期: 新户 / 成长期 / 成熟期 / 沉睡期 |
| 4 | `customer_manager` | VARCHAR(32) | 客户经理姓名 |
| 5 | `vip_tier` | VARCHAR(16) | VIP等级: 钻石 / 白金 / 金卡 / 普通 |
| 6 | `churn_risk_score` | INT | 流失风险评分 (0-100, 越高风险越大) |
| 7 | `last_contact_date` | DATE | 最近联系日期 |
| 8 | `contact_preference` | VARCHAR(16) | 联系偏好: APP Push / 短信 / 邮件 / 电话 |

---

### 6. app_events.csv — APP埋点事件

| 序号 | 字段名 | 类型 | 说明 |
|:--:|--------|------|------|
| 1 | `event_id` | VARCHAR(32) | 事件ID |
| 2 | `device_id` | VARCHAR(32) | 设备ID |
| 3 | `open_id` | VARCHAR(64) | 微信OpenID |
| 4 | `event_type` | VARCHAR(32) | 事件类型: 页面浏览 / 点击 / 搜索 / 停留 / 分享 / 退出 |
| 5 | `page_name` | VARCHAR(64) | 页面名称 (对应掌上生活APP真实页面) |
| 6 | `search_keyword` | VARCHAR(128) | 搜索关键词(可为空) |
| 7 | `duration_sec` | INT | 停留/浏览时长(秒) |
| 8 | `timestamp` | DATETIME | 事件时间 |
| 9 | `app_version` | VARCHAR(16) | APP版本号 (如 9.3.5) |

---

### 7. product_catalog.csv — 产品目录

| 序号 | 字段名 | 类型 | 说明 |
|:--:|--------|------|------|
| 1 | `product_id` | VARCHAR(32) | 产品ID (如 `PROD_CLASSIC_W`) |
| 2 | `product_name` | VARCHAR(64) | 产品名称 (如 `XX银行经典版白金信用卡`) |
| 3 | `card_level` | VARCHAR(16) | 对应卡等级: 校园卡 / 普卡 / 金卡 / 白金卡 / 钻石卡 / 无限卡 |
| 4 | `annual_fee` | DECIMAL(8,2) | 年费(元) |
| 5 | `annual_fee_waiver` | VARCHAR(128) | 年费减免条件 |
| 6 | `target_income` | VARCHAR(16) | 目标收入等级 (逗号分隔: L,M,H) |
| 7 | `key_selling_points` | TEXT | 核心卖点(逗号分隔) |

---

### 8. benefit_catalog.csv — 权益目录

| 序号 | 字段名 | 类型 | 说明 |
|:--:|--------|------|------|
| 1 | `benefit_id` | VARCHAR(32) | 权益ID (如 `BEN_TRV_001`) |
| 2 | `benefit_name` | VARCHAR(64) | 权益名称 |
| 3 | `benefit_category` | VARCHAR(32) | 类别 (9大类): 出行 / 积分 / 生活 / 消费 / 分期 / 健康 / 保险 / 新户 / 高端专属 |
| 4 | `benefit_desc` | TEXT | 权益详细描述 |

**9大类别分布**:

| 类别 | 数量 | 说明 |
|------|:---:|------|
| 出行 | 17 | 机场贵宾厅、接送机、300精选酒店、航班延误险、境外救援等 |
| 生活 | 14 | 周三5折饭票、9元观影、咖啡权益、视频会员、健身优惠等 |
| 消费 | 12 | Apple Pay返现、境外消费返现、电商返现、免税店优惠等 |
| 分期 | 10 | 3/6/12期免息、教育分期、医疗分期、账单分期优惠等 |
| 新户 | 10 | 开卡礼三选一、推荐办卡礼、首刷礼、绑卡礼、额度成长等 |
| 积分 | 8 | 生日10倍积分、积分兑里程、积分兑年费、积分抵现等 |
| 保险 | 7 | 航班延误险、购物保障险、盗刷险、旅行意外险等 |
| 高端专属 | 7 | FHR酒店礼遇、酒店会籍匹配、钻石管家、私人定制旅行等 |
| 健康 | 5 | 健康体检、口腔护理、高尔夫练习场、齿科保险等 |

---

### 9. product_benefit_mapping.csv — 产品-权益关联

| 序号 | 字段名 | 类型 | 说明 |
|:--:|--------|------|------|
| 1 | `product_id` | VARCHAR(32) | 产品ID |
| 2 | `benefit_id` | VARCHAR(32) | 权益ID |

> 权益数随卡等级递增: 普卡/校园卡 ~21项 → 金卡 41~52项 → 白金卡 42~65项 → 钻石卡 70项 / 世界卡 66项

---

### 10. campaign_catalog.csv — 营销活动

| 序号 | 字段名 | 类型 | 说明 |
|:--:|--------|------|------|
| 1 | `campaign_id` | VARCHAR(32) | 活动ID (如 `CAMP_2026_APPLEPAY`) |
| 2 | `campaign_name` | VARCHAR(128) | 活动名称 |
| 3 | `start_date` | DATE | 开始日期 |
| 4 | `end_date` | DATE | 结束日期 |
| 5 | `target_segment` | TEXT | 目标客群(JSON格式) |
| 6 | `rules` | TEXT | 活动规则(JSON格式) |
| 7 | `budget` | INT | 活动预算(元) |
| 8 | `expected_reach` | INT | 预期触达人数 |
| 9 | `campaign_poster_path` | VARCHAR(256) | 活动海报路径 |

**25个营销活动完整列表**:

| campaign_id | 活动名称 | 时间 |
|------------|------|------|
| `CAMP_2026_APPLEPAY` | Apple Pay笔笔1%返现 | 2025-07 ~ 2026-03 |
| `CAMP_2026_DOUBLE11` | 双十一分期免息大促 | 2026-11-01 ~ 11-11 |
| `CAMP_2026_SPRINGFEST` | 春节境外消费返现 | 2026-01-15 ~ 02-15 |
| `CAMP_2026_NEWUSER` | 新户开卡三重礼 | 2025-07 ~ 2026-12 |
| `CAMP_2026_DORMANT` | 沉睡客户唤醒计划 | 2026-04 ~ 2026-10 |
| `CAMP_2026_SUMMER` | 暑期出行季 | 2026-07-01 ~ 08-31 |
| `CAMP_2026_UPGRADE` | 金卡升级白金卡邀请 | 2026-05 ~ 2026-11 |
| `CAMP_2026_618` | 618购物节返现 | 2026-06-01 ~ 06-18 |
| `CAMP_2026_CAMPUS` | 校园卡毕业季 | 2026-06-01 ~ 07-31 |
| `CAMP_2026_BIRTHDAY` | 生日月专属福利 | 跨年度(2年) |
| `CAMP_2026_CROSSBORDER` | 跨境消费达人 | 2026-06 ~ 2026-10 |
| `CAMP_2026_WEDDING5` | 周三5折饭票 | 跨年度(2年) |
| `CAMP_2026_MOVIE9` | 9元观影 | 跨年度(2年) |
| `CAMP_2026_REFERRAL` | 推荐办卡有礼 | 2026-04-01 ~ 06-30 |
| `CAMP_2026_AI_TOKEN` | AI算力权益新户礼 | 2025-12 ~ 2026-12 |
| `CAMP_2026_POINTS_BOOST` | 积分膨胀季 | 2026-09-01 ~ 11-30 |
| `CAMP_2026_GREEN` | 绿色消费计划 | 2026-03-01 ~ 08-31 |
| `CAMP_2026_WOMEN` | 女性消费节 | 2026-03-01 ~ 03-31 |
| `CAMP_2026_NYE` | 年终回馈盛典 | 2026-12-01 ~ 12-31 |
| `CAMP_2026_SPRING_TRAVEL` | 春季出行节 | 2026-03-15 ~ 05-15 |
| `CAMP_2026_BACK_SCHOOL` | 开学季特惠 | 2026-08-15 ~ 09-30 |
| `CAMP_2026_NATIONAL` | 国庆黄金周出行保障 | 2026-09-25 ~ 10-10 |
| `CAMP_2026_CLOUD_FLASH` | 云闪付专属优惠 | 2026-07-01 ~ 09-30 |
| `CAMP_2026_FAMILY` | 亲子家庭日 | 2026-05-15 ~ 08-15 |
| `CAMP_2026_SPORTS` | 运动健康月 | 2026-10-01 ~ 11-30 |

---

### 11. channel_config.csv — 触达渠道配置 🆕

> 供项目二 Strategy Agent 做渠道决策时使用，包含各渠道的成本、容量和转化率。

| 序号 | 字段名 | 类型 | 说明 |
|:--:|--------|------|------|
| 1 | `channel_code` | VARCHAR(16) | 渠道编码 (如 `CH_PUSH`) |
| 2 | `channel_name` | VARCHAR(32) | 渠道名称: APP Push / 短信 / 微信公众号 / 邮件 / 掌上生活APP内消息 / 电话外呼 / 彩信 / 直邮 |
| 3 | `channel_type` | VARCHAR(16) | 渠道类型: owned(自有) / offline(线下) |
| 4 | `cost_per_send` | DECIMAL(6,2) | 单次触达成本(元) |
| 5 | `availability` | VARCHAR(16) | 可用时段: always / business_hours / business_days |
| 6 | `daily_capacity` | INT | 日最大发送量 |
| 7 | `monthly_capacity` | INT | 月最大发送量 |
| 8 | `requires_consent` | BOOLEAN | 是否需要客户授权 |
| 9 | `supported_content_types` | VARCHAR(64) | 支持的内容类型 (逗号分隔) |
| 10 | `avg_open_rate` | DECIMAL(4,2) | 历史平均打开率 |
| 11 | `avg_click_rate` | DECIMAL(4,2) | 历史平均点击率 |
| 12 | `typical_response_time_sec` | INT | 典型响应时间(秒) |
| 13 | `status` | VARCHAR(16) | 渠道状态: active / inactive |

| 渠道 | 单次成本 | 日容量 | 打开率 | 点击率 | 状态 |
|------|:---:|:---:|:---:|:---:|:--:|
| APP Push | ¥0.02 | 500K | 18% | 6% | active |
| 掌上生活APP内消息 | ¥0.01 | 800K | 25% | 10% | active |
| 短信 | ¥0.06 | 200K | 8% | 2% | active |
| 微信公众号 | ¥0.03 | 300K | 12% | 4% | active |
| 邮件 | ¥0.01 | 100K | 5% | 1% | active |
| 电话外呼 | ¥2.50 | 5K | 35% | 15% | active |
| 彩信 | ¥0.15 | 50K | 10% | 3% | active |
| 直邮 | ¥3.00 | 10K | 20% | 5% | inactive |

---

### 12. customer_consent.csv — 客户营销授权+退订+风险+价值 🆕

> 供项目二 Strategy Agent 做阶段2硬门槛校验。**覆盖项目二全部客户标识/授权/退订/投诉/风险字段**。

| 序号 | 字段名 | 类型 | 说明 | 项目二用途 |
|:--:|--------|------|------|:--:|
| 1 | `cust_id` | VARCHAR(32) | 客户ID (外键→customer_basic) | 客户标识 |
| 2 | `marketing_consent` | BOOLEAN | 营销总授权 (95.0%) | 硬门槛 |
| 3 | `personalization_consent` | BOOLEAN | 个性化推荐授权 (80%) | 硬门槛 |
| 4 | `data_sharing_consent` | BOOLEAN | 数据共享授权 (60%) | 硬门槛 |
| 5 | `sms_consent` | BOOLEAN | 短信渠道许可 (85%) | 渠道授权 |
| 6 | `phone_consent` | BOOLEAN | 电话外呼许可 (30%) | 渠道授权 |
| 7 | `email_consent` | BOOLEAN | 邮件渠道许可 (70%) | 渠道授权 |
| 8 | `push_consent` | BOOLEAN | APP Push许可 (90%) | 渠道授权 |
| 9 | `wechat_consent` | BOOLEAN | 微信公众号许可 (75%) | 渠道授权 |
| 10 | `consent_updated_at` | DATE | 授权最近更新日期 | 时效判断 |
| 11 | `dnc_list` | BOOLEAN | 免打扰名单 (2.7%) | 硬门槛 |
| 12 | `unsubscribe_channels` | VARCHAR(128) | **退订渠道列表** (逗号分隔, 如"短信,APP Push") | 退订信息 |
| 13 | `unsubscribe_at` | DATE | **退订日期** | 退订信息 |
| 14 | `complaint_count_90d` | INT | **近90天投诉次数** (5%客户≥1) | 投诉信息 |
| 15 | `do_not_contact_signal` | BOOLEAN | **禁止触达信号** (5.4%) | 硬门槛 |
| 16 | `risk_level` | VARCHAR(8) | **风险等级**: low(83%)/medium(8%)/high(9%) | 风险状态 |
| 17 | `blacklist_flag` | BOOLEAN | **黑名单标识** (3.0%) | 硬门槛 |
| 18 | `value_level` | VARCHAR(8) | **客户价值**: low(18%)/medium(50%)/high(32%) | 画像标签 |

> ⚠️ **项目二硬门槛判定逻辑**: `marketing_consent=false` OR `blacklist_flag=true` OR `do_not_contact_signal=true` → 绝对不可触达  
> ⚠️ **渠道过滤逻辑**: `{channel}_consent=false` → 该渠道不可用; 渠道名在 `unsubscribe_channels` 中 → 永久禁止

---

### 13. contact_history.csv — 近90天触达历史 🆕

> 供项目二计算近7/30天触达次数，配合频控规则使用。

| 序号 | 字段名 | 类型 | 说明 |
|:--:|--------|------|------|
| 1 | `contact_id` | VARCHAR(16) | 触达记录ID |
| 2 | `cust_id` | VARCHAR(32) | 客户ID |
| 3 | `campaign_id` | VARCHAR(32) | 关联活动ID (非营销类为空) |
| 4 | `channel` | VARCHAR(16) | 触达渠道: APP Push/短信/微信公众号/邮件/掌上生活APP内消息/电话外呼 |
| 5 | `contact_time` | DATETIME | 触达时间 (近90天, 120,000条) |
| 6 | `contact_type` | VARCHAR(16) | 触达类型: marketing(85%)/service/transactional |
| 7 | `status` | VARCHAR(16) | 状态: sent / delivered / opened(45%) / clicked(25%) / bounced / unsubscribed |
| 8 | `response_time_sec` | INT | 响应时间(秒), 仅 opened/clicked 有值 |
| 9 | `cost` | DECIMAL(6,2) | **单次触达成本(元)**, 按 channel_config 映射 🆕 |

> ⚠️ **项目二使用**: 按cust_id聚合contact_time → 得近7/30天触达次数 → 对比frequency_rules频控上限

---

### 14. product_eligibility.csv — 产品办理资格规则 🆕

> 供项目二判断客户是否具备办理某产品的资格（避免无效推荐）。

| 序号 | 字段名 | 类型 | 说明 |
|:--:|--------|------|------|
| 1 | `product_id` | VARCHAR(32) | 产品ID (外键→product_catalog, 15条) |
| 2 | `required_income` | VARCHAR(16) | 收入等级要求 (L,M,H逗号分隔) |
| 3 | `min_age` | INT | 最低年龄要求 |
| 4 | `max_age` | INT | 最高年龄要求 |
| 5 | `required_card_level` | VARCHAR(32) | 需持有的卡等级 ("-" 表示无要求) |
| 6 | `min_credit` | INT | 最低授信额度(元) |
| 7 | `special_conditions` | VARCHAR(256) | 特殊办理条件 |

| 产品 | 收入 | 年龄 | 需持有 | 最低额度 | 特殊条件 |
|------|:--:|:--:|------|:--:|------|
| 标准普卡 | L+ | 21-65 | — | ¥0 | 无 |
| YOUNG校园版 | L | 18-28 | — | ¥0 | 在校生 |
| Hello Kitty普卡 | L+ | 18-60 | — | ¥0 | 限女性 |
| 标准金卡 | L+ | 21-65 | 普卡+ | ¥1万 | 可升级 |
| YOUNG青年版 | L+ | 21-30 | — | ¥5千 | ≤30岁 |
| 京东PLUS金卡 | L+ | 21-60 | — | ¥5千 | — |
| 携程旅行金卡 | M+ | 21-60 | — | ¥1万 | 出行优先 |
| 经典版白金 | M+ | 25-60 | 金卡+ | ¥5万 | 暂停新户 |
| 自由人生白金 | M+ | 23-55 | — | ¥3万 | 入门 |
| 银联白金 | M+ | 23-60 | — | ¥3万 | — |
| 全币种白金 | M+ | 23-60 | — | ¥3万 | 境外需求 |
| 精致版白金 | M+ | 23-55 | — | ¥3万 | 新户有礼 |
| 百夫长白金 | H | 28-60 | 金卡+ | ¥8万 | 邀请制 |
| 银联钻石 | H | 30-60 | 白金+ | ¥10万 | 亲子 |
| 万事达世界 | H | 30-60 | 白金+ | ¥20万 | 私行邀请 |

---

### 15. campaign_attribution.csv — 活动归因明细 🆕

> 把"活动触达 → 客户点击 → 后续消费"串联起来，用于回答"这个活动到底带来了多少收入"。

| 序号 | 字段名 | 类型 | 说明 |
|:--:|--------|------|------|
| 1 | `attribution_id` | VARCHAR(16) | 归因记录ID |
| 2 | `campaign_id` | VARCHAR(32) | 活动ID (外键→campaign_catalog) |
| 3 | `cust_id` | VARCHAR(32) | 客户ID |
| 4 | `touch_id` | VARCHAR(16) | 触达记录ID (外键→contact_history) |
| 5 | `channel` | VARCHAR(16) | 触达渠道 |
| 6 | `touch_time` | DATETIME | 触达时间 |
| 7 | `touch_cost` | DECIMAL(8,4) | 单次触达成本(元) |
| 8 | `converted` | BOOLEAN | 是否转化 (99.5%) |
| 9 | `conversion_amount` | DECIMAL(12,2) | 归因消费金额(元) |
| 10 | `conversion_time` | DATETIME | 转化发生时间 |
| 11 | `attribution_hours` | DECIMAL(8,1) | 从触达到转化的时间(小时) |
| 12 | `attribution_window_days` | INT | 归因窗口(天) |

| 指标 | 数值 |
|------|------|
| 总归因记录 | 30,092 条 |
| 转化率 | 99.5% |
| 总归因收入 | ¥97,853,830 |
| 平均归因时长 | 128 小时 (~5.3天) |

> **归因逻辑**: 客户点击活动推送后 14 天内产生的消费，记为本次活动的归因收入。

---

### 16. campaign_performance.csv — 活动ROI汇总 🆕

> 聚合每个活动的触达成本、转化、收入、ROI，用于策略效果评估。

| 序号 | 字段名 | 类型 | 说明 |
|:--:|--------|------|------|
| 1 | `campaign_id` | VARCHAR(32) | 活动ID |
| 2 | `campaign_name` | VARCHAR(128) | 活动名称 |
| 3 | `budget` | INT | 活动预算(元) |
| 4 | `expected_reach` | INT | 预期触达人数 |
| 5 | `actual_touches` | INT | 实际触达次数 |
| 6 | `actual_reach_rate` | DECIMAL(6,4) | 触达达成率 |
| 7 | `impressions` | INT | 曝光次数 |
| 8 | `clicks` | INT | 点击次数 |
| 9 | `click_rate` | DECIMAL(6,4) | 点击率 |
| 10 | `conversions` | INT | 转化数 |
| 11 | `conversion_rate` | DECIMAL(6,4) | 转化率 |
| 12 | `total_cost` | DECIMAL(12,2) | 总触达成本(元) |
| 13 | `attributed_revenue` | DECIMAL(14,2) | 归因收入(元) |
| 14 | `roi` | DECIMAL(10,4) | 投资回报率 (Revenue-Cost)/Cost |
| 15 | `cpa` | DECIMAL(10,2) | 单次转化成本(元) Cost/Conversions |
| 16 | `avg_attribution_hours` | DECIMAL(8,1) | 平均归因时长(小时) |

**ROI Top 5 活动**:

| 活动 | ROI | 转化数 | 归因收入 | CPA |
|------|:--:|:--:|------|:--:|
| 生日月专属福利 | 2,379x | 1,020 | ¥4,156,849 | ¥1.71 |
| 双十一分期免息大促 | 2,117x | 1,047 | ¥3,746,255 | ¥1.69 |
| Apple Pay笔笔1%返现 | 2,103x | 1,025 | ¥3,679,573 | ¥1.71 |
| 国庆黄金周出行保障 | 2,085x | 1,012 | ¥3,632,209 | ¥1.77 |
| 春季出行节 | 2,033x | 1,059 | ¥3,622,962 | ¥1.74 |

> ⚠️ **项目二/三使用指引**: 
> - `roi` + `cpa` 用于评估活动效果，指导后续策略优化
> - `attribution_hours` 用于分析"触达后多久客户最可能转化"
> - `click_rate` + `conversion_rate` 用于比较不同渠道的转化效率

---

### 客服ASR对话 (JSON)

每条对话一个文件, 文件名: `ASR_ASRXXXXXX.json` (共956个)

```json
{
  "call_id": "ASR000001",
  "cust_id": "C000513",
  "phone": "189****0313",
  "timestamp": "2026-03-25T06:31:00Z",
  "duration_sec": 382,
  "call_direction": "inbound | outbound",
  "call_reason": "分期/借贷需求",
  "transcript": [
    {"role": "customer", "text": "..."},
    {"role": "agent", "text": "..."}
  ],
  "resolution": "成功办理12期账单分期",
  "sentiment_label": "anxious_to_relieved | neutral_to_satisfied | dissatisfied | ...",
  "intent_label": "分期/借贷需求 | 跨境/出行需求 | 额度/升级需求 | 权益/优惠需求 | 沉睡/流失风险 | 新户/激活引导 | 一般咨询"
}
```

**8类场景分布**:

| 场景大类 | intent_label | 约数量 |
|---------|-------------|:---:|
| 分期费率咨询/办理 | 分期/借贷需求 | ~300 |
| 出境游用卡咨询 | 跨境/出行需求 | ~120 |
| 额度调整/升级申请 | 额度/升级需求 | ~140 |
| 积分兑换/权益使用 | 权益/优惠需求 | ~170 |
| 投诉/争议处理 | 沉睡/流失风险 | ~150 |
| 长期未用卡激活 | 沉睡/流失风险 | ~60 |
| 新户开卡咨询 | 新户/激活引导 | ~80 |
| 一般查询/挂失 | 一般咨询 | ~160 |

---

### 产品文档 (TXT + 索引)

文档索引文件: `product_docs/_index.json` (20份文档)

覆盖产品: 经典版白金卡、银联白金卡、全币种国际白金卡、精致版白金卡、自由人生白金卡、
百夫长白金卡、银联钻石卡、万事达世界卡、标准金卡、YOUNG卡青年版、携程旅行金卡、
京东PLUS联名金卡、标准普卡、Hello Kitty普卡、YOUNG校园版 + 分期条款/章程/积分/境外指南等通用文档

```json
[
  {
    "doc_id": "DOC_001",
    "title": "经典版白金信用卡权益说明说明",
    "doc_type": "权益说明 | 分期条款 | 通用",
    "file_path": "doc_01.txt",
    "product_name": "经典版白金信用卡",
    "char_count": 3500,
    "generated_at": "2026-07-16"
  }
]
```

---

### 活动海报 (JSON)

每个海报对应一份JSON描述文件 (12个), 文件名与图片同名:

```json
{
  "image_file": "nov11_promo.png",
  "activity_name": "双十一分期免息大促",
  "campaign_id": "CAMP_2026_DOUBLE11",
  "start_date": "2026-11-01",
  "end_date": "2026-11-11",
  "main_title": "双十一分期免息，最高省500元！",
  "sub_title": "指定商户单笔满3000元享3期免息",
  "visual_description": "红金渐变背景...",
  "rules_summary": ["规则1", "规则2", ...],
  "target_segment": "22-45岁金卡及以上持卡人",
  "cta_text": "立即查看我的分期额度"
}
```

---

### 频控规则 (frequency_rules.json) 🆕

供项目二 Strategy Agent 做触达决策前查询，含4层规则：

```json
{
  "default_rules": {
    "global_max_per_day": 2,
    "global_max_per_week": 5,
    "global_max_per_month": 12,
    "global_cooldown_hours": 4
  },
  "per_channel_rules": { "..." },
  "per_customer_type_rules": {
    "high_value":    { "override": "降低频控，允许精准高频" },
    "dormant":       { "override": "大幅降频，优先低打扰渠道" },
    "complaint_risk":{ "override": "暂停主动营销，禁止短信和外呼" },
    "new_customer":  { "override": "适当增加引导触达" }
  },
  "negative_feedback_escalation": {
    "连续3次推送未点击": "cooldown_72h",
    "短信回复TD退订":    "永久禁止短信营销",
    "客户投诉营销骚扰":   "全局禁止主动营销"
  }
}
```

### 合规规则 (compliance_rules.json) 🆕

供项目二/三在策略生成和内容生成时做合规校验：

| 类别 | 规则数 | 关键规则 |
|------|:---:|------|
| 产品营销规范 | 4条 | 禁止承诺收益、必须标注APR、必须含风险提示、禁止虚假紧迫感 |
| 数据隐私授权 | 3条 | 未授权不可触达、未授权不可个性化推荐、敏感信息脱敏 |
| 内容规范 | 4条 | 短信必须含退订、禁止夜间推送(21:00-08:00)、外呼前查免打扰、AB测试标识 |
| 渠道专项规范 | 3条 | iOS推送≤110字符、短信≤140字符、微信公众号模板月限4次 |

---

## 四、关键业务数据分布

### 客户 (8,000人)
- **城市**: 深圳12% / 上海11% / 北京10% / 广州8% / 杭州6% / 成都5% / 南京5% / 武汉4% / 西安4% / 重庆3% / 其他32%
- **收入等级**: 高(H) 15.8% / 中(M) 47.0% / 普通(L) 37.2%
- **生命周期**: 成熟期 66.7% / 成长期 15.4% / 沉睡期 11.6% / 新户 6.3%

### 信用卡 (19,939张, 平均2.5张/人)
- **卡等级分布**:
  - 金卡: 11,227张 (56.3%)
  - 校园卡: 3,555张 (17.8%)
  - 白金卡: 2,846张 (14.3%)
  - 普卡: 1,810张 (9.1%)
  - 钻石卡: 331张 (1.7%)
  - 无限卡: 170张 (0.9%)

### 交易
- 消费78% / 还款12% / 退款4% / 取现3% / 分期3%
- 境外交易占比约5-6%
- 金额分布: 多数在¥10-5,000, 少量大额>¥10,000

### 意图 (在ASR和APP埋点中分布)
- 分期/借贷需求 ~20%
- 跨境/出行需求 ~10%
- 额度/升级需求 ~10%
- 权益/优惠需求 ~15%
- 沉睡/流失风险 ~15%
- 新户/激活引导 ~10%
- 一般咨询 ~20%

---

## 五、使用方法

### 一键生成全部数据

```bash
cd mock_data/scripts
python run_all.py
```

### 分步生成

```bash
# 1. 先生成产品/权益/活动 (无依赖, 基于招行真实体系)
python generate_products.py

# 2. 生成客户和信用卡 (依赖产品)
python generate_customers.py

# 3. 生成交易和账单 (依赖信用卡)
python generate_transactions.py

# 4. 生成CRM (依赖客户+信用卡)
python generate_crm.py

# 5. 生成APP事件 (依赖客户+信用卡)
python generate_app_events.py

# 6. 生成ASR对话 (依赖客户)
python generate_asr.py

# 7. 生成文档和海报 (独立)
python generate_docs.py

# 8. (可选) 同步非结构化数据中的产品名引用
python sync_names.py
```

### 依赖关系

```
generate_products.py         ← 无依赖, 先跑. 生成15款招行产品+90项权益+25个活动
generate_customers.py        ← 依赖 products, 根据卡等级分配真实产品ID
generate_transactions.py     ← 依赖 customers (信用卡)
generate_crm.py              ← 依赖 customers + cards
generate_app_events.py       ← 依赖 customers + cards
generate_asr.py              ← 依赖 customers
generate_docs.py             ← 无依赖, 生成20份产品文档+12份海报
```

### 修改数据量

编辑 `config.py` 中的以下变量:

```python
N_CUSTOMERS = 8000           # 客户数
N_TRANSACTIONS_TOTAL = 600000 # 交易总条数(实际≈76万)
N_APP_EVENTS_TOTAL = 500000   # APP埋点总数(实际≈37万)
N_ASR_TRANSCRIPTS = 1500      # 客服对话数(实际956)
N_PRODUCTS = 15               # 信用卡产品数（6个等级×15款）
N_BENEFITS = 75               # 权益项数(目标值，实际90项)
N_CAMPAIGNS = 25              # 营销活动数
```

### 修改随机种子 (生成不同分布的数据)

```python
RANDOM_SEED = 42  # 改为其他值
```

---

## 六、数据一致性说明

为确保多表关联查询的完整性, 所有数据基于XX银行信用卡中心真实产品体系构建, 请关注以下关键关联字段:

| 关联 | 字段 | 说明 |
|------|------|------|
| customer_basic ↔ credit_card | `cust_id` | 一人多卡 (平均2.5张) |
| credit_card ↔ transaction_log | `card_no` | 每卡对应多条交易 |
| credit_card ↔ bill_record | `card_no` | 每月一张账单 |
| customer_basic ↔ crm_customer | `cust_id` | 一对一关系 |
| customer_basic ↔ app_events | 通过 `device_id` / `open_id` (内存中映射) | 多设备 |
| customer_basic ↔ asr_transcripts | `cust_id` | 可能多条通话 |
| product_catalog ↔ credit_card | `product_id` | 15款招行真实产品 |
| customer_basic ↔ customer_consent | `cust_id` | 8,000条, 含18字段(授权+退订+投诉+风险+价值) |
| customer_basic ↔ contact_history | `cust_id` | 120,000条近90天触达记录 |
| product_catalog ↔ product_eligibility | `product_id` | 15条办理资格规则 |
| campaign_catalog ↔ campaign_performance | `campaign_id` | 25个活动ROI汇总 |
| campaign_catalog ↔ campaign_attribution | `campaign_id` | 30,092条归因明细 |
| contact_history ↔ campaign_attribution | `touch_id` | 触达→转化归因链路 |
| product_catalog ↔ product_benefit_mapping | `product_id` | 711条产品-权益关联 |
| benefit_catalog ↔ product_benefit_mapping | `benefit_id` | 90项权益 |
| campaign_catalog ↔ posters | `campaign_poster_path` | 25个活动关联12个海报 |

> ⚠️ 后续 OneID 引擎将通过 `cust_id`、`id_card`、`phone`、`card_no`、`device_id`、`open_id` 进行统一映射。

---

## 七、与XX银行真实数据对应说明

本 Mock 数据集严格基于XX银行信用卡中心公开信息构建:

| 数据层 | 真实来源参考 |
|--------|------------|
| **产品体系** | XX银行信用卡官网公告 (2025-2026年度高端信用卡礼遇)、掌上生活APP产品目录 |
| **权益体系** | 官网权益说明页、机场贵宾厅/300精选酒店/积分兑换等官方说明 |
| **营销活动** | Apple Pay返现活动(2025.7-2026.3)、周三5折饭票、9元观影等常态化活动 |
| **卡等级** | 校园卡/普卡/金卡/白金卡/钻石卡/无限卡 — XX银行六级卡等体系 |
| **商户/渠道** | 招行合作商户品牌(海底捞/西贝/星巴克/喜茶等) + 主流支付渠道分布 |
| **APP页面** | 掌上生活APP实际页面结构(账单详情/分期计算器/权益商城/积分兑换等) |

> 数据中的客户个人信息为随机生成并已脱敏, 与实际招行客户无任何关联。

---

## 八、三项目接口对接 🆕

本 Mock 数据集为三项目联调提供了完整的数据支撑，详见：

> 📄 **[接口对接规范_项目一KnowledgeAgent.md](../接口对接规范_项目一KnowledgeAgent.md)**

### 项目一对外暴露的 7 个 API

**A→B (供给端)**:

| # | 接口 | 核心数据来源 |
|:--:|------|------------|
| API-01 | `POST /api/v1/customer/insight` | customer_basic + credit_card + crm_customer + consent + app_events |
| API-02 | `POST /api/v1/customer/search` | 全部结构化表 (15个筛选维度) |
| API-03 | `POST /api/v1/knowledge/search` | product + benefit + campaign + docs + compliance_rules |
| API-04 | `GET /api/v1/channels/context` | channel_config |
| API-05 | `POST /api/v1/customer/frequency-check` | customer_consent + frequency_rules |

**C→A (回流端)**:

| # | 接口 | 说明 |
|:--:|------|------|
| API-06 | `POST /api/v1/feedback/events` | 曝光/点击/转化/投诉事件 → 更新画像 |
| API-07 | `POST /api/v1/feedback/conversation` | 对话摘要 → 更新意图向量 |

### 接口数据覆盖度

| 接口 | 数据支撑度 |
|------|:--:|
| API-01 客户全景洞察 | 🟢 完整 |
| API-02 客户搜索圈选 | 🟢 完整 |
| API-03 GraphRAG知识检索 | 🟢 完整 |
| API-04 渠道上下文查询 | 🟢 完整 |
| API-05 频控状态查询 | 🟢 完整 |
| API-06 反馈事件回传 | 🟡 接口就绪 |
| API-07 对话摘要回传 | 🟡 接口就绪 |

> 🟢 = 数据完整，可直接联调 | 🟡 = 接口已定义，待对方对接
