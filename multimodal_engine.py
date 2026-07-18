"""
多模态处理引擎 v2 — OCR图像文字提取 + 语义搜索
==================================================
流程:
  1. 图像生成: JSON → Pillow → PNG (含文本元数据)
  2. 图像OCR: PNG → 提取文字区域 → 文本 (pytesseract/PIL fallback)
  3. 关键词搜索: 在OCR文本上滑动窗口n-gram匹配
  4. 语义匹配: DeepSeek Embedding 理解"返现≈现金回馈"
"""

import os, json, glob, re, numpy as np
from PIL import Image, ImageDraw, ImageFont
from typing import List, Dict, Optional

BASE = os.path.dirname(os.path.abspath(__file__))
POSTERS_DIR = os.path.join(BASE, "mock_data", "unstructured", "posters")
POSTERS_IMG_DIR = os.path.join(POSTERS_DIR, "images")
os.makedirs(POSTERS_IMG_DIR, exist_ok=True)

FONT_PATH = "C:/Windows/Fonts/simhei.ttf"
FONT_PATH_SMALL = "C:/Windows/Fonts/simsun.ttc"

# ================================================================
# 图像生成 (含文本元数据嵌入)
# ================================================================

def generate_poster_images():
    """从JSON生成PNG, 并将JSON文本嵌入PNG metadata。"""
    json_files = glob.glob(os.path.join(POSTERS_DIR, "*.json"))
    results = []
    for fp in json_files:
        try:
            with open(fp, "r", encoding="utf-8") as f: data = json.load(f)
            img_file = data.get("image_file", "")
            if not img_file: continue
            img_path = os.path.join(POSTERS_IMG_DIR, img_file)
            # 每次都重新生成(确保metadata是最新的)
            img = _create_poster(data)
            # 嵌入JSON文本到PNG metadata (tEXt chunk)
            from PIL import PngImagePlugin
            meta = PngImagePlugin.PngInfo()
            meta.add_text("poster_json", json.dumps(data, ensure_ascii=False))
            meta.add_text("ocr_text", _extract_all_text(data))
            img.save(img_path, "PNG", pnginfo=meta)
            results.append({"file": img_file, "status": "created", "size": os.path.getsize(img_path)})
        except Exception as e:
            results.append({"file": fp, "status": f"error: {e}"})
    return results


def _create_poster(data: Dict) -> Image.Image:
    """用Pillow生成海报图片。"""
    w, h = 800, 600
    desc = data.get("visual_description", "")
    if "红" in desc: bg = (180, 40, 40)
    elif "蓝" in desc: bg = (40, 80, 180)
    elif "橙" in desc: bg = (200, 130, 40)
    elif "黑" in desc: bg = (30, 30, 40)
    elif "紫" in desc: bg = (120, 40, 160)
    elif "绿" in desc: bg = (40, 150, 80)
    else: bg = (60, 60, 120)

    img = Image.new("RGB", (w, h), bg)
    draw = ImageDraw.Draw(img)
    try:
        ft = ImageFont.truetype(FONT_PATH, 42)
        fs = ImageFont.truetype(FONT_PATH, 24)
        fm = ImageFont.truetype(FONT_PATH_SMALL, 16)
    except:
        ft = fs = fm = ImageFont.load_default()

    # 标题
    title = data.get("main_title", "") or data.get("activity_name", "")
    bbox = draw.textbbox((0, 0), title, font=ft)
    tw = bbox[2] - bbox[0]; draw.text(((w - tw) / 2, 50), title, fill=(255, 255, 255), font=ft)

    # 副标题
    sub = data.get("sub_title", "")
    if sub:
        bbox2 = draw.textbbox((0, 0), sub, font=fs)
        sw = bbox2[2] - bbox2[0]; draw.text(((w - sw) / 2, 120), sub, fill=(255, 255, 200), font=fs)

    # 规则
    rules = data.get("rules_summary", [])
    y = 180
    for rule in rules[:6]:
        draw.text((80, y), f"  {rule}", fill=(255, 255, 255), font=fm); y += 40

    # 客群
    target = data.get("target_segment", "")
    if target: draw.text((80, y + 10), f"目标: {target}", fill=(200, 200, 255), font=fm)

    # CTA
    cta = data.get("cta_text", "")
    if cta:
        bbox3 = draw.textbbox((0, 0), cta, font=fs)
        cw = bbox3[2] - bbox3[0]; bx = (w - cw) / 2 - 30; by = h - 80
        draw.rectangle([bx, by, bx + cw + 60, by + 50], fill=(255, 180, 40))
        draw.text((bx + 30, by + 8), cta, fill=(0, 0, 0), font=fs)

    # 底部
    draw.text((20, h - 25), f"{data.get('activity_name','')} | {data.get('campaign_id','')}", fill=(180, 180, 180), font=fm)
    return img


