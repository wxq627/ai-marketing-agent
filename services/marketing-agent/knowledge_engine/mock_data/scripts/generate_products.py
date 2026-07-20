"""
产品、权益与营销活动数据生成脚本（基于XX银行信用卡中心真实产品体系）
================================================================
生成:
  - product_catalog.csv          (信用卡产品目录, 15款)
  - benefit_catalog.csv          (权益目录, 75项)
  - product_benefit_mapping.csv  (产品-权益关联)
  - campaign_catalog.csv         (营销活动目录, 25个)

产品体系基于XX银行真实信用卡产品线:
  普卡(3款) → 金卡(4款) → 白金卡(6款) → 钻石卡(1款) + 世界卡(1款)
权益类别:
  出行 / 积分 / 生活 / 消费 / 分期 / 健康 / 保险 / 新户 / 高端专属
"""

import random, os, pandas as pd
from datetime import datetime, timedelta
from typing import List, Dict, Any

from config import *

random.seed(RANDOM_SEED + 4)


# ============================================================
# 产品定义 (15款, 基于XX银行真实产品体系)
# ============================================================

PRODUCT_DEFINITIONS = [
    # ---- 普卡 (3款) ----
    {"product_id": "PROD_STANDARD_N", "product_name": "XX银行标准信用卡（普卡）",
     "card_level": "普卡", "annual_fee": 100,
     "annual_fee_waiver": "首年免年费，年度刷卡6次免次年年费",
     "target_income": "L,M",
     "key_selling_points": "申请门槛低,日常消费返现,积分永不过期,新户开卡礼,免费短信提醒"},
    {"product_id": "PROD_YOUNG_CAMPUS", "product_name": "XX银行YOUNG卡（校园版）",
     "card_level": "校园卡", "annual_fee": 0,
     "annual_fee_waiver": "在校期间终身免年费",
     "target_income": "L",
     "key_selling_points": "零额度/低额度培养信用,校园消费返现,毕业转卡权益升级,考试季专属优惠,潮流卡面设计"},
    {"product_id": "PROD_HELLOKITTY_N", "product_name": "XX银行Hello Kitty粉丝信用卡（普卡）",
     "card_level": "普卡", "annual_fee": 100,
     "annual_fee_waiver": "首年免年费，年度刷卡6次免次年年费",
     "target_income": "L,M",
     "key_selling_points": "Hello Kitty主题卡面,粉丝专属周边优惠,新户开卡礼三选一,积分永不过期,生日双倍积分"},

    # ---- 金卡 (4款) ----
    {"product_id": "PROD_STANDARD_G", "product_name": "XX银行标准信用卡（金卡）",
     "card_level": "金卡", "annual_fee": 300,
     "annual_fee_waiver": "首年免年费，年度消费满2万元或刷卡12次免次年年费",
     "target_income": "L,M",
     "key_selling_points": "额度1万-10万,全国商户优惠,生日当月双倍积分,免费短信提醒,临时额度灵活调整"},
    {"product_id": "PROD_YOUNG_G", "product_name": "XX银行YOUNG卡（青年版）",
     "card_level": "金卡", "annual_fee": 300,
     "annual_fee_waiver": "首年免年费，年度刷卡6次免次年年费",
     "target_income": "L,M",
     "key_selling_points": "30周岁以下专属,每月首笔取现免手续费,生日月双倍积分,最高额度5万,潮流IP联名卡面"},
    {"product_id": "PROD_JD_G", "product_name": "XX银行京东PLUS联名信用卡（金卡）",
     "card_level": "金卡", "annual_fee": 300,
     "annual_fee_waiver": "首年免年费，年度刷卡6次免次年年费",
     "target_income": "L,M",
     "key_selling_points": "京东购物95折起,PLUS会员专享权益,6期免息分期,专属秒杀通道,新户达标送PLUS会员"},
    {"product_id": "PROD_CTRIP_G", "product_name": "XX银行携程旅行信用卡（金卡）",
     "card_level": "金卡", "annual_fee": 300,
     "annual_fee_waiver": "首年免年费，年度消费满2万元或刷卡12次免次年年费",
     "target_income": "M",
     "key_selling_points": "携程订票立减优惠,出行保险赠送,境外消费双倍积分,酒店升级权益,旅行意外险保障"},

    # ---- 白金卡 (6款) ----
    {"product_id": "PROD_CLASSIC_W", "product_name": "XX银行经典版白金信用卡",
     "card_level": "白金卡", "annual_fee": 3600,
     "annual_fee_waiver": "年度消费满18万元享10000永久积分兑换年费",
     "target_income": "M,H",
     "key_selling_points": "6次/年机场贵宾厅,6次/年300精选酒店贵宾价,1次/年体检+1次/年口腔护理,12次/年高尔夫,航班延误险最高2000元,生日10倍积分,积分兑里程1500:2000"},
    {"product_id": "PROD_FREELIFE_W", "product_name": "XX银行自由人生白金信用卡",
     "card_level": "白金卡", "annual_fee": 800,
     "annual_fee_waiver": "首年免年费，年度消费满8万元免次年年费",
     "target_income": "M,H",
     "key_selling_points": "境外消费1%返现,2次/年机场贵宾厅,积分兑换视频会员,300精选酒店贵宾价,专属客服热线"},
    {"product_id": "PROD_UNIONPAY_W", "product_name": "XX银行银联白金信用卡",
     "card_level": "白金卡", "annual_fee": 1800,
     "annual_fee_waiver": "首年免年费，年度消费满5万元免次年年费",
     "target_income": "M,H",
     "key_selling_points": "银联白金权益(机场1元停车等),购物返现最高5%,专属客服热线,临时额度灵活调整,300精选酒店贵宾价,积分兑换文娱会员"},
    {"product_id": "PROD_GLOBAL_W", "product_name": "XX银行全币种国际白金信用卡",
     "card_level": "白金卡", "annual_fee": 2600,
     "annual_fee_waiver": "有效期内免年费",
     "target_income": "M,H",
     "key_selling_points": "境外消费免货币转换费,全球机场贵宾厅(3000积分/人次),境外紧急补卡,多币种自动结算,境外消费返现最高8%"},
    {"product_id": "PROD_REFINED_W", "product_name": "XX银行精致版白金信用卡",
     "card_level": "白金卡", "annual_fee": 800,
     "annual_fee_waiver": "首年免年费，年度消费满8万元免次年年费",
     "target_income": "M,H",
     "key_selling_points": "2次/年300精选酒店贵宾价,积分兑换文娱会员,免外汇兑换手续费,新户达标赠饮品券(星巴克/喜茶/奈雪),银联白金权益"},
    {"product_id": "PROD_CENTURION_W", "product_name": "XX银行百夫长白金卡",
     "card_level": "白金卡", "annual_fee": 3600,
     "annual_fee_waiver": "刚性年费(不可减免)",
     "target_income": "M,H",
     "key_selling_points": "60次/年机场贵宾厅含运通百夫长休息室,PP卡不限次,万豪积分1:2兑换,6次/年300精选酒店,FHR/THC高端酒店礼遇,酒店精英会籍匹配(万豪金/希尔顿金),生日10倍积分"},

    # ---- 钻石卡 (1款) ----
    {"product_id": "PROD_DIAMOND", "product_name": "XX银行银联钻石信用卡",
     "card_level": "钻石卡", "annual_fee": 3600,
     "annual_fee_waiver": "刚性年费(不可减免)",
     "target_income": "H",
     "key_selling_points": "60次/年机场贵宾厅(可带1人),12次/年接送机,6次/年300精选酒店贵宾价,4张境内儿童经济舱机票,2次儿童口腔涂氟,专属钻石管家,顶级医疗健康,旅行保险1000万"},

    # ---- 世界卡 (1款) ----
    {"product_id": "PROD_WORLD", "product_name": "XX银行万事达世界信用卡",
     "card_level": "无限卡", "annual_fee": 3600,
     "annual_fee_waiver": "刚性年费(不可减免)",
     "target_income": "H",
     "key_selling_points": "60次/年机场贵宾厅(可带1人),2次境内+2次境外机票返现各最高900元,6次/年300精选酒店,2张境外博物馆门票,积分兑里程上限5万,万事达世界卡专属权益"},
]


