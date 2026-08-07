"""
知拾 Agent — 封装 LLM 调用 + 本地/Dify 检索，提供流式对话
"""
import logging
from typing import Generator, List, Optional, TYPE_CHECKING

from app.core.config import is_local_rag

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

SYSTEM_PROMPT_LEARNING = """你是知拾（Zhishi）的苏格拉底式学习教练 Tina。你的目标不是直接给出答案，而是通过提问引导学习者自己思考并发现答案。

## 核心原则
- 永远不要直接给出答案，而是通过反问和提示引导学习者思考
- 如果学习者卡住了，提供分步骤的线索，逐步降低难度
- 肯定学习者的每一个正确推理，鼓励试错
- 基于用户知识库中的文档内容设计引导问题

## 对话策略
1. 先理解学习者当前的知识水平和困惑点
2. 提出开放式问题，引导学习者表达自己的理解
3. 针对学习者的回答，提出更深一层的问题
4. 在学习者接近答案时，给予积极反馈
5. 如果学习者请求直接答案，温和地解释"自己发现的知识记得更牢"

## 回答风格
- 友善、鼓励、有耐心
- 使用"你觉得呢？""如果这样想呢？""再想想看？"等引导语
- 适度使用 Markdown 格式，但保持对话感
- 使用中文，适当使用 emoji 增加亲和力 😊
"""

SYSTEM_PROMPT_CLASSROOM_NOTE = """你是知拾（Zhishi）的课堂笔记助手 Tina。你帮助用户将对话内容整理为结构化的学习笔记。

## 核心原则
- **严格基于当前对话中的事实**，不凭空添加任何对话中没有涉及的知识点
- 以 Markdown 格式输出结构清晰的笔记
- 只提取和整理对话中明确讨论过的内容

## 笔记模板
```markdown
# 📝 [主题标题]
> 生成时间：[当前时间]
> 来源：本次对话

## 一、核心概念
- [对话中讨论的关键概念1]
- [对话中讨论的关键概念2]

## 二、知识要点
### 2.1 [要点标题]
[对话中涉及的详细解释]

### 2.2 [要点标题]
[对话中涉及的详细解释]

## 三、关键结论
1. [从对话中提取的结论1]
2. [从对话中提取的结论2]

## 四、待探索问题
- [对话中学习者表示还想了解的问题]
```

## 输出要求
- 直接输出 Markdown 笔记，不需要额外解释
- 如果对话中没有足够内容生成笔记，诚实地告知用户
- 使用中文
"""

MODE_PROMPTS = {
    "qa": SYSTEM_PROMPT,
    "verify": SYSTEM_PROMPT,
    "learning": SYSTEM_PROMPT_LEARNING,
    "classroom_note": SYSTEM_PROMPT_CLASSROOM_NOTE,
}


class ZhishiAgent:
    """
    知拾智能体 — 每个用户一个实例

    职责：
        1. 持有检索后端（本地 Chroma 或 DifyKB）
        2. 通过 TinaGateway 统一调用 LLM（key 池 + 用量记账）
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

        # 通过 TinaGateway 判断 LLM 就绪状态
        self._llm_ready = False
        try:
            from app.services.tina_gateway import tina_gateway
            self._llm_ready = bool(tina_gateway._api_keys)
            if self._llm_ready:
                logger.info(
                    "ZhishiAgent LLM 就绪 (via Gateway): user_id=%s",
                    user_id,
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
        mode: str = "qa",
    ) -> Generator[dict, None, None]:
        """
        流式对话 — 通过 TinaGateway 调用 LLM（key 池轮换 + 自动用量记账）
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

        # 2. 根据 mode 选择 System Prompt
        system_prompt = MODE_PROMPTS.get(mode, SYSTEM_PROMPT)

        # 3. 构建消息
        messages = [{"role": "system", "content": system_prompt}]
        if history:
            for h in history[-20:]:
                role = h.get("role", "user")
                content = h.get("content", "")
                if role in ("user", "assistant") and content:
                    messages.append({"role": role, "content": content})
        messages.append({"role": "user", "content": enhanced_message})

        # 3. 通过 TinaGateway 流式调用（统一 key 池 + 用量记账）
        try:
            from app.services.tina_gateway import tina_gateway

            for chunk in tina_gateway.stream_chat(
                user_id=self.user_id,
                instruction="",
                messages=messages,
                sys_prompt="",
                temperature=0.7,
                max_tokens=2048,
            ):
                content = chunk.get("content", "")
                reasoning = chunk.get("reasoning_content", "")
                if content:
                    yield {"role": "assistant", "content": content}
                if reasoning:
                    yield {"role": "assistant", "content": "", "reasoning_content": reasoning}

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