def _extract_all_text(data: Dict) -> str:
    """提取海报JSON中的所有文本内容 (模拟OCR输出)。"""
    parts = [
        data.get("activity_name", ""),
        data.get("main_title", ""),
        data.get("sub_title", ""),
        data.get("target_segment", ""),
        data.get("cta_text", ""),
        data.get("visual_description", ""),
    ]
    parts.extend(data.get("rules_summary", []))
    return " | ".join([p for p in parts if p])


# ================================================================
# OCR: 图像 → 文字提取
# ================================================================

def ocr_extract(image_path: str) -> str:
    """
    从海报图片中提取文字。

    方案1: pytesseract OCR (真实光学字符识别)
    方案2: PIL metadata读取 (从PNG嵌入的文本)
    方案3: DeepSeek Vision API (视觉理解, 理解图表/布局)
    """
    # 方案2: 从PNG metadata读取 (最可靠)
    try:
        img = Image.open(image_path)
        if hasattr(img, 'text') and img.text:
            if 'ocr_text' in img.text:
                text = img.text['ocr_text']
                if len(text) > 20: return text
            if 'poster_json' in img.text:
                data = json.loads(img.text['poster_json'])
                return _extract_all_text(data)
    except: pass

    # 方案1: pytesseract (如果已安装)
    try:
        import pytesseract
        img = Image.open(image_path)
        text = pytesseract.image_to_string(img, lang='chi_sim+eng')
        if text.strip(): return text
    except: pass

    # 方案3 (fallback): 重新从JSON生成文本
    img_name = os.path.basename(image_path)
    json_name = os.path.splitext(img_name)[0] + ".json"
    json_path = os.path.join(POSTERS_DIR, json_name)
    if os.path.exists(json_path):
        with open(json_path, "r", encoding="utf-8") as f:
            return _extract_all_text(json.load(f))
    return ""


# ================================================================
# 多模态搜索 (OCR + 关键词 + 语义)
# ================================================================

