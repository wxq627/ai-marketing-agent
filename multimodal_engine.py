"""
多模态处理引擎 — multimodal_engine.py
=======================================
功能:
  1. 从JSON描述生成真实PNG海报图片 (Pillow)
  2. 图像→文本信息提取 (OCR/视觉理解)
  3. 集成到知识检索中 (多模态搜索)

Mock环境: Pillow生成图片 + 结构化提取
生产环境: Qwen2.5-VL-7B 做真实视觉理解
"""
import os, json, glob, re
from PIL import Image, ImageDraw, ImageFont
from typing import List, Dict, Optional

BASE = os.path.dirname(os.path.abspath(__file__))
POSTERS_DIR = os.path.join(BASE, "mock_data", "unstructured", "posters")
POSTERS_IMG_DIR = os.path.join(POSTERS_DIR, "images")  # 新增: 真实图片目录
os.makedirs(POSTERS_IMG_DIR, exist_ok=True)

# 中文字体路径 (Windows系统)
FONT_PATH = "C:/Windows/Fonts/simhei.ttf"  # 黑体
FONT_PATH_SMALL = "C:/Windows/Fonts/simsun.ttc"  # 宋体


def generate_poster_images():
    """从JSON描述生成真实PNG海报图片。"""
    json_files = glob.glob(os.path.join(POSTERS_DIR, "*.json"))
    results = []
    for fp in json_files:
        try:
            with open(fp, "r", encoding="utf-8") as f:
                data = json.load(f)
            img_file = data.get("image_file", "")
            if not img_file: continue

            img_path = os.path.join(POSTERS_IMG_DIR, img_file)
            if os.path.exists(img_path):  # 已生成则跳过
                results.append({"file": img_file, "status": "exists"})
                continue

            # 创建海报图片
            img = _create_poster(data)
            img.save(img_path, "PNG")
            results.append({"file": img_file, "status": "created", "size": os.path.getsize(img_path)})
        except Exception as e:
            results.append({"file": fp, "status": f"error: {e}"})
    return results


def _create_poster(data: Dict) -> Image.Image:
    """用Pillow生成海报图片。"""
    w, h = 800, 600
    # 背景色
    desc = data.get("visual_description", "")
    if "红" in desc or "春节" in data.get("activity_name", ""):
        bg = (180, 40, 40)
    elif "蓝" in desc or "新户" in data.get("activity_name", ""):
        bg = (40, 80, 180)
    elif "橙" in desc or "唤醒" in data.get("activity_name", ""):
        bg = (200, 130, 40)
    elif "黑" in desc or "白金" in data.get("activity_name", ""):
        bg = (30, 30, 40)
    elif "紫" in desc or "618" in data.get("activity_name", ""):
        bg = (120, 40, 160)
    elif "绿" in desc:
        bg = (40, 150, 80)
    else:
        bg = (60, 60, 120)

    img = Image.new("RGB", (w, h), bg)
    draw = ImageDraw.Draw(img)

    # 标题 (大号字体)
    title = data.get("main_title", "") or data.get("activity_name", "活动海报")
    try:
        font_title = ImageFont.truetype(FONT_PATH, 42)
        font_sub = ImageFont.truetype(FONT_PATH, 24)
        font_small = ImageFont.truetype(FONT_PATH_SMALL, 16)
    except:
        font_title = ImageFont.load_default()
        font_sub = font_title
        font_small = font_title

    # 居中标题
    bbox = draw.textbbox((0, 0), title, font=font_title)
    tw = bbox[2] - bbox[0]
    draw.text(((w - tw) / 2, 60), title, fill=(255, 255, 255), font=font_title)

    # 副标题
    sub = data.get("sub_title", "")
    if sub:
        bbox2 = draw.textbbox((0, 0), sub, font=font_sub)
        sw = bbox2[2] - bbox2[0]
        draw.text(((w - sw) / 2, 130), sub, fill=(255, 255, 200), font=font_sub)

    # 规则列表
    rules = data.get("rules_summary", [])
    y = 200
    for rule in rules[:6]:
        draw.text((100, y), f"  {rule}", fill=(255, 255, 255), font=font_small)
        y += 35

    # 目标客群
    target = data.get("target_segment", "")
    if target:
        draw.text((100, y + 20), f"目标客群: {target}", fill=(200, 200, 255), font=font_small)

    # CTA按钮
    cta = data.get("cta_text", "立即参与")
    bbox3 = draw.textbbox((0, 0), cta, font=font_sub)
    cw = bbox3[2] - bbox3[0]
    btn_x = (w - cw) / 2 - 30
    btn_y = h - 80
    draw.rectangle([btn_x, btn_y, btn_x + cw + 60, btn_y + 50], fill=(255, 180, 40))
    draw.text((btn_x + 30, btn_y + 8), cta, fill=(0, 0, 0), font=font_sub)

    # 活动名和ID
    draw.text((20, h - 25), f"{data.get('activity_name','')} | {data.get('campaign_id','')}",
              fill=(180, 180, 180), font=font_small)

    return img


