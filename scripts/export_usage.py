"""导出用户用量信息（usage_token / usage_daily）为 CSV。

用法（在仓库根目录执行）：
    python scripts/export_usage.py                     # 导出全部
    python scripts/export_usage.py --yyyymm 202609     # 只导出指定月份的 token

输出到 exports/，文件名带 UTC 时间戳，UTF-8 BOM（Excel 可直接打开）。
"""

from __future__ import annotations

import argparse
import csv
import sys
from datetime import datetime, timezone
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from sqlalchemy import text

from app.core.database import SessionLocal

EXPORT_DIR = REPO_ROOT / "exports"


def _write_csv(path: Path, header: list[str], rows) -> None:
    with open(path, "w", newline="", encoding="utf-8-sig") as fh:
        writer = csv.writer(fh)
        writer.writerow(header)
        writer.writerows(rows)


def export_token(
    ts: str, yyyymm: str | None, user_id: int | None = None, email: str | None = None
) -> Path:
    sql = """
        SELECT t.user_id, u.email, u.nickname AS display_name, t.yyyymm,
               t.prompt_tokens, t.completion_tokens, t.total_tokens
        FROM usage_token t
        LEFT JOIN users u ON u.id = t.user_id
    """
    params: dict = {}
    where = []
    if yyyymm:
        where.append("t.yyyymm = :yyyymm")
        params["yyyymm"] = yyyymm
    if user_id is not None:
        where.append("t.user_id = :user_id")
        params["user_id"] = user_id
    if email:
        where.append("u.email = :email")
        params["email"] = email
    if where:
        sql += " WHERE " + " AND ".join(where)
    sql += " ORDER BY t.user_id, t.yyyymm"

    suffix = f"_{yyyymm}" if yyyymm else ""
    if user_id is not None:
        suffix += f"_u{user_id}"
    path = EXPORT_DIR / f"usage_token{suffix}_{ts}.csv"
    with SessionLocal() as db:
        rows = list(db.execute(text(sql), params))
    _write_csv(
        path,
        [
            "user_id",
            "email",
            "display_name",
            "yyyymm",
            "prompt_tokens",
            "completion_tokens",
            "total_tokens",
        ],
        rows,
    )
    return path


def export_daily(
    ts: str, user_id: int | None = None, email: str | None = None
) -> Path:
    sql = """
        SELECT d.user_id, u.email, u.nickname AS display_name, d.date, d.api_calls
        FROM usage_daily d
        LEFT JOIN users u ON u.id = d.user_id
    """
    params: dict = {}
    where = []
    if user_id is not None:
        where.append("d.user_id = :user_id")
        params["user_id"] = user_id
    if email:
        where.append("u.email = :email")
        params["email"] = email
    if where:
        sql += " WHERE " + " AND ".join(where)
    sql += " ORDER BY d.date, d.user_id"

    suffix = f"_u{user_id}" if user_id is not None else ""
    path = EXPORT_DIR / f"usage_daily{suffix}_{ts}.csv"
    with SessionLocal() as db:
        rows = list(db.execute(text(sql), params))
    _write_csv(path, ["user_id", "email", "display_name", "date", "api_calls"], rows)
    return path


def main() -> None:
    parser = argparse.ArgumentParser(description="导出用户用量信息为 CSV")
    parser.add_argument("--yyyymm", help="仅导出该月份 token，如 202609")
    parser.add_argument("--user-id", type=int, help="仅导出指定 user_id")
    parser.add_argument("--email", help="仅导出指定邮箱用户")
    args = parser.parse_args()

    EXPORT_DIR.mkdir(exist_ok=True)
    ts = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")

    paths = [export_token(ts, args.yyyymm, args.user_id, args.email)]
    if not args.yyyymm:
        paths.append(export_daily(ts, args.user_id, args.email))

    for p in paths:
        print(f"已导出: {p}")


if __name__ == "__main__":
    main()
