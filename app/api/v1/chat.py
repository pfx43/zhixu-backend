import json
import logging
from uuid import uuid4
from datetime import datetime, timezone
from typing import Optional, List

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session

from app.api.deps import get_current_active_user, get_current_token, get_db
from app.api.deps_quota import check_quota
from app.core.config import is_local_rag
from app.core.redis import cache
from app.core.agent_manager import agent_manager
from app.schemas.common import (
    ChatBreakRequest,
    ChatRequest,
    ChatResponse,
    ChatHistoryItem,
    ChatSession,
    ChatSessionList,
)
from app.services.tutor.citation_service import resolve_chat_collection
from app.services.knowledge.storage_service import storage_service
from app.services.tcn.tcn_client import tcn_client
import asyncio

logger = logging.getLogger(__name__)

router = APIRouter(tags=["chat"])

VALID_MODES = {"qa", "learning", "classroom_note", "verify"}

# 用户打断：前端 POST /api/v1/chat/break 设置标记，流式生成器检查到后停止，
# 已产出的内容保存并在消息末尾追加打断提示。
INTERRUPT_NOTICE = "\n\n> ⏹️ 对话已被用户打断"
_INTERRUPT_TTL = 300  # 打断标记有效期（秒）


def _interrupt_key(user_id: int, session_id: str) -> str:
    return f"chat:interrupt:{user_id}:{session_id}"


def _mark_interrupt(user_id: int, session_id: str) -> None:
    """前端请求打断：写入一次性标记。"""
    try:
        cache.set_value(_interrupt_key(user_id, session_id), "1")
        cache.expire(_interrupt_key(user_id, session_id), _INTERRUPT_TTL)
    except Exception as e:
        logger.warning(f"标记打断失败: {e}")


def _check_interrupt(user_id: int, session_id: str) -> bool:
    """检查并消费打断标记（一次性：取到即删除，不会残留影响下次对话）。"""
    try:
        key = _interrupt_key(user_id, session_id)
        if cache.get_value(key):
            cache.delete_key(key)
            return True
        return False
    except Exception:
        return False


def _clear_interrupt(user_id: int, session_id: str) -> None:
    """清除残留标记（新流启动时调用，防止上次的打断信号误中断本轮）。"""
    try:
        cache.delete_key(_interrupt_key(user_id, session_id))
    except Exception:
        pass


def _session_list_key(user_id: int) -> str:
    return f"chat:sessions:{user_id}"


def _session_meta_key(user_id: int, session_id: str) -> str:
    return f"chat:session:{user_id}:{session_id}"


def _session_history_key(user_id: int, session_id: str) -> str:
    return f"chat:history:{user_id}:{session_id}"


def _now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


# ─── 文件持久化（主存储） ──────────────────────────────

def _file_save_full(user_id: int, session_id: str, meta: dict, messages: List[dict]):
    """将完整会话数据写入文件"""
    try:
        storage_service.save_chat_history(user_id, session_id, {
            "meta": meta,
            "messages": messages,
        })
    except Exception as e:
        logger.error(f"文件保存会话失败: {e}")


def _file_load_full(user_id: int, session_id: str) -> Optional[dict]:
    """从文件读取完整会话数据"""
    try:
        return storage_service.load_chat_history(user_id, session_id)
    except Exception as e:
        logger.error(f"文件读取会话失败: {e}")
        return None


def _file_list_sessions(user_id: int) -> List[dict]:
    """从文件目录列出所有会话"""
    try:
        return storage_service.list_chat_sessions(user_id)
    except Exception as e:
        logger.error(f"文件列出会话失败: {e}")
        return []


def _file_delete_session(user_id: int, session_id: str) -> bool:
    """删除文件中的会话"""
    try:
        return storage_service.delete_chat_history(user_id, session_id)
    except Exception as e:
        logger.error(f"文件删除会话失败: {e}")
        return False


# ─── 会话缓存（MemoryCache + 文件持久化） ────────────────

def _load_session_meta(user_id: int, session_id: str) -> Optional[dict]:
    raw = cache.get_value(_session_meta_key(user_id, session_id))
    return json.loads(raw) if raw else None


def _save_session_meta(user_id: int, session_id: str, meta: dict):
    cache.set_value(_session_meta_key(user_id, session_id), json.dumps(meta))
    cache.lrem(_session_list_key(user_id), 0, session_id)
    cache.lpush(_session_list_key(user_id), session_id)