# ============================================================
# 权益定义 (75项, 基于XX银行真实权益体系)
# ============================================================

BENEFIT_DEFINITIONS = [
    # ---- 出行权益 (17项) ----
    ("BEN_TRV_001", "机场贵宾厅服务", "出行", "全年60次全球100余间机场贵宾厅（含北京首都、上海浦东、深圳宝安等），每次标准服务2小时，可免费携带1人（扣减1次）"),
    ("BEN_TRV_002", "接送机服务", "出行", "每年12次豪华商务车接送机服务，覆盖全国主要城市，提前24小时预约"),
    ("BEN_TRV_003", "300精选酒店贵宾价入住", "出行", "每年6次以贵宾价入住全国300余家精选高端酒店，含行政楼层升级"),
    ("BEN_TRV_004", "航班延误险", "出行", "航班延误3小时以上赔付最高2000元（经典白），延误2小时赔付最高4000元（钻石/百夫长），无需提供发票"),
    ("BEN_TRV_005", "境外租车优惠", "出行", "Hertz/AVIS等国际租车公司最高7折优惠，含免费额外驾驶员注册"),
    ("BEN_TRV_006", "高铁贵宾厅", "出行", "全国主要高铁站贵宾厅服务（800积分/次），部分车站含快速安检通道"),
    ("BEN_TRV_007", "行李延误险", "出行", "行李延误6小时以上赔付最高3000元，含必要生活用品采购报销"),
    ("BEN_TRV_008", "旅行意外险", "出行", "保额500万元旅行意外险（钻石卡1000万），含高风险运动保障及医疗运送"),
    ("BEN_TRV_009", "境外紧急救援", "出行", "24小时全球紧急救援服务，含医疗转运、法律援助和紧急翻译"),
    ("BEN_TRV_010", "境外取现免手续费", "出行", "境外ATM取现每月前3笔免手续费，适用于银联/VISA/MasterCard标识ATM"),
    ("BEN_TRV_011", "货币兑换优惠", "出行", "XX银行合作网点外币现钞兑换享汇率优惠，免兑换手续费"),
    ("BEN_TRV_012", "五星酒店自助餐买一赠一", "出行", "指定五星级酒店自助餐厅两人同行一人免单，每卡每年限享4次"),
    ("BEN_TRV_013", "全球WiFi租赁优惠", "出行", "境外WiFi租赁首日1元起，覆盖全球100+国家和地区，每卡每年限享2次"),
    ("BEN_TRV_014", "境外博物馆门票", "出行", "万事达世界卡专属——每年2张境外知名博物馆免费门票"),
    ("BEN_TRV_015", "机票返现", "出行", "万事达世界卡专属——境内2次（最高900元/次）+境外2次（最高900元/次）机票返现"),
    ("BEN_TRV_016", "儿童经济舱机票", "出行", "钻石卡专属——每年4张境内儿童经济舱机票（亲子出行定位）"),
    ("BEN_TRV_017", "PP卡PriorityPass", "出行", "百夫长白金卡无限次Priority Pass全球机场贵宾厅，含运通百夫长休息室"),

    # ---- 积分权益 (8项) ----
    ("BEN_PTS_001", "生日10倍积分", "积分", "生日当天消费享10倍积分（经典白/百夫长白），封顶赠送10000奖励积分"),
    ("BEN_PTS_002", "积分兑里程", "积分", "航空里程兑换比例1500积分=2000里程（国航/东航），年上限5万里程"),
    ("BEN_PTS_003", "积分兑年费", "积分", "经典版白金卡可用10000永久积分兑换3600元年费（芯片版需年消费满18万）"),
    ("BEN_PTS_004", "积分兑酒店积分", "积分", "百夫长白金卡积分可兑换万豪积分(3000:6000)和希尔顿积分(1000:2000)"),
    ("BEN_PTS_005", "线上支付积分加速", "积分", "支付宝/微信支付消费享1.5倍积分，加速积分累积速度"),
    ("BEN_PTS_006", "积分兑换文娱会员", "积分", "积分可兑换腾讯视频/爱奇艺/优酷/B站等视频会员月卡/季卡/年卡"),
    ("BEN_PTS_007", "积分兑换膨胀", "积分", "特定品类积分兑换享1.2倍价值膨胀，如星巴克饮品券、必胜客代金券等"),
    ("BEN_PTS_008", "积分抵现", "积分", "手机银行APP内商城/饭票等场景可用积分直接抵扣现金，比例约500:1"),

    # ---- 生活权益 (14项) ----
    ("BEN_LIF_001", "周三5折饭票", "生活", "每周三合作大牌餐饮（海底捞/西贝/星巴克/喜茶等）5折代金券限量抢购"),
    ("BEN_LIF_002", "9元观影", "生活", "指定影院周五/周末电影票9元起，含IMAX/杜比厅，每月限享2次"),
    ("BEN_LIF_003", "咖啡权益", "生活", "星巴克每周五买一赠一，瑞幸咖啡每日首杯半价"),
    ("BEN_LIF_004", "视频会员月月领", "生活", "腾讯视频/优酷/爱奇艺VIP月卡三选一，有效期6个月，每月领取1次"),
    ("BEN_LIF_005", "音乐会员优惠", "生活", "QQ音乐/网易云音乐/Spotify年度会员7折，积分可全额兑换"),
    ("BEN_LIF_006", "健身会员优惠", "生活", "超级猩猩/乐刻运动/Keep线下店会员8折，新用户首月半价"),
    ("BEN_LIF_007", "鲜花订阅优惠", "生活", "花点时间/花加/野兽派等鲜花订阅月度首单半价，每周一限时"),
    ("BEN_LIF_008", "图书知识付费优惠", "生活", "得到/樊登读书/知乎盐选年度会员7折，部分免费试听"),
    ("BEN_LIF_009", "亲子教育折扣", "生活", "英孚教育/新东方/少年得到等教育机构专属8折，部分课程积分兑换"),
    ("BEN_LIF_010", "宠物服务优惠", "生活", "合作宠物医院诊疗8折，宠物用品商城9折，新瑞鹏/瑞鹏等连锁适用"),
    ("BEN_LIF_011", "家政服务优惠", "生活", "自如保洁/好慷在家/天鹅到家等家政服务首单立减50元"),
    ("BEN_LIF_012", "超市购物返现", "生活", "永辉/沃尔玛/盒马鲜生每周五返现5%，月上限100元"),
    ("BEN_LIF_013", "外卖优惠", "生活", "美团外卖/饿了么每日首单立减最高15元，每周三额外红包"),
    ("BEN_LIF_014", "网红茶饮满减", "生活", "喜茶/奈雪的茶/霸王茶姬满30减10，每日限享一次"),

    # ---- 消费权益 (12项) ----
    ("BEN_SPD_001", "Apple Pay笔笔1%返现", "消费", "通过Apple Pay使用XX银行信用卡消费享1%返现，境内单笔最高10元/月上限100元，境外单笔最高50元/月上限200元"),
    ("BEN_SPD_002", "境外消费返现", "消费", "境外线下消费返现5%，月上限500元人民币，需在手机银行APP报名参与"),
    ("BEN_SPD_003", "指定电商返现", "消费", "天猫/京东/拼多多大促期间最高返现10%，日常消费随机立减最高99元"),
    ("BEN_SPD_004", "云闪付支付优惠", "消费", "云闪付APP支付满50减10，每日限享一次，名额有限先到先得"),
    ("BEN_SPD_005", "大牌购物折扣", "消费", "SKP/万象城/太古里等高端商场会员资格匹配及专属折扣"),
    ("BEN_SPD_006", "免税店优惠", "消费", "DFS/Sunrise免税店额外95折+双倍积分，合作免税店满额赠礼"),
    ("BEN_SPD_007", "海淘返利", "消费", "Amazon/Shopbop/Farfetch等海淘网站返利最高8%，叠加免货币转换费"),
    ("BEN_SPD_008", "数码产品免息分期", "消费", "Apple/华为官方商城12期免息分期，部分新品首发24期免息"),
    ("BEN_SPD_009", "家电以旧换新补贴", "消费", "苏宁/京东家电以旧换新额外补贴，刷XX银行信用卡再享分期免息"),
    ("BEN_SPD_010", "加油优惠", "消费", "中石油/中石化/壳牌加油站周五满200减30，每月限享2次"),
    ("BEN_SPD_011", "充电桩优惠", "消费", "特来电/星星充电等主要充电桩服务费8折，每周五额外立减"),
    ("BEN_SPD_012", "消费达标礼", "消费", "月消费满5000元赠送星巴克中杯券1张，满10000元赠2张"),

    # ---- 分期权益 (10项) ----
    ("BEN_INS_001", "3期免息分期", "分期", "指定商户单笔满500元享3期免息分期，覆盖餐饮/购物/出行等"),
    ("BEN_INS_002", "6期免息分期", "分期", "指定商户单笔满1000元享6期免息分期，大促期间适用商户扩增"),
    ("BEN_INS_003", "12期免息分期", "分期", "指定大额消费（家电/数码/教育/医疗）享12期免息分期"),
    ("BEN_INS_004", "24期教育分期", "分期", "指定教育机构（新东方/好未来/中公教育等）专享24期免息分期"),
    ("BEN_INS_005", "账单分期优惠费率", "分期", "首笔账单分期享手续费5折优惠，次笔起享8折优惠"),
    ("BEN_INS_006", "现金分期优惠", "分期", "现金分期利率最低0.35%/月，优质客户享专属利率优惠"),
    ("BEN_INS_007", "专项分期额度", "分期", "额外授予专项分期额度（最高为信用额度的2倍），独立于消费额度"),
    ("BEN_INS_008", "大额消费自动分期提醒", "分期", "单笔消费超5000元自动触发分期提醒并享优惠费率"),
    ("BEN_INS_009", "医疗分期", "分期", "牙科/眼科/医美等指定医疗机构12期免息，合作机构覆盖全国"),
    ("BEN_INS_010", "旅行分期", "分期", "携程/飞猪/同程旅行单笔满2000元享6期免息分期"),

    # ---- 健康权益 (5项) ----
    ("BEN_HTH_001", "健康体检", "健康", "每年1次高端体检套餐（含肿瘤标志物筛查），合作机构为美年大健康/爱康国宾，7000积分可兑换"),
    ("BEN_HTH_002", "口腔护理", "健康", "每年1次洁牙+口腔检查服务（3000积分可兑换），合作机构为瑞尔齿科/通策医疗"),
    ("BEN_HTH_003", "儿童口腔涂氟", "健康", "钻石卡专属——每年2次儿童口腔涂氟服务"),
    ("BEN_HTH_004", "高尔夫练习场", "健康", "每年12次全国合作高尔夫练习场畅打，含练习球和球杆租赁"),
    ("BEN_HTH_005", "齿科保险特惠", "健康", "瑞尔齿科/泰康拜博等齿科机构种植/正畸项目8折，含免费检查方案"),

    # ---- 保险权益 (7项) ----
    ("BEN_INSR_001", "航班延误险（高额版）", "保险", "延误2小时赔付1000元，4小时赔付2000元（钻石/百夫长升级为4000元），无需发票"),
    ("BEN_INSR_002", "购物保障险", "保险", "刷卡购物30天内商品因意外损坏或被盗，最高赔付2万元/件"),
    ("BEN_INSR_003", "盗刷险", "保险", "信用卡被盗刷72小时内全额赔付，含线上/线下所有交易渠道"),
    ("BEN_INSR_004", "租车保险", "保险", "境外租车含CDW碰撞损失险和LDW盗抢险，无需额外购买"),
    ("BEN_INSR_005", "高额旅行意外险", "保险", "保额500万-1000万旅行意外险，含高风险运动保障和医疗运送/送返"),
    ("BEN_INSR_006", "法律援助服务", "保险", "免费法律咨询及律师推荐服务，含合同审核和纠纷调解"),
    ("BEN_INSR_007", "高尔夫一杆进洞险", "保险", "高尔夫一杆进洞庆祝费用赔付，限额2万元/次"),

    # ---- 新户权益 (10项) ----
    ("BEN_NEW_001", "新户开卡礼三选一", "新户", "新户达标（核发后次2个自然月内任意消费满36元）可选：1000积分/笔笔返现资格/实物礼品(拉杆箱/保温杯/煎炒锅等)"),
    ("BEN_NEW_002", "推荐办卡礼", "新户", "邀请好友办卡达标各得50元还款金，累计推荐满5人额外赠扫地机器人/海量积分"),
    ("BEN_NEW_003", "首刷礼", "新户", "首笔消费满99元赠XX银行定制礼品（经典保温杯/定制帆布袋/手机支架三选一）"),
    ("BEN_NEW_004", "绑卡礼", "新户", "首次绑定支付宝/微信支付/云闪付各赠10元红包，三端绑齐额外赠20元"),
    ("BEN_NEW_005", "新户首年笔笔返现", "新户", "新户首年每月享100次交易返现资格，单笔消费最高返99元"),
    ("BEN_NEW_006", "额度成长计划", "新户", "开卡后6个月按时全额还款可获得额度自动提升，最高翻倍"),
    ("BEN_NEW_007", "新户见面礼", "新户", "首月登录手机银行APP领腾讯视频VIP月卡或星巴克中杯券"),
    ("BEN_NEW_008", "新户专享商城", "新户", "新户专享积分商城商品5折兑换，含数码/美妆/家居等品类"),
    ("BEN_NEW_009", "消费进阶礼", "新户", "首月消费满3000元额外赠5000积分，满8000元赠10000积分"),
    ("BEN_NEW_010", "校园毕业转卡礼", "新户", "校园卡用户毕业转标准卡享额度直升（+5000元起），赠50元刷卡金"),

    # ---- 高端专属权益 (7项) ----
    ("BEN_PRM_001", "FHR/THC高端酒店礼遇", "高端专属", "百夫长白金/钻石卡专属——Fine Hotels & Resorts及The Hotel Collection预订享免费双早、房型升级、延迟退房、100美元消费额度"),
    ("BEN_PRM_002", "酒店精英会籍匹配", "高端专属", "百夫长白金卡自动匹配万豪旅享家金卡、希尔顿荣誉客会金卡、丽笙丽赏会高级会员"),
    ("BEN_PRM_003", "专属钻石管家", "高端专属", "钻石卡专属一对一管家服务，含旅行规划/餐厅预订/演唱会票务/紧急协助"),
    ("BEN_PRM_004", "私人定制旅行", "高端专属", "钻石/百夫长卡专属——根据客户偏好定制专属旅行方案，含精品小团和私人导游"),
    ("BEN_PRM_005", "无限次豪华车接送", "高端专属", "无限卡/钻石卡专属——全年无限次豪华商务车接送机/站服务"),
    ("BEN_PRM_006", "专属艺术品鉴赏", "高端专属", "高端卡客户专享艺术品鉴赏会/拍卖会预展邀请及私人导览服务"),
    ("BEN_PRM_007", "全球奢华酒店会员匹配", "高端专属", "无限卡专属——四季/半岛/瑞吉/丽思卡尔顿等奢华酒店会员资格匹配"),
]


