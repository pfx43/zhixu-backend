"""
Tina 导入辅助 — 统一将 backend/3rdParty 加入 sys.path，业务代码无需再手写 sys.path。

用法:
    from app.utils.tina_loader import tina, tina_env_path
    from tina import Agent
    from tina.llm import BaseAPI

    llm = BaseAPI(env_path=tina_env_path())
"""
from __future__ import annotations

import sys
from functools import lru_cache
from pathlib import Path
from types import ModuleType


class TinaImport:
    """管理 Tina 第三方库路径与模块加载。"""

    @classmethod
    def backend_dir(cls) -> Path:
        """backend/ 目录（app/utils -> app -> backend）。"""
        return Path(__file__).resolve().parents[2]

    @classmethod
    def third_party_dir(cls) -> Path:
        """backend/3rdParty/ 目录。"""
        return cls.backend_dir() / "3rdParty"

    @classmethod
    def tina_env_path(cls) -> str:
        """backend/tina.env 绝对路径。"""
        return str(cls.backend_dir() / "tina.env")

    @classmethod
    def ensure_path(cls) -> Path:
        """将 3rdParty 加入 sys.path（幂等）。"""
        party = cls.third_party_dir()
        if not party.is_dir():
            raise ImportError(f"Tina 目录不存在: {party}")

        path_str = str(party)
        if path_str not in sys.path:
            sys.path.insert(0, path_str)
        return party

    @classmethod
    @lru_cache(maxsize=1)
    def load(cls) -> ModuleType:
        """加载并返回 tina 包（路径只配置一次）。"""
        cls.ensure_path()
        import tina as tina_module

        return tina_module


def tina_env_path() -> str:
    return TinaImport.tina_env_path()


# 模块导入时完成路径配置，对外暴露 tina 包
tina = TinaImport.load()

__all__ = ["TinaImport", "tina", "tina_env_path"]