def _save_message(
    user_id: int,
    session_id: str,
    role: str,
    content: str,
    reasoning_content: Optional[str] = None,
    tool_names: Optional[List[str]] = None,
) -> dict:
    now = _now_iso()
    message = {
        "role": role,
        "content": content,
        "created_at": now,
    }
    if reasoning_content:
        message["reasoning_content"] = reasoning_content
    if tool_names:
        message["tool_names"] = list(tool_names)

    # 1. 写入内存缓存
    cache.rpush(_session_history_key(user_id, session_id), json.dumps(message))

    # 2. 更新或创建 meta
    meta = _load_session_meta(user_id, session_id)
    if not meta:
        meta = {
            "id": session_id,
            "title": content[:40] if role == "user" else "新会话",
            "created_at": now,
            "updated_at": now,
            "message_count": 1,
        }
    else:
        meta["updated_at"] = now
        meta["message_count"] = meta.get("message_count", 0) + 1
        if not meta.get("title") and role == "user":
            meta["title"] = content[:40]

    _save_session_meta(user_id, session_id, meta)

    # 3. 同步写入文件持久化
    full_messages = _load_history(user_id, session_id)
    _file_save_full(user_id, session_id, meta, full_messages)

    return message


def _load_history(user_id: int, session_id: str) -> List[dict]:
    raw_messages = cache.lrange(_session_history_key(user_id, session_id), 0, -1)
    if raw_messages:
        return [json.loads(item) for item in raw_messages]

    full = _file_load_full(user_id, session_id)
    return full.get("messages", []) if full else []


def _load_sessions(user_id: int) -> List[dict]:
    session_ids = cache.lrange(_session_list_key(user_id), 0, -1) or []
    sessions = []
    for session_id in session_ids:
        meta = _load_session_meta(user_id, session_id)
        if meta:
            # 清理旧格式 datetime（+00:00Z → +00:00）
            for key in ("created_at", "updated_at"):
                if key in meta and isinstance(meta[key], str):
                    meta[key] = meta[key].replace("+00:00Z", "+00:00").replace("Z", "+00:00")
            sessions.append(meta)
    if sessions:
        return sessions
    return _file_list_sessions(user_id)


def _delete_session(user_id: int, session_id: str) -> bool:
    meta_key = _session_meta_key(user_id, session_id)
    history_key = _session_history_key(user_id, session_id)
    list_key = _session_list_key(user_id)

    cache.delete_key(meta_key)
    cache.delete_key(history_key)
    cache.lrem(list_key, 0, session_id)

    _file_delete_session(user_id, session_id)
    return True


def _generate_assistant_response(user_message: str) -> str:
    return f"已收到：{user_message}"


def _tc_predict_background(user_hash: str, tc_node_id: str, tc_user_action: str, tc_domain_id: str, session_id: str):
    """TCN predict 同步包装 — 从 sync generator 中调用 async predict"""
    try:
        loop = asyncio.new_event_loop()
        result = loop.run_until_complete(
            tcn_client.predict(
                user_hash=user_hash,
                current_node=tc_node_id,
                user_action=tc_user_action,
                domain_id=tc_domain_id,
            )
        )
        loop.close()
        return {
            "session_id": session_id,
            "lvr": result.get("lvr"),
            "diagnosis": result.get("diagnosis"),
        }
    except Exception as e:
        logger.warning(f"TCN predict 异步失败: {e}")
        return None


