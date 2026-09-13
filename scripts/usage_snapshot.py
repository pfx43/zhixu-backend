"""用量快照与差值 — 测量 test 用户在指定阶段（出题 / 对话）的 token 与调用量。

聚合表没有明细和 timestamp，只能在阶段之间快照相减。

用法：
    python scripts/usage_snapshot.py B0            # 阶段开始前快照
    python scripts/usage_snapshot.py A             # 出题后快照
    python scripts/usage_snapshot.py B             # 三轮对话后快照
    python scripts/usage_delta.py B0 A             # 打印 A-B0

快照写入 exports/usage_snapshot_<label>_<ts>.json。
"""

from __future__ import annotations

import json
import sys
from datetime import datetime, timezone
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from sqlalchemy import text

from app.core.config import APP_TIMEZONE
from app.core.database import SessionLocal

EXPORT_DIR = REPO_ROOT / "exports"

try:
    from zoneinfo import ZoneInfo

    _TZ = ZoneInfo(APP_TIMEZONE)
except Exception:  # pragma: no cover
    _TZ = timezone.utc


def snapshot(label: str, user_id: int) -> Path:
    now_utc = datetime.now(timezone.utc)
    now_local = now_utc.astimezone(_TZ)
    yyyymm = now_local.strftime("%Y%m")
    today = now_local.date().isoformat()

    with SessionLocal() as db:
        token = db.execute(
            text(
                "SELECT prompt_tokens, completion_tokens, total_tokens "
                "FROM usage_token WHERE user_id=:uid AND yyyymm=:ym"
            ),
            {"uid": user_id, "ym": yyyymm},
        ).fetchone()
        daily = db.execute(
            text(
                "SELECT api_calls FROM usage_daily "
                "WHERE user_id=:uid AND date=:d"
            ),
            {"uid": user_id, "d": today},
        ).fetchone()
        jobs = [
            {
                "id": r[0],
                "status": r[1],
                "created_at": r[2].isoformat() if r[2] else None,
                "finished_at": r[3].isoformat() if r[3] else None,
                "pages": r[4],
            }
            for r in db.execute(
                text(
                    "SELECT j.id, j.status, j.created_at, j.finished_at, "
                    "       count(p.id) AS pages "
                    "FROM qgen_jobs j LEFT JOIN qgen_job_pages p ON p.job_id=j.id "
                    "WHERE j.user_id=:uid GROUP BY j.id ORDER BY j.created_at"
                ),
                {"uid": user_id},
            )
        ]
        user = db.execute(
            text("SELECT email, nickname FROM users WHERE id=:uid"), {"uid": user_id}
        ).fetchone()

    data = {
        "label": label,
        "user_id": user_id,
        "email": user[0] if user else None,
        "nickname": user[1] if user else None,
        "captured_at_utc": now_utc.isoformat(),
        "captured_at_local": now_local.isoformat(),
        "yyyymm": yyyymm,
        "date": today,
        "prompt_tokens": (token[0] if token else 0) or 0,
        "completion_tokens": (token[1] if token else 0) or 0,
        "total_tokens": (token[2] if token else 0) or 0,
        "api_calls_today": (daily[0] if daily else 0) or 0,
        "qgen_jobs": jobs,
    }
    ts = now_utc.strftime("%Y%m%d_%H%M%S")
    path = EXPORT_DIR / f"usage_snapshot_{label}_{ts}.json"
    EXPORT_DIR.mkdir(exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(
        {k: data[k] for k in (
            "label", "yyyymm", "date", "prompt_tokens", "completion_tokens",
            "total_tokens", "api_calls_today",
        )},
        ensure_ascii=False,
    ))
    return path


if __name__ == "__main__":
    label = sys.argv[1] if len(sys.argv) > 1 else "snap"
    uid = int(sys.argv[2]) if len(sys.argv) > 2 else 19
    print(f"已写入: {snapshot(label, uid)}")
