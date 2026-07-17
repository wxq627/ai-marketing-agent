"""
客户基础信息与信用卡生成脚本
================================
生成 mock_data/structured/customer_basic.csv 和 credit_card.csv

业务逻辑约束：
  1. 收入等级与卡等级正相关（高收入 → 高等级卡概率更高）
  2. 年龄与卡等级相关（校园卡仅限<28岁，高端卡偏向30+）
  3. 一人可持多张卡（1-4张），主卡等级通常最高
  4. 城市分布按XX银行实际业务重点城市加权
  5. 身份证号、手机号、卡号均需脱敏处理
"""

import random
import pandas as pd
import numpy as np
from datetime import datetime, timedelta
from typing import Tuple, List, Dict, Any
from faker import Faker
import hashlib

from config import *

# 初始化 Faker（中文模式）
fake = Faker("zh_CN")
random.seed(RANDOM_SEED)
np.random.seed(RANDOM_SEED)
Faker.seed(RANDOM_SEED)


# ============================================================
# 工具函数
# ============================================================

def mask_string(s: str, keep_start: int = 3, keep_end: int = 1, mask_char: str = "*") -> str:
    """对敏感字符串进行脱敏处理，保留首尾少量字符"""
    if len(s) <= keep_start + keep_end:
        return s[0] + mask_char * (len(s) - 2) + s[-1] if len(s) > 2 else mask_char * len(s)
    return s[:keep_start] + mask_char * (len(s) - keep_start - keep_end) + s[-keep_end:]


def generate_masked_id_card() -> str:
    """生成脱敏身份证号（符合中国大陆18位身份证编码规则）"""
    # 地区码（6位）：使用常见城市编码
    area_codes = [
        "440305", "310115", "110108", "440106", "330102",
        "510107", "320106", "420106", "610103", "500103",
        "320502", "120101", "430103", "410103", "441900",
        "370202", "350203", "340103", "350102", "530102",
    ]
    area = random.choice(area_codes)
    # 出生日期：1965-2005
    year = random.randint(1965, 2005)
    month = random.randint(1, 12)
    day = random.randint(1, 28)
    birth = f"{year}{month:02d}{day:02d}"
    # 顺序码（3位）
    seq = random.randint(0, 999)
    # 校验码（简化：随机生成一位数字或X）
    check = random.choice([str(i) for i in range(10)] + ["X"])
    full_id = f"{area}{birth}{seq:03d}{check}"
    return mask_string(full_id, keep_start=4, keep_end=2)


def generate_masked_phone() -> str:
    """生成脱敏手机号（大陆11位手机号）"""
    prefixes = ["138", "139", "136", "137", "158", "159", "186", "187", "188", "189", "177", "176", "135", "150", "151", "152"]
    prefix = random.choice(prefixes)
    suffix = "".join([str(random.randint(0, 9)) for _ in range(8)])
    full_phone = prefix + suffix
    return mask_string(full_phone, keep_start=3, keep_end=4)


def generate_masked_card_number(bin_prefix: str = None) -> str:
    """生成脱敏银行卡号（16-19位，银联标准BIN前缀）"""
    if bin_prefix is None:
        bin_prefix = random.choice(BANK_BIN_PREFIXES)
    # 卡号长度：16或19位
    card_length = random.choice([16, 16, 16, 19])
    remaining = card_length - len(bin_prefix)
    digits = bin_prefix + "".join([str(random.randint(0, 9)) for _ in range(remaining)])
    return mask_string(digits, keep_start=4, keep_end=2)


def generate_device_id() -> str:
    """生成模拟设备ID"""
    prefixes = ["DEV_A", "DEV_B", "DEV_iOS", "DEV_HW", "DEV_OP"]
    prefix = random.choice(prefixes)
    suffix = "".join([str(random.randint(0, 9)) for _ in range(3)])
    return f"{prefix}{suffix}"


def determine_lifecycle_stage(open_date: datetime, has_recent_txn: bool = True) -> str:
    """根据开卡时间判断生命周期阶段"""
    months_since_open = (REFERENCE_DATE - open_date).days / 30.44
    if months_since_open <= 3:
        return "新户"
    elif months_since_open <= 12:
        return "成长期"
    elif months_since_open <= 36:
        return "成熟期"
    else:
        if not has_recent_txn:
            return "沉睡期"
        return "成熟期"  # 超过36月但仍有交易 → 仍是成熟期


def derive_income_range(income_level: str) -> Tuple[float, float]:
    """根据收入等级返回月收入范围"""
    info = INCOME_LEVELS[income_level]
    return info["monthly_min"], info["monthly_max"]


# ============================================================
# 客户基础信息生成
# ============================================================

