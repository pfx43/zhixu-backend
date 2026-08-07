"""
本地向量检索 — Chroma 检索 + citation 元数据
"""
from typing import List, Optional

from app.services.knowledge.vector_store import get_vector_store

_vector_store = get_vector_store()


def search(
    query: str,
    *,
    user_id: int,
    collection_id: Optional[str] = None,
    top_k: int = 5,
) -> List[dict]:
    """
    检索用户知识库片段。

    返回命中列表，字段含 score/content/document_id/segment_id/title/char_start/char_end/display_name
    """
    if not query or not query.strip():
        return []
    return _vector_store.search(
        query.strip(),
        user_id=user_id,
        collection_id=collection_id,
        top_k=top_k,
    )