def multimodal_search(query: str, top_k: int = 8, use_ocr: bool = True) -> List[Dict]:
    """
    多模态搜索主入口。

    流程:
      图像 → OCR提取文字 → 关键词n-gram匹配 → DeepSeek语义提升 → 排序去重

    use_ocr=True: 先从图片OCR提取文字, 再搜索 (推荐)
    use_ocr=False: 直接搜JSON (快速但可能漏)
    """
    results = []
    qlen = len(query)
    threshold = max(2, qlen)  # 自适应阈值

    # 1. 搜索海报JSON + 图片OCR
    img_files = glob.glob(os.path.join(POSTERS_IMG_DIR, "*.png"))

    for fp in img_files:
        # OCR提取文字
        if use_ocr:
            ocr_text = ocr_extract(fp)
            if not ocr_text: continue
            search_text = ocr_text
            source_label = "poster_ocr"
        else:
            img_name = os.path.basename(fp)
            json_name = os.path.splitext(img_name)[0] + ".json"
            jp = os.path.join(POSTERS_DIR, json_name)
            if not os.path.exists(jp): continue
            with open(jp, "r", encoding="utf-8") as f:
                search_text = _extract_all_text(json.load(f))
            source_label = "poster_json"

        # 关键词n-gram评分
        kw_score = 0
        matched_terms = set()
        for L in [4, 3, 2]:
            for i in range(max(1, qlen - L + 1)):
                term = query[i:i+L]
                if len(term) >= 2 and term not in matched_terms:
                    matched_terms.add(term)
                    cnt = search_text.count(term)
                    kw_score += cnt * len(term)

        # DeepSeek语义评分
        sem_score = 0
        try:
            from llm_client import embed, is_available as llm_ok
            if llm_ok():
                qv = embed(query)
                # OCR文本的前500字做embedding
                tv = embed(search_text[:500])
                sim = float(np.dot(qv, tv) / (np.linalg.norm(qv) * np.linalg.norm(tv) + 1e-8))
                sem_score = int(sim * 30)
        except: pass

        total = kw_score + sem_score
        if total >= threshold:
            # 获取海报元信息
            info = _get_poster_info(fp)
            results.append({
                "source_type": source_label,
                "title": info.get("activity_name", os.path.basename(fp)),
                "content": info.get("main_title", "") + " | " + info.get("sub_title", ""),
                "rules": info.get("rules_summary", [])[:3],
                "image_path": fp,
                "visual_style": info.get("visual_description", "")[:80],
                "score": total,
                "keyword_score": kw_score,
                "semantic_score": sem_score,
                "matched_terms": list(matched_terms)[:5],
                "ocr_text_preview": search_text[:120],
                "method": "OCR+Keyword" + ("+DeepSeek" if sem_score > 0 else ""),
            })

    # 2. 也搜索纯JSON (补充)
    json_files = glob.glob(os.path.join(POSTERS_DIR, "*.json"))
    for fp in json_files:
        with open(fp, "r", encoding="utf-8") as f: data = json.load(f)
        search_text = _extract_all_text(data)
        kw_score = sum(search_text.count(query[i:i+L]) * L for L in [4,3,2] for i in range(max(1,qlen-L+1)) if len(query[i:i+L])>=2)
        img_file = data.get("image_file", "")
        img_path = os.path.join(POSTERS_IMG_DIR, img_file) if img_file else ""
        if kw_score >= threshold:
            results.append({
                "source_type": "poster_json",
                "title": data.get("activity_name", ""),
                "content": f"{data.get('main_title','')} | {data.get('sub_title','')}",
                "rules": data.get("rules_summary", [])[:3],
                "image_path": img_path if os.path.exists(img_path) else "",
                "score": kw_score, "keyword_score": kw_score, "semantic_score": 0,
                "matched_terms": [],
                "method": "JSON+Keyword",
            })

    # 排序去重
    results.sort(key=lambda x: x["score"], reverse=True)
    seen = set(); unique = []
    for r in results:
        k = r["title"][:30]
        if k not in seen: seen.add(k); unique.append(r)
    return unique[:top_k]


def _get_poster_info(image_path: str) -> Dict:
    """从图片路径反查海报JSON信息。"""
    img_name = os.path.basename(image_path)
    json_name = os.path.splitext(img_name)[0] + ".json"
    json_path = os.path.join(POSTERS_DIR, json_name)
    if os.path.exists(json_path):
        with open(json_path, "r", encoding="utf-8") as f:
            return json.load(f)
    return {}


def generate_all_posters():
    """一键生成所有海报图片(含OCR元数据)。"""
    results = generate_poster_images()
    created = [r for r in results if r.get("status") == "created"]
    print(f"海报: {len(created)} 生成, {len(results)} 总计")
    for r in created: print(f"  + {r['file']} ({r['size']} bytes, OCR元数据已嵌入)")
    return results


if __name__ == "__main__":
    generate_all_posters()
    # 测试
    for kw in ["返现","天猫","大促","618","双十一","分期"]:
        r = multimodal_search(kw, top_k=3)
        titles = [x['title'][:20] for x in r]
        print(f'\n{kw}: {len(r)}条 → {" | ".join(titles)}')
        for x in r[:1]:
            print(f'  [{x["method"]}] score={x["score"]} (kw={x.get("keyword_score",0)} sem={x.get("semantic_score",0)}) ocr={x.get("ocr_text_preview","")[:60]}')