def generate_customer_basic(cust_index: int) -> Dict[str, Any]:
    """
    生成一个客户的完整基础信息。
    遵循金融行业真实分布。
    """
    cust_id = f"C{str(cust_index + 1).zfill(6)}"

    # 城市（加权抽样）
    city = random.choices(CITIES, weights=CITY_WEIGHTS, k=1)[0]

    # 年龄：正态分布，均值35，标准差10，范围21-65
    age = int(np.clip(np.random.normal(35, 10), 21, 65))

    # 性别
    gender = random.choices(["M", "F"], weights=[0.52, 0.48], k=1)[0]

    # 收入等级（与年龄弱相关：年龄太小收入偏低）
    if age < 23:
        income_weights = [0.02, 0.28, 0.70]  # H, M, L
    elif age < 28:
        income_weights = [0.08, 0.50, 0.42]
    elif age < 45:
        income_weights = [0.20, 0.52, 0.28]
    else:
        income_weights = [0.18, 0.48, 0.34]
    income_level = random.choices(["H", "M", "L"], weights=income_weights, k=1)[0]

    # 职业
    occupation = random.choices(OCCUPATIONS, weights=OCCUPATION_WEIGHTS, k=1)[0]
    # 学生特殊处理
    if occupation == "在校学生":
        age = min(age, 28)
        income_level = "L"

    # 学历（与收入弱相关）
    if income_level == "H":
        edu_weights = [0.08, 0.30, 0.42, 0.15, 0.05]
    elif income_level == "M":
        edu_weights = [0.02, 0.18, 0.45, 0.25, 0.10]
    else:
        edu_weights = [0.01, 0.08, 0.30, 0.35, 0.26]
    education = random.choices(EDUCATION_LEVELS, weights=edu_weights, k=1)[0]

    # 开户日期（在模拟时间范围内）
    max_tenure_days = (REFERENCE_DATE - datetime(2010, 1, 1)).days  # 最早2010年开户
    tenure_days = int(np.random.exponential(scale=1500))  # 指数分布，多数较新
    tenure_days = min(tenure_days, max_tenure_days)
    register_date = REFERENCE_DATE - timedelta(days=tenure_days)

    # 身份证号
    id_card = generate_masked_id_card()

    # 手机号
    phone = generate_masked_phone()

    # 姓名
    name = fake.name()

    return {
        "cust_id": cust_id,
        "name": name,
        "gender": gender,
        "age": age,
        "city": city,
        "occupation": occupation,
        "income_level": income_level,
        "education": education,
        "id_card": id_card,
        "phone": phone,
        "register_date": register_date.strftime("%Y-%m-%d"),
    }


# ============================================================
# 信用卡生成
# ============================================================

def select_card_level(income_level: str, age: int) -> str:
    """根据收入和年龄选择合适的卡等级"""
    level_probs = {}
    for level, info in CARD_LEVELS.items():
        prob = info["prob"]
        # 收入匹配加成
        if income_level in info["target_income"]:
            prob *= 2.0
        else:
            prob *= 0.3
        # 年龄约束
        if level == "校园卡" and age > 28:
            prob = 0
        if level in ["钻石卡", "无限卡"] and age < 25:
            prob *= 0.1
        level_probs[level] = prob

    # 归一化
    total = sum(level_probs.values())
    levels = list(level_probs.keys())
    probs = [level_probs[l] / total for l in levels]
    return random.choices(levels, weights=probs, k=1)[0]


