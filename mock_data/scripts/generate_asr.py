"""
客服ASR对话文本生成脚本
=========================
生成 mock_data/unstructured/asr_transcripts/ASR_XXXXX.json (1500条)

对话场景覆盖8大类，每类按意图标签标注。

重要: ASR = 自动语音识别，文本已转写完毕，这里生成的是JSON格式对话记录。
"""

import random, os, json
import pandas as pd
from datetime import datetime, timedelta
from typing import List, Dict, Any

from config import *

random.seed(RANDOM_SEED + 5)


# ============================================================
# 对话模板库 (8类场景 × 多条模板 = 丰富的仿真对话)
# ============================================================

class ASRTemplates:
    """客服对话模板。每条模板是一个函数，返回(transcript, resolution, sentiment_label)。"""

    @staticmethod
    def installment_01() -> tuple:
        """场景：账单压力大，咨询分期费率"""
        return (
            [
                {"role": "customer", "text": "你好，我这个月账单金额有点多，能帮我查一下分期怎么办理吗？"},
                {"role": "agent", "text": "好的，我帮您查询一下。张先生，您本期账单是18500元，目前支持3期、6期和12期分期，手续费率分别是0.6%/期、0.5%/期和0.45%/期。您觉得哪个期限比较合适？"},
                {"role": "customer", "text": "12期的话每个月要还多少？"},
                {"role": "agent", "text": "12期的话，每期本金约1541元，加上手续费约83元，合计每月约1624元。相比3期和6期，12期的总手续费会多一些，但每月还款压力最小。"},
                {"role": "customer", "text": "那就帮我办12期的吧，最近确实手头比较紧。"},
                {"role": "agent", "text": "好的，我现在为您办理12期账单分期。办理成功后您会收到短信确认。另外提醒您，分期期间如果提前还款，剩余期数的手续费也是需要支付的哦。"},
                {"role": "customer", "text": "明白了，谢谢你。"},
            ],
            "成功办理12期账单分期",
            "anxious_to_relieved"
        )

    @staticmethod
    def installment_02() -> tuple:
        """场景：大额消费后想分期"""
        return (
            [
                {"role": "customer", "text": "喂你好，我上周在京东买了台电脑花了12000，这个能不能分期还？"},
                {"role": "agent", "text": "您好！可以的，单笔消费满500元就可以申请消费分期。您这笔12000元的消费支持3/6/12/24期，24期的手续费率最低，只要0.35%/期。"},
                {"role": "customer", "text": "24期太长了，6期的手续费多少？"},
                {"role": "agent", "text": "6期的手续费率是0.5%/期，每期本金2000元加手续费60元，合计2060元。总计手续费360元。"},
                {"role": "customer", "text": "那就6期吧，帮我办一下。"},
            ],
            "成功办理消费分期(6期)",
            "neutral_to_satisfied"
        )

    @staticmethod
    def installment_03() -> tuple:
        """场景：比较不同分期方案"""
        return (
            [
                {"role": "customer", "text": "我想问一下，我这个月账单两万多，想办分期但是不知道选几个月的划算。"},
                {"role": "agent", "text": "您好，我帮您分析一下。您本期账单是23500元。3期每期约7960元含手续费141元，还款压力比较大；6期每期约4035元含手续费117元；12期每期约2065元含手续费105元。如果您的现金流比较充裕建议选6期总手续费更低，如果希望月供低一些可以选12期。"},
                {"role": "customer", "text": "那12期的总手续费一共是多少？"},
                {"role": "agent", "text": "12期总手续费大约1260元，比6期多了约440元，但每月只需还2065元。"},
                {"role": "customer", "text": "行，那12期吧。最近公司裁员风声紧，还是保守一点。"},
            ],
            "成功办理12期账单分期",
            "anxious"
        )

    @staticmethod
    def cross_border_01() -> tuple:
        """场景：出境游前咨询境外用卡"""
        return (
            [
                {"role": "customer", "text": "你好，我下个月要去日本旅游，想问一下在境外用信用卡有什么要注意的？"},
                {"role": "agent", "text": "您好！去日本旅游用XX银行信用卡非常方便。首先建议您开通境外免货币转换费服务，这样日元消费直接按银联汇率结算，不额外收费。另外您可以看看您的卡是否有境外返现权益。"},
                {"role": "customer", "text": "我的是白金卡，有境外返现吗？"},
                {"role": "agent", "text": "有的！白金卡境外消费返现最高5%，月上限500元。而且日本很多百货商场（如三越、伊势丹）刷XX银行卡还有额外折扣。"},
                {"role": "customer", "text": "太好了，那取现方面呢？"},
                {"role": "agent", "text": "境外ATM取现每月前3笔免手续费，建议您到日本后在7-11便利店的ATM取日元，汇率比机场换汇划算很多。不过提醒您取现会产生利息，建议提前在APP上预存一些现金到信用卡。"},
                {"role": "customer", "text": "好的明白了，非常感谢！"},
            ],
            "提供境外用卡指导",
            "neutral_to_satisfied"
        )

    @staticmethod
    def cross_border_02() -> tuple:
        """场景：境外消费后致电确认"""
        return (
            [
                {"role": "customer", "text": "喂，我刚才收到短信说我在美国消费了一笔500美金的交易，但是我现在人在国内啊？"},
                {"role": "agent", "text": "您别着急，我先帮您核实一下。请问您的卡号后四位是？"},
                {"role": "customer", "text": "8801。"},
                {"role": "agent", "text": "好的，我查到这笔500美金的交易是在Apple.com美国官网的消费，时间是一小时前。您最近是否有在Apple美国官网购买过产品？"},
                {"role": "customer", "text": "哦对对对！我忘了，我刚在官网订了一个iPad，那应该就是这个。不好意思虚惊一场。"},
                {"role": "agent", "text": "没关系！我们也建议您下载掌上生活APP开通交易实时提醒功能，这样每一笔消费都能在手机上即时看到明细。"},
            ],
            "确认交易为本人操作",
            "anxious_to_relieved"
        )

    @staticmethod
    def credit_upgrade_01() -> tuple:
        """场景：主动申请提额"""
        return (
            [
                {"role": "customer", "text": "你好，我想申请提高一下信用卡额度。"},
                {"role": "agent", "text": "好的，我帮您查看一下。您当前额度是5万元，最近半年的消费记录良好，没有逾期。我这边可以为您提交临时额度提升到8万元的申请，有效期60天。您觉得临时额度可以吗？"},
                {"role": "customer", "text": "我想要固定额度提高，不是临时的。"},
                {"role": "agent", "text": "固定额度需要系统综合评估，包括您的收入水平、消费习惯、还款记录等。我这边可以先帮您提交申请，1-3个工作日出结果。不过看您的记录，通过的可能性还是比较大的。"},
                {"role": "customer", "text": "好的那帮我提交吧。"},
            ],
            "提交固定额度提升申请",
            "neutral"
        )

    @staticmethod
    def credit_upgrade_02() -> tuple:
        """场景：询问升级白金卡条件"""
        return (
            [
                {"role": "customer", "text": "你好，我现在是金卡，想升级成白金卡，需要什么条件？"},
                {"role": "agent", "text": "您好，升级白金卡主要看几个方面：近12个月的消费总额、收入水平、以及是否有逾期记录。通常年消费在10万元以上，月收入在15000元以上的客户比较容易通过。您方便告诉我您大概的年消费吗？"},
                {"role": "customer", "text": "我一年大概消费15万左右，收入也符合你说的条件。"},
                {"role": "agent", "text": "那您的条件应该是够的。我为您推荐经典版白金卡，年费3600元但消费满8万可以免年费，权益包含机场贵宾厅、接送机、酒店升级等。要不我帮您提交升级申请？"},
                {"role": "customer", "text": "好的，帮我申请吧。"},
            ],
            "提交白金卡升级申请",
            "satisfied"
        )

    @staticmethod
    def benefits_01() -> tuple:
        """场景：积分即将过期，询问兑换方式"""
        return (
            [
                {"role": "customer", "text": "我收到短信说有8万积分下个月要过期了，能怎么兑换掉？"},
                {"role": "agent", "text": "您好，积分兑换的方式很多。您可以登录掌上生活APP进入积分商城，可以兑换实物礼品、优惠券、视频会员、航空里程等。8万积分大概可以兑换价值约400元的商品。"},
                {"role": "customer", "text": "航空里程怎么换？我经常坐南航的飞机。"},
                {"role": "agent", "text": "XX银行积分可以兑换南航明珠里程，兑换比例大约是25积分换1里程。您的8万积分大概可以换3200南航里程，足够兑换一张短途机票或者升舱。"},
                {"role": "customer", "text": "那就帮我全部换成南航里程吧。"},
            ],
            "完成积分兑换南航里程",
            "satisfied"
        )

    @staticmethod
    def benefits_02() -> tuple:
        """场景：询问权益如何使用"""
        return (
            [
                {"role": "customer", "text": "你好，我的白金卡有机场贵宾厅权益，但是我不知道怎么用？"},
                {"role": "agent", "text": "使用机场贵宾厅非常方便。您只需要在掌上生活APP上提前预约，或者直接到机场贵宾厅前台出示您的白金卡和登机牌即可。目前覆盖深圳、北京、上海、广州等主要机场，部分机场还支持带一位同行人。"},
                {"role": "customer", "text": "需要提前多久预约？"},
                {"role": "agent", "text": "建议提前24小时在APP上预约，部分热门机场（如北京首都T3）最好提前48小时。如果是临时使用直接去前台也可以，但可能排队。另外提醒您，贵宾厅里提供免费餐饮和淋浴设施，可以提前到达机场慢慢享受。"},
                {"role": "customer", "text": "好的谢谢，我下周三飞北京，现在就预约。"},
            ],
            "指导贵宾厅使用流程",
            "satisfied"
        )

    @staticmethod
    def complaint_01() -> tuple:
        """场景：账单争议/投诉"""
        return (
            [
                {"role": "customer", "text": "你们这个账单是怎么回事？我明明已经还清了怎么还说我逾期？"},
                {"role": "agent", "text": "非常抱歉给您带来困扰！我马上帮您核查。请问您的卡号后四位是？"},
                {"role": "customer", "text": "6632。我上个月5号就还了8000块，这个月账单显示我还欠300多，还有逾期记录！"},
                {"role": "agent", "text": "我查到了，您上个月确实还了8000元，但账单总金额是8320元，差额320元因为没有全额还清，系统按最低还款处理并收取了利息。不过逾期记录这边我帮您看一下..."},
                {"role": "customer", "text": "320块的事就给我上征信了？这也太过分了吧！"},
                {"role": "agent", "text": "我理解您的心情。查实确实是您还款时少还了320元。如果您是首次出现这种情况，我可以为您申请减免利息并申请征信异议处理。以后建议您开通自动还款功能，就不会出现这种情况了。"},
                {"role": "customer", "text": "那赶紧帮我处理，以后我开自动还款。"},
            ],
            "申请利息减免并处理征信异议",
            "dissatisfied_to_accepted"
        )

    @staticmethod
    def complaint_02() -> tuple:
        """场景：对年费收取不满"""
        return (
            [
                {"role": "customer", "text": "我今天查账单发现扣了3600的年费，但是我这一年刷了十几万怎么还扣年费？"},
                {"role": "agent", "text": "我帮您查一下。您的经典版白金卡确实有年费减免政策，年度消费满8万元可以免年费。我查一下您本年度的消费总额..."},
                {"role": "agent", "text": "您好，我查到您从去年9月到今年9月这个年费周期内的消费总额是76500元，离8万免年费的标准还差3500元。所以系统自动扣除了年费。"},
                {"role": "customer", "text": "就差3500？这也太亏了吧。我从上个月到现在还有好几笔消费没出账单呢。"},
                {"role": "agent", "text": "我理解您的心情。如果您的消费集中在最近，我建议您可以向客服主管申请年费退回，同时我们可以在下一个年费周期帮您标注提醒。您需要我现在帮您提交吗？"},
                {"role": "customer", "text": "帮我提交吧，以后快到8万的时候能提醒我一下就好了。"},
            ],
            "提交年费减免申请",
            "dissatisfied_to_hopeful"
        )

    @staticmethod
    def dormant_01() -> tuple:
        """场景：长期未使用后确认卡片状态"""
        return (
            [
                {"role": "customer", "text": "你好，我有一张XX银行信用卡很久没用了，想确认一下还能不能用。"},
                {"role": "agent", "text": "好的，我帮您查一下。您的尾号3321的普通信用卡确实有一年多没有交易记录了，但卡片状态还是正常的，可以继续使用。"},
                {"role": "customer", "text": "那不会扣什么费用吧？"},
                {"role": "agent", "text": "您这张普通卡年费100元，但已经满足年度刷卡6次的条件所以不会扣年费。不过如果继续闲置超过两年，系统可能会自动降低额度或者暂停使用。"},
                {"role": "customer", "text": "哦，那我还是偶尔刷一下吧。最近有什么活动吗？"},
                {"role": "agent", "text": "有的！目前我们有'沉睡唤醒'活动，您只要在30天内任意消费一笔就可以获得50元刷卡金，消费满500额外再送5000积分。要不要了解一下？"},
                {"role": "customer", "text": "那挺划算的，我先去楼下便利店刷一笔。"},
            ],
            "唤醒沉睡客户并介绍活动",
            "neutral_to_interested"
        )

    @staticmethod
    def new_user_01() -> tuple:
        """场景：新户开卡咨询"""
        return (
            [
                {"role": "customer", "text": "你好，我刚申请了XX银行信用卡，想问下开卡之后有什么福利？"},
                {"role": "agent", "text": "恭喜您成为XX银行信用卡持卡人！目前新户有三重礼：第一，开卡后30天内任意消费1笔送100元刷卡金；第二，首笔消费满99元可以选XX银行定制礼品（保温杯/蓝牙耳机/U盘三选一）；第三，首次绑定支付宝、微信和云闪付各送10元红包。"},
                {"role": "customer", "text": "这么多！那我需要怎么操作？"},
                {"role": "agent", "text": "很简单，您先下载掌上生活APP用手机号登录，然后在APP里激活卡片。之后日常消费自动就会触发这些奖励。另外建议您开通自动还款功能，这样不会忘记还款，还额外送20元话费券。"},
                {"role": "customer", "text": "好的我马上去下载，谢谢你！"},
            ],
            "新户权益介绍",
            "excited"
        )

    @staticmethod
    def general_01() -> tuple:
        """场景：一般查询"""
        return (
            [
                {"role": "customer", "text": "你好，我换了新手机号，怎么更新信用卡绑定的手机号？"},
                {"role": "agent", "text": "您好，更新手机号可以在掌上生活APP上操作，路径是：我的→设置→安全中心→修改手机号。需要验证身份证号和原手机号接收验证码。如果您原手机号已经不能用了，需要携带身份证到任意XX银行网点办理。"},
                {"role": "customer", "text": "APP上就能改是吧？那我试试。"},
            ],
            "指导手机号更新",
            "neutral"
        )

    @staticmethod
    def general_02() -> tuple:
        """场景：挂失"""
        return (
            [
                {"role": "customer", "text": "喂！我的钱包丢了，信用卡也在里面，能不能马上帮我挂失？"},
                {"role": "agent", "text": "您别急，我现在马上帮您挂失！请告诉我您的姓名和身份证号，我核实身份后立即冻结卡片。"},
                {"role": "customer", "text": "我叫李*芳，身份证号是3101****002。"},
                {"role": "agent", "text": "已核实，李女士，您的尾号8801和6632两张卡已经立即冻结。挂失后卡片所有功能停止，不会产生任何损失。请问您需要补办新卡吗？补办新卡7个工作日内寄到，卡号会改变。"},
                {"role": "customer", "text": "要补办，两张都要。太感谢了！"},
            ],
            "紧急挂失并补办新卡",
            "urgent_to_relieved"
        )


