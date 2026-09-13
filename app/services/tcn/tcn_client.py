"""TCN 引擎层 HTTP 客户端 — 单例模式

核实依据：TCN_API_CONFIRMATION_REPLY.md v1.4（源码级确认）
OpenAPI 文档：http://127.0.0.1:8001/docs
"""

import asyncio
import hashlib
import logging
import time
from datetime import datetime, timezone
from typing import Optional

import httpx

from app.core.tcn_config import (
    TCN_ADMIN_TOKEN,
    TCN_API_KEY,
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
            headers=self._auth_headers(),
        )
        self._enabled = TCN_ENABLED

    @staticmethod
    def _auth_headers() -> dict:
        """服务侧鉴权头：/v1/user/* 用 X-Api-Key（TCN 签发的服务密钥）。"""
        headers: dict[str, str] = {}
        api_key = (TCN_API_KEY or "").strip()
        if api_key:
            headers["X-Api-Key"] = api_key
        return headers

    @staticmethod
    def _admin_headers() -> dict:
        """admin 图接口鉴权头：控制台签发的 admin token 走 Authorization: Bearer。

        实测 TCN 引擎的 /admin/graph/* 只认 Bearer JWT，不认 X-Admin-Token、
        也不认 /v1/user/* 的服务密钥，故单独构造。
        """
        headers: dict[str, str] = {}
        admin = (TCN_ADMIN_TOKEN or "").strip()
        if admin:
            headers["Authorization"] = f"Bearer {admin}"
        return headers

    @property
    def is_enabled(self) -> bool:
        return self._enabled

    def refresh_auth_headers(self) -> None:
        """测试或运行时改了环境变量后，刷新底层客户端头。"""
        self._client.headers.update(self._auth_headers())

    @staticmethod
    def _degraded_at() -> str:
        """返回当前 UTC 时间 ISO 格式字符串"""
        return datetime.now(timezone.utc).isoformat()

    @staticmethod
    def generate_user_hash(user_id: int) -> str:
        """生成用户哈希，sha256 前 32 位 hex（TCN 无长度限制）"""
        raw = f"{user_id}:{TCN_SECRET_SALT}"
        return hashlib.sha256(raw.encode()).hexdigest()[:32]

    # ─── 核心重试机制 ─────────────────────────────────────

    async def _call_with_retry(
        self,
        request_name: str,
        fn,
        *args,
        affects_availability: bool = True,
        **kwargs,
    ) -> dict:
        """统一的 TCN 调用重试包装：
        - 第 1 次失败 → 打印重试日志，等待 1s 后重试
        - 第 2 次失败 → 再等待 1s 后重试
        - 第 3 次仍失败 → 返回降级数据
        - 任意一次成功 → 自动恢复 _enabled = True

        affects_availability=False 用于 admin 图接口：这些接口用独立凭证、
        失败不代表 /v1/user/* 不可用，绝不能触发全局熔断（否则一个 admin
        401 会把整个 KT 读接口打成 503）。
        """
        fallback = kwargs.pop("_fallback", {})  # 取出降级数据，不传给 fn
        last_error: Exception | None = None
        for attempt in range(1, self._MAX_RETRIES + 2):  # 1, 2, 3
            try:
                result = await fn(*args, **kwargs)
                # 成功 → 恢复可用状态（仅当该调用代表 user 通道可用性）
                if affects_availability and not self._enabled:
                    logger.info(f"TCN 服务恢复可用 ({request_name})")
                    self._enabled = True
                return result
            except httpx.HTTPStatusError as e:
                status = e.response.status_code if e.response is not None else 0
                # 404 = 未建档 / 无数据，是正常业务态：不重试、不熔断
                if status == 404:
                    logger.info(f"TCN 404 按空态降级 ({request_name})")
                    return fallback
                last_error = e
            except Exception as e:
                last_error = e

            if attempt < self._MAX_RETRIES + 1:
                logger.warning(
                    f"TCN 调用失败 ({request_name})，正在进行第 {attempt} 次重试: {last_error}"
                )
                await asyncio.sleep(1)
            else:
                logger.error(
                    f"TCN 调用连续 {self._MAX_RETRIES + 1} 次失败 ({request_name}): {last_error}"
                )
                if affects_availability:
                    logger.error(f"判定 user 通道异常 ({request_name})")
                    self._enabled = False

        # 全部重试失败 → 返回降级数据（由各方法提供）
        return fallback

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

    async def register_user(self, user_hash: str) -> dict:
        """POST /v1/user/register — 显式建档（幂等），body 仅 user_hash。"""
        user_hash = (user_hash or "").strip()
        if not user_hash:
            return {"ok": False, "_degraded": True, "_degraded_reason": "empty user_hash"}

        async def _call():
            resp = await self._client.post(
                "/v1/user/register",
                json={"user_hash": user_hash},
                headers=self._auth_headers(),
            )
            resp.raise_for_status()
            if resp.content:
                try:
                    return resp.json()
                except Exception:
                    pass
            return {"ok": True, "user_hash": user_hash}

        fallback = {
            "ok": False,
            "user_hash": user_hash,
            "_degraded": True,
            "_degraded_reason": "TCN register 不可达，本地已保留 user_hash，稍后可重试建档",
        }
        return await self._call_with_retry("register_user", _call, **{"_fallback": fallback}) or fallback

    def register_user_sync(self, user_hash: str) -> dict:
        """同步建档：供注册/登录等同步路由调用，避免复用 AsyncClient 跨 loop。"""
        user_hash = (user_hash or "").strip()
        if not user_hash:
            return {"ok": False, "_degraded": True, "_degraded_reason": "empty user_hash"}
        if not self._enabled:
            return {
                "ok": False,
                "user_hash": user_hash,
                "_degraded": True,
                "_degraded_reason": "TCN_ENABLED=false",
            }

        headers = {"Content-Type": "application/json", **self._auth_headers()}
        last_error: Exception | None = None
        for attempt in range(1, self._MAX_RETRIES + 2):
            try:
                with httpx.Client(
                    base_url=TCN_BASE_URL.rstrip("/"),
                    timeout=httpx.Timeout(TCN_TIMEOUT),
                    headers=headers,
                ) as client:
                    resp = client.post("/v1/user/register", json={"user_hash": user_hash})
                    resp.raise_for_status()
                    if not self._enabled:
                        self._enabled = True
                    if resp.content:
                        try:
                            body = resp.json()
                            if isinstance(body, dict):
                                body.setdefault("ok", True)
                                body.setdefault("user_hash", user_hash)
                                return body
                        except Exception:
                            pass
                    return {"ok": True, "user_hash": user_hash}
            except Exception as e:
                last_error = e
                if attempt < self._MAX_RETRIES + 1:
                    logger.warning(
                        "TCN register 失败，第 %s 次重试: user_hash=%s err=%s",
                        attempt,
                        user_hash,
                        e,
                    )
                    time.sleep(1)
                else:
                    logger.error(
                        "TCN register 连续失败，降级放行注册: user_hash=%s err=%s",
                        user_hash,
                        e,
                    )
                    self._enabled = False

        return {
            "ok": False,
            "user_hash": user_hash,
            "_degraded": True,
            "_degraded_reason": f"TCN register 失败: {last_error}",
        }

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
        """GET /admin/graph/domains — 控制台 admin 接口，不参与 user 通道熔断。"""
        fallback: list = []
        if not (TCN_ADMIN_TOKEN or "").strip():
            logger.warning("TCN_ADMIN_TOKEN 未配置，跳过图谱域拉取（KT 用户接口不受影响）")
            return fallback

        async def _call():
            resp = await self._client.get(
                "/admin/graph/domains", headers=self._admin_headers()
            )
            resp.raise_for_status()
            return resp.json()

        result = await self._call_with_retry(
            "get_graph_domains",
            _call,
            _fallback=fallback,
            affects_availability=False,
        )
        return result or fallback

    async def get_graph_data(self, domain: str) -> dict:
        """GET /admin/graph/data/{domain} — 控制台 admin 接口，不参与 user 通道熔断。"""
        fallback: dict = {"nodes": [], "edges": []}
        if not (TCN_ADMIN_TOKEN or "").strip():
            logger.warning("TCN_ADMIN_TOKEN 未配置，跳过图谱数据拉取: domain=%s", domain)
            return fallback

        async def _call():
            resp = await self._client.get(
                f"/admin/graph/data/{domain}", headers=self._admin_headers()
            )
            resp.raise_for_status()
            return resp.json()

        result = await self._call_with_retry(
            "get_graph_data",
            _call,
            _fallback=fallback,
            affects_availability=False,
        )
        return result or fallback

    # ─── 4 个新接口（respond_fix.md 真实格式确认） ─────────────

    async def get_summary(self, user_hash: str) -> dict:
        """GET /v1/user/summary/{user_hash} — 用户知识状态摘要"""

        async def _call():
            resp = await self._client.get(f"/v1/user/summary/{user_hash}")
            resp.raise_for_status()
            return resp.json()

        fallback = {
            "user_hash": user_hash,
            "diagnosis_version": "degraded",
            "total_steps": 0,
            "overall_mastery": None,
            "global_lvr": None,
            "lvr_level": "unavailable",
            "graph_version": 0,
            "domain_summary": [],
            "last_active_node": None,
            "computed_at": self._degraded_at(),
            "_degraded": True,
            "_degraded_reason": "TCN 引擎不可达，此数据为降级占位，不可作为当前诊断依据",
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
            "diagnosis_version": "degraded",
            "mastery_threshold": threshold,
            "total_gaps": None,
            "returned_gaps": 0,
            "limit": limit,
            "gaps": [],
            "computed_at": self._degraded_at(),
            "_degraded": True,
            "_degraded_reason": "TCN 引擎不可达，此数据为降级占位，不可作为当前诊断依据",
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
            "diagnosis_version": "degraded",
            "mastery_threshold_high": 0.7,
            "total_vulnerabilities": None,
            "returned_vulnerabilities": 0,
            "limit": limit,
            "vulnerabilities": [],
            "computed_at": self._degraded_at(),
            "_degraded": True,
            "_degraded_reason": "TCN 引擎不可达，此数据为降级占位，不可作为当前诊断依据",
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
            "diagnosis_version": "degraded",
            "global_lvr": None,
            "lvr_level": "unavailable",
            "alert_code": "LVR_UNAVAILABLE",
            "alert_text": "TCN 引擎不可达，无法计算 LVR 预警",
            "total_violations": None,
            "returned_violations": 0,
            "limit": limit,
            "violations": [],
            "backtrack_recommended": [],
            "computed_at": self._degraded_at(),
            "_degraded": True,
            "_degraded_reason": "TCN 引擎不可达，此数据为降级占位，不可作为当前诊断依据",
        }
        return await self._call_with_retry("get_lvr_alert", _call, **{"_fallback": fallback}) or fallback

    async def close(self):
        await self._client.aclose()


tcn_client = TCNClient()