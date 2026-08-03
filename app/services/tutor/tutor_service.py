"""
辅导会话服务 — 绑定题目与分段上下文的苏格拉底式对话
"""
import json
import logging
from datetime import datetime, timezone
from typing import Generator, List, Optional, Tuple
from uuid import uuid4

from fastapi import HTTPException
from sqlalchemy.orm import Session

from app.core.redis import cache
from app.crud import question as question_crud
from app.crud import quiz as quiz_crud
from app.crud import tutor as tutor_crud
from app.models import DocumentSegment, GlobalQuestion, QuestionProvenance, QuizAnswer, UserQuestionRef
from app.schemas.tutor import (
    SegmentContextOut,
    TutorMessage,
    TutorReplyOut,
    TutorSessionCreate,
    TutorSessionOut,
)
from app.utils.tina_loader import tina_env_path
from app.services.llm.llm_runner import agent_predict_no_stream, iter_agent_predict_stream

logger = logging.getLogger(__name__)

SEGMENT_MAX_CHARS = 4000

SOCRATIC_RULES = """## 辅导规则
- 你是苏格拉底式辅导老师，通过提问引导学习者思考
- **禁止直接给出题目的最终答案**
- 优先围绕下方「教材分段」内容讲解，不要跑题到无关知识
- 结合学习者的困惑，用简短、清晰的中文回复
- 适当使用 Markdown 列表或加粗突出重点
"""

_in_memory_history: dict[str, List[dict]] = {}


def _now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def _history_key(user_id: int, chat_session_id: str) -> str:
    return f"tutor:history:{user_id}:{chat_session_id}"


def _load_history(user_id: int, chat_session_id: str) -> List[dict]:
    key = _history_key(user_id, chat_session_id)
    try:
        raw_messages = cache.lrange(key, 0, -1)
        if raw_messages:
            return [json.loads(item) for item in raw_messages]
    except Exception as e:
        logger.warning(f"辅导历史 Redis 读取失败，回退内存: {e}")
    return list(_in_memory_history.get(key, []))


def _save_message(user_id: int, chat_session_id: str, role: str, content: str) -> dict:
    key = _history_key(user_id, chat_session_id)
    message = {"role": role, "content": content, "created_at": _now_iso()}
    try:
        cache.rpush(key, json.dumps(message, ensure_ascii=False))
    except Exception as e:
        logger.warning(f"辅导历史 Redis 写入失败，回退内存: {e}")
        _in_memory_history.setdefault(key, []).append(message)
        return message
    if key not in _in_memory_history:
        _in_memory_history[key] = []
    _in_memory_history[key].append(message)
    return message


def _truncate_segment_text(content: str, excerpt: Optional[str]) -> str:
    if excerpt and excerpt.strip():
        text = excerpt.strip()
    else:
        text = content or ""
    if len(text) > SEGMENT_MAX_CHARS:
        return text[:SEGMENT_MAX_CHARS] + "\n\n…（分段内容已截断）"
    return text


def _format_question_block(question: GlobalQuestion) -> str:
    lines = [f"**题干**：{question.stem}"]
    options = question_crud.parse_options_json(question.options)
    if options:
        lines.append("**选项**：")
        for opt in options:
            key = opt.get("key", "")
            text = opt.get("text", "")
            lines.append(f"- {key}. {text}")
    lines.append(f"**题型**：{question.question_type}")
    return "\n".join(lines)


def _build_system_prompt(
    question: GlobalQuestion,
    segment: DocumentSegment,
    excerpt: Optional[str],
    user_answer: Optional[str] = None,
    unknown: bool = False,
) -> str:
    segment_text = _truncate_segment_text(segment.content, excerpt)
    title = segment.title or "（无标题）"
    if unknown:
        user_part = "\n## 学习者当前作答\n（表示「我不会」，尚未作答）\n"
    elif user_answer:
        user_part = f"\n## 学习者当前作答\n{user_answer}\n"
    else:
        user_part = ""

    return (
        "你是知拾（Zhishi）的苏格拉底式辅导老师 Tina。\n\n"
        f"{SOCRATIC_RULES}\n"
        f"## 当前辅导题目\n{_format_question_block(question)}\n"
        f"{user_part}"
        f"## 内部参考（仅供你判断，禁止直接告诉学习者）\n"
        f"**正确答案**：{question.answer or '（未知）'}\n\n"
        f"## 教材分段（辅导依据）\n"
        f"**章节**：{title}\n\n"
        f"{segment_text}\n"
    )


