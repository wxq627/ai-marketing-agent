"""
DeepSeek LLM 客户端 — llm_client.py
=====================================
统一封装 DeepSeek API, 提供:
  - embed(): 文本→向量 (deepseek-chat / 兼容 OpenAI embedding)
  - chat():  对话生成
  - classify_intent(): 意图分类
  - analyze_sentiment(): 情感分析

API Key 从环境变量 DEEPSEEK_API_KEY 读取, 未设置时自动降级为本地Mock。
"""
import os, json, hashlib, numpy as np

DEEPSEEK_API_KEY = os.environ.get("DEEPSEEK_API_KEY", "")  # 设置环境变量启用
DEEPSEEK_BASE_URL = "https://api.deepseek.com/v1"

# 检测是否可用
_available = None

def is_available() -> bool:
    """检查 DeepSeek API 是否可用。"""
    global _available
    if _available is not None:
        return _available
    if not DEEPSEEK_API_KEY:
        _available = False
        return False
    try:
        import requests
        r = requests.get(f"{DEEPSEEK_BASE_URL}/models",
                        headers={"Authorization": f"Bearer {DEEPSEEK_API_KEY}"}, timeout=5)
        _available = r.status_code == 200
    except:
        _available = False
    return _available


def embed(texts, mock_mode=None):
    """文本向量化。支持单条字符串或字符串列表。

    生产: DeepSeek Embedding API
    Mock: 基于文本哈希的确定性伪向量(768维)
    """
    if mock_mode is None:
        mock_mode = not is_available()

    if isinstance(texts, str):
        texts = [texts]

    if mock_mode:
        # 确定性伪向量: 用文本哈希生成
        vectors = []
        for t in texts:
            h = hashlib.sha256(t.encode()).digest()
            # 生成768维伪向量
            vec = np.array([(h[i % len(h)] / 255.0 * 2 - 1) for i in range(768)])
            vec = vec / (np.linalg.norm(vec) + 1e-8)
            vectors.append(vec)
        return np.array(vectors) if len(vectors) > 1 else vectors[0]

    # 真实 API 调用
    try:
        import requests
        resp = requests.post(
            f"{DEEPSEEK_BASE_URL}/embeddings",
            headers={"Authorization": f"Bearer {DEEPSEEK_API_KEY}", "Content-Type": "application/json"},
            json={"model": "deepseek-chat", "input": texts},
            timeout=30
        )
        if resp.status_code == 200:
            data = resp.json()
            vectors = [d["embedding"] for d in data["data"]]
            return np.array(vectors) if len(vectors) > 1 else np.array(vectors[0])
    except Exception as e:
        print(f"DeepSeek Embedding API error: {e}")

    # 降级为mock
    return embed(texts, mock_mode=True)


def chat(messages, temperature=0.7, mock_mode=None):
    """对话生成。

    messages: [{"role":"system","content":"..."}, {"role":"user","content":"..."}]
    """
    if mock_mode is None:
        mock_mode = not is_available()

    if mock_mode:
        user_msg = messages[-1]["content"] if messages else ""
        return _mock_chat(user_msg)

    try:
        import requests
        resp = requests.post(
            f"{DEEPSEEK_BASE_URL}/chat/completions",
            headers={"Authorization": f"Bearer {DEEPSEEK_API_KEY}", "Content-Type": "application/json"},
            json={"model": "deepseek-chat", "messages": messages, "temperature": temperature},
            timeout=60
        )
        if resp.status_code == 200:
            return resp.json()["choices"][0]["message"]["content"]
    except Exception as e:
        print(f"DeepSeek Chat API error: {e}")

    return _mock_chat(messages[-1]["content"] if messages else "")


