"""
用量跟踪包装器 — 包装 tina BaseAPI，自动捕获真实 token 用量并按用户写入数据库。

设计：
- 包装器透明代理 BaseAPI 的所有属性/方法，仅拦截 predict* / apredict* 调用。
- 流式请求自动注入 ``stream_options.include_usage``，让上游返回精确 token 数。
- 每次 LLM 调用（含 Agent 工具循环内的每一轮上游请求）都会记录一条用量。
- 用户归属：优先使用创建时绑定的 user_id，否则回退到当前上下文的 user_id
  （见 ``usage_context``），两者皆为空时跳过记账（如内部/匿名调用）。
"""
from __future__ import annotations

import contextvars
import json
import logging
from contextlib import contextmanager
from typing import AsyncGenerator, Generator, Optional

from app.services.usage_service import record_turn_usage

logger = logging.getLogger(__name__)

_current_user_id: contextvars.ContextVar[int] = contextvars.ContextVar(
    "usage_current_user_id", default=0
)


def get_current_user_id() -> int:
    """返回当前上下文中绑定的用户 id（未绑定返回 0）。"""
    return _current_user_id.get()


def set_current_user_id(user_id: int) -> None:
    """在调用方上下文中绑定当前用户 id。"""
    _current_user_id.set(int(user_id or 0))


@contextmanager
def usage_context(user_id: int):
    """在指定作用域内绑定用户 id，退出时自动还原上下文。

    用法（在发起 LLM 调用前包一层）::

        with usage_context(user_id):
            resp = llm_predict_no_stream(llm, ...)
    """
    token = _current_user_id.set(int(user_id or 0))
    try:
        yield
    finally:
        _current_user_id.reset(token)


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


class UsageTrackedAPI:
    """透明包装 tina BaseAPI — 记录每次 LLM 调用的 token 用量。"""

    def __init__(self, api, user_id: int = 0):
        self._api = api
        self._user_id = int(user_id or 0)

    # ── 用户归属 ──

    def set_user_id(self, user_id: int) -> None:
        self._user_id = int(user_id or 0)

    def _resolve_user_id(self) -> int:
        return self._user_id or get_current_user_id()

    # ── 属性透传 ──

    def __getattr__(self, name):
        return getattr(self._api, name)

    def __repr__(self):
        return f"<UsageTrackedAPI user_id={self._user_id or 0} wrapping {self._api!r}>"

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
        user_id = self._resolve_user_id()
        if not user_id:
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
        user_id = self._resolve_user_id()
        if not user_id:
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


def wrap_base_api(api, user_id: int = 0) -> UsageTrackedAPI:
    """包装 tina BaseAPI 实例；已是包装器则直接返回。"""
    if isinstance(api, UsageTrackedAPI):
        if user_id:
            api.set_user_id(user_id)
        return api
    return UsageTrackedAPI(api, user_id=user_id)
