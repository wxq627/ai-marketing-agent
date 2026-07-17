"""
非结构化文档与活动海报生成脚本
================================
生成:
  - mock_data/unstructured/product_docs/  (产品说明书/条款, JSON描述)
  - mock_data/unstructured/posters/       (活动海报JSON描述)

说明:
  实际PDF需外部工具生成。本脚本生成的是:
  1) 每份"文档"的完整文本内容 (存为 .txt)
  2) 文档元信息 (存为 _index.json)
  3) 海报结构化描述 (存为 JSON)
  这些JSON可直接被 doc_loader.py 消费用于GraphRAG构建。
"""

import random, os, json
from datetime import datetime
from typing import List, Dict, Any

from config import *

random.seed(RANDOM_SEED + 6)


# ============================================================
# 产品文档内容生成
# ============================================================

def generate_doc_content(doc_type: str, product_name: str = "") -> str:
    """生成一份仿真文档的文本内容。"""
    if doc_type == "权益说明":
        return f"""
{product_name}权益说明手册
============================
XX银行信用卡中心 | 2026年版

第一章 总则
-----------
{product_name}是XX银行面向{"高端" if "白金" in product_name or "钻石" in product_name or "无限" in product_name else "优质"}客群推出的信用卡产品，持卡人享有本手册所列全部权益。本手册自2026年1月1日起生效。

第二章 出行权益
--------------
2.1 机场贵宾厅服务
持卡人可全年无限次使用全球超过1000间机场贵宾厅。服务覆盖深圳宝安国际机场、北京首都国际机场、上海浦东国际机场、上海虹桥国际机场、广州白云国际机场、成都天府国际机场、杭州萧山国际机场等国内主要机场，以及香港、东京成田、新加坡樟宜、伦敦希思罗、纽约肯尼迪等国际枢纽。
使用方式：登录掌上生活APP → 高端权益 → 机场贵宾厅 → 选择机场和日期 → 生成二维码 → 至前台扫码入场。
部分热门机场（北京首都T3、上海浦东T1/T2）建议提前48小时预约。

2.2 接送机服务
白金卡持卡人每年享有6次豪华商务车接送机服务；钻石卡持卡人每年享有12次；无限卡持卡人享有无限次。
服务范围：全国主要城市机场 ↔ 市区任意地址。
预约方式：掌上生活APP → 高端权益 → 接送机 → 填写航班信息和目的地 → 预约成功后将收到司机信息。
取消政策：用车前2小时可免费取消。

2.3 酒店升级权益
白金卡及以上持卡人每年享有酒店免费升级权益。预订合作酒店（万豪、希尔顿、洲际、凯悦等）普通房型，可免费升级至行政楼层或套房，每年限2-4次（依卡等而定）。

第三章 消费权益
--------------
3.1 指定商户返现
每周五在天猫、京东、拼多多、唯品会等指定线上商户消费，享最高5%返现，每月返现上限100元。

3.2 境外消费返现
境外线下消费享5%返现，每月返现上限500元。含港澳台地区。返现金额将于次月15日前返还至信用卡账户。

3.3 线上支付积分加倍
通过支付宝、微信支付、云闪付进行的消费，享1.5倍积分。与生日双倍积分可叠加，最高享3倍积分。

第四章 分期权益
--------------
4.1 灵活分期
持卡人可选择3/6/12/18/24期分期还款。手续费率分别为0.60%/期、0.50%/期、0.45%/期、0.40%/期、0.35%/期。

4.2 大额消费自动分期
单笔消费超过5000元时，系统自动推送分期提醒，可享手续费8折优惠。

第五章 保险权益
--------------
5.1 航班延误险
航班延误2小时以上，赔付1000元；延误4小时以上，赔付2000元。无需提供发票，自动触发理赔。

5.2 旅行意外险
保额500万元，覆盖全球范围。含高风险运动（潜水、滑雪、登山等）保障。

5.3 购物保障险
刷卡购物30天内，如商品因意外损坏或被盗，最高赔付2万元（需提供购买凭证和报案回执）。

第六章 附则
-----------
XX银行保留对本手册的最终解释权。如有调整，将通过掌上生活APP提前30天公告。
客服热线：400-820-5555
"""

    elif doc_type == "分期条款":
        return f"""
XX银行信用卡分期付款业务条款（2026版）
========================================

第一条 定义
-----------
信用卡分期付款业务（以下简称"分期业务"）是指持卡人将其信用卡账户中的消费或账单金额，按照约定期数分期偿还，并支付相应手续费的业务。

第二条 分期类型
--------------
2.1 消费分期：持卡人对单笔消费金额申请分期。
2.2 账单分期：持卡人对已出账单金额申请分期。
2.3 现金分期：持卡人将信用卡额度转为现金并分期偿还。

第三条 分期期数与手续费率
--------------------------
| 期数 | 消费分期费率 | 账单分期费率 | 现金分期费率 |
|------|------------|------------|------------|
| 3期  | 0.60%/期   | 0.60%/期   | 0.65%/期   |
| 6期  | 0.50%/期   | 0.50%/期   | 0.55%/期   |
| 12期 | 0.45%/期   | 0.45%/期   | 0.50%/期   |
| 18期 | 0.40%/期   | 0.40%/期   | 0.45%/期   |
| 24期 | 0.35%/期   | 0.35%/期   | 0.40%/期   |

年化利率（单利）：3期约10.8%、6期约10.5%、12期约9.9%、18期约9.4%、24期约8.9%。

第四条 申请条件
--------------
4.1 持卡人账户状态正常，无逾期记录。
4.2 消费分期：单笔消费金额≥500元。
4.3 账单分期：当期账单金额≥1000元。
4.4 现金分期：可用额度≥1000元。

第五条 提前还款
--------------
持卡人可申请提前还款，但已收取的手续费不予退还，剩余期数手续费仍需一次性支付。

第六条 违约责任
--------------
持卡人未按期足额偿还分期款项的，本行有权：
1. 收取逾期利息（日利率0.05%）；
2. 暂停持卡人使用分期业务；
3. 将逾期记录报送征信机构。

客服热线：400-820-5555
"""

    else:  # 通用模板
        return f"""
XX银行信用卡{product_name}使用指南
=====================================
尊敬的持卡人：
感谢您选择XX银行信用卡。本指南将帮助您快速了解用卡须知和常见问题。

一、卡片激活
新卡需通过掌上生活APP或拨打400-820-5555激活后方可使用。

二、账单与还款
账单日：每月{random.randint(5,25)}日
到期还款日：账单日后第20天
最低还款额：当期账单金额的10%（不低于100元）
全额还款：免息期内全额还款不产生利息
最低还款：未还部分自消费日起按日利率0.05%计息

三、积分规则
消费1元积1分（部分商户类别除外）
积分有效期：自获取之日起24个月
生日月消费享双倍积分

四、安全提示
• 请勿将卡号、CVV码、有效期告知他人
• 境外网站消费建议使用虚拟卡号
• 遗失卡片请立即致电挂失

客服热线：400-820-5555（24小时）
"""
    return ""