def classify_intent(conversation_text):
    """意图分类 — 调用 DeepSeek 或本地关键词降级。"""
    if not is_available():
        from intent_engine.llm_classifier import LLMClassifier
        clf = LLMClassifier(mock_mode=True)
        return clf.classify(conversation_text)

    system_prompt = """你是银行信用卡客户意图分析专家。分析对话,识别客户意图和情感。
严格以JSON格式返回,不要有任何其他文字:
{"primary_intent":"分期借贷需求|跨境出行需求|额度升级需求|权益优惠需求|沉睡流失风险|新户激活引导",
 "intent_score":0-100, "sentiment":"焦虑|满意|中性|不满|好奇",
 "anxiety_score":0-100, "satisfaction_score":0-100,
 "key_phrases":["关键词1","关键词2"], "urgency":"高|中|低"}"""

    try:
        result = chat([
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": conversation_text}
        ], temperature=0.3)
        # 尝试解析JSON
        result = result.strip()
        if result.startswith("```"):
            result = result.split("\n", 1)[1].rsplit("\n", 1)[0]
            if result.startswith("json"): result = result[4:]
        return json.loads(result)
    except:
        from intent_engine.llm_classifier import LLMClassifier
        clf = LLMClassifier(mock_mode=True)
        return clf.classify(conversation_text)


def analyze_sentiment(conversation_text):
    """情感分析 — 调用 DeepSeek 或本地降级。"""
    if not is_available():
        return _fallback_sentiment(conversation_text)

    system_prompt = """你是银行客户情感分析专家。分析客户对话,评估情感状态。
严格以JSON格式返回:
{"overall":"焦虑|满意|中性|不满|好奇", "anxiety_score":0-100, "satisfaction_score":0-100,
 "key_evidence":"一句话总结情绪原因", "b_strategy_impact":"对营销策略的一句话建议"}"""

    try:
        result = chat([
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": conversation_text}
        ], temperature=0.3)
        result = result.strip()
        if result.startswith("```"):
            result = result.split("\n", 1)[1].rsplit("\n", 1)[0]
            if result.startswith("json"): result = result[4:]
        return json.loads(result)
    except:
        return _fallback_sentiment(conversation_text)


def _mock_chat(user_msg):
    """本地Mock对话(降级方案)。"""
    if "分期" in user_msg or "手续费" in user_msg:
        return '{"primary_intent":"分期借贷需求","intent_score":75,"sentiment":"焦虑","anxiety_score":65,"satisfaction_score":35,"key_phrases":["分期","手续费"],"urgency":"高"}'
    if "权益" in user_msg or "白金" in user_msg or "贵宾厅" in user_msg:
        return '{"primary_intent":"权益优惠需求","intent_score":70,"sentiment":"中性","anxiety_score":30,"satisfaction_score":60,"key_phrases":["权益","白金卡"],"urgency":"中"}'
    return '{"primary_intent":"分期借贷需求","intent_score":50,"sentiment":"中性","anxiety_score":30,"satisfaction_score":60,"key_phrases":["咨询"],"urgency":"中"}'


def _fallback_sentiment(text):
    """情感分析降级方案。"""
    anxiety = 20; satisfaction = 60
    if any(w in text for w in ["压力","还不上","太高","逾期","投诉","销户"]): anxiety += 30
    if any(w in text for w in ["谢谢","很好","不错","满意","优惠","权益"]): satisfaction += 15
    if any(w in text for w in ["销户","注销","投诉"]): satisfaction -= 20
    anxiety = min(100, max(0, anxiety)); satisfaction = min(100, max(0, satisfaction))
    overall = "焦虑" if anxiety >= 60 else ("满意" if satisfaction >= 70 else "中性")
    return {"overall": overall, "anxiety_score": anxiety, "satisfaction_score": satisfaction,
            "key_evidence": text[:60], "b_strategy_impact": "按标准策略执行"}


# 启动时打印状态
if is_available():
    print(f"[LLM] DeepSeek API 已连接 ({DEEPSEEK_BASE_URL})")
else:
    print(f"[LLM] DeepSeek API 未配置, 使用本地Mock降级。设置环境变量 DEEPSEEK_API_KEY 启用。")
