"""
用量跟踪包装器 — 包装 tina BaseAPI，按客户端登录 token 无状态记账。

设计：
- 无状态：身份来源是客户端登录 token（``set_token``），不依赖任何服务端
  "当前用户"状态；每次调用显式携带身份。
- 记账时通过 auth_sessions 用 token 反查 user_id（每个实例解析一次并缓存），
  随后写入 usage_token / usage_daily。
- 流式请求自动注入 ``stream_options.include_usage`` 拿到上游精确 token 数；
  非流式用 BaseAPI.tokens 增量取精确 total；均拿不到时降级 tiktoken 估算。
- 每次 LLM 调用（含 Agent 工具循环内的每一轮上游请求）记录一条用量；
  token 为空或解析不到用户时跳过记账（如内部/匿名调用）。
"""
from __future__ import annotations

import json
import logging
from typing import AsyncGenerator, Generator, Optional

from app.services.usage_service import record_turn_usage

logger = logging.getLogger(__name__)


class UsageTrackedAPI:
    """透明包装 tina BaseAPI — 记录每次 LLM 调用的 token 用量。"""

    def __init__(self, api, token: str = ""):
        self._api = api
        self._token = token or ""
        self._resolved_user_id: Optional[int] = None

    # ── 身份绑定 ──

    def set_token(self, token: str) -> None:
        """绑定客户端登录 token；更换 token 时清空已缓存的用户解析。"""
        token = token or ""
        if token != self._token:
            self._token = token
            self._resolved_user_id = None

    def _resolve_user_id(self) -> int:
        """token → user_id（实例缓存一次，解析不到返回 0）。"""
        if self._resolved_user_id is not None:
            return self._resolved_user_id
        user_id = 0
        if self._token:
            try:
                from app.core.database import SessionLocal
                from app.services.auth.auth_session_service import get_session_user

                db = SessionLocal()
                try:
                    user = get_session_user(db, self._token)
                    user_id = user.id if user else 0
                finally:
                    db.close()
            except Exception:
                logger.exception("UsageTrackedAPI 反查用户失败: token=<redacted>")
        self._resolved_user_id = user_id
        return user_id

    # ── 属性透传 ──

    def __getattr__(self, name):
        return getattr(self._api, name)

    def __repr__(self):
        return f"<UsageTrackedAPI token={'set' if self._token else 'empty'} wrapping {self._api!r}>"

    # ── 记账 ──

    def _record(
        self,
        prompt_text: str,
        completion_text: str,
        *,
        usage: Optional[dict] = None,
        total_tokens: Optional[int] = None,
    ) -> None:
        user_id = self._resolve_user_id()
        if not user_id:
            return
        try:
            if usage:
                record_turn_usage(
                    user_id,
                    prompt=prompt_text,
                    completion=completion_text,
                    prompt_tokens=usage.get("prompt_tokens"),
                    completion_tokens=usage.get("completion_tokens"),
                    total_tokens=usage.get("total_tokens"),
                )
            else:
                record_turn_usage(
                    user_id,
                    prompt=prompt_text,
                    completion=completion_text,
                    total_tokens=total_tokens,
                )
        except Exception:
            logger.exception("UsageTrackedAPI 记账失败: user_id=%s", user_id)

    # ── 同步入口 ──

    def predict(self, *args, stream: bool = False, **kwargs):
        if stream:
            return self.predict_stream(*args, **kwargs)
        return self.predict_no_stream(*args, **kwargs)

    def predict_no_stream(self, *args, **kwargs) -> dict:
        api = self._api
        tokens_before = getattr(api, "tokens", 0) or 0
        result = api.predict_no_stream(*args, **kwargs)
        total = (getattr(api, "tokens", 0) or 0) - tokens_before
        content = result.get("content", "") if isinstance(result, dict) else ""
        self._record(
            _prompt_text_from_kwargs(kwargs),
            content,
            total_tokens=total or None,
        )
        return result

    def predict_stream(self, *args, **kwargs) -> Generator[dict, None, None]:
        kwargs = _with_include_usage(kwargs)
        gen = self._api.predict_stream(*args, **kwargs)
        return self._wrap_stream(gen, _prompt_text_from_kwargs(kwargs))

    def _wrap_stream(
        self, gen: Generator[dict, None, None], prompt_text: str
    ) -> Generator[dict, None, None]:
        if not self._token:
            yield from gen
            return

        parts: list[str] = []
        usage: Optional[dict] = None
        recorded = False

        try:
            for chunk in gen:
                if isinstance(chunk, dict):
                    u = chunk.get("usage")
                    if u:
                        usage = u
                    content = chunk.get("content") or ""
                    if content:
                        parts.append(content)
                yield chunk
                if usage and not recorded:
                    recorded = True
                    self._record(prompt_text, "".join(parts), usage=usage)
                    usage = None
        finally:
            if not recorded:
                self._record(prompt_text, "".join(parts), usage=usage)

    # ── 异步入口 ──

    async def apredict(self, *args, stream: bool = False, **kwargs):
        if stream:
            return await self.apredict_stream(*args, **kwargs)
        return await self.apredict_no_stream(*args, **kwargs)

    async def apredict_no_stream(self, *args, **kwargs) -> dict:
        api = self._api
        tokens_before = getattr(api, "tokens", 0) or 0
        result = await api.apredict_no_stream(*args, **kwargs)
        total = (getattr(api, "tokens", 0) or 0) - tokens_before
        content = result.get("content", "") if isinstance(result, dict) else ""
        self._record(
            _prompt_text_from_kwargs(kwargs),
            content,
            total_tokens=total or None,
        )
        return result

    async def apredict_stream(self, *args, **kwargs):
        kwargs = _with_include_usage(kwargs)
        agen = await self._api.apredict_stream(*args, **kwargs)
        return self._awrap_stream(agen, _prompt_text_from_kwargs(kwargs))

    async def _awrap_stream(
        self, agen: AsyncGenerator[dict, None], prompt_text: str
    ) -> AsyncGenerator[dict, None]:
        if not self._token:
            async for chunk in agen:
                yield chunk
            return

        parts: list[str] = []
        usage: Optional[dict] = None
        recorded = False

        try:
            async for chunk in agen:
                if isinstance(chunk, dict):
                    u = chunk.get("usage")
                    if u:
                        usage = u
                    content = chunk.get("content") or ""
                    if content:
                        parts.append(content)
                yield chunk
                if usage and not recorded:
                    recorded = True
                    self._record(prompt_text, "".join(parts), usage=usage)
                    usage = None
        finally:
            if not recorded:
                self._record(prompt_text, "".join(parts), usage=usage)


