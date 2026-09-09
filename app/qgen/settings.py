"""出题 FastAPI 进程配置。"""
from __future__ import annotations

import os


def _bool_env(name: str, default: str = "false") -> bool:
    return os.getenv(name, default).strip().lower() == "true"


QGEN_HOST = os.getenv("QGEN_HOST", "127.0.0.1")
QGEN_PORT = int(os.getenv("QGEN_PORT", "8766"))
QGEN_MAIN_URL = os.getenv("QGEN_MAIN_URL", "http://127.0.0.1:8765").rstrip("/")
QGEN_POLL_SECONDS = float(os.getenv("QGEN_POLL_SECONDS", "2"))
QGEN_CONSUME = _bool_env("QGEN_CONSUME", "true")
INTERNAL_API_KEY = os.getenv("INTERNAL_API_KEY", "")


def max_agents() -> int:
    """同时跑的出题 Agent 数（一页一个）；与一次入队多少页无关。"""
    from app.core.config import QUESTION_GEN_MAX_AGENTS

    return max(1, int(QUESTION_GEN_MAX_AGENTS))
