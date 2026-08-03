"""
知拾 Agent — 封装 LLM 调用 + 本地/Dify 检索，提供流式对话
"""
import json
import logging
import os
from typing import Generator, List, Optional, TYPE_CHECKING

import requests
from dotenv import dotenv_values

from app.core.config import is_local_rag
from app.utils.tina_loader import tina_env_path

from app.services.tutor.citation_service import build_citations_from_hits
from app.services.chat.local_retrieval_service import search as local_search

if TYPE_CHECKING:
    from sqlalchemy.orm import Session

if not is_local_rag():
    from app.services.tutor.citation_service import filter_hits_by_collection
    from app.services.knowledge.dify_kb import DifyKB

logger = logging.getLogger(__name__)

SYSTEM_PROMPT = """你是知拾（Zhishi）的知识管理助手 Tina。你帮助用户管理知识、解答问题。

## 核心能力
- 基于用户知识库中的文档内容回答问题
- 如果知识库中有相关内容，优先基于知识库回答，并引用来源
- 如果知识库中没有相关内容，基于你自身的知识诚实回答
- 帮助用户整理笔记、生成学习路径、解释复杂概念

## 回答风格
- 清晰、有条理，适当使用 Markdown 格式
- 对于复杂问题，先给出概述再展开细节
- 如果引用了知识库内容，可以标明"根据你的知识库..."
- 使用中文回答，专业术语保留英文原文
"""


def _load_llm_config() -> dict:
    """从 tina.env 读取 LLM 配置"""
    env_path = tina_env_path()
    if os.path.exists(env_path):
        return dict(dotenv_values(env_path))
    return {}


class ZhishiAgent:
    """
    知拾智能体 — 每个用户一个实例

    职责：
        1. 持有检索后端（本地 Chroma 或 DifyKB）
        2. 直接调用 LLM API（绕过 Tina 框架避免 Windows 兼容问题）
        3. 对话时自动检索知识库，注入上下文后流式输出
    """

    def __init__(self, user_id: int, dataset_id: str = ""):
        self.user_id = user_id
        self.dataset_id = dataset_id or ""
        self._active_collection_id: Optional[str] = None
        self._active_db: Optional["Session"] = None

        self.kb = None
        if not is_local_rag() and dataset_id:
            self.kb = DifyKB(dataset_id)

        # 直接加载 LLM 配置，不依赖 Tina 框架
        self._llm_ready = False
        try:
            cfg = _load_llm_config()
            self._api_key = cfg.get("LLM_API_KEY", "").strip('"').strip("'")
            self._base_url = cfg.get("BASE_URL", "").strip('"').strip("'")
            self._model = cfg.get("MODEL_NAME", "").strip('"').strip("'")

            if self._api_key and self._base_url and self._model:
                self._llm_ready = True
                logger.info(
                    "ZhishiAgent LLM 就绪: model=%s, url=%s, user_id=%s",
                    self._model, self._base_url[:50], user_id,
                )
            else:
                logger.warning("ZhishiAgent LLM 配置不完整: user_id=%s", user_id)
        except Exception as e:
            logger.error(f"ZhishiAgent 初始化失败: user_id={user_id}, error={e}")

    @property
    def is_ready(self) -> bool:
        return self._llm_ready

    def _retrieve(self, query: str, top_k: int = 5) -> List[dict]:
        if is_local_rag():
            return local_search(
                query,
                user_id=self.user_id,
                collection_id=self._active_collection_id,
                top_k=top_k,
            )
        if not self.kb:
            return []
        results = self.kb.query(query, top_k=top_k)
        if self._active_db and self._active_collection_id is not None:
            results = filter_hits_by_collection(
                self._active_db,
                self.user_id,
                self._active_collection_id,
                results,
            )
        return results

    def predict_stream(
        self,
        message: str,
        history: Optional[List[dict]] = None,
        collection_id: Optional[str] = None,
        db: Optional["Session"] = None,
    ) -> Generator[dict, None, None]:
        """
        流式对话 — 直接调用 DeepSeek API（requests 同步流式）
        """
        self._active_collection_id = collection_id
        self._active_db = db

        if not self._llm_ready:
            yield {"role": "assistant", "content": "抱歉，AI 服务暂未配置，请联系管理员。"}
            return

        # 1. 检索知识库
        enhanced_message = message
        retrieval_hits: List[dict] = []

        knowledge_context = ""
        try:
            retrieval_hits = self._retrieve(message, top_k=3)
            if retrieval_hits:
                fragments = []
                for i, r in enumerate(retrieval_hits, 1):
                    fragments.append(
                        f"[片段{i}] (相关度: {r['score']:.2f})\n{r['content']}"
                    )
                knowledge_context = "\n\n".join(fragments)
        except Exception as e:
            logger.warning(f"ZhishiAgent 知识库检索失败: {e}")

        if knowledge_context:
            enhanced_message = (
                f"请基于以下知识库内容回答用户问题。\n\n"
                f"## 知识库相关内容\n{knowledge_context}\n\n"
                f"## 用户问题\n{message}"
            )

        # 2. 构建消息
        messages = [{"role": "system", "content": SYSTEM_PROMPT}]
        if history:
            for h in history[-20:]:
                role = h.get("role", "user")
                content = h.get("content", "")
                if role in ("user", "assistant") and content:
                    messages.append({"role": role, "content": content})
        messages.append({"role": "user", "content": enhanced_message})

        # 3. 调用 DeepSeek API（同步流式）
        try:
            headers = {
                "Authorization": f"Bearer {self._api_key}",
                "Content-Type": "application/json",
            }
            payload = {
                "model": self._model,
                "messages": messages,
                "stream": True,
                "temperature": 0.7,
                "max_tokens": 2048,
            }

            resp = requests.post(
                self._base_url,
                headers=headers,
                json=payload,
                stream=True,
                timeout=120,
            )
            resp.raise_for_status()

            for line in resp.iter_lines():
                if not line:
                    continue
                line = line.decode("utf-8")
                if line.startswith("data: "):
                    data_str = line[6:]
                    if data_str.strip() == "[DONE]":
                        break
                    try:
                        data = json.loads(data_str)
                        delta = data.get("choices", [{}])[0].get("delta", {})
                        content = delta.get("content", "")
                        reasoning = delta.get("reasoning_content", "")
                        if content:
                            yield {"role": "assistant", "content": content}
                        if reasoning:
                            yield {"role": "assistant", "content": "", "reasoning_content": reasoning}
                    except json.JSONDecodeError:
                        continue

        except requests.exceptions.Timeout:
            logger.error("ZhishiAgent LLM 请求超时")
            yield {"role": "assistant", "content": "抱歉，AI 服务响应超时，请稍后重试。"}
        except Exception as e:
            logger.error(f"ZhishiAgent.predict_stream 错误: {e}")
            yield {"role": "assistant", "content": f"抱歉，生成回复时出错了，请稍后重试。"}

        # 4. 构建 citations
        if db and retrieval_hits:
            try:
                citations = build_citations_from_hits(
                    db, self.user_id, collection_id, retrieval_hits
                )
                if citations:
                    yield {
                        "role": "assistant",
                        "content": "",
                        "citations": [c.model_dump() for c in citations],
                    }
            except Exception as e:
                logger.warning(f"ZhishiAgent 构建 citations 失败: {e}")

        self._active_collection_id = None
        self._active_db = None