def extract_from_image(image_path: str, use_llm: bool = False) -> Dict:
    """
    从图像中提取信息。

    Mock: 匹配JSON描述返回结构化信息
    生产: Qwen2.5-VL-7B 做真实OCR+视觉理解
    """
    # 查找匹配的JSON描述
    img_name = os.path.basename(image_path)
    json_name = os.path.splitext(img_name)[0] + ".json"
    json_path = os.path.join(POSTERS_DIR, json_name)

    if os.path.exists(json_path):
        with open(json_path, "r", encoding="utf-8") as f:
            data = json.load(f)
        return {
            "source": "poster_image",
            "file": img_name,
            "extracted": {
                "activity_name": data.get("activity_name", ""),
                "main_title": data.get("main_title", ""),
                "sub_title": data.get("sub_title", ""),
                "rules": data.get("rules_summary", []),
                "target_segment": data.get("target_segment", ""),
                "cta": data.get("cta_text", ""),
                "start_date": data.get("start_date", ""),
                "end_date": data.get("end_date", ""),
                "visual_style": data.get("visual_description", "")[:80],
                "campaign_id": data.get("campaign_id", ""),
            },
            "method": "structured_json" if not use_llm else "qwen_vl",
        }

    # 无JSON匹配, 尝试OCR (Mock: 返回基础信息)
    return {
        "source": "poster_image",
        "file": img_name,
        "extracted": {"file_name": img_name},
        "method": "mock_ocr",
        "note": "生产环境: Qwen2.5-VL-7B OCR+视觉理解"
    }


