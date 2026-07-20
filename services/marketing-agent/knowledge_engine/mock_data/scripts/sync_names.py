"""
批量更新非结构化数据中的旧产品名称引用
===========================================
更新ASR对话记录和文档索引中的旧产品名称 → 新产品名称。
基于XX银行真实信用卡产品体系。
"""
import json, os, glob, re

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
ASR_DIR = os.path.join(BASE_DIR, "unstructured", "asr_transcripts")

# 旧名→新名映射
NAME_MAP = {
    "全币种白金信用卡": "全币种国际白金信用卡",
    "全币种白金卡": "全币种国际白金卡",
    "钻石信用卡": "银联钻石信用卡",
    "无限信用卡": "万事达世界信用卡",
    "无限卡": "万事达世界信用卡",
    "京东联名信用卡": "京东PLUS联名信用卡",
    "YOUNG卡（普卡）": "YOUNG卡（青年版）",
    "YOUNG卡(普卡)": "YOUNG卡(青年版)",
    "校园信用卡": "YOUNG卡（校园版）",
    "携程旅行信用卡": "携程旅行信用卡",
    "经典版白金信用卡": "经典版白金信用卡",
}

def update_asr_transcripts():
    """更新所有ASR对话JSON中的旧产品名称。"""
    files = glob.glob(os.path.join(ASR_DIR, "*.json"))
    updated = 0
    total_replacements = 0

    for fpath in files:
        with open(fpath, "r", encoding="utf-8") as f:
            try:
                data = json.load(f)
            except json.JSONDecodeError:
                continue

        text = json.dumps(data, ensure_ascii=False)
        new_text = text
        changes = 0
        for old_name, new_name in NAME_MAP.items():
            if old_name in new_text and old_name != new_name:
                count = new_text.count(old_name)
                new_text = new_text.replace(old_name, new_name)
                changes += count

        if changes > 0:
            data = json.loads(new_text)
            with open(fpath, "w", encoding="utf-8") as f:
                json.dump(data, f, ensure_ascii=False, indent=2)
            updated += 1
            total_replacements += changes

    print(f"ASR对话: 更新 {updated} 个文件, {total_replacements} 处替换")

def update_docs_index():
    """更新product_docs索引文件。"""
    idx_path = os.path.join(BASE_DIR, "unstructured", "product_docs", "_index.json")
    if not os.path.exists(idx_path):
        return
    with open(idx_path, "r", encoding="utf-8") as f:
        docs = json.load(f)

    for doc in docs:
        text = json.dumps(doc, ensure_ascii=False)
        for old_name, new_name in NAME_MAP.items():
            if old_name in text and old_name != new_name:
                # 精确替换 product_name 和 title 字段
                if doc.get("product_name") == old_name:
                    doc["product_name"] = new_name
                old_title = old_name + "说明"
                if doc.get("title") == old_title:
                    doc["title"] = new_name + "说明"

    with open(idx_path, "w", encoding="utf-8") as f:
        json.dump(docs, f, ensure_ascii=False, indent=2)
    print(f"文档索引: 已更新 {len(docs)} 条")

def update_poster_jsons():
    """更新活动海报JSON中的旧引用。"""
    posters_dir = os.path.join(BASE_DIR, "unstructured", "posters")
    files = glob.glob(os.path.join(posters_dir, "*.json"))
    updated = 0

    for fpath in files:
        with open(fpath, "r", encoding="utf-8") as f:
            data = json.load(f)

        text = json.dumps(data, ensure_ascii=False)
        changed = False
        for old_name, new_name in NAME_MAP.items():
            if old_name in text and old_name != new_name:
                text = text.replace(old_name, new_name)
                changed = True

        if changed:
            data = json.loads(text)
            with open(fpath, "w", encoding="utf-8") as f:
                json.dump(data, f, ensure_ascii=False, indent=2)
            updated += 1

    print(f"活动海报: 更新 {updated} 个文件")


if __name__ == "__main__":
    print("=" * 50)
    print("非结构化数据名称同步")
    print("=" * 50)
    update_asr_transcripts()
    update_docs_index()
    update_poster_jsons()
    print("完成")
