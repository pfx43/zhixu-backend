from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Mapping, Optional, Union

from dotenv import dotenv_values


LlmEnvPath = Union[str, os.PathLike[str]]


@dataclass(frozen=True)
class LlmSettings:
    api_key: str = field(repr=False)
    base_url: str
    model_name: str

    @property
    def is_ready(self) -> bool:
        return bool(self.api_key and self.base_url and self.model_name)


def _clean_setting(value: object) -> str:
    if value is None:
        return ""
    cleaned = str(value).strip()
    if len(cleaned) >= 2 and cleaned[0] == cleaned[-1] and cleaned[0] in "\"'":
        return cleaned[1:-1].strip()
    return cleaned


def _default_env_path() -> Path:
    return Path(__file__).resolve().parents[3] / "tina.env"


def load_llm_settings(
    *,
    env_path: Optional[LlmEnvPath] = None,
    environ: Optional[Mapping[str, str]] = None,
) -> LlmSettings:
    """Load LLM settings from the process environment, then ``tina.env``.

    A present process variable wins even when it is blank. This prevents a
    stale file secret from silently taking over after an explicit deployment
    override.
    """
    source = os.environ if environ is None else environ
    path = Path(env_path) if env_path is not None else _default_env_path()
    file_values = dotenv_values(path) if path.is_file() else {}

    def resolve(name: str) -> str:
        if name in source:
            return _clean_setting(source.get(name))
        return _clean_setting(file_values.get(name))

    return LlmSettings(
        api_key=resolve("LLM_API_KEY"),
        base_url=resolve("BASE_URL"),
        model_name=resolve("MODEL_NAME"),
    )


def create_base_api(*, env_path: Optional[LlmEnvPath] = None):
    """Create Tina ``BaseAPI`` with explicitly resolved settings."""
    path = Path(env_path) if env_path is not None else _default_env_path()
    settings = load_llm_settings(env_path=path)
    if not settings.is_ready:
        raise ValueError("LLM configuration is incomplete")

    # Importing tina_loader registers the bundled Tina package on sys.path.
    from app.utils import tina_loader  # noqa: F401
    from tina.llm import BaseAPI

    return BaseAPI(
        model=settings.model_name,
        api_key=settings.api_key,
        base_url=settings.base_url,
        env_path=str(path),
    )


__all__ = ["LlmSettings", "create_base_api", "load_llm_settings"]
