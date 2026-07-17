"""模块五: 意图识别引擎 测试"""
import os, sys, json
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from intent_engine.rule_scorer import RuleScorer
from intent_engine.llm_classifier import LLMClassifier, SentimentAnalyzer

PASS = FAIL = 0
def check(name, cond, detail=""):
    global PASS, FAIL
    if cond: PASS += 1; print(f"  [PASS] {name}")
    else: FAIL += 1; print(f"  [FAIL] {name} - {detail}")

print("=" * 60)
print("模块五: 意图识别引擎 测试")
print("=" * 60)

# ================================================================
# 1. 规则评分引擎
# ================================================================
print("\n[1] 规则评分引擎")
scorer = RuleScorer()

# 测试1: 分期需求强烈的客户
profile1 = {
    "lifecycle_stage": "成熟期", "usage_rate": 0.78,
    "income_level": "M", "card_level": "金卡",
    "search_keywords_7d": "分期费率 12期 最低还款",
}
events1 = {
    "search_keywords": "分期费率 12期 最低还款 账单分期",
    "browse_pages": "分期计算器 分期计算器 分期计算器 账单详情",
    "overdue_count": 0, "min_payment_count": 2, "complaint_count": 0,
}
r1 = scorer.score_all(profile1, events1)
check("6类意图全部输出", len(r1["intents"]) == 6)
check(f"主意图=分期 {r1['primary_intent']}", "分期" in r1["primary_intent"])
inst = [i for i in r1["intents"] if "分期" in i["type"]][0]
check(f"分期评分>40 (got {inst['score']})", inst["score"] >= 40)
check("有sub_signals", len(inst["sub_signals"]) > 0)
for s in inst["sub_signals"][:3]:
    print(f"    signal: {s['signal']} value={s['value']} weight={s['weight']}")

# 测试2: 沉睡风险客户
profile2 = {"lifecycle_stage": "沉睡期", "usage_rate": 0.05, "income_level": "L", "card_level": "普卡"}
events2 = {"search_keywords": "销户 注销", "browse_pages": "", "overdue_count": 0, "min_payment_count": 0, "complaint_count": 1}
r2 = scorer.score_all(profile2, events2)
dormant = [i for i in r2["intents"] if "沉睡" in i["type"]][0]
check(f"沉睡风险>30 (got {dormant['score']})", dormant["score"] >= 30)

# 测试3: 新户
profile3 = {"lifecycle_stage": "新户", "usage_rate": 0.1, "income_level": "M", "card_level": "普卡"}
events3 = {"search_keywords": "开卡 激活", "browse_pages": "新手指引", "overdue_count": 0, "min_payment_count": 0, "complaint_count": 0}
r3 = scorer.score_all(profile3, events3)
new_cust = [i for i in r3["intents"] if "新户" in i["type"]][0]
check(f"新户意图>20 (got {new_cust['score']})", new_cust["score"] >= 20)

print(f"\n[1] Result: {PASS}/{PASS+FAIL}")

# ================================================================
# 2. LLM 分类器
# ================================================================
print("\n[2] LLM分类器 (Mock)")
classifier = LLMClassifier(mock_mode=True)

conv1 = "你好我这个月账单18500太高了实在还不上帮我查一下12期分期的手续费"
r = classifier.classify(conv1)
check("主意图=分期", "分期" in r["primary_intent"])
check(f"intent_score>50 (got {r['intent_score']})", r["intent_score"] >= 50)
check("sentiment有值", r["sentiment"] in ["焦虑","中性","不满","满意","好奇"])
check("key_phrases有值", len(r.get("key_phrases", [])) > 0)
print(f"  primary={r['primary_intent']} score={r['intent_score']} sentiment={r['sentiment']} phrases={r.get('key_phrases',[])}")

conv2 = "我想问一下去日本旅游的话用哪张卡比较好境外消费有返现吗"
r2 = classifier.classify(conv2)
check("主意图=出行", "出行" in r2["primary_intent"])
print(f"  primary={r2['primary_intent']} score={r2['intent_score']} sentiment={r2['sentiment']}")

# ================================================================
# 3. 情感分析
# ================================================================
print("\n[3] 情感分析")
analyzer = SentimentAnalyzer(mock_mode=True)

for label in ["焦虑", "满意", "中性", "不满", "好奇"]:
    s = analyzer.analyze(label)
    check(f"{label}: anxiety={s['anxiety_score']} satisfaction={s['satisfaction_score']}",
          s["overall"] == label)
    print(f"    {label}: anxiety={s['anxiety_score']} satisfaction={s['satisfaction_score']} key={s['key_evidence'][:30]}")

# ================================================================
# 4. 趋势判断
# ================================================================
print("\n[4] 趋势判断")
check("rising", scorer.compute_trend(80, 50) == "rising")
check("falling", scorer.compute_trend(30, 70) == "falling")
check("stable", scorer.compute_trend(55, 50) == "stable")

# ================================================================
print(f"\n{'='*60}")
print(f"Result: {PASS} PASS, {FAIL} FAIL")
if FAIL == 0: print("ALL TESTS PASSED!")
print("=" * 60)
