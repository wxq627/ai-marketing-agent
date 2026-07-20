"""
项目一：企业知识引擎与记忆中心 — Mock 数据生成配置文件
========================================================
定义所有全局参数、常量、概率分布和映射关系。
金融领域数据生成需遵循真实业务逻辑。
"""

import os, sys, io
from datetime import datetime

# ---- Windows 控制台 UTF-8 兼容 ----
if hasattr(sys.stdout, 'buffer'):
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')
if hasattr(sys.stderr, 'buffer'):
    sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding='utf-8')
# 同时设置环境变量以影响子进程
os.environ.setdefault('PYTHONIOENCODING', 'utf-8')

# ============================================================
# 路径配置
# ============================================================
BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
STRUCTURED_DIR = os.path.join(BASE_DIR, "structured")
UNSTRUCTURED_DIR = os.path.join(BASE_DIR, "unstructured")
ASR_DIR = os.path.join(UNSTRUCTURED_DIR, "asr_transcripts")
PRODUCT_DOCS_DIR = os.path.join(UNSTRUCTURED_DIR, "product_docs")
POSTERS_DIR = os.path.join(UNSTRUCTURED_DIR, "posters")

# 确保目录存在
for d in [STRUCTURED_DIR, ASR_DIR, PRODUCT_DOCS_DIR, POSTERS_DIR]:
    os.makedirs(d, exist_ok=True)

# ============================================================
# 数据规模参数
# ============================================================
N_CUSTOMERS = 8000          # 客户总数
N_CARDS_MIN = 1             # 每人最少持卡数
N_CARDS_MAX = 4             # 每人最多持卡数
N_TRANSACTIONS_TOTAL = 600000  # 交易总条数（12个月）
N_APP_EVENTS_TOTAL = 500000    # APP埋点总条数
N_ASR_TRANSCRIPTS = 1500       # 客服对话总数
N_PRODUCT_DOCS = 25           # 产品文档数
N_POSTERS = 12                # 活动海报数
N_CAMPAIGNS = 25              # 营销活动数
N_PRODUCTS = 15               # 信用卡产品数（基于XX银行真实产品体系）
N_BENEFITS = 75               # 权益项数（基于XX银行真实权益体系）

# 时间范围
REFERENCE_DATE = datetime(2026, 7, 15)  # 参考日期（模拟"今天"）
HISTORY_MONTHS = 12                      # 历史数据月数
SIM_START_DATE = datetime(2025, 7, 1)   # 模拟数据开始日期

# 随机种子（可复现）
RANDOM_SEED = 42

# ============================================================
# 金融领域常量
# ============================================================

# --- 城市分布（结合XX银行实际业务重点城市） ---
CITY_DISTRIBUTION = {
    "深圳": 0.12, "上海": 0.11, "北京": 0.10, "广州": 0.08,
    "杭州": 0.06, "成都": 0.05, "南京": 0.05, "武汉": 0.04,
    "西安": 0.04, "重庆": 0.03, "苏州": 0.03, "天津": 0.03,
    "长沙": 0.03, "郑州": 0.03, "东莞": 0.02, "青岛": 0.02,
    "厦门": 0.02, "合肥": 0.02, "福州": 0.02, "昆明": 0.02,
    "大连": 0.02, "宁波": 0.02, "沈阳": 0.02, "济南": 0.02,
}
CITIES = list(CITY_DISTRIBUTION.keys())
CITY_WEIGHTS = list(CITY_DISTRIBUTION.values())

# --- 职业类别 ---
OCCUPATIONS = [
    "IT/互联网", "金融/保险", "制造业", "医疗/卫生", "教育/科研",
    "政府/事业单位", "商业/贸易", "房地产/建筑", "交通/物流",
    "能源/化工", "文化/传媒", "法律/咨询", "服务业", "自由职业",
    "在校学生", "退休"
]
OCCUPATION_WEIGHTS = [0.18, 0.10, 0.08, 0.06, 0.06, 0.05, 0.08,
                       0.05, 0.04, 0.03, 0.04, 0.04, 0.06, 0.05,
                       0.03, 0.05]