def _resolve_provenance(
    db: Session,
    question_id: str,
    document_id: Optional[str] = None,
) -> Tuple[QuestionProvenance, DocumentSegment]:
    provs = question_crud.list_provenance_for_question(db, question_id)
    if not provs:
        raise HTTPException(status_code=404, detail="题目缺少溯源信息，无法辅导")

    prov = provs[0]
    if document_id:
        for p in provs:
            if p.document_id == document_id:
                prov = p
                break

    if not prov.segment_id:
        raise HTTPException(status_code=404, detail="题目未绑定教材分段")

    segment = (
        db.query(DocumentSegment)
        .filter(DocumentSegment.id == prov.segment_id)
        .first()
    )
    if not segment:
        raise HTTPException(status_code=404, detail="教材分段不存在")

    return prov, segment


def _verify_user_question_access(
    db: Session, user_id: int, question_id: str, document_id: str
) -> None:
    ref = (
        db.query(UserQuestionRef)
        .filter(
            UserQuestionRef.user_id == user_id,
            UserQuestionRef.question_id == question_id,
            UserQuestionRef.document_id == document_id,
        )
        .first()
    )
    if not ref:
        raise HTTPException(status_code=404, detail="题目不存在或无权访问")


def _resolve_quiz_context(
    db: Session,
    user_id: int,
    question_id: str,
    quiz_session_id: Optional[str],
    quiz_answer_id: Optional[str],
) -> Tuple[Optional[str], Optional[str], bool]:
    """返回 (document_id, user_answer, unknown)。"""
    document_id: Optional[str] = None
    user_answer: Optional[str] = None
    unknown = False

    if quiz_answer_id:
        answer = db.query(QuizAnswer).filter(QuizAnswer.id == quiz_answer_id).first()
        if not answer or answer.user_id != user_id:
            raise HTTPException(status_code=404, detail="答题记录不存在")
        if answer.question_id != question_id:
            raise HTTPException(status_code=400, detail="答题记录与题目不匹配")
        if quiz_session_id and answer.session_id != quiz_session_id:
            raise HTTPException(status_code=400, detail="答题记录与会话不匹配")
        quiz_session_id = answer.session_id
        user_answer = answer.user_answer
        unknown = answer.status == "unknown"

    if quiz_session_id:
        session = quiz_crud.get_session(db, quiz_session_id, user_id)
        if not session:
            logger.warning(
                "tutor: quiz session %s not found for user %s, continuing without quiz context",
                quiz_session_id,
                user_id,
            )
        else:
            sq = quiz_crud.get_session_question(db, quiz_session_id, question_id)
            if not sq:
                raise HTTPException(status_code=400, detail="题目不在该刷题会话中")
            document_id = session.document_id
            if not quiz_answer_id:
                ans = quiz_crud.get_answer(db, quiz_session_id, question_id)
                if ans:
                    user_answer = ans.user_answer
                    unknown = ans.status == "unknown"

    return document_id, user_answer, unknown


