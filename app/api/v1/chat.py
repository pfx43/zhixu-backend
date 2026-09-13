import asyncio
import json
import logging
from pathlib import Path
from uuid import uuid4
from datetime import datetime, timezone
from typing import Optional, List

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile, status
from fastapi.responses import FileResponse, StreamingResponse

from app.api.deps import get_current_active_user, get_current_token, get_streaming_user
from app.api.deps_quota import enforce_quota_for_user
from app.core.config import DEBUG_MAX_UPLOAD_SIZE, is_local_rag
from app.core.database import short_session
from app.core.redis import async_cache, cache
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
from app.services.onboarding.chat_cards import is_skip_or_uploaded, persistable_cards
from app.services.onboarding.onboarding_service import (
    complete_onboarding_for_user,
    mark_onboarding_in_progress,
)
from app.services.chat.chat_blocks import (
    append_canvas_block,
    append_onboarding_block,
    append_plot_block,
    append_question_block,
    append_text_block,
    append_tip_block,
    pack_assistant_payload,
)

logger = logging.getLogger(__name__)

router = APIRouter(tags=["chat"])

VALID_MODES = {"qa", "learning", "classroom_note", "verify", "onboarding"}

# 用户打断：前端 POST /api/v1/chat/break 设置标记，流式生成器检查到后停止，
# 已产出的内容保存并在消息末尾追加打断提示。
INTERRUPT_NOTICE = "\n\n> ⏹️ 对话已被用户打断"
_INTERRUPT_TTL = 300  # 打断标记有效期（秒）

# 公开 SSE 合同允许的事件类型（白名单）；其余 type 与 role=tool 一律丢弃
ALLOWED_EVENT_TYPES = {
    "reasoning",
    "tool_call",
    "answer",
    "metadata",
    "onboarding_ui",
    "show_question",
    "show_tip",
    "show_plot",
    "show_canvas",
}

_PLOT_PUBLIC_KEYS = ("id", "title", "expressions", "x_min", "x_max")
_CANVAS_PUBLIC_KEYS = ("id", "title", "html")

# ── 对话图片上传（多模态） ──
_CHAT_IMAGE_EXTS = {".png", ".jpg", ".jpeg", ".webp", ".gif"}
_CHAT_IMAGE_MIME = {
    ".png": "image/png",
    ".jpg": "image/jpeg",
    ".jpeg": "image/jpeg",
    ".webp": "image/webp",
    ".gif": "image/gif",
}
# 未配置上传上限时给一个安全默认值（10MB）
_CHAT_IMAGE_FALLBACK_MAX_BYTES = 10 * 1024 * 1024


def _resolve_chat_image_paths(user_id: int, images: Optional[List[str]]) -> List[str]:
    """把上传返回的图片 id 解析成本地绝对路径；不存在或越权的直接跳过。"""
    paths: List[str] = []
    for name in images or []:
        if not name:
            continue
        path = storage_service.get_chat_image(user_id, name)
        if path is not None:
            paths.append(str(path))
    return paths


def _public_embed_plot(plot: dict) -> Optional[dict]:
    if not isinstance(plot, dict):
        return None
    exprs = plot.get("expressions")
    if not isinstance(exprs, list) or not exprs:
        return None
    out = {k: plot.get(k) for k in _PLOT_PUBLIC_KEYS if k in plot}
    out["expressions"] = [str(e) for e in exprs[:3] if str(e).strip()]
    if not out["expressions"] or not out.get("id"):
        return None
    try:
        out["x_min"] = float(out.get("x_min", -10))
        out["x_max"] = float(out.get("x_max", 10))
    except (TypeError, ValueError):
        out["x_min"], out["x_max"] = -10.0, 10.0
    return out


def _public_embed_canvas(canvas: dict) -> Optional[dict]:
    if not isinstance(canvas, dict):
        return None
    html = canvas.get("html")
    if not isinstance(html, str) or not html.strip():
        return None
    out = {k: canvas.get(k) for k in _CANVAS_PUBLIC_KEYS if k in canvas}
    out["html"] = html
    if not out.get("id"):
        return None
    return out