# --- 收入等级 ---
# 根据XX银行信用卡典型客群分布
INCOME_LEVELS = {
    "H": {"label": "高收入", "monthly_min": 30000, "monthly_max": 150000, "prob": 0.15},
    "M": {"label": "中等收入", "monthly_min": 10000, "monthly_max": 30000, "prob": 0.50},
    "L": {"label": "普通收入", "monthly_min": 3000, "monthly_max": 10000, "prob": 0.35},
}

# --- 学历 ---
EDUCATION_LEVELS = ["博士", "硕士", "本科", "大专", "高中及以下"]
EDUCATION_WEIGHTS = [0.03, 0.15, 0.50, 0.22, 0.10]

# --- 信用卡等级体系（XX银行实际卡等） ---
CARD_LEVELS = {
    "普卡":    {"credit_min": 3000,   "credit_max": 50000,  "annual_fee_range": (0, 100),    "target_income": ["L", "M"],       "prob": 0.20},
    "金卡":    {"credit_min": 10000,  "credit_max": 100000, "annual_fee_range": (100, 300),  "target_income": ["L", "M"],       "prob": 0.35},
    "白金卡":  {"credit_min": 50000,  "credit_max": 300000, "annual_fee_range": (800, 3600), "target_income": ["M", "H"],       "prob": 0.30},
    "钻石卡":  {"credit_min": 100000, "credit_max": 500000, "annual_fee_range": (3600, 8000),"target_income": ["H"],          "prob": 0.08},
    "无限卡":  {"credit_min": 300000, "credit_max": 1000000,"annual_fee_range": (8000, 20000),"target_income": ["H"],         "prob": 0.04},
    "校园卡":  {"credit_min": 0,      "credit_max": 5000,   "annual_fee_range": (0, 0),     "target_income": ["L"],           "prob": 0.03},
}

# --- 卡片状态 ---
CARD_STATUSES = ["正常", "正常", "正常", "正常", "正常", "正常", "正常", "冻结", "销卡"]
CARD_STATUS_WEIGHTS = [0.80, 0.00, 0.00, 0.00, 0.00, 0.00, 0.00, 0.10, 0.10]

# --- 生命周期阶段 ---
LIFECYCLE_STAGES = {
    "新户":    {"months_min": 0, "months_max": 3,  "description": "开卡0-3个月"},
    "成长期":  {"months_min": 3, "months_max": 12, "description": "开卡3-12个月，活跃上升"},
    "成熟期":  {"months_min": 12,"months_max": 36, "description": "开卡12-36个月，消费稳定"},
    "沉睡期":  {"months_min": 36,"months_max": 120,"description": "开卡超过36个月，近期无交易"},
}

# --- 交易类型 ---
TRANSACTION_TYPES = {
    "消费":  0.78,
    "取现":  0.03,
    "还款":  0.12,
    "退款":  0.04,
    "分期":  0.03,
}

# --- 商户类别（MCC大类，结合XX银行真实消费场景） ---
MERCHANT_CATEGORIES = {
    "餐饮":      {"prob": 0.20, "amount_range": (15, 500),     "typical_merchants": ["海底捞", "麦当劳", "星巴克", "西贝莜面村", "太二酸菜鱼", "喜茶", "肯德基", "外婆家", "鼎泰丰", "大董"]},
    "商旅":      {"prob": 0.08, "amount_range": (200, 8000),   "typical_merchants": ["携程旅行", "中国国航", "南方航空", "如家酒店", "万豪酒店", "希尔顿", "洲际酒店", "汉庭", "Booking.com", "东方航空"]},
    "购物":      {"prob": 0.25, "amount_range": (30, 5000),    "typical_merchants": ["京东", "天猫", "拼多多", "唯品会", "苏宁易购", "淘宝", "山姆会员店", "Costco", "万象城", "银泰百货"]},
    "境外":      {"prob": 0.05, "amount_range": (100, 50000),  "typical_merchants": ["Apple US", "Amazon.com", "LV Paris", "Duty Free Shop", "MUJI Japan", "Sephora", "Nike US", "DFS Galleria", "UNIQLO HK", "Chanel"]},
    "娱乐":      {"prob": 0.08, "amount_range": (30, 800),     "typical_merchants": ["万达影城", "KTV麦乐迪", "迪士尼乐园", "环球影城", "欢乐谷", "网易云音乐", "腾讯视频", "Bilibili", "Keep", "猫眼电影"]},
    "教育":      {"prob": 0.05, "amount_range": (100, 15000),  "typical_merchants": ["新东方", "好未来", "VIPKID", "Coursera", "知乎", "得到", "网易公开课", "中公教育", "英语流利说", "少年得到"]},
    "医疗":      {"prob": 0.04, "amount_range": (50, 3000),    "typical_merchants": ["京东健康", "阿里健康", "平安好医生", "丁香医生", "瑞尔齿科", "爱尔眼科", "和睦家", "同仁堂", "老百姓大药房", "1药网"]},
    "日用":      {"prob": 0.10, "amount_range": (10, 800),     "typical_merchants": ["美团外卖", "饿了么", "叮咚买菜", "盒马鲜生", "每日优鲜", "永辉超市", "沃尔玛", "物美", "全家便利店", "罗森"]},
    "交通":      {"prob": 0.06, "amount_range": (1, 300),      "typical_merchants": ["滴滴出行", "高德打车", "T3出行", "曹操出行", "12306铁路", "深圳通", "北京一卡通", "上海交通卡", "神州租车", "一嗨租车"]},
    "其他":      {"prob": 0.09, "amount_range": (10, 2000),    "typical_merchants": ["中国移动", "中国电信", "国家电网", "顺丰速运", "EMS", "德邦物流", "58同城", "自如", "贝壳找房", "链家"]},
}