def generate_cards_for_customer(cust_id: str, income_level: str, age: int,
                                 register_date: datetime) -> List[Dict[str, Any]]:
    """
    为一个客户生成他持有的所有信用卡（1-4张）。
    首张卡为主卡，等级通常最高。
    """
    n_cards = random.randint(N_CARDS_MIN, N_CARDS_MAX)

    # 首张卡（主卡）：选最高等级
    primary_level = select_card_level(income_level, age)
    cards = []

    # 为每张卡选择等级（辅卡等级不高于主卡）
    level_hierarchy = ["校园卡", "普卡", "金卡", "白金卡", "钻石卡", "无限卡"]
    primary_idx = level_hierarchy.index(primary_level)

    for i in range(n_cards):
        if i == 0:
            level = primary_level
        else:
            # 辅卡等级不高于主卡
            max_idx = primary_idx
            available = level_hierarchy[:max_idx + 1]
            # 偏向于中等卡等
            mid_idx = min(max_idx, 2)  # 偏向金卡
            weights = [0.1] * len(available)
            weights[mid_idx] = 0.5 if mid_idx < len(weights) else 0.5
            weights = [w / sum(weights) for w in weights]
            level = random.choices(available, weights=weights, k=1)[0]

        level_info = CARD_LEVELS[level]

        # 授信额度（在卡等级范围内，受收入影响）
        credit_min = level_info["credit_min"]
        credit_max = level_info["credit_max"]
        # 收入高 → 额度偏上限
        if income_level == "H":
            credit_amount = round(random.uniform(credit_min + (credit_max - credit_min) * 0.5, credit_max), -2)
        elif income_level == "M":
            credit_amount = round(random.uniform(credit_min + (credit_max - credit_min) * 0.2, credit_max * 0.8), -2)
        else:
            credit_amount = round(random.uniform(credit_min, credit_max * 0.6), -2)
        credit_amount = max(credit_amount, credit_min)

        # 开卡日期（首卡跟注册日期，辅卡可能更晚）
        max_days = max(30, (REFERENCE_DATE - register_date).days - 30)
        if i == 0:
            open_date = register_date + timedelta(days=random.randint(0, min(30, max_days)))
        else:
            lo = min(90, max_days)
            hi = max(lo + 1, max_days)
            days_after_primary = random.randint(lo, hi) if hi > lo else lo
            open_date = register_date + timedelta(days=days_after_primary)
        open_date = min(open_date, REFERENCE_DATE - timedelta(days=30))

        # 卡号
        card_no = generate_masked_card_number()

        # 卡状态（开卡很早的卡有概率已销卡）
        months_open = (REFERENCE_DATE - open_date).days / 30.44
        if months_open > 48 and random.random() < 0.15:
            status = "销卡"
        elif random.random() < 0.03:
            status = "冻结"
        else:
            status = "正常"

        # 分配产品
        product_id = assign_product_to_card(level)

        cards.append({
            "card_no": card_no,
            "cust_id": cust_id,
            "card_level": level,
            "credit_amount": credit_amount,
            "open_date": open_date.strftime("%Y-%m-%d"),
            "card_status": status,
            "product_id": product_id,
            "is_primary": (i == 0),
        })

    return cards


def assign_product_to_card(card_level: str) -> str:
    """根据卡等级分配产品ID（基于XX银行真实信用卡产品体系）"""
    level_to_product = {
        "校园卡": ["PROD_YOUNG_CAMPUS"],
        "普卡":   ["PROD_STANDARD_N", "PROD_HELLOKITTY_N"],
        "金卡":   ["PROD_STANDARD_G", "PROD_YOUNG_G", "PROD_JD_G", "PROD_CTRIP_G"],
        "白金卡": ["PROD_CLASSIC_W", "PROD_FREELIFE_W", "PROD_UNIONPAY_W",
                   "PROD_GLOBAL_W", "PROD_REFINED_W", "PROD_CENTURION_W"],
        "钻石卡": ["PROD_DIAMOND"],
        "无限卡": ["PROD_WORLD"],
    }
    candidates = level_to_product.get(card_level, ["PROD_STANDARD_N"])
    return random.choice(candidates)


# ============================================================
# 主生成函数
# ============================================================

def generate_all_customers_and_cards():
    """生成所有客户和信用卡数据"""
    print("=" * 60)
    print("生成客户基础信息 & 信用卡数据...")
    print(f"  目标客户数: {N_CUSTOMERS}")
    print("=" * 60)

    customers = []
    all_cards = []

    for i in range(N_CUSTOMERS):
        # 生成客户
        customer = generate_customer_basic(i)
        customers.append(customer)

        # 解析开户日期
        register_date = datetime.strptime(customer["register_date"], "%Y-%m-%d")

        # 生成该客户的信用卡
        cards = generate_cards_for_customer(
            cust_id=customer["cust_id"],
            income_level=customer["income_level"],
            age=customer["age"],
            register_date=register_date,
        )
        all_cards.extend(cards)

        if (i + 1) % 1000 == 0:
            print(f"  已生成 {i + 1}/{N_CUSTOMERS} 客户, {len(all_cards)} 张卡")

    # 保存为CSV
    df_customers = pd.DataFrame(customers)
    df_cards = pd.DataFrame(all_cards)

    customer_path = os.path.join(STRUCTURED_DIR, "customer_basic.csv")
    card_path = os.path.join(STRUCTURED_DIR, "credit_card.csv")

    df_customers.to_csv(customer_path, index=False, encoding="utf-8-sig")
    df_cards.to_csv(card_path, index=False, encoding="utf-8-sig")

    print(f"\n✅ 客户基础信息已保存: {customer_path}")
    print(f"   共 {len(df_customers)} 条记录, {len(df_customers.columns)} 列")
    print(f"   列名: {list(df_customers.columns)}")

    print(f"\n✅ 信用卡信息已保存: {card_path}")
    print(f"   共 {len(df_cards)} 条记录, {len(df_cards.columns)} 列")
    print(f"   平均持卡数: {len(df_cards) / len(df_customers):.1f} 张/人")
    print(f"   卡等级分布:")
    for level, count in df_cards["card_level"].value_counts().items():
        print(f"     {level}: {count} ({count/len(df_cards)*100:.1f}%)")

    return df_customers, df_cards


if __name__ == "__main__":
    generate_all_customers_and_cards()
