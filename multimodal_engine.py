"""
多模态搜索引擎 v5 — 普适化 视觉LLM → 关键词 → 语义验证 三步检索
==============================================================
适用范围: 任何图片 (海报/截图/照片), 不依赖预生成JSON。

核心流程（普适化，任意新图片适用）:
  Step0 [预处理/缓存]: 视觉LLM识别图片 → 结构化文本描述 + 核心关键词提取
  Step1 [关键词]:    精准匹配 + 上下文共现验证（杜绝「猫吉祥物→天猫」假阳性）
  Step2 [语义]:      嵌入向量余弦相似度 → 全局语义相关性
  Step3 [LLM终判]:   DeepSeek 相关性评分 → 严格闸门过滤

假阳性控制策略（三层）:
  第1层: 关键词必须在图片文本中有「实质性匹配」，而非单字或间接出现
  第2层: 嵌入语义相似度必须超过最低阈值，过滤语义完全无关的图片
  第3层: LLM 终判 0-10 分，<4 分直接丢弃，不展示

版本: v5.20260720 | 关键修复: JSON fallback不含visual_description | Mock嵌入基于关键词重叠
      纯数字短子串跳过 | 降级相关判断基于结构匹配非字符重叠
"""

__version__ = "v5.20260720"

import os, json, glob, re, base64, hashlib, time, pytesseract, numpy as np
from PIL import Image
from typing import List, Dict, Optional, Tuple
from io import BytesIO

BASE = os.path.dirname(os.path.abspath(__file__))
POSTERS_DIR = os.path.join(BASE, "mock_data", "unstructured", "posters")
POSTERS_IMG_DIR = os.path.join(POSTERS_DIR, "images")
CACHE_DIR = os.path.join(POSTERS_DIR, ".vision_cache")
os.makedirs(POSTERS_IMG_DIR, exist_ok=True)
os.makedirs(CACHE_DIR, exist_ok=True)

# ═══════════════════════════════════════════════════════════════
# 工具函数
# ═══════════════════════════════════════════════════════════════

def _img_to_base64(image_path: str) -> str:
    """将图片文件转为 base64 data URL (用于视觉LLM)。"""
    with open(image_path, "rb") as f:
        data = base64.b64encode(f.read()).decode("utf-8")
    ext = os.path.splitext(image_path)[1].lower().replace(".", "")
    mime = "image/jpeg" if ext in ("jpg", "jpeg") else "image/png"
    return f"data:{mime};base64,{data}"


def _cache_key(image_path: str) -> str:
    """基于文件内容的缓存键 (SHA256前16位)。"""
    with open(image_path, "rb") as f:
        return hashlib.sha256(f.read()).hexdigest()[:16]


def _load_vision_cache(cache_key: str) -> Optional[Dict]:
    """加载视觉LLM缓存结果。"""
    cache_file = os.path.join(CACHE_DIR, f"{cache_key}.json")
    if os.path.exists(cache_file):
        with open(cache_file, "r", encoding="utf-8") as f:
            return json.load(f)
    return None


