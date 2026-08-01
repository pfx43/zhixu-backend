"""
文本向量化 — 懒加载 sentence-transformers，测试环境可回退确定性向量
"""
import hashlib
import logging
import math
from typing import List, Optional

from app.core.config import EMBEDDING_MODEL

logger = logging.getLogger(__name__)

_model = None
_model_load_failed = False
EMBEDDING_DIM = 512  # BAAI/bge-small-zh-v1.5 输出维度
_FALLBACK_DIM = EMBEDDING_DIM


def _load_model():
    global _model, _model_load_failed
    if _model is not None or _model_load_failed:
        return _model
    try:
        from sentence_transformers import SentenceTransformer

        logger.info("加载 embedding 模型: %s", EMBEDDING_MODEL)
        _model = SentenceTransformer(EMBEDDING_MODEL)
        return _model
    except Exception as e:
        _model_load_failed = True
        logger.warning("embedding 模型加载失败，使用 fallback: %s", e)
        return None


def _fallback_embed(text: str, dim: int = _FALLBACK_DIM) -> List[float]:
    """确定性伪向量，供测试或无 GPU/网络环境使用。"""
    digest = hashlib.sha256(text.encode("utf-8")).digest()
    vec: List[float] = []
    i = 0
    while len(vec) < dim:
        chunk = digest[i % len(digest) : (i % len(digest)) + 4]
        if len(chunk) < 4:
            chunk = (chunk + digest)[:4]
        val = int.from_bytes(chunk, "big") / (2**32)
        vec.append(val * 2 - 1)
        i += 4
    norm = math.sqrt(sum(v * v for v in vec)) or 1.0
    return [v / norm for v in vec]


def embed_texts(texts: List[str]) -> List[List[float]]:
    """将文本列表编码为向量列表。"""
    if not texts:
        return []

    model: Optional[object] = _load_model()
    if model is not None:
        try:
            vectors = model.encode(texts, normalize_embeddings=True)
            return [v.tolist() for v in vectors]
        except Exception as e:
            logger.warning("embedding 编码失败，回退 fallback: %s", e)

    return [_fallback_embed(t) for t in texts]