# ============================================================
# 营销活动定义 (25个, 基于XX银行真实营销活动)
# ============================================================

def build_campaigns() -> List[Dict[str, Any]]:
    """构建营销活动列表（基于XX银行真实活动体系）。"""
    ref = REFERENCE_DATE
    campaigns = [
        # -- 重磅活动 --
        {"campaign_id": "CAMP_2026_APPLEPAY", "name": "Apple Pay笔笔1%返现",
         "start": ref.replace(year=2025, month=7, day=1), "end": ref.replace(year=2026, month=3, day=31),
         "target": {"age_range":[20,55],"card_level":["普卡","金卡","白金卡","钻石卡"]},
         "rules": {"境内返现":0.01,"境内单笔上限":10,"境内月上限":100,"境外返现":0.01,"境外单笔上限":50,"境外月上限":200,"报名渠道":"手机银行APP"},
         "budget": 8000000, "expected_reach": 500000,
         "poster": "applepay_cashback.png"},
        {"campaign_id": "CAMP_2026_DOUBLE11", "name": "双十一分期免息大促",
         "start": ref.replace(month=11, day=1), "end": ref.replace(month=11, day=11),
         "target": {"age_range":[22,45],"card_level":["金卡","白金卡","钻石卡"],"income_level":["M","H"]},
         "rules": {"分期期数":[3,6,12],"免息期数":3,"适用商户":["天猫","京东","拼多多"],"最低消费":3000},
         "budget": 500000, "expected_reach": 200000,
         "poster": "nov11_promo.png"},
        {"campaign_id": "CAMP_2026_SPRINGFEST", "name": "春节境外消费返现",
         "start": ref.replace(month=1, day=15), "end": ref.replace(month=2, day=15),
         "target": {"age_range":[25,55],"card_level":["白金卡","钻石卡","无限卡"],"income_level":["H"]},
         "rules": {"境外消费返现":0.08,"封顶":800,"适用地区":["港澳","日韩","东南亚","欧美"]},
         "budget": 800000, "expected_reach": 50000,
         "poster": "spring_festival_promo.png"},
        {"campaign_id": "CAMP_2026_NEWUSER", "name": "新户开卡三重礼",
         "start": ref.replace(year=2025, month=7, day=1), "end": ref.replace(year=2026, month=12, day=31),
         "target": {"lifecycle":["新户"]},
         "rules": {"达标条件":"核发后次2个自然月内任意消费满36元","礼遇":["1000积分","首年笔笔返现资格","实物礼品(拉杆箱/保温杯/煎炒锅)"]},
         "budget": 1500000, "expected_reach": 150000,
         "poster": "new_user_welcome.png"},
        {"campaign_id": "CAMP_2026_DORMANT", "name": "沉睡客户唤醒计划",
         "start": ref - timedelta(days=90), "end": ref + timedelta(days=90),
         "target": {"lifecycle":["沉睡期"],"churn_risk_min":50},
         "rules": {"唤醒红包":50,"条件":"30天内任意消费1笔","额外奖励":"消费满500再赠5000积分"},
         "budget": 600000, "expected_reach": 80000,
         "poster": "dormant_wakeup.png"},
        {"campaign_id": "CAMP_2026_SUMMER", "name": "暑期出行季",
         "start": ref.replace(month=7, day=1), "end": ref.replace(month=8, day=31),
         "target": {"age_range":[22,45],"card_level":["金卡","白金卡","钻石卡"]},
         "rules": {"机票":"满1000减100","酒店":"连住3晚8折","境外WiFi":"首日1元"},
         "budget": 400000, "expected_reach": 150000,
         "poster": "summer_travel.png"},
        {"campaign_id": "CAMP_2026_UPGRADE", "name": "金卡升级白金卡邀请",
         "start": ref - timedelta(days=60), "end": ref + timedelta(days=120),
         "target": {"card_level":["金卡"],"income_level":["M","H"],"age_range":[28,50]},
         "rules": {"升级礼":"首年年费5折","额外权益":"赠送机场贵宾厅2次"},
         "budget": 200000, "expected_reach": 30000,
         "poster": "upgrade_invite.png"},
        {"campaign_id": "CAMP_2026_618", "name": "618购物节返现",
         "start": ref.replace(month=6, day=1), "end": ref.replace(month=6, day=18),
         "target": {"age_range":[20,40],"card_level":["普卡","金卡","白金卡"]},
         "rules": {"天猫/京东":"满500返50","分期":"6期免息","名额":"先到先得"},
         "budget": 300000, "expected_reach": 100000,
         "poster": "618_shopping.png"},
        {"campaign_id": "CAMP_2026_CAMPUS", "name": "校园卡毕业季",
         "start": ref.replace(month=6, day=1), "end": ref.replace(month=7, day=31),
         "target": {"card_level":["校园卡"],"age_range":[21,28]},
         "rules": {"毕业转卡":"升级为标准金卡/YOUNG卡","额外额度":5000,"转卡礼":"50元刷卡金+5000积分"},
         "budget": 100000, "expected_reach": 20000,
         "poster": "campus_graduation.png"},
        {"campaign_id": "CAMP_2026_BIRTHDAY", "name": "生日月专属福利",
         "start": ref.replace(year=2025, month=7, day=1), "end": ref.replace(year=2027, month=6, day=30),
         "target": {"all": True},
         "rules": {"双倍积分":"生日当月(标准卡)","10倍积分":"生日当天(白金卡)","星巴克":"生日当天免费中杯券"},
         "budget": 2000000, "expected_reach": 500000,
         "poster": "birthday_benefit.png"},
        {"campaign_id": "CAMP_2026_CROSSBORDER", "name": "跨境消费达人",
         "start": ref - timedelta(days=30), "end": ref + timedelta(days=90),
         "target": {"has_cross_border": True},
         "rules": {"阶梯返现":"满5000返200,满20000返1000","额外":"免货币转换费"},
         "budget": 350000, "expected_reach": 25000,
         "poster": "crossborder_campaign.png"},
        {"campaign_id": "CAMP_2026_WEDDING5", "name": "周三5折饭票",
         "start": ref.replace(year=2025, month=7, day=1), "end": ref.replace(year=2027, month=6, day=30),
         "target": {"all": True},
         "rules": {"活动时间":"每周三","内容":"合作餐饮品牌5折代金券限量抢购","品牌":["海底捞","西贝","星巴克","喜茶","太二酸菜鱼"]},
         "budget": 5000000, "expected_reach": 800000,
         "poster": "wed_food.png"},
        {"campaign_id": "CAMP_2026_MOVIE9", "name": "9元观影",
         "start": ref.replace(year=2025, month=7, day=1), "end": ref.replace(year=2027, month=6, day=30),
         "target": {"all": True},
         "rules": {"活动时间":"每周五/周末","票价":9,"限制":"每月限享2次","覆盖":"全国合作影院含IMAX/杜比厅"},
         "budget": 3000000, "expected_reach": 600000,
         "poster": "movie9.png"},
        {"campaign_id": "CAMP_2026_REFERRAL", "name": "推荐办卡有礼",
         "start": ref.replace(month=4, day=1), "end": ref.replace(month=6, day=30),
         "target": {"all": True},
         "rules": {"推荐1-2人":"空气炸锅/千元拉杆箱/露营推车","推荐3-4人":"高速吹风机/锅具套装","推荐5人以上":"扫地机器人/海量积分","额外":"每多推荐1人再得50元还款金(封顶500元)"},
         "budget": 800000, "expected_reach": 100000,
         "poster": "referral.png"},
        {"campaign_id": "CAMP_2026_AI_TOKEN", "name": "AI算力权益新户礼",
         "start": ref.replace(year=2025, month=12, day=1), "end": ref.replace(year=2026, month=12, day=31),
         "target": {"education":["大专","本科","硕士","博士"],"age_range":[20,45]},
         "rules": {"方案一":"1个月MiniMax Token Plan Max(18亿Token/月)","方案二":"2个月MiniMax Token Plan Plus(6亿Token/月)","方案三":"1个月MaxClaw基础版+1个月Token Plan Plus","达标条件":"核发后任意消费满36元"},
         "budget": 500000, "expected_reach": 50000,
         "poster": "ai_token.png"},
        {"campaign_id": "CAMP_2026_POINTS_BOOST", "name": "积分膨胀季",
         "start": ref.replace(month=9, day=1), "end": ref.replace(month=11, day=30),
         "target": {"all": True},
         "rules": {"积分加速":"指定品类1.5倍积分","兑换膨胀":"积分商城1.2倍价值兑换","生日月叠加":"生日月额外1倍"},
         "budget": 300000, "expected_reach": 200000,
         "poster": "points_boost.png"},
        {"campaign_id": "CAMP_2026_GREEN", "name": "绿色消费计划",
         "start": ref.replace(month=3, day=1), "end": ref.replace(month=8, day=31),
         "target": {"all": True},
         "rules": {"新能源充电":"充电桩消费双倍积分","公交地铁":"云闪付乘车码5折(月上限20元)","共享单车":"哈啰/美团单车月卡8折"},
         "budget": 200000, "expected_reach": 100000,
         "poster": "green_consumer.png"},
        {"campaign_id": "CAMP_2026_WOMEN", "name": "女性消费节",
         "start": ref.replace(month=3, day=1), "end": ref.replace(month=3, day=31),
         "target": {"gender":["F"],"age_range":[20,45]},
         "rules": {"美妆护肤":"丝芙兰/屈臣氏满300减50","服饰":"ZARA/优衣库满200减30","鲜花":"花点时间/花加5折起"},
         "budget": 150000, "expected_reach": 80000,
         "poster": "women_day.png"},
        {"campaign_id": "CAMP_2026_NYE", "name": "年终回馈盛典",
         "start": ref.replace(month=12, day=1), "end": ref.replace(month=12, day=31),
         "target": {"all": True},
         "rules": {"年度账单":"查看年度账单抽888积分","积分兑换":"年底积分不清零提醒+限时兑换","跨年优惠":"12月31日指定商户双倍积分"},
         "budget": 500000, "expected_reach": 400000,
         "poster": "year_end.png"},
        {"campaign_id": "CAMP_2026_SPRING_TRAVEL", "name": "春季出行节",
         "start": ref.replace(month=3, day=15), "end": ref.replace(month=5, day=15),
         "target": {"age_range":[22,50],"card_level":["金卡","白金卡","钻石卡"]},
         "rules": {"火车票":"12306购票满200减20","酒店":"清明/五一期间精选酒店85折","景区":"合作景区门票8折"},
         "budget": 250000, "expected_reach": 120000,
         "poster": "spring_travel.png"},
        {"campaign_id": "CAMP_2026_BACK_SCHOOL", "name": "开学季特惠",
         "start": ref.replace(month=8, day=15), "end": ref.replace(month=9, day=30),
         "target": {"age_range":[18,28],"card_level":["校园卡","普卡","金卡"]},
         "rules": {"数码":"Apple/华为教育优惠+12期免息","文具书籍":"当当/京东图书满100减30","餐饮":"校园周边商户8折"},
         "budget": 150000, "expected_reach": 60000,
         "poster": "back_school.png"},
        {"campaign_id": "CAMP_2026_NATIONAL", "name": "国庆黄金周出行保障",
         "start": ref.replace(month=9, day=25), "end": ref.replace(month=10, day=10),
         "target": {"age_range":[22,55],"card_level":["金卡","白金卡","钻石卡","无限卡"]},
         "rules": {"机票":"国际航线满3000减300","酒店":"连住5晚8折+延迟退房","旅行险":"活动期间自动升级旅行险保额至1.5倍"},
         "budget": 600000, "expected_reach": 180000,
         "poster": "national_day.png"},
        {"campaign_id": "CAMP_2026_CLOUD_FLASH", "name": "云闪付专属优惠",
         "start": ref.replace(month=7, day=1), "end": ref.replace(month=9, day=30),
         "target": {"all": True},
         "rules": {"每日":"云闪付APP支付满50减10(日限1次)","周末":"云闪付乘车码5折(月上限20元)","新户":"首次绑定云闪付赠15元红包"},
         "budget": 200000, "expected_reach": 300000,
         "poster": "cloud_flash.png"},
        {"campaign_id": "CAMP_2026_FAMILY", "name": "亲子家庭日",
         "start": ref.replace(month=5, day=15), "end": ref.replace(month=8, day=15),
         "target": {"age_range":[28,45],"card_level":["金卡","白金卡","钻石卡"]},
         "rules": {"亲子餐厅":"合作亲子餐厅8折","游乐园":"迪士尼/环球影城/欢乐谷门票9折","教育":"少年得到/火花思维首单7折"},
         "budget": 200000, "expected_reach": 80000,
         "poster": "family_day.png"},
        {"campaign_id": "CAMP_2026_SPORTS", "name": "运动健康月",
         "start": ref.replace(month=10, day=1), "end": ref.replace(month=11, day=30),
         "target": {"all": True},
         "rules": {"健身":"超级猩猩/乐刻首单半价","运动装备":"耐克/阿迪/李宁满500减80","户外":"探路者/迪卡侬满300减50","马拉松":"合作马拉松赛事报名费8折"},
         "budget": 180000, "expected_reach": 90000,
         "poster": "sports_month.png"},
    ]

    return campaigns