class SocraticTutorAgent:
    """轻量 Tina Agent — 仅用于辅导，不挂载知识库工具。"""

    def __init__(self, system_prompt: str, name: str = "socratic_tutor"):
        self.system_prompt = system_prompt
        self._agent = None
        self._llm = None
        self._name = name
        self._init_agent()

    def _init_agent(self) -> None:
        try:
            from tina import Agent
            from tina.agent.core.context_manager import ContextManager
            from tina.llm import BaseAPI

            context_manager = ContextManager(max_length=80000, max_tool_result_length=4000)
            context_manager.set_system_message(self.system_prompt)
            self._llm = BaseAPI(env_path=tina_env_path())
            self._agent = Agent(
                llm=self._llm,
                tools=None,
                system_prompt=self.system_prompt,
                max_context_length=80000,
                max_tool_result_length=4000,
                name=self._name,
            )
        except Exception as e:
            logger.error(f"SocraticTutorAgent 初始化失败: {e}")
            self._agent = None

    @property
    def is_ready(self) -> bool:
        return self._agent is not None

    def predict_sync(self, message: str, history: Optional[List[dict]] = None) -> str:
        if not self._agent:
            return "抱歉，AI 辅导服务暂时不可用，请稍后重试。"
        try:
            self._agent.clear_messages()
            self._agent.context_manager.set_system_message(self.system_prompt)
            if history:
                for msg in history:
                    role = msg.get("role", "user")
                    part = msg.get("content", "")
                    if role in ("user", "assistant"):
                        self._agent.add_message(role=role, content=part)
            result = agent_predict_no_stream(self._agent, instruction=message)
            if isinstance(result, dict):
                return result.get("content", "") or str(result)
            if hasattr(result, "get"):
                return result.get("content", "") or str(result)
            content = getattr(result, "content", None)
            if content:
                return content
            return str(result)
        except Exception as e:
            logger.error(f"SocraticTutorAgent.predict_sync 错误: {e}")
            return f"抱歉，生成辅导回复时出错了：{str(e)}"

    def predict_stream(
        self, message: str, history: Optional[List[dict]] = None
    ) -> Generator[dict, None, None]:
        if not self._agent:
            yield {"role": "assistant", "content": "抱歉，AI 辅导服务暂时不可用，请稍后重试。"}
            return
        try:
            for chunk in iter_agent_predict_stream(
                self._agent,
                message,
                history=history,
                system_prompt=self.system_prompt,
            ):
                yield chunk
        except Exception as e:
            logger.error(f"SocraticTutorAgent.predict_stream 错误: {e}")
            yield {"role": "assistant", "content": f"抱歉，生成辅导回复时出错了：{str(e)}"}


def _call_tutor_agent(
    system_prompt: str,
    message: str,
    history: Optional[List[dict]] = None,
    *,
    stream: bool = False,
):
    agent = SocraticTutorAgent(system_prompt=system_prompt)
    if stream:
        return agent.predict_stream(message, history)
    return agent.predict_sync(message, history)


def _build_session_out(
    db: Session,
    session,
    question: GlobalQuestion,
    segment: DocumentSegment,
    excerpt: Optional[str],
    messages: Optional[List[dict]] = None,
) -> TutorSessionOut:
    snippet = _truncate_segment_text(segment.content, excerpt)
    if len(snippet) > 500:
        snippet = snippet[:500] + "…"
    msg_list = messages if messages is not None else _load_history(
        session.user_id, session.chat_session_id
    )
    return TutorSessionOut(
        id=session.id,
        question_id=session.question_id,
        document_id=session.document_id,
        segment_id=session.segment_id,
        quiz_answer_id=session.quiz_answer_id,
        status=session.status,
        question_stem=question.stem,
        segment_context=SegmentContextOut(
            segment_id=segment.id,
            title=segment.title,
            snippet=snippet,
        ),
        messages=[TutorMessage(**m) for m in msg_list],
        created_at=session.created_at,
        updated_at=session.updated_at,
    )


def create_tutor_session(
    db: Session, user_id: int, payload: TutorSessionCreate
) -> TutorSessionOut:
    question = question_crud.get_question_by_id(db, payload.question_id)
    if not question:
        raise HTTPException(status_code=404, detail="题目不存在")

    document_id, user_answer, unknown = _resolve_quiz_context(
        db,
        user_id,
        payload.question_id,
        payload.quiz_session_id,
        payload.quiz_answer_id,
    )

    prov, segment = _resolve_provenance(db, payload.question_id, document_id)
    _verify_user_question_access(db, user_id, payload.question_id, prov.document_id)

    quiz_answer_id = payload.quiz_answer_id
    if not quiz_answer_id and payload.quiz_session_id:
        ans = quiz_crud.get_answer(db, payload.quiz_session_id, payload.question_id)
        if ans:
            quiz_answer_id = ans.id

    chat_session_id = uuid4().hex
    session = tutor_crud.create_session(
        db,
        user_id=user_id,
        question_id=payload.question_id,
        document_id=prov.document_id,
        segment_id=prov.segment_id,
        chat_session_id=chat_session_id,
        quiz_answer_id=quiz_answer_id,
    )

    system_prompt = _build_system_prompt(
        question, segment, prov.excerpt, user_answer=user_answer, unknown=unknown
    )
    _save_message(user_id, chat_session_id, "system", system_prompt)
    db.flush()

    return _build_session_out(
        db, session, question, segment, prov.excerpt, messages=[]
    )


