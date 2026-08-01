"""
应用运行时配置 — 从 backend/config.json 加载非密钥项。

密钥（LLM API Key、SECRET_KEY 等）仍使用 .env / 环境变量。
config.json 路径：优先 backend/config.json，其次项目根 config.json。
"""
from __future__ import annotations

import json
import logging
from dataclasses import dataclass, fields, asdict
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

_BACKEND_DIR = Path(__file__).resolve().parent.parent.parent
_REPO_ROOT = _BACKEND_DIR.parent


@dataclass(frozen=True)
class AppConfig:
    ocr_max_parallel_pages: int = 1
    pdf_ocr_max_pages: int = 0
    pdf_max_pages: int = 0
    pdf_ocr_render_dpi: int = 150
    max_questions_per_document: int = 20
    document_pipeline_async: bool = True
    question_gen_async: bool = True
    llm_async: bool = True
    image_ocr_async: bool = True
    upload_max_size_mb: int = 0
    ocr_backend: str = "local"
    ocr_pages_dir_name: str = "pages"

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> AppConfig:
        known = {f.name for f in fields(cls)}
        filtered = {k: v for k, v in data.items() if k in known}
        return cls(**filtered)


_DEFAULT_CONFIG = AppConfig()
_config: AppConfig | None = None


def _config_candidates() -> list[Path]:
    return [
        _BACKEND_DIR / "config.json",
        _REPO_ROOT / "config.json",
    ]


def config_path() -> Path:
    for path in _config_candidates():
        if path.is_file():
            return path
    return _config_candidates()[0]


def load_config_file() -> dict[str, Any]:
    path = config_path()
    if not path.is_file():
        logger.info("config.json 不存在，使用内置默认值: %s", path)
        return {}
    try:
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
        if not isinstance(data, dict):
            logger.warning("config.json 根节点须为对象，忽略: %s", path)
            return {}
        return data
    except (OSError, json.JSONDecodeError) as e:
        logger.warning("读取 config.json 失败 (%s)，使用默认值: %s", path, e)
        return {}


def get_app_config() -> AppConfig:
    global _config
    if _config is None:
        raw = load_config_file()
        _config = AppConfig.from_dict({**asdict(_DEFAULT_CONFIG), **raw})
        logger.info(
            "已加载应用配置: path=%s, ocr_max_parallel=%d, pipeline_async=%s",
            config_path(),
            _config.ocr_max_parallel_pages,
            _config.document_pipeline_async,
        )
    return _config


def reload_app_config() -> AppConfig:
    """测试或热重载用。"""
    global _config
    _config = None
    return get_app_config()
