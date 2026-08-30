"""出题服务调用主程序内部接口。"""
from __future__ import annotations

from typing import Any, Optional

import httpx

from app.qgen import settings


class MainApiError(RuntimeError):
    pass


def _headers() -> dict[str, str]:
    return {"X-Internal-Key": settings.INTERNAL_API_KEY}


def _client() -> httpx.Client:
    return httpx.Client(base_url=settings.QGEN_MAIN_URL, timeout=60.0, headers=_headers())


def claim_job() -> Optional[dict[str, Any]]:
    with _client() as client:
        response = client.post("/api/v1/internal/qgen/claim")
        if response.status_code == 403:
            raise MainApiError("内部密钥被拒绝")
        response.raise_for_status()
        data = response.json()
    return data.get("job")


def mark_progress(job_id: str, page_number: int) -> None:
    with _client() as client:
        response = client.post(
            f"/api/v1/internal/qgen/jobs/{job_id}/pages/{page_number}/progress"
        )
        response.raise_for_status()


def complete_page(
    job_id: str,
    page_number: int,
    questions: list[dict],
    usage: Optional[dict] = None,
) -> dict[str, Any]:
    with _client() as client:
        response = client.post(
            f"/api/v1/internal/qgen/jobs/{job_id}/pages/{page_number}/complete",
            json={"questions": questions, "usage": usage},
        )
        response.raise_for_status()
        return response.json()


def fail_page(job_id: str, page_number: int, error: str) -> dict[str, Any]:
    with _client() as client:
        response = client.post(
            f"/api/v1/internal/qgen/jobs/{job_id}/pages/{page_number}/fail",
            json={"error": error},
        )
        response.raise_for_status()
        return response.json()