def get_tutor_session(db: Session, user_id: int, session_id: str) -> TutorSessionOut:
    session = tutor_crud.get_session(db, session_id, user_id)
    if not session:
        raise HTTPException(status_code=404, detail="辅导会话不存在")

    question = question_crud.get_question_by_id(db, session.question_id)
    if not question:
        raise HTTPException(status_code=404, detail="题目不存在")

    segment = (
        db.query(DocumentSegment)
        .filter(DocumentSegment.id == session.segment_id)
        .first()
    )
    if not segment:
        raise HTTPException(status_code=404, detail="教材分段不存在")

    provs = question_crud.list_provenance_for_question(db, session.question_id)
    excerpt = None
    for p in provs:
        if p.segment_id == session.segment_id:
            excerpt = p.excerpt
            break

    history = _load_history(user_id, session.chat_session_id)
    visible = [m for m in history if m.get("role") != "system"]
    return _build_session_out(
        db, session, question, segment, excerpt, messages=visible
    )


def _get_system_prompt_from_history(history: List[dict]) -> str:
    for msg in history:
        if msg.get("role") == "system":
            return msg.get("content", "")
    return ""


def send_tutor_message(
    db: Session,
    user_id: int,
    session_id: str,
    content: str,
) -> TutorReplyOut:
    session = tutor_crud.get_session(db, session_id, user_id)
    if not session:
        raise HTTPException(status_code=404, detail="辅导会话不存在")
    if session.status != "active":
        raise HTTPException(status_code=400, detail="辅导会话已结束")

    chat_id = session.chat_session_id
    _save_message(user_id, chat_id, "user", content)

    history = _load_history(user_id, chat_id)
    system_prompt = _get_system_prompt_from_history(history)
    conv_history = [
        m for m in history if m.get("role") in ("user", "assistant")
    ][:-1]

    reply = _call_tutor_agent(
        system_prompt, content, conv_history, stream=False
    )
    if not isinstance(reply, str):
        reply = "抱歉，未能生成辅导回复。"

    _save_message(user_id, chat_id, "assistant", reply)
    session.updated_at = datetime.now(timezone.utc)
    db.flush()

    return TutorReplyOut(role="assistant", content=reply, created_at=_now_iso())


def stream_tutor_message(
    db: Session,
    user_id: int,
    session_id: str,
    content: str,
) -> Generator[str, None, None]:
    session = tutor_crud.get_session(db, session_id, user_id)
    if not session:
        data = json.dumps(
            {"session_id": session_id, "role": "assistant", "content": "辅导会话不存在"},
            ensure_ascii=False,
        )
        yield f"event: message\ndata: {data}\n\n"
        return

    chat_id = session.chat_session_id
    _save_message(user_id, chat_id, "user", content)

    history = _load_history(user_id, chat_id)
    system_prompt = _get_system_prompt_from_history(history)
    conv_history = [
        m for m in history if m.get("role") in ("user", "assistant")
    ][:-1]

    stream = _call_tutor_agent(
        system_prompt, content, conv_history, stream=True
    )
    full_content = ""
    if hasattr(stream, "__iter__"):
        for chunk in stream:
            role = chunk.get("role", "assistant")
            part = chunk.get("content", "")
            if part:
                full_content += part
            payload = {
                "session_id": session_id,
                "role": role,
                "content": part,
            }
            data = json.dumps(payload, ensure_ascii=False)
            yield f"event: message\ndata: {data}\n\n"

    if full_content:
        _save_message(user_id, chat_id, "assistant", full_content)
        session.updated_at = datetime.now(timezone.utc)
        db.flush()