# ============================================================
# 产品-权益关联生成 (基于真实XX银行产品-权益对应关系)
# ============================================================

def build_product_benefit_mapping() -> List[Dict[str, str]]:
    """
    生成产品→权益关联表。
    基于XX银行各卡种真实权益配置，层级越高权益越多越丰富。
    """
    mapping = []

    # 定义每个产品关联的权益类别及覆盖率
    # 数值表示该类别下权益被选中的概率
    product_benefit_rules = {
        # 普卡：基础消费+生活+新户权益
        "PROD_STANDARD_N":    {"出行":0.05,"积分":0.25,"生活":0.35,"消费":0.30,"分期":0.30,"健康":0.0,"保险":0.05,"新户":0.50,"高端专属":0.0},
        "PROD_YOUNG_CAMPUS":   {"出行":0.0,"积分":0.15,"生活":0.35,"消费":0.20,"分期":0.20,"健康":0.0,"保险":0.05,"新户":0.60,"高端专属":0.0},
        "PROD_HELLOKITTY_N":   {"出行":0.05,"积分":0.25,"生活":0.40,"消费":0.25,"分期":0.25,"健康":0.0,"保险":0.05,"新户":0.50,"高端专属":0.0},
        # 金卡：基础出行+更全生活消费+分期+保险
        "PROD_STANDARD_G":    {"出行":0.25,"积分":0.35,"生活":0.65,"消费":0.55,"分期":0.60,"健康":0.0,"保险":0.25,"新户":0.45,"高端专属":0.0},
        "PROD_YOUNG_G":       {"出行":0.20,"积分":0.35,"生活":0.65,"消费":0.50,"分期":0.55,"健康":0.0,"保险":0.15,"新户":0.55,"高端专属":0.0},
        "PROD_JD_G":          {"出行":0.15,"积分":0.35,"生活":0.55,"消费":0.75,"分期":0.65,"健康":0.0,"保险":0.15,"新户":0.45,"高端专属":0.0},
        "PROD_CTRIP_G":       {"出行":0.55,"积分":0.30,"生活":0.50,"消费":0.50,"分期":0.40,"健康":0.0,"保险":0.45,"新户":0.40,"高端专属":0.0},
        # 白金卡：全面覆盖
        "PROD_CLASSIC_W":     {"出行":0.88,"积分":0.88,"生活":0.88,"消费":0.75,"分期":0.75,"健康":0.60,"保险":0.75,"新户":0.10,"高端专属":0.0},
        "PROD_FREELIFE_W":    {"出行":0.55,"积分":0.50,"生活":0.80,"消费":0.65,"分期":0.60,"健康":0.20,"保险":0.40,"新户":0.30,"高端专属":0.0},
        "PROD_UNIONPAY_W":    {"出行":0.65,"积分":0.60,"生活":0.85,"消费":0.80,"分期":0.70,"健康":0.20,"保险":0.50,"新户":0.10,"高端专属":0.0},
        "PROD_GLOBAL_W":      {"出行":0.88,"积分":0.50,"生活":0.75,"消费":0.80,"分期":0.65,"健康":0.20,"保险":0.70,"新户":0.10,"高端专属":0.0},
        "PROD_REFINED_W":     {"出行":0.45,"积分":0.50,"生活":0.80,"消费":0.60,"分期":0.55,"健康":0.20,"保险":0.30,"新户":0.30,"高端专属":0.0},
        "PROD_CENTURION_W":   {"出行":1.0,"积分":0.88,"生活":0.88,"消费":0.80,"分期":0.75,"健康":0.80,"保险":0.88,"新户":0.05,"高端专属":0.55},
        # 钻石/世界卡：全部顶级
        "PROD_DIAMOND":       {"出行":1.0,"积分":0.75,"生活":0.95,"消费":0.90,"分期":0.80,"健康":0.80,"保险":0.95,"新户":0.0,"高端专属":0.71},
        "PROD_WORLD":          {"出行":1.0,"积分":0.75,"生活":0.95,"消费":0.90,"分期":0.80,"健康":0.60,"保险":0.88,"新户":0.0,"高端专属":0.55},
    }

    for prod_id, cat_probs in product_benefit_rules.items():
        for ben in BENEFIT_DEFINITIONS:
            ben_id, ben_name, ben_cat, ben_desc = ben
            prob = cat_probs.get(ben_cat, 0.2)
            if random.random() < prob:
                mapping.append({"product_id": prod_id, "benefit_id": ben_id})

    return mapping