def _interrupt_key(user_id: int, session_id: str) -> str:
    return f"chat:interrupt:{user_id}:{session_id}"


_QUESTION_PUBLIC_KEYS = (
    "question_id",
    "stem",
    "question_type",
    "options",
    "document_id",
    "document_name",
    "tags",
)
_TIP_PUBLIC_KEYS = (
    "id",
    "title",
    "content_md",
    "tags",
    "document_id",
    "source",
)


def _public_embed_question(question: dict) -> dict:
    """SSE / 历史里的题目卡：只留公开字段，丢掉 answer / explanation。"""
    return {key: question[key] for key in _QUESTION_PUBLIC_KEYS if key in question}


def _public_embed_tip(tip: dict) -> dict:
    return {key: tip[key] for key in _TIP_PUBLIC_KEYS if key in tip}


def _mark_interrupt(user_id: int, session_id: str) -> None:
    """前端请求打断：写入一次性标记。"""
    try:
        cache.set_value(_interrupt_key(user_id, session_id), "1")
        cache.expire(_interrupt_key(user_id, session_id), _INTERRUPT_TTL)
    except Exception as e:
        logger.warning(f"标记打断失败: {e}")


async def _check_interrupt(user_id: int, session_id: str) -> bool:
    """检查并消费打断标记（一次性：取到即删除，不会残留影响下次对话）。"""
    try:
        key = _interrupt_key(user_id, session_id)
        if await async_cache.get_value(key):
            await async_cache.delete_key(key)
            return True
        return False
    except Exception:
        return False


async def _clear_interrupt(user_id: int, session_id: str) -> None:
    """清除残留标记（新流启动时调用，防止上次的打断信号误中断本轮）。"""
    try:
        await async_cache.delete_key(_interrupt_key(user_id, session_id))
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


async def _asave_session_meta(user_id: int, session_id: str, meta: dict):
    await async_cache.set_value(_session_meta_key(user_id, session_id), json.dumps(meta))
    await async_cache.lrem(_session_list_key(user_id), 0, session_id)
    await async_cache.lpush(_session_list_key(user_id), session_id)


async def _aload_session_meta(user_id: int, session_id: str) -> Optional[dict]:
    raw = await async_cache.get_value(_session_meta_key(user_id, session_id))
    return json.loads(raw) if raw else None


