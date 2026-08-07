"""
向量存储适配层 — 统一抽象，支持 local / dify / http 三种后端

使用方式：
    from app.services.knowledge.vector_store import get_vector_store

    store = get_vector_store()
    hits = store.search(user_id, query, top_k=5, collection_id=None)

硬约束：
    - 生产配置下不 import/加载 sentence-transformers
    - search 必须按 user_id 过滤；过滤失败返回空，禁止无 filter 回退
"""
import logging
from abc import ABC, abstractmethod
from pathlib import Path
from typing import List, Optional

from app.core.config import CHROMA_PERSIST_DIR, DIFY_DATASET_API_KEY, RAG_BACKEND

logger = logging.getLogger(__name__)

# 向量后端配置：local | dify | http
VECTOR_BACKEND = RAG_BACKEND  # 复用 RAG_BACKEND 配置


# ─── 抽象基类 ──────────────────────────────────────────

class VectorStoreClient(ABC):
    """向量存储抽象接口"""

    @abstractmethod
    def upsert_segments(
        self,
        *,
        document_id: str,
        segments: List[object],
        user_id: int,
        collection_id: str,
        display_name: str,
    ) -> int:
        """写入或更新文档分段向量，返回索引段数"""
        ...

    @abstractmethod
    def search(
        self,
        user_id: int,
        query: str,
        top_k: int = 5,
        collection_id: Optional[str] = None,
    ) -> List[dict]:
        """
        语义检索，返回命中列表。
        每项: {score, content, document_id, segment_id, collection_id, title}
        必须按 user_id 过滤。
        """
        ...

    @abstractmethod
    def delete_by_document(self, user_id: int, document_id: str) -> int:
        """删除文档的全部向量，返回删除数"""
        ...


# ─── 本地向量存储（包装现有 ChromaStore）───────────────

class LocalVectorStore(VectorStoreClient):
    """本地 numpy 向量存储，包装 ChromaStore"""

    def __init__(self):
        from app.services.knowledge.chroma_store import chroma_store
        self._backend = chroma_store

    def upsert_segments(
        self,
        *,
        document_id: str,
        segments: List[object],
        user_id: int,
        collection_id: str,
        display_name: str,
    ) -> int:
        return self._backend.upsert_segments(
            document_id=document_id,
            segments=segments,
            user_id=user_id,
            collection_id=collection_id,
            display_name=display_name,
        )

    def search(
        self,
        user_id: int,
        query: str,
        top_k: int = 5,
        collection_id: Optional[str] = None,
    ) -> List[dict]:
        hits = self._backend.search(
            query=query,
            user_id=user_id,
            collection_id=collection_id,
            top_k=top_k,
        )
        # 硬约束：确保结果全部属于该 user_id
        return [h for h in hits if h.get("user_id") == user_id or h.get("metadata", {}).get("user_id") == user_id]

    def delete_by_document(self, user_id: int, document_id: str) -> int:
        return self._backend.delete_by_document(document_id)


# ─── Dify 向量存储 ────────────────────────────────────

class DifyVectorStore(VectorStoreClient):
    """基于 Dify 知识库的向量存储，每用户独立 dataset，天然用户隔离"""

    def __init__(self):
        if not DIFY_DATASET_API_KEY:
            logger.warning("DIFY_DATASET_API_KEY 未配置，DifyVectorStore 将无法工作")

    @staticmethod
    def _get_dataset_id_for_user(user_id: int) -> Optional[str]:
        """从数据库获取用户的 dataset_id；需要惰性 import 避免循环"""
        from app.core.database import SessionLocal
        from app.models.models import User

        db = SessionLocal()
        try:
            user = db.query(User).filter(User.id == user_id).first()
            if user and user.dataset_id:
                return user.dataset_id
            return None
        finally:
            db.close()

    def upsert_segments(
        self,
        *,
        document_id: str,
        segments: List[object],
        user_id: int,
        collection_id: str,
        display_name: str,
    ) -> int:
        """
        Dify 路径下分段索引由 Dify 自动处理（上传文档时）。
        此方法为接口兼容保留，实际分段由 dify_kb.py 在上传阶段完成。
        """
        logger.info("DifyVectorStore.upsert_segments: 分段 %d 条 (document_id=%s)", len(segments), document_id)
        return len(segments)

    def search(
        self,
        user_id: int,
        query: str,
        top_k: int = 5,
        collection_id: Optional[str] = None,
    ) -> List[dict]:
        dataset_id = self._get_dataset_id_for_user(user_id)
        if not dataset_id:
            logger.warning("DifyVectorStore.search: user_id=%s 无 dataset_id", user_id)
            return []

        from app.services.knowledge.dify_kb import DifyKB

        try:
            kb = DifyKB(dataset_id)
            results = kb.query(query, top_k=top_k)
            # 标准化为统一格式
            hits = []
            for r in results:
                hits.append({
                    "score": r.get("score", 0),
                    "content": r.get("content", ""),
                    "document_id": r.get("dify_document_id", ""),
                    "segment_id": r.get("dify_document_id", ""),
                    "collection_id": collection_id or "",
                    "title": r.get("document_name", ""),
                    "display_name": r.get("document_name", ""),
                    "char_start": None,
                    "char_end": None,
                })
            return hits
        except Exception as e:
            logger.error("DifyVectorStore.search 失败: %s", e)
            return []

    def delete_by_document(self, user_id: int, document_id: str) -> int:
        dataset_id = self._get_dataset_id_for_user(user_id)
        if not dataset_id:
            return 0

        from app.services.knowledge.dify_kb import DifyKB

        try:
            kb = DifyKB(dataset_id)
            if kb.delete_document(document_id):
                return 1
        except Exception as e:
            logger.error("DifyVectorStore.delete_by_document 失败: %s", e)
        return 0