# ============================================================
# 主入口
# ============================================================

def generate_all_products():
    print("=" * 60)
    print("生成产品、权益 & 营销活动数据 (基于XX银行真实体系)")
    print("=" * 60)

    # 产品目录
    df_prod = pd.DataFrame(PRODUCT_DEFINITIONS)
    prod_path = os.path.join(STRUCTURED_DIR, "product_catalog.csv")
    df_prod.to_csv(prod_path, index=False, encoding="utf-8-sig")
    print(f"[OK] product_catalog.csv : {len(df_prod)} 款产品")
    for _, row in df_prod.iterrows():
        print(f"   {row['product_id']:20s} {row['card_level']:4s} {row['product_name']}")

    # 权益目录
    df_ben = pd.DataFrame(
        [{"benefit_id": b[0], "benefit_name": b[1], "benefit_category": b[2], "benefit_desc": b[3]}
         for b in BENEFIT_DEFINITIONS]
    )
    ben_path = os.path.join(STRUCTURED_DIR, "benefit_catalog.csv")
    df_ben.to_csv(ben_path, index=False, encoding="utf-8-sig")
    print(f"\n[OK] benefit_catalog.csv : {len(df_ben)} 项权益")
    cats = df_ben["benefit_category"].value_counts()
    for c, n in cats.items():
        print(f"   {c}: {n}项")

    # 产品-权益关联
    mapping = build_product_benefit_mapping()
    df_map = pd.DataFrame(mapping)
    map_path = os.path.join(STRUCTURED_DIR, "product_benefit_mapping.csv")
    df_map.to_csv(map_path, index=False, encoding="utf-8-sig")
    print(f"\n[OK] product_benefit_mapping.csv : {len(df_map)} 条关联")

    # 营销活动
    camps = build_campaigns()
    camp_rows = []
    for c in camps:
        camp_rows.append({
            "campaign_id": c["campaign_id"],
            "campaign_name": c["name"],
            "start_date": c["start"].strftime("%Y-%m-%d"),
            "end_date": c["end"].strftime("%Y-%m-%d"),
            "target_segment": str(c["target"]),
            "rules": str(c["rules"]),
            "budget": c["budget"],
            "expected_reach": c["expected_reach"],
            "campaign_poster_path": c.get("poster", ""),
        })
    df_camp = pd.DataFrame(camp_rows)
    camp_path = os.path.join(STRUCTURED_DIR, "campaign_catalog.csv")
    df_camp.to_csv(camp_path, index=False, encoding="utf-8-sig")
    print(f"\n[OK] campaign_catalog.csv : {len(df_camp)} 个活动")

    return df_prod, df_ben, df_map, df_camp


if __name__ == "__main__":
    generate_all_products()
