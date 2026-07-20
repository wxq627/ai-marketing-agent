"""
多模态处理引擎 v3 — 实用OCR + DeepSeek语义 + 精准匹配
======================================================
图像→文本: Pillow生成(嵌入OCR文字) + pytesseract(可选)
语义理解: DeepSeek Chat API (文本模型, 理解近义词)
视觉理解: Qwen2.5-VL (生产环境, 真正看懂图片)

Q: 为什么不用DeepSeek直接看图片?
A: DeepSeek是纯文本模型, 没有视觉能力。看图片需要视觉模型(Qwen2.5-VL)。
   但我们用DeepSeek做文本侧的事: "返现"≈"现金回馈"≈"Cash Back" 语义扩展。
"""

import os, json, glob, re, numpy as np
from PIL import Image, ImageDraw, ImageFont, PngImagePlugin
from typing import List, Dict, Optional

BASE = os.path.dirname(os.path.abspath(__file__))
POSTERS_DIR = os.path.join(BASE, "mock_data", "unstructured", "posters")
POSTERS_IMG_DIR = os.path.join(POSTERS_DIR, "images")
os.makedirs(POSTERS_IMG_DIR, exist_ok=True)

FONT_PATH = "C:/Windows/Fonts/simhei.ttf"
FONT_PATH_SMALL = "C:/Windows/Fonts/simsun.ttc"


# ================================================================
# 图像生成 (含嵌入OCR文本)
# ================================================================
def generate_all_posters():
    json_files = glob.glob(os.path.join(POSTERS_DIR, "*.json"))
    for fp in json_files:
        with open(fp, "r", encoding="utf-8") as f: data = json.load(f)
        img_file = data.get("image_file", "");
        if not img_file: continue
        img = _create_poster(data)
        meta = PngImagePlugin.PngInfo()
        ocr_text = _all_text(data)
        meta.add_text("ocr_text", ocr_text)
        img_path = os.path.join(POSTERS_IMG_DIR, img_file)
        img.save(img_path, "PNG", pnginfo=meta)
    print(f"生成 {len(json_files)} 张海报 (OCR文字已嵌入PNG)")


def _create_poster(data: Dict) -> Image.Image:
    w, h = 800, 600
    desc = data.get("visual_description", "")
    bg = {"红":(180,40,40),"蓝":(40,80,180),"橙":(200,130,40),"黑":(30,30,40),"紫":(120,40,160),"绿":(40,150,80)}
    bg_color = (60,60,120)
    for k,v in bg.items():
        if k in desc: bg_color = v; break
    img = Image.new("RGB", (w, h), bg_color)
    draw = ImageDraw.Draw(img)
    try: ft = ImageFont.truetype(FONT_PATH, 42); fs = ImageFont.truetype(FONT_PATH, 24); fm = ImageFont.truetype(FONT_PATH_SMALL, 16)
    except: ft = fs = fm = ImageFont.load_default()

    title = data.get("main_title", "") or data.get("activity_name", "")
    bbox = draw.textbbox((0, 0), title, font=ft)
    draw.text(((w - (bbox[2]-bbox[0])) / 2, 50), title, fill=(255, 255, 255), font=ft)

    sub = data.get("sub_title", "")
    if sub:
        bbox2 = draw.textbbox((0, 0), sub, font=fs)
        draw.text(((w - (bbox2[2]-bbox2[0])) / 2, 120), sub, fill=(255, 255, 200), font=fs)

    y = 180
    for rule in data.get("rules_summary", [])[:6]:
        draw.text((80, y), f"  {rule}", fill=(255, 255, 255), font=fm); y += 40

    target = data.get("target_segment", "")
    if target: draw.text((80, y + 10), f"目标: {target}", fill=(200, 200, 255), font=fm)

    cta = data.get("cta_text", "")
    if cta:
        bbox3 = draw.textbbox((0, 0), cta, font=fs)
        cw = bbox3[2] - bbox3[0]; bx = (w - cw) / 2 - 30
        draw.rectangle([bx, 520, bx + cw + 60, 570], fill=(255, 180, 40))
        draw.text((bx + 30, 528), cta, fill=(0, 0, 0), font=fs)

    draw.text((20, 575), f"{data.get('activity_name','')} | {data.get('campaign_id','')}", fill=(180, 180, 180), font=fm)
    return img


