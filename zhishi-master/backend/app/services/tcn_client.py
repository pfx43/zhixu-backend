"""TCN 引擎层 HTTP 客户端 — 单例模式

核实依据：TCN_API_CONFIRMATION_REPLY.md v1.4（源码级确认）
OpenAPI 文档：http://127.0.0.1:8001/docs
"""

import asyncio
import hashlib
import logging
from typing import Optional

import httpx

from app.core.tcn_config import (
    TCN_ADMIN_TOKEN,
    TCN_BASE_URL,
    TCN_ENABLED,
    TCN_MAX_RETRIES,
    TCN_SECRET_SALT,
    TCN_TIMEOUT,
)

logger = logging.getLogger(__name__)


class TCNClient:
    """TCN 引擎层 HTTP 客户端 — 单例"""

    _instance: Optional["TCNClient"] = None
    _MAX_RETRIES: int = 2  # 最大连续重试次数

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance._initialized = False
        return cls._instance

    def __init__(self):
        if self._initialized:
            return
        self._initialized = True
        self._client = httpx.AsyncClient(
            base_url=TCN_BASE_URL.rstrip("/"),
            timeout=httpx.Timeout(TCN_TIMEOUT),
            headers={"X-Admin-Token": TCN_ADMIN_TOKEN},
        )
        self._enabled = TCN_ENABLED

    @property
    def is_enabled(self) -> bool:
        return self._enabled

    @staticmethod
    def generate_user_hash(user_id: int) -> str:
        """生成用户哈希，sha256 前 32 位 hex（TCN 无长度限制）"""
        raw = f"{user_id}:{TCN_SECRET_SALT}"
        return hashlib.sha256(raw.encode()).hexdigest()[:32]

    # ─── 核心重试机制 ─────────────────────────────────────

    async def _call_with_retry(self, request_name: str, fn, *args, **kwargs) -> dict:
        """统一的 TCN 调用重试包装：
        - 第 1 次失败 → 打印重试日志，等待 1s 后重试
        - 第 2 次失败 → 再等待 1s 后重试
        - 第 3 次仍失败 → 标记服务异常，返回降级数据
        - 任意一次成功 → 自动恢复 _enabled = True
        """
        fallback = kwargs.pop("_fallback", {})  # 取出降级数据，不传给 fn
        for attempt in range(1, self._MAX_RETRIES + 2):  # 1, 2, 3
            try:
                result = await fn(*args, **kwargs)
                # 成功 → 恢复可用状态
                if not self._enabled:
                    logger.info(f"TCN 服务恢复可用 ({request_name})")
                    self._enabled = True
                return result
            except Exception as e:
                if attempt < self._MAX_RETRIES + 1:
                    logger.warning(
                        f"TCN 调用失败 ({request_name})，正在进行第 {attempt} 次重试: {e}"
                    )
                    await asyncio.sleep(1)
                else:
                    logger.error(
                        f"TCN 调用连续 {self._MAX_RETRIES + 1} 次失败 ({request_name})，判定服务异常: {e}"
                    )
                    self._enabled = False

        # 全部重试失败 → 返回降级数据（由各方法提供）
        return kwargs.pop("_fallback", {})

    # ─── 降级数据工厂 ──────────────────────────────────────

    def _degrade_predict(self) -> dict:
        return {
            "lvr": 0.0, "vs": 0.0, "diagnosis": "",
            "recommended_backtrack": None, "node_mastery": {},
            "epsilon_used": 0.05, "training_phase": "degraded",
            "_degraded": True,
        }

    def _degrade_empty_dict(self) -> dict:
        return {}

    # ─── 已有接口 ──────────────────────────────────────────

    async def health_check(self) -> dict:
        """探测 TCN 引擎可用性 — 仅日志，不改变 _enabled 状态"""
        try:
            resp = await self._client.get("/health")
            resp.raise_for_status()
            return resp.json()
        except Exception as e:
            logger.warning(f"TCN 健康检查失败: {e}")
            return {"status": "unreachable", "nodes": 0}

    async def predict(
        self, user_hash: str, current_node: str, user_action: str,
        domain_id: str = "", step_index: int = 0, session_id: str = "",
    ) -> dict:
        """POST /v1/user/predict — 7字段请求，8字段响应"""

        async def _call():
            resp = await self._client.post("/v1/user/predict", json={
                "api_key": "", "user_hash": user_hash,
                "domain_id": domain_id, "current_node": current_node,
                "user_action": user_action, "step_index": step_index,
                "session_id": session_id,
            })
            resp.raise_for_status()
            return resp.json()

        return await self._call_with_retry("predict", _call) or {
            "lvr": 0.0, "vs": 0.0, "diagnosis": "", "recommended_backtrack": None,
            "node_mastery": {}, "epsilon_used": 0.05, "training_phase": "degraded",
        }

    async def get_profile(self, user_hash: str) -> dict:
        """GET /v1/user/profile/{user_hash}"""

        async def _call():
            resp = await self._client.get(f"/v1/user/profile/{user_hash}")
            resp.raise_for_status()
            return resp.json()

        fallback = {"total_steps": 0, "global_lvr": 0.0, "graph_version": 0, "node_count": 0}
        return await self._call_with_retry("get_profile", _call, **{"_fallback": fallback}) or fallback

    async def get_report(self, user_hash: str) -> dict:
        """GET /v1/user/report/{user_hash} — 顶层 object，nodes 是 dict
        新用户无数据时 TCN 返回 404，此为正常情况，直接返回空 nodes 不重试
        """
        fallback = {"user_hash": user_hash, "global_lvr": 0.0, "total_steps": 0, "nodes": {}}

        async def _call():
            resp = await self._client.get(f"/v1/user/report/{user_hash}")
            if resp.status_code == 404:
                return fallback
            resp.raise_for_status()
            return resp.json()

        try:
            return await self._call_with_retry("get_report", _call) or fallback
        except Exception:
            return fallback

    async def get_graph_domains(self) -> list:
        """GET /admin/graph/domains"""

        async def _call():
            resp = await self._client.get("/admin/graph/domains")
            resp.raise_for_status()
            return resp.json()

        fallback: dict = {"_fallback": []}
        return await self._call_with_retry("get_graph_domains", _call, **fallback) or []

    async def get_graph_data(self, domain: str) -> dict:
        """GET /admin/graph/data/{domain}"""

        async def _call():
            resp = await self._client.get(f"/admin/graph/data/{domain}")
            resp.raise_for_status()
            return resp.json()

        fallback = {"_fallback": {"nodes": [], "edges": []}}
        return await self._call_with_retry("get_graph_data", _call, **fallback) or {"nodes": [], "edges": []}

    # ─── 4 个新接口（respond_fix.md 真实格式确认） ─────────────

    async def get_summary(self, user_hash: str) -> dict:
        """GET /v1/user/summary/{user_hash} — 用户知识状态摘要"""

        async def _call():
            resp = await self._client.get(f"/v1/user/summary/{user_hash}")
            resp.raise_for_status()
            return resp.json()

        fallback = {
            "user_hash": user_hash,
            "diagnosis_version": "rule",
            "total_steps": 0,
            "overall_mastery": 0.5,
            "global_lvr": 0.0,
            "lvr_level": "normal",
            "graph_version": 0,
            "domain_summary": [],
            "last_active_node": None,
            "computed_at": None,
        }
        return await self._call_with_retry("get_summary", _call, **{"_fallback": fallback}) or fallback

    async def get_gaps(self, user_hash: str, limit: int = 50, threshold: float = 0.6) -> dict:
        """GET /v1/user/gaps/{user_hash} — 先修断层查询"""

        async def _call():
            resp = await self._client.get(
                f"/v1/user/gaps/{user_hash}", params={"limit": limit, "threshold": threshold}
            )
            resp.raise_for_status()
            return resp.json()

        fallback = {
            "user_hash": user_hash,
            "diagnosis_version": "rule",
            "mastery_threshold": threshold,
            "total_gaps": 0,
            "returned_gaps": 0,
            "limit": limit,
            "gaps": [],
            "computed_at": None,
        }
        return await self._call_with_retry("get_gaps", _call, **{"_fallback": fallback}) or fallback

    async def get_vulnerabilities(self, user_hash: str, limit: int = 50) -> dict:
        """GET /v1/user/vulnerabilities/{user_hash} — 认知脆弱点（伪掌握）预警"""

        async def _call():
            resp = await self._client.get(
                f"/v1/user/vulnerabilities/{user_hash}", params={"limit": limit}
            )
            resp.raise_for_status()
            return resp.json()

        fallback = {
            "user_hash": user_hash,
            "diagnosis_version": "rule",
            "mastery_threshold_high": 0.7,
            "total_vulnerabilities": 0,
            "returned_vulnerabilities": 0,
            "limit": limit,
            "vulnerabilities": [],
            "computed_at": None,
        }
        return await self._call_with_retry("get_vulnerabilities", _call, **{"_fallback": fallback}) or fallback

    async def get_lvr_alert(self, user_hash: str, limit: int = 10) -> dict:
        """GET /v1/user/lvr_alert/{user_hash} — LVR 预警状态"""

        async def _call():
            resp = await self._client.get(
                f"/v1/user/lvr_alert/{user_hash}", params={"limit": limit}
            )
            resp.raise_for_status()
            return resp.json()

        fallback = {
            "user_hash": user_hash,
            "diagnosis_version": "rule",
            "global_lvr": 0.0,
            "lvr_level": "normal",
            "alert_code": "LVR_NORMAL",
            "alert_text": None,
            "total_violations": 0,
            "returned_violations": 0,
            "limit": limit,
            "violations": [],
            "backtrack_recommended": [],
            "computed_at": None,
        }
        return await self._call_with_retry("get_lvr_alert", _call, **{"_fallback": fallback}) or fallback

    async def close(self):
        await self._client.aclose()


tcn_client = TCNClient()