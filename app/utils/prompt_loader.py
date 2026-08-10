"""
提示词加载器 — 统一从 backend/prompts/ 目录加载提示词文件。

用法:
    from app.utils.prompt_loader import load_prompt

    system_prompt = load_prompt("zhishi_agent_qa")

环境变量:
    PROMPTS_DIR — 覆盖默认的 backend/prompts 路径（生产部署用）
"""
from __future__ import annotations

import os
from functools import lru_cache
from pathlib import Path


def prompts_dir() -> Path:
    """backend/prompts/ 目录（app/utils -> app -> backend）。"""
    env_override = os.getenv("PROMPTS_DIR", "")
    if env_override:
        return Path(env_override)
    return Path(__file__).resolve().parents[2] / "prompts"


@lru_cache(maxsize=64)
def load_prompt(name: str, default: str = "") -> str:
    """读取提示词文件内容（UTF-8，自动去尾空白）。

    Args:
        name: 提示词文件名（不含 .md 后缀）
        default: 文件缺失或读取失败时的回退内容

    Returns:
        提示词文本
    """
    path = prompts_dir() / f"{name}.md"
    try:
        return path.read_text(encoding="utf-8").strip()
    except (OSError, UnicodeDecodeError):
        return default


def clear_prompt_cache() -> None:
    """清空提示词缓存（测试或热更新用）。"""
    load_prompt.cache_clear()


__all__ = ["prompts_dir", "load_prompt", "clear_prompt_cache"]