# --- 交易渠道 ---
TRANSACTION_CHANNELS = {
    "线下刷卡":   0.15,
    "支付宝":     0.30,
    "微信支付":   0.28,
    "银联在线":   0.10,
    "Apple Pay":  0.07,
    "云闪付":     0.08,
    "其他":       0.02,
}

# --- APP 埋点事件类型 ---
APP_EVENT_TYPES = {
    "页面浏览":  0.55,
    "点击":      0.25,
    "搜索":      0.08,
    "停留":      0.07,
    "分享":      0.03,
    "退出":      0.02,
}

# --- APP 页面列表（XX银行手机银行 APP 典型页面） ---
APP_PAGES = [
    "首页", "账单详情", "额度管理", "分期计算器", "权益商城",
    "积分兑换", "境外消费专区", "活动中心", "信用卡申请",
    "还款页面", "交易记录", "我的优惠券", "客户服务",
    "产品升级", "新手指引", "设置中心", "消息中心",
    "联名卡专区", "高端卡专区", "搜索页", "支付成功页",
    "卡片管理", "征信查询", "保险服务", "商城商品详情",
]

# --- APP 搜索关键词库（分意图类别） ---
SEARCH_KEYWORDS = {
    "分期/借贷需求": ["分期", "手续费", "最低还款", "账单分期", "借钱", "贷款", "额度", "12期", "免息分期", "还款压力", "延期还款", "分期费率", "现金分期", "好享贷"],
    "跨境/出行需求": ["境外", "汇率", "海淘", "免税", "出境游", "东京", "巴黎", "曼谷", "新加坡", "签证", "机票", "酒店", "出国", "外币", "境外取现"],
    "额度/升级需求": ["提额", "额度不够", "申请提额", "白金卡", "钻石卡", "高端卡", "升级", "无限卡", "临时额度", "固定额度", "额度查询"],
    "权益/优惠需求": ["积分兑换", "里程", "优惠券", "折扣", "返现", "5折", "生日", "积分", "星巴克", "电影票", "贵宾厅", "接送机", "兑换", "权益"],
    "沉睡/流失风险": ["销户", "注销", "年费", "取消", "退卡", "投诉"],
    "新户/激活引导": ["开卡", "激活", "怎么用", "首刷", "新手", "绑卡"],
}

# --- VIP 等级 ---
VIP_TIERS = {
    "钻石": 0.08,
    "白金": 0.18,
    "金卡": 0.30,
    "普通": 0.44,
}

# --- 联系偏好 ---
CONTACT_PREFERENCES = ["APP Push", "短信", "邮件", "电话"]
CONTACT_PREF_WEIGHTS = [0.45, 0.30, 0.15, 0.10]

# --- 卡号BIN前缀（XX银行银联卡BIN） ---
CMB_BIN_PREFIXES = [
    "622580", "622588", "622598", "622609", "622659",
    "621485", "621486", "622575", "622576", "622577",
    "622578", "622579", "439225", "439226", "439227",
    "518710", "518718", "356886", "356887", "356888",
]