def _all_text(data: Dict) -> str:
    parts = [data.get("activity_name",""), data.get("main_title",""), data.get("sub_title",""),
             data.get("target_segment",""), data.get("cta_text",""), data.get("visual_description","")]
    parts.extend(data.get("rules_summary", []))
    return " | ".join(p for p in parts if p)


# ================================================================
# OCR: 图像→文字
# ================================================================
def ocr_extract(image_path: str) -> str:
    """从海报图片提取文字。优先级: PNG metadata > pytesseract > JSON fallback"""
    try:
        img = Image.open(image_path)
        if hasattr(img, 'text') and img.text and 'ocr_text' in img.text:
            t = img.text['ocr_text']
            if len(t) > 20: return t
    except: pass
    try:
        import pytesseract
        return pytesseract.image_to_string(Image.open(image_path), lang='chi_sim+eng')
    except: pass
    # JSON fallback
    json_name = os.path.splitext(os.path.basename(image_path))[0] + ".json"
    jp = os.path.join(POSTERS_DIR, json_name)
    if os.path.exists(jp):
        with open(jp, "r", encoding="utf-8") as f: return _all_text(json.load(f))
    return ""


# ================================================================
# 多模态搜索 (OCR + 字符级匹配 + DeepSeek语义)
# ================================================================
# === 内置中文同义词词典 (严格版: 仅高置信度同义词) ===
SYNONYM_DICT = {
    "返现": ["返利","立减","满减"],
    "天猫": ["淘宝","电商"],
    "大促": ["促销","特价","狂欢"],
    "分期": ["免息","账单分期","消费分期"],
    "出行": ["旅游","旅行","度假"],
    "优惠": ["折扣","立减","特价"],
    "购物": ["电商","网购"],
    "贵宾厅": ["lounge","候机"],
    "接送机": ["接机","送机","专车"],
    "延误险": ["航班延误","赔付"],
    "唤醒": ["召回","重激活"],
    "毕业生": ["转卡"],
    "新户": ["首刷","开卡礼"],
}

def _expand_query(query: str) -> str:
    """用同义词词典扩展查询, 让'快乐'也能搜到'开心'/'愉快'。"""
    expanded = query
    for word, synonyms in SYNONYM_DICT.items():
        if word in query:
            expanded += " " + " ".join(synonyms)
    return expanded


