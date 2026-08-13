"""
LLM 实例池 — 按 API key 数量创建裸 BaseAPI 实例池，round-robin 提供实例。

用量记账在 Agent 层完成（tina Agent 已透传 usage），LLM 层保持纯净：
此处只聚合裸 BaseAPI 实例，不继承、不包装、不记账。
"""
from __future__ import annotations

import logging
import os
import threading
from typing import Optional

from tina.llm import BaseAPI

from app.services.llm.llm_config import load_llm_settings

logger = logging.getLogger(__name__)


class LLMPool:
    """按 API key 数量创建裸 BaseAPI 实例池，round-robin 提供实例。"""

    def __init__(self):
        keys = [k.strip() for k in os.getenv("LLM_API_KEYS", "").split(",") if k.strip()]
        if not keys:
            single = os.getenv("LLM_API_KEY", "")
            if single:
                keys = [single.strip()]

        settings = load_llm_settings()
        self._instances: list[BaseAPI] = [
            BaseAPI(
                model=settings.model_name,
                api_key=key,
                base_url=settings.base_url,
            )
            for key in keys
        ]
        self._lock = threading.Lock()
        self._next = 0

        if not self._instances:
            logger.warning("LLMPool: 未配置 LLM_API_KEYS 或 LLM_API_KEY，实例池为空")
        else:
            logger.info(
                "LLMPool: 已创建 %d 个 LLM 实例 (model=%s)",
                len(self._instances),
                settings.model_name,
            )

    def acquire(self) -> Optional[BaseAPI]:
        """round-robin 取一个实例；实例池为空返回 None。"""
        with self._lock:
            if not self._instances:
                return None
            instance = self._instances[self._next % len(self._instances)]
            self._next += 1
            return instance

    @property
    def instance_count(self) -> int:
        return len(self._instances)


# 全局单例
llm_pool = LLMPool()