# ============================================================
# 海报JSON描述
# ============================================================

POSTER_DEFS = [
    {
        "image_file": "nov11_promo.png",
        "activity_name": "双十一分期免息大促",
        "campaign_id": "CAMP_2026_DOUBLE11",
        "start_date": "2026-11-01", "end_date": "2026-11-11",
        "main_title": "双十一分期免息，最高省500元！",
        "sub_title": "指定商户单笔满3000元享3期免息",
        "visual_description": "红金渐变背景，中央大字'11.11 分期免息'，左侧展示手机购物场景插画，底部白色区域排列天猫/京东/拼多多logo。右下角有'立即查看额度'按钮。",
        "rules_summary": [
            "活动期间在指定线上商户单笔消费满3000元享3期免息",
            "单笔消费满5000元享6期免息",
            "新户首次分期额外返现50元",
            "每人限享一次免息优惠",
            "不与其它分期优惠叠加"
        ],
        "target_segment": "22-45岁金卡及以上持卡人",
        "cta_text": "立即查看我的分期额度",
    },
    {
        "image_file": "spring_festival_promo.png",
        "activity_name": "春节境外消费返现季",
        "campaign_id": "CAMP_2026_SPRINGFEST",
        "start_date": "2026-01-15", "end_date": "2026-02-15",
        "main_title": "春节出境游，刷XX银行卡返现8%！",
        "sub_title": "港澳日韩东南亚通用",
        "visual_description": "红色春节主题背景，灯笼和福字装饰，中央展示东京、曼谷、新加坡等城市地标剪影。左下有金色'8%返现'图标。底部有活动时间和条款简要。",
        "rules_summary": [
            "境外线下消费享8%返现，单月封顶800元",
            "港澳台、日韩、东南亚、欧美均适用",
            "需提前在APP报名",
            "返现金额次月15日前到账"
        ],
        "target_segment": "25-55岁白金卡及以上持卡人",
        "cta_text": "立即报名参与",
    },
    {
        "image_file": "new_user_welcome.png",
        "activity_name": "新户开卡三重礼",
        "campaign_id": "CAMP_2026_NEWUSER",
        "start_date": "2026-01-01", "end_date": "2026-12-31",
        "main_title": "新户专享·开卡就送100元！",
        "sub_title": "首刷+绑卡+开卡 三重好礼",
        "visual_description": "清新蓝色背景，中央展示三张礼品卡片（刷卡金100元/定制礼品/红包）。顶部有'Welcome'英文字。整体设计年轻化、时尚感。",
        "rules_summary": [
            "开卡后30天内任意消费1笔即送100元刷卡金",
            "首笔消费满99元可选定制礼品（三选一）",
            "首次绑定支付宝/微信/云闪付各送10元红包",
            "三项可兼得"
        ],
        "target_segment": "新户",
        "cta_text": "立即激活卡片",
    },
    {
        "image_file": "dormant_wakeup.png",
        "activity_name": "沉睡客户唤醒计划",
        "campaign_id": "CAMP_2026_DORMANT",
        "start_date": "2026-04-01", "end_date": "2026-12-31",
        "main_title": "好久不见，回来刷一笔领50元！",
        "sub_title": "你的信用卡想你啦~",
        "visual_description": "温暖橙色背景，中央有一只可爱的XX银行猫吉祥物挥手。下方有红包图标'50元'。整体风格温馨、友好。",
        "rules_summary": [
            "30天内任意消费1笔即赠50元刷卡金",
            "消费满500元额外赠送5000积分",
            "限已连续90天无交易的客户"
        ],
        "target_segment": "沉睡期客户",
        "cta_text": "去看看有什么优惠",
    },
    {
        "image_file": "summer_travel.png",
        "activity_name": "暑期出行季",
        "campaign_id": "CAMP_2026_SUMMER",
        "start_date": "2026-07-01", "end_date": "2026-08-31",
        "main_title": "放暑假了！机票酒店刷XX银行卡",
        "sub_title": "机票满1000减100 | 酒店连住8折 | WiFi首日1元",
        "visual_description": "蓝天海滩背景，中央展示飞机和度假酒店图标。右上有'SUMMER'艺术字。底部三个图标分别对应机票/酒店/WiFi优惠。",
        "rules_summary": [
            "机票单笔满1000元立减100元（限携程/飞猪）",
            "合作酒店连住3晚享8折",
            "境外WiFi租赁首日1元起",
            "每人各权益限享1次"
        ],
        "target_segment": "22-45岁金卡及以上",
        "cta_text": "马上预订",
    },
    {
        "image_file": "upgrade_invite.png",
        "activity_name": "金卡升级白金卡专属邀请",
        "campaign_id": "CAMP_2026_UPGRADE",
        "start_date": "2026-05-01", "end_date": "2026-12-31",
        "main_title": "恭喜！您已获得白金卡升级资格",
        "sub_title": "首年年费5折 | 赠机场贵宾厅2次",
        "visual_description": "黑金配色高端风格，中央放置白金卡产品图。左侧列出升级后新增权益的图标列表。右下角有'专属邀请'水印。",
        "rules_summary": [
            "限收到邀请的金卡持卡人（年消费≥8万元）",
            "升级后首年年费5折（原价3600元→1800元）",
            "额外赠送机场贵宾厅2次体验",
            "升级后原卡额度保留并可能提升"
        ],
        "target_segment": "高消费金卡持卡人",
        "cta_text": "查看我的升级权益",
    },
    {
        "image_file": "618_shopping.png",
        "activity_name": "618购物节返现",
        "campaign_id": "CAMP_2026_618",
        "start_date": "2026-06-01", "end_date": "2026-06-18",
        "main_title": "618年中大促·刷XX银行返现5%",
        "sub_title": "天猫/京东满500返50 · 6期免息",
        "visual_description": "紫色电商主题背景，中央'618'大字。周围有购物车、优惠券、快递盒等图标。底部有倒计时组件和适用商户logo。",
        "rules_summary": [
            "在天猫/京东消费满500元返50元",
            "享6期免息分期",
            "名额有限先到先得",
            "每人限享一次返现"
        ],
        "target_segment": "20-40岁普卡/金卡/白金卡",
        "cta_text": "去购物",
    },
    {
        "image_file": "campus_graduation.png",
        "activity_name": "校园卡毕业季升级",
        "campaign_id": "CAMP_2026_CAMPUS",
        "start_date": "2026-06-01", "end_date": "2026-07-31",
        "main_title": "毕业快乐！校园卡免费升级金卡",
        "sub_title": "额度提升 | 50元转卡礼",
        "visual_description": "学院风设计，蓝色毕业袍和学位帽元素。中央展示'校园卡→金卡'的升级动画。底部有毕业生剪影和祝福语。",
        "rules_summary": [
            "应届毕业生凭毕业证/学位证申请转卡",
            "校园卡免费升级为标准金卡",
            "额度在原校园卡基础上+5000元起",
            "转卡成功赠送50元刷卡金"
        ],
        "target_segment": "校园卡即将毕业的学生",
        "cta_text": "申请转卡",
    },
    {
        "image_file": "birthday_benefit.png",
        "activity_name": "生日月专属福利",
        "campaign_id": "CAMP_2026_BIRTHDAY",
        "start_date": "2026-01-01", "end_date": "2026-12-31",
        "main_title": "生日快乐！本月消费双倍积分",
        "sub_title": "生日当天星巴克免费中杯 | 50元专属优惠券",
        "visual_description": "粉金配色温馨风格，中央有蛋糕和气球插画。下方排列三项福利：双倍积分/星巴克券/优惠券。整体设计有生日氛围。",
        "rules_summary": [
            "生日当月所有消费享双倍积分（上限10万分）",
            "生日当天在掌上生活APP可领星巴克免费中杯券1张",
            "生日当月可领50元专属优惠券"
        ],
        "target_segment": "所有持卡人",
        "cta_text": "领取我的生日福利",
    },
    {
        "image_file": "crossborder_campaign.png",
        "activity_name": "跨境消费达人挑战",
        "campaign_id": "CAMP_2026_CROSSBORDER",
        "start_date": "2026-06-15", "end_date": "2026-09-30",
        "main_title": "跨境消费达人·阶梯返现最高1000元",
        "sub_title": "满5000返200 → 满20000返1000",
        "visual_description": "深蓝全球地图背景，中央展示阶梯式返现进度条。世界地标（埃菲尔铁塔/自由女神/大本钟）剪影装饰。金色'UP TO ¥1000'标识。",
        "rules_summary": [
            "境外消费满5000元返200元",
            "满10000元返500元",
            "满20000元返1000元",
            "含港澳台地区",
            "免货币转换费"
        ],
        "target_segment": "近3月有境外消费记录的客户",
        "cta_text": "查看我的进度",
    },
]