def multimodal_search(query: str, top_k: int = 8) -> List[Dict]:
    """
    多模态搜索: 同时搜索文档+海报图片。

    算法: 两步匹配
      Step1: 关键词匹配 (滑动窗口n-gram, 阈值自适应查询长度)
      Step2: DeepSeek Embedding语义匹配 (可选, 理解"返现≈返利")

    输入: "返现" → 搜索所有海报JSON字段(含rules/target_segment等)
    """
    results = []

    # 自适应阈值: 短词降低门槛
    qlen = len(query)
    if qlen <= 2: threshold = 2   # "返现"=2字→阈值为2
    elif qlen <= 4: threshold = 5 # "618购物"=4字→阈值为5
    else: threshold = 8            # 长句→阈值为8

    # === Step1: 全文关键词匹配 ===
    json_files = glob.glob(os.path.join(POSTERS_DIR, "*.json"))
    for fp in json_files:
        with open(fp, "r", encoding="utf-8") as f:
            data = json.load(f)

        # 搜索所有字段 (不只是title): 活动名+标题+副标题+每条规则+客群+视觉描述
        all_texts = [
            data.get("activity_name", ""),
            data.get("main_title", ""),
            data.get("sub_title", ""),
            data.get("visual_description", ""),
            data.get("target_segment", ""),
            data.get("cta_text", ""),
        ]
        all_texts.extend(data.get("rules_summary", []))
        full_text = " ".join(all_texts)

        # 滑动窗口n-gram评分
        score = 0
        terms = set()
        for L in [min(4, qlen), min(3, qlen), 2]:
            for i in range(max(1, qlen - L + 1)):
                term = query[i:i+L]
                if term and len(term) >= 2 and term not in terms:
                    terms.add(term)
                    cnt = full_text.count(term)
                    score += cnt * len(term)

        # DeepSeek Embedding 语义相似度 (可选增强)
        semantic_bonus = 0
        try:
            from llm_client import embed as ds_embed, is_available
            if is_available():
                q_vec = ds_embed(query)
                # 对海报主要文本做embedding
                main_text = data.get("main_title","") + " " + data.get("sub_title","") + " " + " ".join(data.get("rules_summary",[])[:3])
                if main_text.strip():
                    t_vec = ds_embed(main_text)
                    sim = float(np.dot(q_vec, t_vec) / (np.linalg.norm(q_vec) * np.linalg.norm(t_vec) + 1e-8))
                    semantic_bonus = int(sim * 20)  # 0-20分
        except:
            import numpy as np  # 确保numpy可用

        total_score = score + semantic_bonus
        if total_score >= threshold:
            img_file = data.get("image_file", "")
            img_path = os.path.join(POSTERS_IMG_DIR, img_file) if img_file else ""
            results.append({
                "source_type": "poster",
                "title": data.get("activity_name", ""),
                "content": f"{data.get('main_title','')} | {data.get('sub_title','')}",
                "rules": data.get("rules_summary", [])[:3],
                "image_path": img_path if os.path.exists(img_path) else "",
                "score": total_score,
                "keyword_match": score,
                "semantic_match": semantic_bonus,
                "method": "keyword_ngram" + (" + DeepSeek" if semantic_bonus > 0 else ""),
            })

    # === Step2: 图像文本提取匹配 ===
    img_files = glob.glob(os.path.join(POSTERS_IMG_DIR, "*.png"))
    for fp in img_files:
        info = extract_from_image(fp)
        extracted = info.get("extracted", {})
        content = f"{extracted.get('activity_name','')} {extracted.get('main_title','')} {extracted.get('sub_title','')} {' '.join(extracted.get('rules',[]))}"
        score = 0
        for L in [min(3, qlen), 2]:
            for i in range(max(1, qlen - L + 1)):
                term = query[i:i+L]
                if len(term) >= 2:
                    score += content.count(term) * len(term)
        if score >= threshold:
            results.append({
                "source_type": "poster_image",
                "title": extracted.get("activity_name", ""),
                "content": content[:150],
                "rules": extracted.get("rules", [])[:3],
                "image_path": fp,
                "visual_style": extracted.get("visual_style", ""),
                "score": score,
                "method": info.get("method", "keyword"),
            })

    results.sort(key=lambda x: x["score"], reverse=True)
    seen = set(); unique = []
    for r in results:
        k = r["title"][:30]
        if k not in seen: seen.add(k); unique.append(r)
    return unique[:top_k]


def generate_all_posters():
    """一键生成所有海报图片。"""
    results = generate_poster_images()
    created = [r for r in results if r.get("status") == "created"]
    existed = [r for r in results if r.get("status") == "exists"]
    print(f"海报生成: {len(created)} 新建, {len(existed)} 已存在, {len(results)} 总计")
    for r in created:
        print(f"  + {r['file']} ({r['size']} bytes)")
    return results


if __name__ == "__main__":
    generate_all_posters()
    # 测试搜索
    results = multimodal_search("双十一活动")
    print(f"\n多模态搜索 '双十一活动': {len(results)} 条")
    for r in results:
        print(f"  [{r['source_type']}] {r['title'][:30]} score={r['score']}")
