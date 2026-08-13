"""
知序 Agent — tina Agent 封装（检索工具 + 流式对话）

- 组合 KnowledgeRetriever 工具包（kb 命名空间），仅检索当前用户自己的知识库（用户隔离）
- 通过 TinaGateway 统一创建 BaseAPI（key 池 + 用量记账）
- 对话时 Agent 自主决定是否调用检索工具，命中内容用于构建 citations
- 并发安全：predict_stream 以互斥锁保证同一 Agent 实例的生成串行，
  同一用户并发会话不会互相覆盖运行态
"""
import logging
import threading
from typing import Generator, List, Optional, TYPE_CHECKING

from app.core.config import is_local_rag, is_keyword_rag

from app.utils.prompt_loader import load_prompt
from app.services.tutor.citation_service import build_citations_from_hits
from app.services.chat.local_retrieval_service import search as local_search
from app.services.chat.keyword_retrieval_service import search as keyword_search
from app.services.tools.knowledge_retriever import KnowledgeRetriever

if TYPE_CHECKING:
    from sqlalchemy.orm import Session

if not is_local_rag():
    from app.services.tutor.citation_service import filter_hits_by_collection
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
    知序智能体 — 每个用户一个实例

    职责：
        1. 持有 tina Agent + 检索工具包（本地 Chroma / 关键词 / DifyKB）
        2. 通过 TinaGateway 创建 BaseAPI（key 池 + 用量记账）
        3. 对话时 Agent 自主调用检索工具，命中内容注入上下文并构建 citations
    """

    def __init__(self, user_id: int, dataset_id: str = ""):
        self.user_id = user_id
        self.dataset_id = dataset_id or ""
        # 同用户并发会话互斥：一次完整生成期间持有，避免共享运行态互相覆盖
        self._lock = threading.RLock()
        # 最近一次 predict_stream 的聚合结果（完整思考内容 + 完整调用序列工具名），供 chat 层持久化
        self._last_reasoning: str = ""
        self._last_tool_names: list[str] = []

        self.kb = None
        if not is_local_rag() and dataset_id:
            self.kb = DifyKB(dataset_id)

        self.retriever: Optional[KnowledgeRetriever] = None
        self._agent = None

        # 通过 TinaGateway 判断 LLM 就绪状态
        self._llm_ready = False
        try:
            from app.services.tina_gateway import tina_gateway
            self._llm_ready = bool(tina_gateway._api_keys)
            if self._llm_ready:
                logger.info(
                    "ZhixuAgent LLM 就绪 (via Gateway): user_id=%s",
                    user_id,
                )
            else:
                logger.warning("ZhixuAgent LLM 配置不完整: user_id=%s", user_id)
        except Exception as e:
            logger.error(f"ZhixuAgent 初始化失败: user_id={user_id}, error={e}")

    @property
    def is_ready(self) -> bool:
        return self._llm_ready

    def _ensure_agent(self) -> bool:
        """懒创建 tina Agent（llm 每次调用时替换，走 key 池轮换）。

        工具包按 tina 复杂 Agent 范式组织：KnowledgeRetriever 类内定义
        工具并暴露 get_tools()，Agent 以工具包列表组合。
        """
        if self._agent is not None:
            return True
        try:
            from tina import Agent
            from app.services.tina_gateway import tina_gateway

            self.retriever = KnowledgeRetriever(retrieve_fn=self._retrieve)
            self._agent = Agent(
                llm=tina_gateway.create_base_api(),
                tools=[self.retriever.get_tools()],
                system_prompt=SYSTEM_PROMPT,
                max_context_length=80000,
                max_tool_result_length=6000,
                name=f"zhixu_{self.user_id}",
            )
            return True
        except Exception as e:
            logger.error(
                "ZhixuAgent 创建 tina Agent 失败: user_id=%s error=%s",
                self.user_id,
                e,
            )
            return False

    def _retrieve(self, query: str, top_k: int = 5) -> List[dict]:
        """检索当前用户自己的知识库（user_id / collection_id 硬过滤，用户隔离）。"""
        if is_keyword_rag():
            # 纯关键词检索：不走向量，直接对 document_segments 做词法匹配
            return keyword_search(
                self._active_db,
                query,
                user_id=self.user_id,
                collection_id=self._active_collection_id,
                top_k=top_k,
            )
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
        mode: str = "qa",
        token: Optional[str] = None,
    ) -> Generator[dict, None, None]:
        """
        流式对话 — tina Agent 自主决定是否调用检索工具。

        并发安全：整个生成（含生成器提前关闭）期间持有 per-agent 互斥锁，
        同一用户的并发会话串行执行，不共享/覆盖彼此运行态。
        """
        with self._lock:
            yield from self._predict_stream_locked(
                message, history, collection_id, db, mode, token
            )

    def _predict_stream_locked(
        self,
        message: str,
        history: Optional[List[dict]] = None,
        collection_id: Optional[str] = None,
        db: Optional["Session"] = None,
        mode: str = "qa",
        token: Optional[str] = None,
    ) -> Generator[dict, None, None]:
        self._active_collection_id = collection_id
        self._active_db = db

        if not self._llm_ready:
            yield {"role": "assistant", "content": "抱歉，AI 服务暂未配置，请联系管理员。"}
            return

        if not self._ensure_agent():
            yield {"role": "assistant", "content": "抱歉，AI 服务初始化失败，请稍后重试。"}
            return

        # 每次调用从 key 池获取新 llm（轮换 + 并发/RPM 限制）
        try:
            from app.services.tina_gateway import tina_gateway
            llm = tina_gateway.create_base_api()
            llm.set_token(token or "")
            self._agent.llm = llm
            # tina runtime 持有独立的 llm 引用，需同步替换（否则仍用旧 llm：
            # 会导致 set_token 不生效 + aclient 绑定到已关闭的事件循环）
            runtime = getattr(self._agent, "runtime", None)
            if runtime is not None:
                runtime.llm = llm
        except Exception as e:
            logger.error("ZhixuAgent 获取 llm 失败: user_id=%s error=%s", self.user_id, e)
            yield {"role": "assistant", "content": "抱歉，AI 服务暂时不可用，请稍后重试。"}
            return

        # 按 mode 选择 System Prompt
        system_prompt = MODE_PROMPTS.get(mode, SYSTEM_PROMPT)

        from app.services.llm.llm_runner import iter_agent_predict_stream
        from app.services.chat.chat_contract import ChatChunkNormalizer

        # 归一化 + 聚合（思考内容 / 工具名），供 chat 层持久化
        normalizer = ChatChunkNormalizer()
        self._last_reasoning = ""
        self._last_tool_names: list[str] = []

        try:
            for chunk in iter_agent_predict_stream(
                self._agent,
                message,
                history=history,
                system_prompt=system_prompt,
                temperature=0.7,
            ):
                event = normalizer.normalize(chunk)
                if event:
                    yield event
        except Exception as e:
            logger.error(f"ZhixuAgent.predict_stream 错误: {e}")
            yield {"type": "answer", "role": "assistant", "content": "抱歉，生成回复时出错了，请稍后重试。"}
        finally:
            # 生成器被提前关闭（用户打断/连接断开）时也保留聚合结果，供 chat 层保存
            self._last_reasoning = normalizer.reasoning
            self._last_tool_names = list(normalizer.tool_names)
            # 释放 key lease（成功/异常/生成器关闭路径均执行）
            try:
                from app.services.tina_gateway import tina_gateway
                tina_gateway.release_base_api_key(llm)
            except Exception:
                logger.exception("ZhixuAgent 释放 key lease 失败: user_id=%s", self.user_id)

        # 构建 citations（基于检索工具本次命中的内容）
        if db and self.retriever and self.retriever.last_hits:
            try:
                citations = build_citations_from_hits(
                    db, self.user_id, collection_id, self.retriever.last_hits
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

        self._active_collection_id = None
        self._active_db = None
