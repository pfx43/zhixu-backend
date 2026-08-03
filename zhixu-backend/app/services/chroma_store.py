"""
纯 Python 向量存储 — 替代 chromadb，避免 Windows Rust 兼容问题
使用 numpy 做余弦相似度检索，JSON 文件持久化
"""
import json
import logging
import math
import os
import threading
from pathlib import Path
from typing import List, Optional

import numpy as np

from app.core.config import CHROMA_PERSIST_DIR
from app.services.embedding_service import EMBEDDING_DIM, embed_texts

logger = logging.getLogger(__name__)

COLLECTION_NAME = "zhishi_segments"


def _seg_field(seg, name, default=None):
    if isinstance(seg, dict):
        return seg.get(name, default)
    return getattr(seg, name, default)


class ChromaStore:
    """纯 Python 向量存储：内存 numpy 数组 + JSON 持久化"""

    def __init__(self):
        self._lock = threading.Lock()
        self._ids: List[str] = []
        self._embeddings: List[np.ndarray] = []
        self._documents: List[str] = []
        self._metadatas: List[dict] = []
        self._persist_path = Path(CHROMA_PERSIST_DIR) / "zhishi_vectors.json"
        self._persist_path.parent.mkdir(parents=True, exist_ok=True)
        self._loaded = False

    def _ensure_loaded(self):
        if self._loaded:
            return
        with self._lock:
            if self._loaded:
                return
            # 尝试从磁盘加载
            if self._persist_path.exists():
                try:
                    data = json.loads(self._persist_path.read_text("utf-8"))
                    self._ids = data.get("ids", [])
                    self._embeddings = [np.array(e, dtype=np.float32) for e in data.get("embeddings", [])]
                    self._documents = data.get("documents", [])
                    self._metadatas = data.get("metadatas", [])
                    logger.info("向量存储加载成功: %d 条向量 @ %s", len(self._ids), self._persist_path)
                except Exception as e:
                    logger.warning("加载向量存储失败: %s，从空开始", e)
            self._loaded = True

    def _persist(self):
        """保存到磁盘"""
        try:
            data = {
                "ids": self._ids,
                "embeddings": [e.tolist() for e in self._embeddings],
                "documents": self._documents,
                "metadatas": self._metadatas,
            }
            self._persist_path.parent.mkdir(parents=True, exist_ok=True)
            self._persist_path.write_text(json.dumps(data, ensure_ascii=False), "utf-8")
        except Exception as e:
            logger.warning("向量持久化失败: %s", e)

    def upsert_segments(
        self,
        *,
        document_id: str,
        segments: List[object],
        user_id: int,
        collection_id: str,
        display_name: str,
    ) -> int:
        """写入或更新文档分段向量"""
        if not segments:
            return 0

        self._ensure_loaded()
        texts = [_seg_field(s, "content", "") for s in segments]
        embeddings = embed_texts(texts)

        with self._lock:
            # 删除旧数据
            new_ids = []
            new_embs = []
            new_docs = []
            new_metas = []
            for i in range(len(self._ids)):
                if self._metadatas[i].get("document_id") != document_id:
                    new_ids.append(self._ids[i])
                    new_embs.append(self._embeddings[i])
                    new_docs.append(self._documents[i])
                    new_metas.append(self._metadatas[i])

            # 添加新数据
            for seg, text, emb in zip(segments, texts, embeddings):
                seg_id = _seg_field(seg, "id")
                new_ids.append(str(seg_id))
                new_embs.append(np.array(emb, dtype=np.float32))
                new_docs.append(text)
                new_metas.append({
                    "user_id": int(user_id),
                    "collection_id": str(collection_id),
                    "document_id": str(document_id),
                    "segment_id": str(seg_id),
                    "char_start": int(_seg_field(seg, "char_start", 0)),
                    "char_end": int(_seg_field(seg, "char_end", 0)),
                    "title": str(_seg_field(seg, "title") or ""),
                    "display_name": str(display_name),
                })

            self._ids = new_ids
            self._embeddings = new_embs
            self._documents = new_docs
            self._metadatas = new_metas

            self._persist()
            logger.info("向量 upsert: document_id=%s segments=%d total=%d", document_id, len(segments), len(self._ids))
            return len(segments)

    def delete_by_document(self, document_id: str) -> int:
        self._ensure_loaded()
        with self._lock:
            before = len(self._ids)
            keep = []
            for i in range(len(self._ids)):
                if self._metadatas[i].get("document_id") != document_id:
                    keep.append(i)
            self._ids = [self._ids[i] for i in keep]
            self._embeddings = [self._embeddings[i] for i in keep]
            self._documents = [self._documents[i] for i in keep]
            self._metadatas = [self._metadatas[i] for i in keep]
            self._persist()
            deleted = before - len(self._ids)
            logger.info("向量删除: document_id=%s deleted=%d", document_id, deleted)
            return deleted

    def search(
        self,
        query: str,
        *,
        user_id: int,
        collection_id: Optional[str] = None,
        top_k: int = 5,
    ) -> List[dict]:
        """余弦相似度检索"""
        self._ensure_loaded()

        query_emb = np.array(embed_texts([query])[0], dtype=np.float32)

        with self._lock:
            if not self._embeddings:
                return []

            # 构建过滤后的索引
            indices = []
            for i in range(len(self._ids)):
                meta = self._metadatas[i]
                if int(meta.get("user_id", -1)) != int(user_id):
                    continue
                if collection_id and meta.get("collection_id") != collection_id:
                    continue
                indices.append(i)

            if not indices:
                return []

            # 提取过滤后的向量矩阵
            filtered_embs = np.stack([self._embeddings[i] for i in indices])
            # 余弦相似度 = 点积（向量已归一化）
            scores = np.dot(filtered_embs, query_emb)

            # 取 top_k
            if len(scores) <= top_k:
                top_indices = np.argsort(-scores)
            else:
                top_indices = np.argpartition(-scores, top_k)[:top_k]
                top_indices = top_indices[np.argsort(-scores[top_indices])]

            hits = []
            for idx in top_indices:
                orig_idx = indices[idx]
                score = float(scores[idx])
                meta = self._metadatas[orig_idx]
                hits.append({
                    "score": max(0.0, min(1.0, score)),
                    "content": self._documents[orig_idx],
                    "document_id": meta.get("document_id"),
                    "segment_id": meta.get("segment_id"),
                    "collection_id": meta.get("collection_id"),
                    "title": meta.get("title") or None,
                    "display_name": meta.get("display_name"),
                    "char_start": meta.get("char_start"),
                    "char_end": meta.get("char_end"),
                })

            return hits[:top_k]


chroma_store = ChromaStore()