def _save_vision_cache(cache_key: str, data: Dict):
    """保存视觉LLM缓存结果。"""
    cache_file = os.path.join(CACHE_DIR, f"{cache_key}.json")
    with open(cache_file, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


# ═══════════════════════════════════════════════════════════════
# tesseract OCR 配置
# ═══════════════════════════════════════════════════════════════

_tess_ready = False

def _init_tesseract() -> bool:
    """初始化 tesseract OCR。"""
    global _tess_ready
    if _tess_ready:
        return True
    for p in [
        r"C:\Program Files\Tesseract-OCR\tesseract.exe",
        r"C:\Program Files (x86)\Tesseract-OCR\tesseract.exe",
    ]:
        if os.path.exists(p):
            pytesseract.pytesseract.tesseract_cmd = p
            _tess_ready = True
            return True
    for td in ["tessdata", os.path.expandvars(r"%LOCALAPPDATA%\tessdata")]:
        if os.path.exists(os.path.join(td, "chi_sim.traineddata")):
            os.environ["TESSDATA_PREFIX"] = os.path.dirname(td)
    return False


# ═══════════════════════════════════════════════════════════════
# Step0: 视觉LLM 图片识别 (普适化核心 — 任意图片适用)
# ═══════════════════════════════════════════════════════════════

def vision_recognize(image_path: str, use_cache: bool = True) -> Dict:
    """
    用视觉LLM识别任意图片的内容，返回结构化描述。

    优先级:
      1. DeepSeek Vision API (最准确，适用于任意图片)
      2. tesseract OCR + LLM 文本理解 (降级)
      3. JSON metadata (仅兼容旧数据)

    结果缓存到磁盘，避免重复调用API。
    """
    ck = _cache_key(image_path)
    if use_cache:
        cached = _load_vision_cache(ck)
        if cached:
            return cached

    result = None

    # ── 方案1: DeepSeek Vision API ──
    try:
        from llm_client import is_available, chat
        if is_available():
            b64_url = _img_to_base64(image_path)
            # 使用 DeepSeek 视觉能力识别图片
            prompt = """请仔细分析这张图片，并按以下JSON格式输出（只输出JSON，不要其他文字）:
{
  "main_topic": "图片主题/活动名称(简短一句话)",
  "all_text": "图片中出现的所有文字，逐条列出，用|分隔",
  "key_entities": ["核心实体1", "核心实体2", ...],
  "target_audience": "目标人群描述",
  "category": "图片类别(如:电商促销/节日活动/客户关怀/产品推广/其他)",
  "keywords": ["关键词1", "关键词2", ...]
}"""
            resp = chat(
                [
                    {
                        "role": "user",
                        "content": [
                            {"type": "image_url", "image_url": {"url": b64_url}},
                            {"type": "text", "text": prompt},
                        ],
                    }
                ],
                temperature=0.1,
            )
            # 尝试解析JSON
            resp = resp.strip()
            if resp.startswith("```"):
                resp = resp.split("\n", 1)[1].rsplit("\n", 1)[0]
                if resp.startswith("json"):
                    resp = resp[4:]
            result = json.loads(resp)
            result["_source"] = "vision_llm"
    except Exception as e:
        pass  # 降级到OCR

    # ── 方案2: tesseract OCR + LLM理解 ──
    if result is None:
        ocr_text = _ocr_tesseract(image_path)
        if ocr_text:
            try:
                from llm_client import is_available, chat
                if is_available():
                    prompt = f"""请根据OCR识别结果分析图片内容，按JSON格式输出:
{{
  "main_topic": "图片主题(简短一句话)",
  "all_text": "原文复制OCR内容",
  "key_entities": ["核心实体"],
  "target_audience": "目标人群",
  "category": "图片类别",
  "keywords": ["关键词"]
}}
OCR内容: {ocr_text[:800]}"""
                    resp = chat([{"role": "user", "content": prompt}], temperature=0.1)
                    resp = resp.strip()
                    if resp.startswith("```"):
                        resp = resp.split("\n", 1)[1].rsplit("\n", 1)[0]
                        if resp.startswith("json"):
                            resp = resp[4:]
                    result = json.loads(resp)
                    result["_source"] = "ocr+llm"
            except Exception:
                pass

    # ── 方案3: JSON metadata fallback ──
    if result is None:
        json_text = _json_fallback_text(image_path)
        result = {
            "main_topic": "",
            "all_text": json_text,
            "key_entities": [],
            "target_audience": "",
            "category": "未知",
            "keywords": [],
            "_source": "json_fallback",
        }
        # 从JSON补充main_topic
        info = _poster_info(image_path)
        if info:
            result["main_topic"] = info.get("activity_name", "")
            result["target_audience"] = info.get("target_segment", "")

    # ── 缓存 ──
    if result:
        result["_cached_at"] = time.time()
        _save_vision_cache(ck, result)

    return result


def _ocr_tesseract(image_path: str) -> str:
    """tesseract OCR提取文字。"""
    if not _init_tesseract():
        return ""
    try:
        img = Image.open(image_path)
        text = pytesseract.image_to_string(img, lang="chi_sim+eng", config="--psm 6")
        text = text.strip()
        chinese_chars = sum(1 for c in text if "一" <= c <= "鿿")
        if chinese_chars >= 3:
            return text
    except Exception:
        pass
    return ""


def _json_fallback_text(image_path: str) -> str:
    """从JSON metadata构造文本。"""
    info = _poster_info(image_path)
    if not info:
        return ""
    # 只拼接有意义的信息字段，不包含 visual_description（容易引入噪声）
    parts = [
        info.get("activity_name", ""),
        info.get("main_title", ""),
        info.get("sub_title", ""),
        info.get("target_segment", ""),
        info.get("cta_text", ""),
    ]
    parts.extend(info.get("rules_summary", []))
    return " | ".join(p for p in parts if p)


def _poster_info(image_path: str) -> Dict:
    """反查海报JSON信息。"""
    json_name = os.path.splitext(os.path.basename(image_path))[0] + ".json"
    jp = os.path.join(POSTERS_DIR, json_name)
    if os.path.exists(jp):
        with open(jp, "r", encoding="utf-8") as f:
            return json.load(f)
    return {}


# ═══════════════════════════════════════════════════════════════
# Step1: 关键词精准匹配 (含上下文验证)
# ═══════════════════════════════════════════════════════════════

def keyword_match_strict(query: str, text: str) -> Tuple[float, List[str]]:
    """
    严格关键词匹配 — 杜绝假阳性。

    匹配规则（按优先级）:
      1. 完整词匹配: query完整出现在text中 → 最高权重 (30分/次)
      2. 实体级匹配: query作为独立词(前后有空格/标点/行首尾)出现 → 额外加分
      3. 子串匹配: 仅当子串长度>=2且query为复合词时(如"天猫"→子串"天猫"本身)
         —— 不对单字做匹配，避免"猫吉祥物"误匹配"天猫"
      4. 反向验证: 匹配到的文本上下文是否与query语义一致

    返回: (score, matched_terms)
    """
    score = 0.0
    matched = []
    qlen = len(query)

    if not query or not text:
        return 0.0, []

    # ── 规则1: 完整词匹配 ──
    cnt_full = text.count(query)
    if cnt_full > 0:
        # 完整匹配权重: 30分 × 出现次数 × 查询长度因子
        score += cnt_full * 30.0 * min(qlen / 2, 2.0)
        matched.append(query)

    # ── 规则2: 边界匹配（query作为独立词出现） ──
    # 前后有空格、标点、或行首行尾
    boundary_pattern = re.compile(
        r"(?:^|[\s\|\.\,\!\?\;\:\"\'\(\)\[\]\{\}，。！？；：""''（）【】《》\n])"
        + re.escape(query)
        + r"(?:$|[\s\|\.\,\!\?\;\:\"\'\(\)\[\]\{\}，。！？；：""''（）【】《》\n])"
    )
    cnt_boundary = len(boundary_pattern.findall(text))
    if cnt_boundary > 0:
        score += cnt_boundary * 15.0  # 边界匹配额外加分

    # ── 规则3: 子串匹配 (仅限有意义的长子串) ──
    # query本身已经在规则1中处理过了
    # 这里只处理 query长度>=3 时的有意义子串
    if qlen >= 3:
        for L in [4, 3]:  # 只匹配3-4字子串
            for i in range(qlen - L + 1):
                sub = query[i : i + L]
                if sub == query:
                    continue  # 完整词已在规则1处理
                if sub in matched:
                    continue
                # 跳过纯数字短子串 (如"618"→"18", 数字太常见)
                if sub.isdigit():
                    continue
                cnt = text.count(sub)
                if cnt > 0:
                    matched.append(sub)
                    score += cnt * L * 3.0  # 子串低权重

    # ── 规则4: 上下文验证 ──
    # 对每个匹配到的词，检查是否真的是相关内容
    # 例: "猫吉祥物"匹配了"猫"但这不是"天猫"
    if matched:
        for term in matched:
            # 如果匹配词较短 (2字)，检查前后文是否改变了含义
            if len(term) == 2:
                idx = text.find(term)
                if idx >= 0:
                    # 取匹配位置前后各一个字符的上下文
                    ctx_start = max(0, idx - 1)
                    ctx_end = min(len(text), idx + len(term) + 1)
                    ctx = text[ctx_start:ctx_end]
                    # 如果上下文中出现了否定或改变含义的词，降低分数
                    # 例如："吉祥物猫" → "猫"匹配了"天猫"查询，但上下文是"吉祥物"
                    negation_words = ["吉祥物", "玩具", "宠物", "动物", "卡通"]
                    if any(nw in ctx for nw in negation_words):
                        score *= 0.2  # 大幅降低权重
                        break

    return score, matched


# ═══════════════════════════════════════════════════════════════
# Step2: 嵌入语义相似度
# ═══════════════════════════════════════════════════════════════

def embedding_similarity(query: str, text: str) -> float:
    """
    计算查询词与图片文本的语义相似度。

    生产模式: DeepSeek Embedding API → 余弦相似度
    Mock模式: 关键词重叠率 → 伪相似度 (避免随机hash向量误杀)
    """
    if not query or not text:
        return 0.0

    try:
        from llm_client import embed, is_available
        if is_available():
            # ── 生产模式: 真实嵌入向量 ──
            q_vec = embed(query)
            t_vec = embed(text[:500])
            cos_sim = np.dot(q_vec, t_vec) / (np.linalg.norm(q_vec) * np.linalg.norm(t_vec) + 1e-8)
            return float(max(0.0, cos_sim))
        else:
            # ── Mock模式: 关键词重叠率伪相似度 ──
            # 不能用hash伪向量(高维空间余弦≈0), 改用有意义的文本重叠
            return _mock_similarity(query, text)
    except Exception:
        return _mock_similarity(query, text)


def _mock_similarity(query: str, text: str) -> float:
    """Mock模式下的伪语义相似度 — 基于关键词匹配而非字符重叠。

    计算方式:
      - 完整词匹配: query完整出现在text中 → 0.6~0.9
      - 子串匹配: query的有意义子串出现 → 0.3~0.5
      - 无匹配 → 0.05~0.15 (不直接给0, 留给LLM终判决定)
    """
    qlen = len(query)
    if query in text:
        # 完整匹配: 基础0.5, 文本越短相似度越高
        ratio = min(len(query) / max(len(text.split()), 1), 1.0)
        return 0.5 + ratio * 0.4  # 0.5~0.9 range

    # 子串匹配
    best_overlap = 0
    for L in [4, 3, 2]:
        for i in range(max(0, qlen - L + 1)):
            sub = query[i:i+L]
            if len(sub) >= 2 and sub in text:
                best_overlap = max(best_overlap, len(sub) / qlen)

    if best_overlap > 0:
        return 0.25 + best_overlap * 0.3  # 0.25~0.55 range

    # 无直接匹配: 给一个低基准值, 不直接判死
    return 0.08


# ═══════════════════════════════════════════════════════════════
# Step3: LLM 语义终判
# ═══════════════════════════════════════════════════════════════

def llm_relevance_judge(query: str, image_text: str) -> Tuple[int, str]:
    """
    用LLM做最终相关性判断 (0-10分)。
    - 0-3: 无关，不展示
    - 4-6: 弱相关，需结合其他分数
    - 7-10: 明确相关，展示

    返回: (score, reason)
    """
    try:
        from llm_client import chat, is_available
        if not is_available():
            return _fallback_relevance(query, image_text)

        prompt = f"""你是银行营销素材相关性判断专家。判断搜索词与图片内容是否相关。
只输出一个0-10的整数和一句简短理由，格式: "分数|理由"

搜索词: {query}
图片内容: {image_text[:400]}

判断标准:
- 0-3分: 完全无关或仅极微弱关联(如搜索"天猫"但图片是"猫吉祥物"，这不相关)
- 4-6分: 有一定关联但不是核心内容
- 7-10分: 明确相关，搜索词是图片的核心主题或重要元素

请判断:"""

        resp = chat([{"role": "user", "content": prompt}], temperature=0.0)
        resp = resp.strip()

        # 解析 "分数|理由"
        if "|" in resp:
            parts = resp.split("|", 1)
            digits = "".join(c for c in parts[0] if c.isdigit())
            score = min(10, max(0, int(digits) if digits else 0))
            reason = parts[1].strip()
        else:
            digits = "".join(c for c in resp if c.isdigit())
            score = min(10, max(0, int(digits) if digits else 0))
            reason = resp

        return score, reason
    except Exception:
        return _fallback_relevance(query, image_text)


def _fallback_relevance(query: str, text: str) -> Tuple[int, str]:
    """降级相关性判断 (无LLM时使用) — 基于关键词结构匹配, 杜绝字符重叠假阳性。

    规则:
      - 完整词匹配 → 高相关 (8-10分)
      - 有意义子串匹配 → 中相关 (5-7分)
      - 关键词出现在标题/重要位置 → 额外加分
      - 不存在任何匹配 → 0-3分 (由嵌入相似度决定)
    """
    if not query or not text:
        return 0, "空输入"

    qlen = len(query)

    # ── 规则1: 完整词匹配 (最高置信度) ──
    if query in text:
        cnt = text.count(query)
        if cnt >= 2:
            return 10, f"多次完整匹配: 出现{cnt}次"
        return 8, "完整匹配"

    # ── 规则2: 有意义子串匹配 ──
    # 仅当子串长度>=2, 且子串不因单字拆分而产生
    best_sub = ""
    best_len = 0
    for L in [4, 3, 2]:
        for i in range(max(0, qlen - L + 1)):
            sub = query[i : i + L]
            if len(sub) >= 2 and sub in text:
                # 跳过纯数字短子串 (数字太常见, 容易假阳性)
                if sub.isdigit() and len(sub) <= 3:
                    continue
                if len(sub) > best_len:
                    best_sub = sub
                    best_len = len(sub)

    if best_sub:
        cnt = text.count(best_sub)
        # 子串越长, 置信度越高
        if best_len >= 3:
            score = min(7, 5 + cnt)
            return score, f"子串匹配: '{best_sub}'出现{cnt}次"
        else:
            # 2字子串: 需要额外验证不是意外匹配
            # 检查子串是否作为独立词出现（而非长词的一部分）
            idx = text.find(best_sub)
            if idx >= 0:
                ctx_start = max(0, idx - 1)
                ctx_end = min(len(text), idx + best_len + 1)
                ctx = text[ctx_start:ctx_end]
                # 检查是否被其他词裹挟 (如 "猫吉祥物" 中的 "猫")
                false_positive_markers = [
                    "吉祥物", "玩具", "宠物", "动物", "卡通", "流浪",
                ]
                if any(m in ctx for m in false_positive_markers):
                    return 2, f"可能假阳性: '{best_sub}'上下文为'{ctx}'"
            score = min(5, 3 + cnt)
            return score, f"短子串匹配: '{best_sub}'出现{cnt}次"

    # ── 规则3: 完全无匹配 ──
    return 0, "无关键词匹配"


# ═══════════════════════════════════════════════════════════════
# 主入口: 多模态搜索
# ═══════════════════════════════════════════════════════════════

def multimodal_search(
    query: str,
    top_k: int = 8,
    min_relevance: int = 4,  # LLM相关性最低分 (0-10), <此分直接丢弃
    min_embed_sim: float = None,  # 最低嵌入相似度阈值 (None=自动选择)
) -> List[Dict]:
    """
    多模态搜索 — 普适化三步流程，适用于任意图片。

    流程:
      对每张图片:
        1. 视觉LLM识别 → 结构化文本
        2. 关键词精准匹配 + 嵌入相似度
        3. LLM相关性终判
      最终: 严格过滤 → 排序 → 返回

    参数:
      query: 搜索关键词
      top_k: 最多返回条数
      min_relevance: LLM相关性最低分 (0-10), 低于此分直接丢弃
      min_embed_sim: 最低嵌入相似度阈值 (None=自动: 生产0.20, Mock 0.06)

    返回: 仅包含真正相关的图片结果
    """
    if not query or len(query) < 1:
        return []

    # 自动选择嵌入阈值
    if min_embed_sim is None:
        try:
            from llm_client import is_available
            min_embed_sim = 0.20 if is_available() else 0.06
        except Exception:
            min_embed_sim = 0.06

    results = []
    img_files = glob.glob(os.path.join(POSTERS_IMG_DIR, "*.png"))

    if not img_files:
        # 无图片时降级到纯JSON搜索
        return _json_only_search(query, top_k)

    for fp in img_files:
        # ── Step0: 视觉LLM识别图片内容 (含缓存) ──
        vision = vision_recognize(fp, use_cache=True)
        if not vision:
            continue

        # 构建用于匹配的全文 (优先级: all_text > main_topic + keywords)
        full_text = vision.get("all_text", "")
        topic = vision.get("main_topic", "")
        keywords_list = vision.get("keywords", [])
        category = vision.get("category", "")

        # 组合文本: 主题 + 关键词 + 全文
        composite_text = f"{topic} | {' '.join(keywords_list)} | {category} | {full_text}"

        if not composite_text.strip():
            continue

        # ── Step1: 关键词精准匹配 ──
        kw_score, matched_terms = keyword_match_strict(query, composite_text)

        # ── Step2: 嵌入语义相似度 ──
        embed_sim = embedding_similarity(query, composite_text)

        # 嵌入相似度过低 → 直接跳过 (第2层过滤)
        if embed_sim < min_embed_sim:
            continue

        # ── Step3: LLM相关性终判 ──
        llm_score, llm_reason = llm_relevance_judge(query, composite_text)

        # LLM终判分数 < min_relevance → 直接丢弃 (第3层过滤)
        if llm_score < min_relevance:
            continue

        # ── 综合评分 ──
        # keyword: 0-150+  (缩小到0-50)
        # embed:   0.0-1.0 (放大到0-30)
        # llm:     0-10    (放大到0-40)
        kw_norm = min(kw_score / 3.0, 50.0)
        embed_norm = embed_sim * 30.0
        llm_norm = llm_score * 4.0

        total = kw_norm + embed_norm + llm_norm

        # 最低总分阈值
        MIN_TOTAL = 15.0
        if total < MIN_TOTAL:
            continue

        results.append(
            {
                "source_type": "multimodal_v5",
                "title": topic,
                "content": full_text[:200] if full_text else composite_text[:200],
                "category": category,
                "keywords": keywords_list[:8],
                "image_path": fp,
                "score": round(total, 1),
                "kw_score": round(kw_score, 1),
                "embed_sim": round(embed_sim, 3),
                "llm_relevance": llm_score,
                "llm_reason": llm_reason,
                "matched_terms": matched_terms[:5],
                "vision_source": vision.get("_source", "unknown"),
            }
        )

    # ── 排序 + 去重 ──
    results.sort(key=lambda x: x["score"], reverse=True)

    # 去重: 相同标题只保留最高分
    seen_titles = set()
    unique = []
    for r in results:
        title_key = r["title"][:30]
        if title_key and title_key in seen_titles:
            continue
        if title_key:
            seen_titles.add(title_key)
        unique.append(r)

    return unique[:top_k]


def _json_only_search(query: str, top_k: int = 8) -> List[Dict]:
    """纯JSON搜索 (无图片时的降级方案)。"""
    results = []
    json_files = glob.glob(os.path.join(POSTERS_DIR, "*.json"))
    for jf in json_files:
        with open(jf, "r", encoding="utf-8") as f:
            info = json.load(f)
        text = _json_fallback_text(jf.replace(".json", ".png"))  # 构造文本
        kw_score, matched = keyword_match_strict(query, text)
        embed_sim = embedding_similarity(query, text)
        llm_score, llm_reason = llm_relevance_judge(query, text)

        if llm_score < 4 or embed_sim < 0.15:
            continue

        total = min(kw_score / 3.0, 50.0) + embed_sim * 30.0 + llm_score * 4.0
        if total < 15:
            continue

        results.append(
            {
                "source_type": "json_fallback",
                "title": info.get("activity_name", ""),
                "content": text[:200],
                "score": round(total, 1),
                "kw_score": round(kw_score, 1),
                "embed_sim": round(embed_sim, 3),
                "llm_relevance": llm_score,
                "llm_reason": llm_reason,
                "matched_terms": matched[:5],
                "vision_source": "json_fallback",
            }
        )

    results.sort(key=lambda x: x["score"], reverse=True)
    return results[:top_k]


# ═══════════════════════════════════════════════════════════════
# 批量预处理 (可选: 提前对图片做视觉识别)
# ═══════════════════════════════════════════════════════════════

def preprocess_all_images(force: bool = False):
    """
    批量预处理所有图片 (调用视觉LLM识别并缓存)。
    可在系统初始化时调用一次，后续搜索直接使用缓存。
    """
    img_files = glob.glob(os.path.join(POSTERS_IMG_DIR, "*.png"))
    results = {}
    for i, fp in enumerate(img_files):
        name = os.path.basename(fp)
        ck = _cache_key(fp)
        if not force and _load_vision_cache(ck):
            results[name] = "cached"
            continue
        try:
            vision = vision_recognize(fp, use_cache=False)
            results[name] = f"ok ({vision.get('_source', '?')})"
        except Exception as e:
            results[name] = f"error: {e}"
    return results


# ═══════════════════════════════════════════════════════════════
# 命令行测试
# ═══════════════════════════════════════════════════════════════

def search_and_display(query: str, top_k: int = 8):
    """命令行友好输出。"""
    results = multimodal_search(query, top_k=top_k)
    print(f"\n{'='*70}")
    print(f'  搜索: "{query}"  →  找到 {len(results)} 条相关结果')
    print(f"{'='*70}")
    if not results:
        print("  (无相关结果 — 不相关的内容已被过滤)")
        return results

    for i, r in enumerate(results):
        print(f"  [{i+1}] {r['title'][:35]}  |  score={r['score']:.1f}")
        print(f"      关键词分={r['kw_score']:.1f}  嵌入相似={r['embed_sim']:.3f}  LLM相关={r['llm_relevance']}/10")
        if r.get("llm_reason"):
            print(f"      LLM: {r['llm_reason'][:60]}")
        if r.get("matched_terms"):
            print(f"      匹配词: {r['matched_terms']}")
        print(f"      来源: {r.get('vision_source', '?')}")
    return results


if __name__ == "__main__":
    # 先批量预处理 (可选)
    print("预处理图片 (视觉LLM识别)...")
    preprocess_all_images()

    # 测试搜索
    test_queries = ["天猫", "返现", "毕业生", "618", "分期", "大促", "双十一", "生日", "沉睡"]
    for kw in test_queries:
        search_and_display(kw)