def _stream_agent_response(
    user_id: int,
    session_id: str,
    message: str,
    dataset_id: str,
    collection_id: Optional[str] = None,
    db: Optional[Session] = None,
    history: Optional[list] = None,
    user_hash: Optional[str] = None,
    tc_node_id: Optional[str] = None,
    tc_user_action: Optional[str] = None,
    tc_domain_id: Optional[str] = None,
    mode: str = "qa",
    token: Optional[str] = None,
):
    if not dataset_id and not is_local_rag():
        logger.warning(f"_stream_agent_response: user_id={user_id} 没有 dataset_id，使用 echo 回退")
    if not dataset_id and not is_local_rag():
        content = _generate_assistant_response(message)
        data = json.dumps({
            "session_id": session_id,
            "type": "answer",
            "role": "assistant",
            "content": content,
        }, ensure_ascii=False)
        yield f"event: message\ndata: {data}\n\n"
        return

    try:
        agent = agent_manager.get_agent(user_id, dataset_id or "")

        if not agent.is_ready:
            logger.error(f"_stream_agent_response: user_id={user_id} Agent 不可用")
            data = json.dumps({
                "session_id": session_id,
                "type": "answer",
                "role": "assistant",
                "content": "抱歉，AI 服务暂时不可用，请稍后重试。",
            }, ensure_ascii=False)
            yield f"event: message\ndata: {data}\n\n"
            return

        full_content = ""
        tcn_result = None
        interrupted = False

        # 新流启动：清除上次残留的打断标记，避免误中断本轮
        _clear_interrupt(user_id, session_id)

        try:
            for chunk in agent.predict_stream(
                message, history, collection_id=collection_id, db=db, mode=mode, token=token
            ):
                # 用户打断：停止产出，已产出内容保存时追加打断提示
                if _check_interrupt(user_id, session_id):
                    interrupted = True
                    break

                # 公开字段白名单：只放行 Chat 合同允许的字段
                event_type = chunk.get("type", "answer")
                role = chunk.get("role", "assistant")
                content = chunk.get("content", "")

                if event_type == "answer" and content:
                    full_content += content

                payload: dict = {
                    "session_id": session_id,
                    "type": event_type,
                    "role": role,
                    "content": content,
                }

                if event_type == "reasoning" and chunk.get("reasoning_content"):
                    payload["reasoning_content"] = chunk["reasoning_content"]
                elif event_type == "tool_call" and chunk.get("tool_name"):
                    payload["tool_name"] = chunk["tool_name"]
                elif event_type == "metadata":
                    if chunk.get("citations"):
                        payload["citations"] = chunk["citations"]

                data = json.dumps(payload, ensure_ascii=False)
                yield f"event: message\ndata: {data}\n\n"
        except (GeneratorExit, ConnectionResetError, BrokenPipeError):
            # 客户端断开：不 yield，保存已产出内容并标记打断
            interrupted = True
        except Exception as e:
            logger.error(f"_stream_agent_response 异常: {e}", exc_info=True)
            data = json.dumps({
                "session_id": session_id,
                "type": "answer",
                "role": "assistant",
                "content": "抱歉，处理您的请求时出错了，请稍后重试。",
            }, ensure_ascii=False)
            yield f"event: message\ndata: {data}\n\n"
            return

        # 稳定的流结束语义
        yield "data: [DONE]\n\n"

        _clear_interrupt(user_id, session_id)

        if full_content or interrupted:
            content = full_content + (INTERRUPT_NOTICE if interrupted else "")
            try:
                _save_message(
                    user_id,
                    session_id,
                    "assistant",
                    content,
                    reasoning_content=getattr(agent, "_last_reasoning", None),
                    tool_names=getattr(agent, "_last_tool_names", None),
                )
            except Exception as e:
                logger.error(f"保存助理消息失败: {e}")

        # TCN 集成：对话完成后异步更新知识状态并透传结果
        if user_hash and tc_node_id and tc_user_action:
            try:
                tcn_result = _tc_predict_background(user_hash, tc_node_id, tc_user_action, tc_domain_id or "", session_id)
            except Exception as e:
                logger.warning(f"TCN predict 调用异常: {e}")

        if tcn_result:
            tcn_payload = {
                "session_id": session_id,
                "type": "metadata",
                "role": "system",
                "content": "",
                "lvr": tcn_result.get("lvr"),
                "diagnosis": tcn_result.get("diagnosis"),
            }
            yield f"event: message\ndata: {json.dumps(tcn_payload, ensure_ascii=False)}\n\n"

    except Exception as e:
        logger.error(f"_stream_agent_response 异常: {e}", exc_info=True)
        data = json.dumps({
            "session_id": session_id,
            "type": "answer",
            "role": "assistant",
            "content": "抱歉，处理您的请求时出错了，请稍后重试。",
        }, ensure_ascii=False)
        yield f"event: message\ndata: {data}\n\n"


@router.get("")
def chat_info():
    """返回聊天服务状态与接口说明"""
    return {
        "service": "chat",
        "endpoints": {
            "send": "POST /api/v1/chat",
            "history": "GET /api/v1/chat/history?session_id=xxx",
            "sessions": "GET /api/v1/chat/sessions",
            "delete_session": "DELETE /api/v1/chat/sessions/{session_id}",
        },
    }