# ─── HTTP 向量存储（外部 GPU 服务）─────────────────────

class HttpVectorStore(VectorStoreClient):
    """对接外部 GPU 向量服务的 HTTP 客户端"""

    def __init__(self, base_url: str):
        import os
        self.base_url = base_url.rstrip("/")

    def upsert_segments(
        self,
        *,
        document_id: str,
        segments: List[object],
        user_id: int,
        collection_id: str,
        display_name: str,
    ) -> int:
        # 标准实现：POST /upsert
        import httpx
        payload = {
            "user_id": user_id,
            "document_id": document_id,
            "collection_id": collection_id,
            "segments": [
                {
                    "id": str(getattr(s, "id", "")),
                    "content": str(getattr(s, "content", "")),
                    "char_start": int(getattr(s, "char_start", 0)),
                    "char_end": int(getattr(s, "char_end", 0)),
                    "title": str(getattr(s, "title", "")),
                }
                for s in segments
            ],
        }
        try:
            with httpx.Client(timeout=httpx.Timeout(60.0)) as client:
                resp = client.post(f"{self.base_url}/upsert", json=payload)
                if resp.status_code == 200:
                    return len(segments)
                logger.error("HttpVectorStore.upsert_segments 失败: %s", resp.text)
                return 0
        except Exception as e:
            logger.error("HttpVectorStore.upsert_segments 异常: %s", e)
            return 0

    def search(
        self,
        user_id: int,
        query: str,
        top_k: int = 5,
        collection_id: Optional[str] = None,
    ) -> List[dict]:
        import httpx

        payload = {
            "user_id": user_id,
            "query": query,
            "top_k": top_k,
        }
        if collection_id:
            payload["collection_id"] = collection_id

        try:
            with httpx.Client(timeout=httpx.Timeout(30.0)) as client:
                resp = client.post(f"{self.base_url}/search", json=payload)
                if resp.status_code == 200:
                    data = resp.json()
                    return data.get("hits", [])
                logger.error("HttpVectorStore.search 失败: %s", resp.text)
                return []
        except Exception as e:
            logger.error("HttpVectorStore.search 异常: %s", e)
            return []

    def delete_by_document(self, user_id: int, document_id: str) -> int:
        import httpx

        payload = {
            "user_id": user_id,
            "document_id": document_id,
        }
        try:
            with httpx.Client(timeout=httpx.Timeout(30.0)) as client:
                resp = client.post(f"{self.base_url}/delete", json=payload)
                if resp.status_code == 200:
                    data = resp.json()
                    return data.get("deleted", 0)
                return 0
        except Exception as e:
            logger.error("HttpVectorStore.delete_by_document 异常: %s", e)
            return 0


# ─── 工厂 ─────────────────────────────────────────────

_vector_store: Optional[VectorStoreClient] = None


def get_vector_store() -> VectorStoreClient:
    """获取全局向量存储实例"""
    global _vector_store
    if _vector_store is None:
        if VECTOR_BACKEND == "http":
            import os
            base_url = os.getenv("VECTOR_BASE_URL", "http://127.0.0.1:8080")
            _vector_store = HttpVectorStore(base_url)
            logger.info("向量存储: HTTP (%s)", base_url)
        elif VECTOR_BACKEND == "dify":
            _vector_store = DifyVectorStore()
            logger.info("向量存储: Dify")
        else:
            _vector_store = LocalVectorStore()
            logger.info("向量存储: Local (ChromaStore)")
    return _vector_store


# 兼容：原 chroma_store 被引用处可通过此单例平滑过渡
# 不删除原 chroma_store，仅在此包装