def wrap_base_api(api, token: str = "") -> UsageTrackedAPI:
    """包装 tina BaseAPI 实例；已是包装器则直接返回。"""
    if isinstance(api, UsageTrackedAPI):
        if token:
            api.set_token(token)
        return api
    return UsageTrackedAPI(api, token=token)


def _prompt_text_from_kwargs(kwargs: dict) -> str:
    """从调用参数中拼出用于估算 prompt token 的文本（含 system/tools/history）。"""
    parts: list[str] = []
    messages = kwargs.get("messages")
    if messages:
        for m in messages:
            if isinstance(m, dict):
                content = m.get("content")
                if content:
                    parts.append(str(content))
    input_text = kwargs.get("input_text")
    if input_text:
        parts.append(str(input_text))
    sys_prompt = kwargs.get("sys_prompt")
    if sys_prompt:
        parts.append(str(sys_prompt))
    tools = kwargs.get("tools")
    if tools:
        try:
            parts.append(json.dumps(tools, ensure_ascii=False))
        except Exception:
            parts.append(str(tools))
    return "\n".join(parts)


def _with_include_usage(kwargs: dict) -> dict:
    """为流式请求开启 usage 返回（上游需支持 stream_options.include_usage）。"""
    if "stream_options" not in kwargs:
        kwargs = dict(kwargs)
        kwargs["stream_options"] = {"include_usage": True}
    return kwargs
