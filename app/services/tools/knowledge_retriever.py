"""
知识库检索工具包 — 把检索能力以 tina Tools 形式暴露给 Agent。

按 tina 复杂 Agent 开发范式：类内定义工具，Tools(name=...) 设置命名空间
防止与其他工具包冲突，get_tools() 供 Agent 组合使用。
"""
import json
import logging
from typing import Callable, List, Optional

from tina import Tools

from app.services.usage_service import resolve_user_id_by_token

logger = logging.getLogger(__name__)

_RETRIEVAL_TOP_K_DEFAULT = 5
_RETRIEVAL_TOP_K_MAX = 10


class KnowledgeRetriever:
    """
    知识库检索工具包 — 只检索当前绑定用户的文档（用户隔离）。

    通过 ``set_token`` 动态绑定当前用户身份，检索工具随之为该用户工作；
    ``last_hits`` 保留本次命中结果，供调用方构建 citations。
    """

    def __init__(self, retrieve_fn: Callable[[int, str, int], List[dict]]):
        self._retrieve_fn = retrieve_fn
        self._user_id: int = 0
        self.last_hits: List[dict] = []

        self.tools = Tools(name="kb")
        self.tools.register_tool(tool=self.search)

    async def set_token(self, token: str) -> None:
        """动态绑定当前用户身份：token 反查 user_id，检索工具随之切换。"""
        self._user_id = await resolve_user_id_by_token(token)

    @property
    def user_id(self) -> int:
        return self._user_id

    def get_tools(self) -> Tools:
        """把工具包公开给 Agent 使用。"""
        return self.tools

    def search(self, query: str, top_k: int = 5) -> str:
        """
        在用户自己的知识库中检索相关内容（仅限当前登录用户的文档，不涉及其他用户数据）。

        Args:
            query (str): 检索关键词或用户问题的核心内容
            top_k (int): 返回片段数量上限，默认 5，最大 10
        """
        hits = self._retrieve_fn(
            self._user_id,
            query,
            top_k=max(1, min(int(top_k), _RETRIEVAL_TOP_K_MAX)),
        )
        self.last_hits = list(hits)

        fragments = []
        for h in hits:
            fragments.append(
                {
                    "score": round(float(h.get("score") or 0.0), 4),
                    "content": h.get("content", ""),
                    "title": h.get("title"),
                    "display_name": h.get("display_name"),
                    "document_id": h.get("document_id"),
                    "segment_id": h.get("segment_id"),
                }
            )
        return json.dumps(
            {"hits": fragments, "count": len(fragments)},
            ensure_ascii=False,
        )