@router.post("", response_model=ChatResponse)
def send_chat(
    request: ChatRequest,
    current_user: dict = Depends(get_current_active_user),
    _quota: dict = Depends(check_quota),
    db: Session = Depends(get_db),
    token: str = Depends(get_current_token),
):
    mode = request.mode or "qa"
    if mode not in VALID_MODES:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"不支持的 mode: {mode}，支持的模式: {', '.join(sorted(VALID_MODES))}",
        )

    user_id = current_user["user_id"]
    user_dataset_id = current_user.get("dataset_id")
    collection, dataset_id = resolve_chat_collection(
        db, user_id, request.collection_id, user_dataset_id
    )
    collection_id = collection.id

    session_id = request.session_id or uuid4().hex
    session_meta = _load_session_meta(user_id, session_id)

    if session_meta is None and not request.content:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="新会话必须提供 content"
        )

    _save_message(user_id, session_id, "user", request.content)

    if request.stream:
        history = _load_history(user_id, session_id)
        if history:
            history = history[:-1]

        user_hash = current_user.get("user_hash")
        return StreamingResponse(
            _stream_agent_response(
                user_id=user_id,
                session_id=session_id,
                message=request.content,
                dataset_id=dataset_id,
                collection_id=collection_id,
                db=db,
                history=history,
                user_hash=user_hash,
                tc_node_id=request.tc_node_id,
                tc_user_action=request.tc_user_action,
                tc_domain_id=request.tc_domain_id,
                mode=mode,
                token=token,
            ),
            media_type="text/event-stream",
            headers={
                "Cache-Control": "no-cache",
                "Connection": "keep-alive",
                "X-Accel-Buffering": "no",
            }
        )

    citations = None
    assistant_content = _generate_assistant_response(request.content)
    _reasoning = None
    _tool_names = None

    if dataset_id or is_local_rag():
        try:
            agent = agent_manager.get_agent(user_id, dataset_id or "")

            # qa / learning / classroom_note 三种 mode 下 agent 不可用 → 503
            if mode in ("qa", "learning", "classroom_note") and not agent.is_ready:
                raise HTTPException(
                    status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                    detail="AI 服务暂时不可用，请稍后重试",
                )

            if agent.is_ready:
                history = _load_history(user_id, session_id)
                if history:
                    history = history[:-1]
                full_content = ""
                for chunk in agent.predict_stream(
                    request.content,
                    history,
                    collection_id=collection_id,
                    db=db,
                    mode=mode,
                    token=token,
                ):
                    event_type = chunk.get("type", "answer")
                    if event_type == "metadata" and chunk.get("citations"):
                        citations = chunk["citations"]
                    elif event_type == "answer" and chunk.get("content"):
                        full_content += chunk["content"]
                if full_content:
                    assistant_content = full_content
                _reasoning = getattr(agent, "_last_reasoning", None)
                _tool_names = getattr(agent, "_last_tool_names", None)
        except HTTPException:
            raise
        except Exception as e:
            logger.error(f"非流式 chat Agent 调用失败: {e}")

    _save_message(
        user_id,
        session_id,
        "assistant",
        assistant_content,
        reasoning_content=_reasoning,
        tool_names=_tool_names,
    )

    meta = _load_session_meta(user_id, session_id)
    title = meta.get("title") if meta else request.content[:40]
    return {
        "session_id": session_id,
        "session_title": title,
        "role": "assistant",
        "content": assistant_content,
        "created_at": _now_iso(),
        "citations": citations,
        "reasoning_content": _reasoning,
        "tool_names": _tool_names,
    }


@router.post("/break")
def break_chat(
    request: ChatBreakRequest,
    current_user: dict = Depends(get_current_active_user),
):
    """用户打断当前流式输出：标记后，正在进行的流会停止，
    已产出的内容保存并在消息末尾追加打断提示。"""
    user_id = current_user["user_id"]
    _mark_interrupt(user_id, request.session_id)
    return {
        "message": "已请求打断",
        "session_id": request.session_id,
    }


@router.get("/history", response_model=List[ChatHistoryItem])
def get_chat_history(
    session_id: str,
    current_user: dict = Depends(get_current_active_user)
):
    user_id = current_user["user_id"]
    if not session_id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="session_id is required"
        )

    return _load_history(user_id, session_id)


@router.get("/sessions", response_model=ChatSessionList)
def list_chat_sessions(
    current_user: dict = Depends(get_current_active_user)
):
    user_id = current_user["user_id"]
    sessions = _load_sessions(user_id)
    return {"sessions": sessions}


@router.delete("/sessions/{session_id}")
def delete_chat_session(
    session_id: str,
    current_user: dict = Depends(get_current_active_user)
):
    user_id = current_user["user_id"]
    _delete_session(user_id, session_id)
    return {"message": "Chat session deleted"}