async def _save_message(
    user_id: int,
    session_id: str,
    role: str,
    content: str,
    reasoning_content: Optional[str] = None,
    tool_names: Optional[List[str]] = None,
    payload: Optional[dict] = None,
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
    if payload:
        message["payload"] = payload

    history_key = _session_history_key(user_id, session_id)
    await async_cache.rpush(history_key, json.dumps(message))

    meta = await _aload_session_meta(user_id, session_id)
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

    await _asave_session_meta(user_id, session_id, meta)

    raw_messages = await async_cache.lrange(history_key, 0, -1)
    if raw_messages:
        full_messages = [json.loads(item) for item in raw_messages]
    else:
        full_messages = await asyncio.to_thread(_load_history, user_id, session_id)
    await asyncio.to_thread(_file_save_full, user_id, session_id, meta, full_messages)

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


async def _stream_agent_response(
    user_id: int,
    session_id: str,
    message: str,
    dataset_id: str,
    collection_id: Optional[str] = None,
    history: Optional[list] = None,
    user_hash: Optional[str] = None,
    tc_node_id: Optional[str] = None,
    tc_user_action: Optional[str] = None,
    tc_domain_id: Optional[str] = None,
    mode: str = "qa",
    token: Optional[str] = None,
    images: Optional[List[str]] = None,
):
    """流式 Agent 回复（async generator）。

    结束语义（[DONE] 合同）：
    - 正常 / 受控错误：恰好一次 [DONE]，且为客户端可见的最后一个事件（TCN metadata 在其前）；
    - 用户 break：保存部分内容后正常结束；
    - 客户端断开（GeneratorExit/连接重置）：不再 yield，清理与保存走 finally。
    """
    if not dataset_id and not is_local_rag() and mode != "onboarding":
        logger.warning(f"_stream_agent_response: user_id={user_id} 没有 dataset_id，使用 echo 回退")
        content = _generate_assistant_response(message)
        data = json.dumps({
            "session_id": session_id,
            "type": "answer",
            "role": "assistant",
            "content": content,
        }, ensure_ascii=False)
        yield f"event: message\ndata: {data}\n\n"
        yield "data: [DONE]\n\n"
        return

    agent = None
    try:
        agent = agent_manager.get_agent(user_id, dataset_id or "")
    except Exception as e:
        logger.error(f"_stream_agent_response: 获取 Agent 失败 user_id={user_id} error={e}", exc_info=True)

    if agent is None or not agent.is_ready:
        logger.error(f"_stream_agent_response: user_id={user_id} Agent 不可用")
        data = json.dumps({
            "session_id": session_id,
            "type": "answer",
            "role": "assistant",
            "content": "抱歉，AI 服务暂时不可用，请稍后重试。",
        }, ensure_ascii=False)
        yield f"event: message\ndata: {data}\n\n"
        yield "data: [DONE]\n\n"
        return

    full_content = ""
    reasoning_parts: List[str] = []
    tool_names: List[str] = []
    onboarding_items: List[dict] = []
    question_widgets: List[dict] = []
    tip_widgets: List[dict] = []
    plot_widgets: List[dict] = []
    canvas_widgets: List[dict] = []
    blocks: List[dict] = []
    tcn_result = None
    interrupted = False
    disconnected = False
    failed = False

    # 新流启动：清除上次残留的打断标记，避免误中断本轮
    await _clear_interrupt(user_id, session_id)

    chunk_counter = 0
    try:
        async for chunk in agent.generate(
            message,
            history,
            collection_id=collection_id,
            mode=mode,
            token=token,
            image_paths=images,
        ):
            chunk_counter += 1
            # 用户打断：降频检查（每 8 chunk 一次 Redis 往返），命中则停止产出
            if chunk_counter % 8 == 0 and await _check_interrupt(user_id, session_id):
                interrupted = True
                break

            # 公开白名单：显式枚举 type，拒绝 role=tool 与未知事件（不进入公开流）
            event_type = chunk.get("type", "")
            role = chunk.get("role", "")
            if event_type not in ALLOWED_EVENT_TYPES or role == "tool":
                continue

            content = chunk.get("content", "")
            if event_type == "answer" and content:
                full_content += content
                append_text_block(blocks, content)
            elif event_type == "reasoning":
                rc = chunk.get("reasoning_content")
                if rc:
                    reasoning_parts.append(rc)
            elif event_type == "tool_call":
                tn = chunk.get("tool_name")
                if tn and tn not in tool_names:
                    tool_names.append(tn)
            elif event_type == "onboarding_ui" and chunk.get("item"):
                onboarding_items.append(chunk["item"])
                append_onboarding_block(blocks, chunk["item"])
            elif event_type == "show_question" and isinstance(chunk.get("question"), dict):
                public_q = _public_embed_question(chunk["question"])
                question_widgets.append(public_q)
                append_question_block(blocks, public_q)
            elif event_type == "show_tip" and isinstance(chunk.get("tip"), dict):
                public_tip = _public_embed_tip(chunk["tip"])
                tip_widgets.append(public_tip)
                append_tip_block(blocks, public_tip)
            elif event_type == "show_plot" and isinstance(chunk.get("plot"), dict):
                public_plot = _public_embed_plot(chunk["plot"])
                if public_plot and not any(p.get("id") == public_plot["id"] for p in plot_widgets):
                    plot_widgets.append(public_plot)
                    append_plot_block(blocks, public_plot)
            elif event_type == "show_canvas" and isinstance(chunk.get("canvas"), dict):
                public_canvas = _public_embed_canvas(chunk["canvas"])
                if public_canvas and not any(c.get("id") == public_canvas["id"] for c in canvas_widgets):
                    canvas_widgets.append(public_canvas)
                    append_canvas_block(blocks, public_canvas)

            payload: dict = {
                "session_id": session_id,
                "type": event_type,
                "role": role,
            }
            if content:
                payload["content"] = content
            elif event_type in ("answer", "reasoning", "tool_call", "metadata", "onboarding_ui"):
                payload["content"] = content
            if event_type == "reasoning" and chunk.get("reasoning_content"):
                payload["reasoning_content"] = chunk["reasoning_content"]
            elif event_type == "tool_call" and chunk.get("tool_name"):
                payload["tool_name"] = chunk["tool_name"]
            elif event_type == "onboarding_ui" and chunk.get("item"):
                payload["item"] = chunk["item"]
            elif event_type == "show_question":
                payload["question"] = question_widgets[-1] if question_widgets else chunk.get("question")
            elif event_type == "show_tip":
                payload["tip"] = tip_widgets[-1] if tip_widgets else chunk.get("tip")
            elif event_type == "show_plot":
                payload["plot"] = plot_widgets[-1] if plot_widgets else chunk.get("plot")
            elif event_type == "show_canvas":
                payload["canvas"] = canvas_widgets[-1] if canvas_widgets else chunk.get("canvas")
            elif event_type == "metadata":
                if chunk.get("citations"):
                    payload["citations"] = chunk["citations"]

            data = json.dumps(payload, ensure_ascii=False)
            yield f"event: message\ndata: {data}\n\n"
    except (GeneratorExit, ConnectionResetError, BrokenPipeError):
        # 客户端断开：不再 yield（GeneratorExit 期间 yield 会抛 RuntimeError），
        # 部分内容保存交给下方保存路径
        disconnected = True
    except Exception as e:
        failed = True
        logger.error(f"_stream_agent_response 异常: {e}", exc_info=True)
        data = json.dumps({
            "session_id": session_id,
            "type": "answer",
            "role": "assistant",
            "content": "抱歉，处理您的请求时出错了，请稍后重试。",
        }, ensure_ascii=False)
        yield f"event: message\ndata: {data}\n\n"

    # ── 保存前置：先持久化，再产出 [DONE]（客户端收到 [DONE] 即认为完成） ──
    onboarding_cards = persistable_cards(onboarding_items)
    if interrupted:
        append_text_block(blocks, INTERRUPT_NOTICE)
    history_payload = pack_assistant_payload(
        blocks=blocks,
        questions=question_widgets,
        tips=tip_widgets,
        plots=plot_widgets,
        canvases=canvas_widgets,
        onboarding=onboarding_cards,
    ) or {}
    if full_content or interrupted or history_payload:
        content = full_content + (INTERRUPT_NOTICE if interrupted else "")
        try:
            await _save_message(
                user_id,
                session_id,
                "assistant",
                content,
                reasoning_content="".join(reasoning_parts) or None,
                tool_names=tool_names or None,
                payload=history_payload or None,
            )
        except Exception as e:
            logger.error(f"保存助理消息失败: {e}")

    # ── 统一结束语义：metadata 在前，[DONE] 必为最后事件；断连不再产出任何事件 ──
    if not disconnected:
        # TCN 集成：对话完成后异步更新知识状态并透传结果
        if not failed and user_hash and tc_node_id and tc_user_action:
            try:
                tcn_result = await tcn_client.predict(
                    user_hash=user_hash,
                    current_node=tc_node_id,
                    user_action=tc_user_action,
                    domain_id=tc_domain_id or "",
                )
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

        yield "data: [DONE]\n\n"

    # ── 清理：断连/打断/正常路径均清除打断标记 ──
    try:
        await _clear_interrupt(user_id, session_id)
    except Exception:
        pass


def _resolve_chat_collection_snapshot(
    user_id: int,
    collection_id: Optional[str],
    user_dataset_id: Optional[str],
):
    """短 Session 解析分区；供 async 路由丢到线程里跑。"""
    with short_session() as db:
        collection, dataset_id = resolve_chat_collection(
            db, user_id, collection_id, user_dataset_id
        )
        return collection.id, dataset_id


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
            "upload_image": "POST /api/v1/chat/images",
        },
    }