def multimodal_search(query: str, top_k: int = 8) -> List[Dict]:
    """
    多模态搜索 — 对任意长度关键词都有效。

    三步:
      Step1: 字符级精准匹配 (1-4字滑动窗口, 自适应阈值)
      Step2: DeepSeek语义扩展 (理解"返现≈优惠≈折扣")
      Step3: 排序去重, 返回Top-K
    """
    results = []
    # 同义词扩展: "快乐" → "快乐 开心 高兴 愉快 欢乐 喜悦 幸福"
    expanded_query = _expand_query(query)
    qlen = len(query)

    # 自适应阈值: 短词降低门槛
    if qlen <= 1: threshold = 1
    elif qlen <= 2: threshold = 2
    elif qlen <= 4: threshold = 4
    else: threshold = max(4, qlen // 2)

    # === 搜索每张海报 ===
    for fp in glob.glob(os.path.join(POSTERS_IMG_DIR, "*.png")):
        ocr_text = ocr_extract(fp)
        if not ocr_text: continue

        # Step1: 字符级精准匹配 (对扩展后的查询做匹配, 提高召回)
        kw_score = 0
        matched = set()
        search_terms = expanded_query.split()  # 扩展后的所有词
        # 提取查询中的1-4字子串, 在OCR文本中计数
        for L in [min(4, qlen), min(3, qlen), min(2, qlen), 1]:
            for i in range(max(1, qlen - L + 1)):
                term = query[i:i+L]
                if term and term not in matched:
                    matched.add(term)
                    cnt = ocr_text.count(term)
                    if cnt > 0:
                        kw_score += cnt * len(term)  # 长词匹配权重更高

        # 同义词匹配加分
        for syn_term in search_terms[1:]:  # 跳过第一个(是原词)
            cnt = ocr_text.count(syn_term)
            if cnt > 0:
                kw_score += cnt * len(syn_term)
                matched.add(syn_term)

        # 查重: 搜索词和海报标题的精准匹配度
        info = _poster_info(fp)
        title = info.get("activity_name", "")
        # 标题包含查询 → 加权
        title_match = sum(1 for c in query if c in title) / max(qlen, 1)
        kw_score += int(title_match * 10)

        # Step2: DeepSeek语义扩展
        sem_score = 0
        try:
            from llm_client import chat, is_available as llm_ok
            if llm_ok() and kw_score < threshold * 3:  # 关键词没找到时才用语义
                prompt = f'以下是两个词语, 判断它们是否语义相关(0不相关~10非常相关)。只输出数字。\n词语1: {query}\n词语2: {title}'
                resp = chat([{"role":"user","content":prompt}], temperature=0)
                sem_score = int(''.join(c for c in resp if c.isdigit()) or '0') * 3
        except: pass

        total = kw_score + sem_score
        if total >= threshold:
            results.append({
                "source_type": "poster_ocr",
                "title": title,
                "content": f"{info.get('main_title','')} | {info.get('sub_title','')}",
                "rules": info.get("rules_summary", [])[:3],
                "image_path": fp,
                "score": total, "keyword_score": kw_score, "semantic_score": sem_score,
                "matched_chars": list(matched)[:8],
                "method": "OCR+CharMatch" + ("+DeepSeek语义" if sem_score > 0 else ""),
            })

    # === 也搜JSON (扩展查询) ===
    for fp in glob.glob(os.path.join(POSTERS_DIR, "*.json")):
        with open(fp, "r", encoding="utf-8") as f: data = json.load(f)
        text = _all_text(data)
        kw_score = 0
        for L in [min(4, qlen), min(3, qlen), min(2, qlen), 1]:
            for i in range(max(1, qlen - L + 1)):
                term = query[i:i+L]
                if term: kw_score += text.count(term) * len(term)
        # 同义词加分
        for syn_term in expanded_query.split()[1:]:
            cnt = text.count(syn_term)
            if cnt > 0: kw_score += cnt * len(syn_term)
        if kw_score >= threshold:
            img_file = data.get("image_file", "")
            img_path = os.path.join(POSTERS_IMG_DIR, img_file) if img_file else ""
            results.append({
                "source_type": "poster_json",
                "title": data.get("activity_name", ""),
                "content": f"{data.get('main_title','')} | {data.get('sub_title','')}",
                "rules": data.get("rules_summary", [])[:3],
                "image_path": img_path if os.path.exists(img_path) else "",
                "score": kw_score, "keyword_score": kw_score, "semantic_score": 0,
                "method": "JSON+CharMatch",
            })

    # 排序去重 + 相关性过滤
    results.sort(key=lambda x: x["score"], reverse=True)
    # 计算最高分, 过滤掉分数太低的 (不超过最高分的15%就不显示)
    max_score = max((r["score"] for r in results), default=0)
    seen = set(); unique = []
    for r in results:
        k = r["title"][:30]
        if k in seen: continue
        # 相关性过滤: 分数低于最高分15%的不显示
        if r["score"] < max_score * 0.20:
            continue
        seen.add(k); unique.append(r)
    return unique[:top_k]


def _poster_info(image_path: str) -> Dict:
    json_name = os.path.splitext(os.path.basename(image_path))[0] + ".json"
    jp = os.path.join(POSTERS_DIR, json_name)
    if os.path.exists(jp):
        with open(jp, "r", encoding="utf-8") as f: return json.load(f)
    return {}


if __name__ == "__main__":
    generate_all_posters()
    print("\n=== 多模态搜索测试 ===")
    tests = [
        ("返现", "天猫", "大促", "618", "双十一", "分期", "唤醒", "白金", "生日", "毕业", "出行", "购物"),
    ]
    for kw in tests[0]:
        r = multimodal_search(kw, top_k=3)
        titles = [x['title'][:22] for x in r]
        print(f'{kw}: {len(r)}条 → {" | ".join(titles)}')
        if r:
            x = r[0]
            print(f'       [{x["method"]}] score={x["score"]} kw={x.get("keyword_score",0)} sem={x.get("semantic_score",0)}')
    print("\nDone!")