# ============================================================
# 场景分布与意图标签映射
# ============================================================

SCENARIO_DISTRIBUTION = [
    # (方法名, 数量区间, 意图标签, 情感标签)
    ("installment_01", (80, 150), "分期/借贷需求", "anxious"),
    ("installment_02", (60, 100), "分期/借贷需求", "neutral"),
    ("installment_03", (40, 80),  "分期/借贷需求", "anxious"),
    ("cross_border_01", (40, 80),  "跨境/出行需求", "neutral"),
    ("cross_border_02", (30, 60),  "跨境/出行需求", "anxious_to_relieved"),
    ("credit_upgrade_01", (40, 80), "额度/升级需求", "neutral"),
    ("credit_upgrade_02", (30, 60), "额度/升级需求", "satisfied"),
    ("benefits_01", (50, 90),   "权益/优惠需求", "satisfied"),
    ("benefits_02", (40, 80),   "权益/优惠需求", "satisfied"),
    ("complaint_01", (40, 70),  "沉睡/流失风险", "dissatisfied"),
    ("complaint_02", (30, 60),  "沉睡/流失风险", "dissatisfied"),
    ("dormant_01", (30, 60),    "沉睡/流失风险", "neutral_to_interested"),
    ("new_user_01", (40, 80),   "新户/激活引导", "excited"),
    ("general_01", (50, 100),   "一般咨询", "neutral"),
    ("general_02", (30, 60),    "一般咨询", "urgent_to_relieved"),
]