@router.post("/images", status_code=status.HTTP_201_CREATED)
async def upload_chat_image(
    file: UploadFile = File(...),
    current_user: dict = Depends(get_current_active_user),
):
    """上传对话图片（先上传拿 id，再随消息用）。仅本人可读。"""
    user_id = current_user["user_id"]
    ext = Path(file.filename or "").suffix.lower()
    if ext not in _CHAT_IMAGE_EXTS:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="仅支持 png/jpg/jpeg/webp/gif 图片",
        )
    content = await file.read()
    if not content:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail="空文件"
        )
    max_bytes = DEBUG_MAX_UPLOAD_SIZE or _CHAT_IMAGE_FALLBACK_MAX_BYTES
    if len(content) > max_bytes:
        raise HTTPException(
            status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
            detail=f"图片超过大小上限 {max_bytes} 字节",
        )
    filename = f"{uuid4().hex}{ext}"
    storage_service.save_chat_image(user_id, filename, content)
    return {"id": filename, "url": f"/api/v1/chat/images/{filename}"}


@router.get("/images/{filename}")
def get_chat_image(
    filename: str,
    current_user: dict = Depends(get_current_active_user),
):
    """读取本人上传的对话图片。"""
    path = storage_service.get_chat_image(current_user["user_id"], filename)
    if path is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="图片不存在"
        )
    return FileResponse(
        str(path),
        media_type=_CHAT_IMAGE_MIME.get(path.suffix.lower(), "application/octet-stream"),
    )