# ============================================================
# 主入口
# ============================================================

def generate_all_docs_and_posters():
    print("=" * 60)
    print("生成非结构化文档 & 活动海报描述 ...")
    print("=" * 60)

    # ---- 产品文档 ----
    doc_index = []
    doc_list = [
        ("经典版白金信用卡", "权益说明"),
        ("银联白金信用卡", "权益说明"),
        ("全币种国际白金信用卡", "权益说明"),
        ("精致版白金信用卡", "权益说明"),
        ("自由人生白金信用卡", "权益说明"),
        ("百夫长白金卡", "权益说明"),
        ("银联钻石信用卡", "权益说明"),
        ("万事达世界信用卡", "权益说明"),
        ("标准信用卡（金卡）", "权益说明"),
        ("YOUNG卡（青年版）", "权益说明"),
        ("携程旅行信用卡（金卡）", "权益说明"),
        ("京东PLUS联名信用卡（金卡）", "权益说明"),
        ("标准信用卡（普卡）", "权益说明"),
        ("Hello Kitty粉丝信用卡（普卡）", "权益说明"),
        ("YOUNG卡（校园版）", "权益说明"),
        ("分期付款条款", "分期条款"),
        ("信用卡章程", "通用"),
        ("积分规则说明", "通用"),
        ("境外消费指南", "通用"),
        ("保险权益细则", "通用"),
        ("新户开卡礼规则", "通用"),
        ("电子现金使用说明", "通用"),
        ("掌上生活APP功能介绍", "通用"),
        ("用卡安全指南", "通用"),
    ]

    for i, (name, dtype) in enumerate(doc_list):
        content = generate_doc_content(dtype, name)
        # 保存文本
        txt_name = f"doc_{i+1:02d}.txt"
        txt_path = os.path.join(PRODUCT_DOCS_DIR, txt_name)
        with open(txt_path, "w", encoding="utf-8") as f:
            f.write(content)

        doc_index.append({
            "doc_id": f"DOC_{i+1:03d}",
            "title": f"{name}{'说明' if dtype != '分期条款' else ''}",
            "doc_type": dtype,
            "file_path": txt_name,
            "product_name": name,
            "char_count": len(content),
            "generated_at": REFERENCE_DATE.strftime("%Y-%m-%d"),
        })

    # 保存文档索引
    idx_path = os.path.join(PRODUCT_DOCS_DIR, "_index.json")
    with open(idx_path, "w", encoding="utf-8") as f:
        json.dump(doc_index, f, ensure_ascii=False, indent=2)

    print(f"✅ 产品文档: {len(doc_list)} 份 → {PRODUCT_DOCS_DIR}")
    print(f"   索引文件: _index.json")

    # ---- 活动海报 ----
    poster_dir = POSTERS_DIR
    for p in POSTER_DEFS:
        fname = p["image_file"].replace(".png", ".json")
        fpath = os.path.join(poster_dir, fname)
        with open(fpath, "w", encoding="utf-8") as f:
            json.dump(p, f, ensure_ascii=False, indent=2)

    # 额外生成几个通用海报
    extras = [
        {"image_file": "weekend_promo.png", "activity_name": "周末消费狂欢", "main_title": "周末刷XX银行·随机立减最高99元", "sub_title": "每周六日 · 不限商户", "rules_summary":["每周六日任意消费随机立减","每单最高99元","每日限1次"]},
        {"image_file": "points_boost.png", "activity_name": "积分膨胀季", "main_title": "积分兑换膨胀1.2倍！", "sub_title": "限时活动 · 兑完即止", "rules_summary":["积分商城兑换指定商品享1.2倍价值","含航空里程/视频会员/实物礼品","活动期间每人限兑3次"]},
    ]
    for ep in extras:
        ep["campaign_id"] = ""
        ep["start_date"] = "2026-01-01"
        ep["end_date"] = "2026-12-31"
        ep["visual_description"] = "通用营销海报风格"
        ep["target_segment"] = "所有持卡人"
        ep["cta_text"] = "了解更多"
        fname = ep["image_file"].replace(".png", ".json")
        with open(os.path.join(poster_dir, fname), "w", encoding="utf-8") as f:
            json.dump(ep, f, ensure_ascii=False, indent=2)

    total_posters = len(POSTER_DEFS) + len(extras)
    print(f"✅ 活动海报描述: {total_posters} 份 → {poster_dir}")

    return doc_index


if __name__ == "__main__":
    generate_all_docs_and_posters()
