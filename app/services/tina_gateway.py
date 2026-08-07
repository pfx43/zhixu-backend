"""
Tina 门面网关 — 统一的 LLM 调用入口

职责：
  1. API Key 池管理（多 key 轮换、并发数/RPM 限制）
  2. 用户级并发控制
  3. 流式/非流式统一接口
  4. 内置用量记账（调用 usage_service.record_turn_usage）
"""

from __future__ import annotations

import logging
import os
import time
from typing import AsyncGenerator, Generator, List, Optional

from app.core.redis import cache

logger = logging.getLogger(__name__)

# ── Redis key 前缀 ──
_KEY_INFLIGHT_PREFIX = "llm:key:inflight:"
_KEY_RPM_PREFIX = "llm:key:rpm:"
_USER_INFLIGHT_PREFIX = "llm:inflight:"


class TinaGateway:
    """LLM 调用门面，封装 BaseAPI + Key 池 + 用户并发 + 用量记账。"""

    def __init__(self):
        # 从环境变量读取配置
        keys_str = os.getenv("LLM_API_KEYS", "")
        self._api_keys = [k.strip() for k in keys_str.split(",") if k.strip()]
        if not self._api_keys:
            # 回退：使用单一 LLM_API_KEY
            single_key = os.getenv("LLM_API_KEY", "")
            if single_key:
                self._api_keys = [single_key.strip()]

        self._max_concurrency = int(os.getenv("LLM_KEY_MAX_CONCURRENCY", "5"))
        self._rpm = int(os.getenv("LLM_KEY_RPM", "60"))
        self._default_concurrent_limit = int(os.getenv("LLM_USER_CONCURRENT_LIMIT", "3"))

        if not self._api_keys:
            logger.warning(
                "TinaGateway: 未配置 LLM_API_KEYS 或 LLM_API_KEY，"
                "网关将无法工作"
            )
        else:
            logger.info(
                "TinaGateway: 已加载 %d 个 API key, "
                "max_concurrency=%d, rpm=%d",
                len(self._api_keys),
                self._max_concurrency,
                self._rpm,
            )

    # ── Key 池管理 ──

    def _acquire_key(self) -> Optional[str]:
        """从池中获取一个可用 key，递增 inflight 计数。

        遍历所有 key，找到未达并发上限和 RPM 上限的第一个 key。
        若全满返回 None。当 Redis 不可用时降级为直接返回首个 key。
        """
        now_ms = int(time.time() * 1000)
        window_ms = 60_000  # 1 分钟滑动窗口

        for key in self._api_keys:
            # 检查并发
            inflight_key = f"{_KEY_INFLIGHT_PREFIX}{key}"
            try:
                current = cache.get_value(inflight_key)
                inflight = int(current) if current else 0
            except Exception:
                inflight = 0

            if inflight >= self._max_concurrency:
                continue

            # 检查 RPM（使用 ZSET 滑动窗口；MemoryCache 返回 0 即不限）
            rpm_key = f"{_KEY_RPM_PREFIX}{key}"
            try:
                cache.zremrangebyscore(rpm_key, 0, now_ms - window_ms)
                rpm_count = cache.zcard(rpm_key)
            except Exception:
                rpm_count = 0

            if rpm_count >= self._rpm:
                continue

            # 可用：递增 inflight + 记录 RPM
            try:
                cache.incr(inflight_key)
                cache.expire(inflight_key, 120)  # 防止死锁，2 分钟自动过期
                cache.zadd(rpm_key, {str(now_ms): now_ms})
                cache.expire(rpm_key, 120)
            except Exception as e:
                logger.warning("TinaGateway: 缓存操作失败（降级放行）: %s", e)
                return key  # 降级：不阻塞业务

            return key

        return None

    def _release_key(self, key: str) -> None:
        """释放 key 的 inflight 计数（调用完成后）。"""
        inflight_key = f"{_KEY_INFLIGHT_PREFIX}{key}"
        try:
            cache.decr(inflight_key)
        except Exception:
            pass

    # ── 用户级并发 ──

    def _acquire_user_slot(self, user_id: int, concurrent_limit: int) -> bool:
        """尝试获取用户并发槽位。MemoryCache 模式下直接放行。"""
        user_key = f"{_USER_INFLIGHT_PREFIX}{user_id}"
        try:
            current = cache.incr(user_key)
            cache.expire(user_key, 300)  # 5 分钟过期，防止死锁
            return current <= concurrent_limit
        except Exception:
            # 缓存不可用时放行（不阻塞业务）
            return True

    def _release_user_slot(self, user_id: int) -> None:
        """释放用户并发槽位。"""
        user_key = f"{_USER_INFLIGHT_PREFIX}{user_id}"
        try:
            cache.decr(user_key)
        except Exception:
            pass

    # ── 公开方法 ──

    def create_base_api(self):
        """创建带 key 轮换的 BaseAPI 实例（用于 Tina Agent 框架）。

        从 key 池中获取可用 key，创建 BaseAPI。
        若 key 池为空或全满，回退到默认 key 创建。
        """
        from app.utils import tina_loader  # noqa: F401
        from tina.llm import BaseAPI
        from app.services.llm.llm_config import load_llm_settings

        settings = load_llm_settings()
        api_key = self._acquire_key()

        # 若池中无可用 key，使用默认 key（保持原有行为）
        if api_key is None:
            api_key = settings.api_key
            logger.warning("TinaGateway: key 池无可用 key，使用默认 key")

        return BaseAPI(
            model=settings.model_name,
            api_key=api_key,
            base_url=settings.base_url,
        )

    def release_base_api_key(self, llm_instance) -> None:
        """释放与 BaseAPI 实例关联的 key。

        注意：BaseAPI 不直接暴露 api_key，此处通过遍历池中 key
        来释放（最简单的方式是释放所有 inflight 计数中的一项）。
        由于无法从 BaseAPI 实例反查 key，调用方需自行管理。
        实际上，如果 key 池使用了 Redis inflight 计数，需要调用方
        在完成 Agent 调用后手动调用 release_key。
        """
        pass  # BaseAPI 不暴露 key，无法精确释放；依赖 Redis key 的 TTL 自动过期

    def stream_chat(
        self,
        user_id: int,
        instruction: str,
        *,
        messages: Optional[List[dict]] = None,
        sys_prompt: str = "你的工作非常的出色！",
        temperature: float = 0.7,
        max_tokens: int = 2048,
        concurrent_limit: Optional[int] = None,
        **kwargs,
    ) -> Generator[dict, None, None]:
        """流式对话 — 自动选择 key、记账、用户并发控制。

        Yields:
            dict: {"role": "assistant", "content": "..."}
        """
        if not self._api_keys:
            yield {
                "role": "assistant",
                "content": "抱歉，AI 服务暂未配置，请联系管理员。",
            }
            return

        # 用户级并发控制
        limit = concurrent_limit or self._default_concurrent_limit
        if not self._acquire_user_slot(user_id, limit):
            yield {
                "role": "assistant",
                "content": "请求过于频繁，请稍后重试。",
            }
            return

        # 获取 key
        api_key = self._acquire_key()
        if api_key is None:
            self._release_user_slot(user_id)
            yield {
                "role": "assistant",
                "content": "服务繁忙，请稍后重试。",
            }
            return

        # 创建 BaseAPI 实例
        try:
            from app.services.llm.llm_config import load_llm_settings
            from app.utils import tina_loader  # noqa: F401
            from tina.llm import BaseAPI

            settings = load_llm_settings()
            llm = BaseAPI(
                model=settings.model_name,
                api_key=api_key,
                base_url=settings.base_url,
            )
        except Exception as e:
            self._release_key(api_key)
            self._release_user_slot(user_id)
            logger.error("TinaGateway: 创建 BaseAPI 失败: %s", e)
            yield {
                "role": "assistant",
                "content": "AI 服务初始化失败，请联系管理员。",
            }
            return

        # 流式调用 + 收集 completion 文本
        completion_parts: list[str] = []
        collected_usage = None

        try:
            for chunk in llm.predict_stream(
                messages=messages,
                input_text=instruction if not messages else None,
                sys_prompt=sys_prompt,
                temperature=temperature,
                max_tokens=max_tokens,
                **kwargs,
            ):
                # 统一 chunk 格式为 dict
                if isinstance(chunk, dict):
                    item = {
                        "role": chunk.get("role", "assistant"),
                        "content": chunk.get("content", ""),
                    }
                    if "usage" in chunk:
                        collected_usage = chunk["usage"]
                else:
                    item = {
                        "role": getattr(chunk, "role", "assistant"),
                        "content": getattr(chunk, "content", ""),
                    }

                # 透传额外字段（reasoning_content 等）
                for extra in ("reasoning_content", "tool_calls", "tool_name"):
                    val = chunk.get(extra) if isinstance(chunk, dict) else getattr(chunk, extra, None)
                    if val:
                        item[extra] = val

                content = item.get("content", "")
                if content:
                    completion_parts.append(content)
                yield item

        except Exception as e:
            logger.error("TinaGateway.stream_chat 错误: %s", e)
            yield {
                "role": "assistant",
                "content": "抱歉，生成回复时出错了，请稍后重试。",
            }
        finally:
            self._release_key(api_key)
            self._release_user_slot(user_id)

        # 用量记账
        try:
            from app.services.usage_service import record_turn_usage

            completion_text = "".join(completion_parts)
            if collected_usage:
                record_turn_usage(
                    user_id=user_id,
                    prompt=instruction,
                    completion=completion_text,
                    prompt_tokens=collected_usage.get("prompt_tokens"),
                    completion_tokens=collected_usage.get("completion_tokens"),
                    total_tokens=collected_usage.get("total_tokens"),
                )
            else:
                record_turn_usage(
                    user_id=user_id,
                    prompt=instruction,
                    completion=completion_text,
                )
        except Exception:
            logger.exception("TinaGateway 用量记账失败: user_id=%s", user_id)

    def complete(
        self,
        user_id: int,
        instruction: str,
        *,
        messages: Optional[List[dict]] = None,
        sys_prompt: str = "你的工作非常的出色！",
        temperature: float = 0.7,
        max_tokens: int = 2048,
        concurrent_limit: Optional[int] = None,
        **kwargs,
    ) -> dict:
        """非流式对话 — 返回完整响应 dict。

        Returns:
            dict: {"role": "assistant", "content": "...", "tool_calls": [...]}
        """
        if not self._api_keys:
            return {
                "role": "assistant",
                "content": "抱歉，AI 服务暂未配置，请联系管理员。",
            }

        # 用户级并发控制
        limit = concurrent_limit or self._default_concurrent_limit
        if not self._acquire_user_slot(user_id, limit):
            return {
                "role": "assistant",
                "content": "请求过于频繁，请稍后重试。",
            }

        # 获取 key
        api_key = self._acquire_key()
        if api_key is None:
            self._release_user_slot(user_id)
            return {
                "role": "assistant",
                "content": "服务繁忙，请稍后重试。",
            }

        try:
            from app.services.llm.llm_config import load_llm_settings
            from app.utils import tina_loader  # noqa: F401
            from tina.llm import BaseAPI

            settings = load_llm_settings()
            llm = BaseAPI(
                model=settings.model_name,
                api_key=api_key,
                base_url=settings.base_url,
            )
        except Exception as e:
            self._release_key(api_key)
            self._release_user_slot(user_id)
            logger.error("TinaGateway: 创建 BaseAPI 失败: %s", e)
            return {
                "role": "assistant",
                "content": "AI 服务初始化失败，请联系管理员。",
            }

        try:
            result = llm.predict_no_stream(
                messages=messages,
                input_text=instruction if not messages else None,
                sys_prompt=sys_prompt,
                temperature=temperature,
                max_tokens=max_tokens,
                **kwargs,
            )

            # 用量记账
            try:
                from app.services.usage_service import record_turn_usage

                record_turn_usage(
                    user_id=user_id,
                    prompt=instruction,
                    completion=result.get("content", ""),
                )
            except Exception:
                logger.exception("TinaGateway 非流式用量记账失败: user_id=%s", user_id)

            return result

        except Exception as e:
            logger.error("TinaGateway.complete 错误: %s", e)
            return {
                "role": "assistant",
                "content": "抱歉，生成回复时出错了，请稍后重试。",
            }
        finally:
            self._release_key(api_key)
            self._release_user_slot(user_id)


# 全局单例
tina_gateway = TinaGateway()