@router.post("", response_model=ChatResponse)
async def send_chat(
    request: ChatRequest,
    current_user: dict = Depends(get_streaming_user),
    token: str = Depends(get_current_token),
):
    mode = request.mode or "qa"
    if mode not in VALID_MODES:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"不支持的 mode: {mode}，支持的模式: {', '.join(sorted(VALID_MODES))}",
        )

    await asyncio.to_thread(enforce_quota_for_user, current_user)

    user_id = current_user["user_id"]
    user_dataset_id = current_user.get("dataset_id")
    collection_id, dataset_id = await asyncio.to_thread(
        _resolve_chat_collection_snapshot,
        user_id,
        request.collection_id,
        user_dataset_id,
    )

    session_id = request.session_id or uuid4().hex
    session_meta = await _aload_session_meta(user_id, session_id)

    image_paths = await asyncio.to_thread(
        _resolve_chat_image_paths, user_id, request.images
    )

    if session_meta is None and not request.content and not image_paths:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="新会话必须提供 content 或图片"
        )

    user_payload = {"images": request.images} if request.images else None
    await _save_message(
        user_id,
        session_id,
        "user",
        request.content or ("[图片]" if image_paths else ""),
        payload=user_payload,
    )

    if mode == "onboarding":
        def _touch_onboarding():
            with short_session() as db:
                if is_skip_or_uploaded(request.content):
                    complete_onboarding_for_user(db, user_id)
                else:
                    mark_onboarding_in_progress(db, user_id)
                db.commit()

        await asyncio.to_thread(_touch_onboarding)
        meta = await _aload_session_meta(user_id, session_id)
        if meta:
            meta["kind"] = "onboarding"
            await _asave_session_meta(user_id, session_id, meta)

    history = await asyncio.to_thread(_load_history, user_id, session_id)
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
            history=history,
            user_hash=user_hash,
            tc_node_id=request.tc_node_id,
            tc_user_action=request.tc_user_action,
            tc_domain_id=request.tc_domain_id,
            mode=mode,
            token=token,
            images=image_paths,
        ),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        }
    )


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