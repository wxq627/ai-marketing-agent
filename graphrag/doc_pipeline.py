"""
文档处理流水线 — doc_pipeline.py
==================================
① 文档加载 (TXT/JSON/CSV)
② 文本切片 (RecursiveCharacterTextSplitter风格, chunk_size=800, overlap=100)
③ 向量化 (DeepSeek Embedding, 降级为 TF-IDF)
"""
import os, sys, json, glob, re, numpy as np
from typing import List, Dict, Any
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from llm_client import embed as deepseek_embed, is_available as deepseek_available
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.metrics.pairwise import cosine_similarity

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DOCS_DIR = os.path.join(BASE, "mock_data", "unstructured", "product_docs")


class DocPipeline:
    """文档处理流水线: 加载→切片→向量化"""

    def __init__(self, chunk_size: int = 800, overlap: int = 100):
        self.chunk_size = chunk_size
        self.overlap = overlap
        self.chunks: List[Dict] = []
        self.vectorizer: TfidfVectorizer = None
        self.embeddings = None

    def load_and_process(self) -> "DocPipeline":
        """加载所有文档并处理。"""
        print("Loading documents...")
        # 1. 加载产品文档 TXT
        txt_files = glob.glob(os.path.join(DOCS_DIR, "doc_*.txt"))
        for fp in txt_files:
            with open(fp, "r", encoding="utf-8") as f:
                text = f.read()
            chunks = self._chunk(text)
            doc_name = os.path.basename(fp)
            for i, chunk in enumerate(chunks):
                self.chunks.append({
                    "chunk_id": f"{doc_name}_chunk_{i}",
                    "doc_name": doc_name, "chunk_index": i,
                    "text": chunk, "char_count": len(chunk),
                })

        # 2. 加载产品/权益/活动 CSV 描述
        self._load_csv_descriptions()

        print(f"Loaded {len(self.chunks)} chunks from {len(txt_files)} documents + CSV")

        # 3. 向量化 — 优先 DeepSeek, 降级 TF-IDF
        if self.chunks:
            texts = [c["text"] for c in self.chunks]
            if deepseek_available():
                print("Using DeepSeek Embedding...")
                self.embeddings = deepseek_embed(texts)
                self._use_deepseek = True
                print(f"DeepSeek vectorized: {self.embeddings.shape[1]} dimensions")
            else:
                print("DeepSeek unavailable, using TF-IDF fallback...")
                self.vectorizer = TfidfVectorizer(max_features=2000, ngram_range=(1,2))
                self.embeddings = self.vectorizer.fit_transform(texts)
                self._use_deepseek = False
                print(f"TF-IDF vectorized: {self.embeddings.shape[1]} dimensions")

        return self

    def _chunk(self, text: str) -> List[str]:
        """按段落+字符边界智能切分。"""
        paragraphs = text.split("\n\n")
        chunks = []
        current = ""
        for para in paragraphs:
            para = para.strip()
            if not para: continue
            if len(current) + len(para) < self.chunk_size:
                current += para + "\n"
            else:
                if current: chunks.append(current.strip())
                # 保留overlap
                if current and self.overlap > 0:
                    current = current[-self.overlap:] + para + "\n"
                else:
                    current = para + "\n"
        if current.strip():
            chunks.append(current.strip())
        return chunks

    def _load_csv_descriptions(self):
        """从CSV中提取产品/权益/活动描述作为文档片段。"""
        import pandas as pd
        s = os.path.join(BASE, "mock_data", "structured")
        for fname, text_cols in [
            ("product_catalog.csv", ["product_name", "key_selling_points", "annual_fee_waiver"]),
            ("benefit_catalog.csv", ["benefit_name", "benefit_desc"]),
            ("campaign_catalog.csv", ["campaign_name", "rules"]),
        ]:
            fp = os.path.join(s, fname)
            if os.path.exists(fp):
                df = pd.read_csv(fp)
                for i, row in df.iterrows():
                    text = " ".join([str(row.get(c,"")) for c in text_cols if c in row])
                    if len(text) > 20:
                        self.chunks.append({
                            "chunk_id": f"{fname}_row_{i}",
                            "doc_name": fname, "chunk_index": i,
                            "text": text[:1000], "char_count": len(text[:1000]),
                        })

    def search(self, query: str, top_k: int = 5) -> List[Dict]:
        """向量相似检索 — DeepSeek Embedding 或 TF-IDF。"""
        if self.embeddings is None:
            return []

        if getattr(self, '_use_deepseek', False):
            # DeepSeek: numpy 数组, 直接算余弦相似度
            q_vec = deepseek_embed(query)
            if q_vec.ndim == 1: q_vec = q_vec.reshape(1, -1)
            scores = cosine_similarity(q_vec, self.embeddings)[0]
        else:
            # TF-IDF: 稀疏矩阵
            if self.vectorizer is None: return []
            q_vec = self.vectorizer.transform([query])
            scores = cosine_similarity(q_vec, self.embeddings)[0]
        top_indices = np.argsort(scores)[-top_k:][::-1]
        results = []
        for idx in top_indices:
            if scores[idx] > 0:
                results.append({
                    "rank": len(results) + 1,
                    "chunk_id": self.chunks[idx]["chunk_id"],
                    "doc_name": self.chunks[idx]["doc_name"],
                    "content": self.chunks[idx]["text"][:300],
                    "relevance_score": round(float(scores[idx]), 4),
                })
        return results


_pipeline_instance = None
def get_pipeline() -> DocPipeline:
    global _pipeline_instance
    if _pipeline_instance is None:
        _pipeline_instance = DocPipeline().load_and_process()
    return _pipeline_instance