# ============================================================
# 主生成函数
# ============================================================

def generate_all_asr(df_customers: pd.DataFrame):
    print("=" * 60)
    print("生成客服 ASR 对话文本 ...")
    print(f"  目标: ~{N_ASR_TRANSCRIPTS} 条")
    print("=" * 60)

    templates = ASRTemplates()
    cust_ids = df_customers["cust_id"].tolist()
    phones  = df_customers["phone"].tolist()
    cust_phone = dict(zip(cust_ids, phones))

    records = []
    seq = 1

    for method_name, (lo, hi), intent_label, sentiment in SCENARIO_DISTRIBUTION:
        n = random.randint(lo, hi)
        for _ in range(n):
            cid = random.choice(cust_ids)
            phone = cust_phone[cid]
            ts = REFERENCE_DATE - timedelta(days=random.randint(1, 180),
                                             hours=random.randint(0, 23),
                                             minutes=random.randint(0, 59))

            fn = getattr(templates, method_name)
            transcript, resolution, sent_detail = fn()

            records.append({
                "call_id": f"ASR{seq:06d}",
                "cust_id": cid,
                "phone": phone,
                "timestamp": ts.strftime("%Y-%m-%dT%H:%M:%SZ"),
                "duration_sec": random.randint(90, 600),
                "call_direction": random.choices(["inbound","outbound"], weights=[0.8,0.2])[0],
                "call_reason": intent_label,
                "transcript": transcript,
                "resolution": resolution,
                "sentiment_label": sent_detail,
                "intent_label": intent_label,
            })
            seq += 1

    # 写入JSON文件
    saved = 0
    for rec in records:
        fname = f"ASR_{rec['call_id']}.json"
        fpath = os.path.join(ASR_DIR, fname)
        with open(fpath, "w", encoding="utf-8") as f:
            json.dump(rec, f, ensure_ascii=False, indent=2)
        saved += 1

    print(f"\n✅ ASR 对话: {saved} 个文件 → {ASR_DIR}")
    # 统计意图分布
    from collections import Counter
    intent_count = Counter(r["intent_label"] for r in records)
    for k, v in intent_count.most_common():
        print(f"   {k}: {v} ({v/saved*100:.1f}%)")

    return records


if __name__ == "__main__":
    cp = os.path.join(STRUCTURED_DIR, "customer_basic.csv")
    if os.path.exists(cp):
        generate_all_asr(pd.read_csv(cp))
    else:
        print("⚠️ 请先运行 generate_customers.py")
