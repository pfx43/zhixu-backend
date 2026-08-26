"""
知序 Agent — tina Agent 组合封装（检索工具 + 流式对话 + 用户计量）

- 无状态：每次 ``generate`` 从 LLMPool 取一个 llm 实例并绑定**新建**的 tina
  Agent，不共享运行态、不加锁、不动态替换 llm；
- 用户隔离：RAGTools（KnowledgeRetriever）通过 ``set_token`` 动态绑定当前
  用户身份，检索只在数据层按 user_id 硬过滤；
- 用户计量：遍历 Agent 流时发现 usage 键即按 token 记账（record_usage_for_token）；
- 输出映射：内部用 ChatChunkNormalizer 把 Agent chunk 归一为公开 SSE 事件
  （reasoning / tool_call / answer / metadata），chat 路由可直接透传。
"""
from __future__ import annotations

import asyncio
import logging
from typing import AsyncGenerator, List, Optional

from tina import Agent

from app.core.config import LLM_MAX_TOOL_LOOP, is_local_rag, is_keyword_rag
from app.core.database import async_short_session

from app.utils.prompt_loader import load_prompt
from app.services.tutor.citation_service import build_citations_from_hits_async
from app.services.chat.local_retrieval_service import search as local_search
from app.services.chat.keyword_retrieval_service import search_async as keyword_search_async
from app.services.chat.chat_contract import ChatChunkNormalizer
from app.services.tools.knowledge_retriever import KnowledgeRetriever
from app.services.tools.task_tools import TaskPlannerTools, build_user_context
from app.services.llm.llm_pool import llm_pool
from app.services.usage_service import record_usage_for_token

if not is_local_rag():
    from app.services.tutor.citation_service import filter_hits_by_collection_async
    from app.services.knowledge.dify_kb import DifyKB

logger = logging.getLogger(__name__)

SYSTEM_PROMPT = load_prompt("zhixu_agent_qa")
SYSTEM_PROMPT_LEARNING = load_prompt("zhixu_agent_learning")
SYSTEM_PROMPT_CLASSROOM_NOTE = load_prompt("zhixu_agent_classroom_note")

MODE_PROMPTS = {
    "qa": SYSTEM_PROMPT,
    "verify": SYSTEM_PROMPT,
    "learning": SYSTEM_PROMPT_LEARNING,
    "classroom_note": SYSTEM_PROMPT_CLASSROOM_NOTE,
}


class ZhixuAgent:
    """
    知序智能体 — 无状态配置载体 + 流式生成。

    实例只持有用户/知识库配置，不持有任何运行态；每次 ``generate`` 在请求内
    新建 tina Agent（llm 从 LLMPool 取）、绑定 RAGTools 用户身份、全量灌入
    历史后流式生成，因此同一实例可安全服务于任意数量的并发请求。
    """

    def __init__(self, user_id: int, dataset_id: str = ""):
        self.user_id = user_id
        self.dataset_id = dataset_id or ""

        self.kb = None
        if not is_local_rag() and dataset_id:
            self.kb = DifyKB(dataset_id)

        self._llm_ready = llm_pool.instance_count > 0
        if self._llm_ready:
            logger.info("ZhixuAgent LLM 就绪 (via LLMPool): user_id=%s", user_id)
        else:
            logger.warning("ZhixuAgent LLM 配置不完整: user_id=%s", user_id)

    @property
    def is_ready(self) -> bool:
        return self._llm_ready

    def _make_retrieve_fn(self, collection_id):
        """按请求构造检索闭包：只绑定 collection_id；查库用短 AsyncSession。

        工具是 async def，Tina apredict 会直接 await，不再丢默认线程池。
        """

        async def retrieve(user_id: int, query: str, top_k: int = 5) -> List[dict]:
            if is_keyword_rag():
                async with async_short_session() as db:
                    return await keyword_search_async(
                        db,
                        query,
                        user_id=user_id,
                        collection_id=collection_id,
                        top_k=top_k,
                    )
            if is_local_rag():
                return await asyncio.to_thread(
                    local_search,
                    query,
                    user_id=user_id,
                    collection_id=collection_id,
                    top_k=top_k,
                )
            if not self.kb:
                return []
            results = await asyncio.to_thread(self.kb.query, query, top_k=top_k)
            if collection_id is not None:
                async with async_short_session() as db:
                    results = await filter_hits_by_collection_async(
                        db, user_id, collection_id, results
                    )
            return results

        return retrieve

    async def generate(
        self,
        message: str,
        history: Optional[List[dict]] = None,
        collection_id: Optional[str] = None,
        mode: str = "qa",
        token: str = "",
    ) -> AsyncGenerator[dict, None]:
        """流式生成，产出归一化的公开 SSE 事件（reasoning/tool_call/answer/metadata）。

        每次调用独立创建 tina Agent（无共享、无锁）；流中发现 usage 即按 token
        记账；检索工具通过 RAGTools.set_token 动态绑定当前用户。
        """
        if not self._llm_ready:
            yield {
                "type": "answer",
                "role": "assistant",
                "content": "抱歉，AI 服务暂未配置，请联系管理员。",
            }
            return

        llm = llm_pool.acquire()
        if llm is None:
            yield {
                "type": "answer",
                "role": "assistant",
                "content": "抱歉，AI 服务暂时不可用，请稍后重试。",
            }
            return

        retriever = KnowledgeRetriever(
            retrieve_fn=self._make_retrieve_fn(collection_id)
        )
        await retriever.set_token(token)

        # Issue #20：主对话注册「派任务」工具包（只调已有接口，user_id 只来自登录）。
        # 内部出题 submit_question 不挂到这里。
        task_tools = TaskPlannerTools(user_id=self.user_id, token=token)

        try:
            base_prompt = MODE_PROMPTS.get(mode, SYSTEM_PROMPT)
            try:
                context = build_user_context(self.user_id)
                if context:
                    base_prompt = f"{base_prompt}\n\n【当前状态】\n{context}"
            except Exception as e:
                logger.warning(f"构建任务上下文失败: {e}")

            agent = Agent(
                llm=llm,
                tools=[retriever.get_tools(), task_tools.get_tools()],
                system_prompt=base_prompt,
                max_context_length=80000,
                max_tool_result_length=6000,
                max_tool_loop=LLM_MAX_TOOL_LOOP,
                name=f"zhixu_{self.user_id}"
            )
            agent.clear_messages()
            if history:
                for msg in history:
                    role = msg.get("role")
                    content = msg.get("content")
                    if role in ("user", "assistant") and content:
                        agent.add_message(role=role, content=content)

            normalizer = ChatChunkNormalizer()
            async for chunk in agent.apredict(instruction=message, temperature=0.7):
                if isinstance(chunk, dict) and chunk.get("usage"):
                    await record_usage_for_token(token, chunk["usage"])
                for event in normalizer.normalize(chunk):
                    yield event

            if retriever.last_hits:
                try:
                    async with async_short_session() as db:
                        citations = await build_citations_from_hits_async(
                            db, retriever.user_id, collection_id, retriever.last_hits
                        )
                    if citations:
                        yield {
                            "type": "metadata",
                            "role": "assistant",
                            "content": "",
                            "citations": [c.model_dump() for c in citations],
                        }
                except Exception as e:
                    logger.warning(f"ZhixuAgent 构建 citations 失败: {e}")
        except Exception as e:
            logger.error(f"ZhixuAgent.generate 错误: {e}")
            yield {
                "type": "answer",
                "role": "assistant",
                "content": "抱歉，生成回复时出错了，请稍后重试。",
            }
