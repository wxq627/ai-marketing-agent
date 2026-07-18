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


def multimodal_search(query: str, top_k: int = 5) -> List[Dict]:
    """
    多模态搜索: 同时搜索文档+海报图片。

    输入: "双十一有什么活动" → 搜索文档 + 匹配海报JSON/图片
    """
    results = []

    # 1. 搜索海报JSON
    json_files = glob.glob(os.path.join(POSTERS_DIR, "*.json"))
    for fp in json_files:
        with open(fp, "r", encoding="utf-8") as f:
            data = json.load(f)
        text = json.dumps(data, ensure_ascii=False)
        score = sum(text.count(q) * (i + 1) for i, q in enumerate([query[i:i+L] for L in [4, 3, 2] for i in range(len(query) - L + 1)]))
        if score > 5:
            img_file = data.get("image_file", "")
            img_path = os.path.join(POSTERS_IMG_DIR, img_file) if img_file else ""
            results.append({
                "source_type": "poster",
                "title": data.get("activity_name", ""),
                "content": f"{data.get('main_title','')} | {data.get('sub_title','')}",
                "rules": data.get("rules_summary", [])[:3],
                "image_path": img_path if os.path.exists(img_path) else "",
                "score": score,
            })

    # 2. 如果有图片, 提取信息
    img_files = glob.glob(os.path.join(POSTERS_IMG_DIR, "*.png"))
    for fp in img_files:
        info = extract_from_image(fp)
        extracted = info.get("extracted", {})
        content = f"{extracted.get('activity_name','')} {extracted.get('main_title','')} {extracted.get('sub_title','')}"
        score = sum(content.count(q) for q in query.split() if len(q) >= 2)
        if score > 3:
            results.append({
                "source_type": "poster_image",
                "title": extracted.get("activity_name", ""),
                "content": content,
                "rules": extracted.get("rules", [])[:3],
                "image_path": fp,
                "visual_style": extracted.get("visual_style", ""),
                "score": score,
                "method": info.get("method", ""),
            })

    results.sort(key=lambda x: x["score"], reverse=True)
    # 去重
    seen = set()
    unique = []
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
