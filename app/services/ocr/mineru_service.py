"""MinerU 云端解析 — 扫描件走精准解析 API，产出带页码的影子 Markdown。

本地文件：申请上传链接 → PUT 文件 → 轮询 batch 结果 → 解开 zip 里的 full.md /
content_list.json，按页写成影子文档（与 Paddle OCR 同一套 parsed pages 目录）。

开关：OCR_BACKEND=mineru，Token 用 MINERU_API_TOKEN（.env）。
HTTP 全部 async，轮询用 asyncio.sleep，挂在事件循环上，不堵 FastAPI worker。
文档：https://mineru.net/apiManage/docs
"""
from __future__ import annotations

import asyncio
import io
import json
import logging
import re
import zipfile
from pathlib import Path
from typing import Callable, Optional

import httpx

from app.core.config import (
    MINERU_API_TOKEN,
    MINERU_BASE_URL,
    MINERU_MODEL_VERSION,
    MINERU_POLL_INTERVAL_SEC,
    MINERU_POLL_TIMEOUT_SEC,
    PDF_OCR_MAX_PAGES,
)
from app.services.knowledge.file_parser import ParseOutcome
from app.services.knowledge.storage_service import safe_parsed_image_name
from app.services.ocr.pdf_ocr_service import build_shadow_markdown

_MD_IMAGE = re.compile(r"!\[([^\]]*)\]\(([^)]+)\)")

logger = logging.getLogger(__name__)

_TIMEOUT = httpx.Timeout(60.0, connect=15.0)
_UPLOAD_TIMEOUT = httpx.Timeout(180.0, connect=15.0)


def is_mineru_configured() -> bool:
    return bool((MINERU_API_TOKEN or "").strip())


def _auth_headers() -> dict[str, str]:
    return {
        "Authorization": f"Bearer {MINERU_API_TOKEN.strip()}",
        "Content-Type": "application/json",
        "Accept": "*/*",
    }


def _page_ranges() -> Optional[str]:
    if PDF_OCR_MAX_PAGES > 0:
        return f"1-{PDF_OCR_MAX_PAGES}"
    return None


def _api_error(payload: dict) -> str:
    msg = str(payload.get("msg") or payload.get("message") or "").strip()
    code = payload.get("code")
    if code not in (None, 0, "0"):
        return f"MinerU 错误 {code}: {msg or '请求失败'}"
    return msg or "MinerU 请求失败"


async def parse_with_mineru(
    file_path: str,
    original_filename: Optional[str] = None,
    on_page_progress: Optional[Callable[[int, int], None]] = None,
) -> ParseOutcome:
    """把本地扫描件/图片交给 MinerU，返回影子 Markdown + page_texts。"""
    if not is_mineru_configured():
        return ParseOutcome(
            text=None,
            error="OCR_BACKEND=mineru，但未配置 MINERU_API_TOKEN",
            ocr_used=True,
        )
    path = Path(file_path)
    if not path.is_file():
        return ParseOutcome(text=None, error=f"MinerU: 找不到文件 {file_path}", ocr_used=True)

    display_name = original_filename or path.name
    try:
        markdown, page_texts, images = await _extract_file(
            path, display_name, on_page_progress
        )
    except MineruError as e:
        logger.warning("mineru 解析失败: %s", e)
        return ParseOutcome(text=None, error=str(e), ocr_used=True)
    except Exception as e:
        logger.exception("mineru 解析异常")
        return ParseOutcome(text=None, error=f"MinerU 解析异常: {e}", ocr_used=True)

    if not any((t or "").strip() for t in page_texts) and not (markdown or "").strip():
        return ParseOutcome(
            text=None,
            error="MinerU 完成但未识别到文字",
            ocr_used=True,
        )

    if not page_texts:
        page_texts = [markdown]
    shadow = build_shadow_markdown(display_name, page_texts)
    logger.info(
        "mineru - 完成: %s, %d 页, %d 字符, %d 图",
        display_name,
        len(page_texts),
        len(shadow),
        len(images),
    )
    return ParseOutcome(
        text=shadow,
        error=None,
        ocr_used=True,
        page_texts=page_texts,
        images=images or None,
    )


class MineruError(RuntimeError):
    pass


async def _extract_file(
    path: Path,
    display_name: str,
    on_page_progress: Optional[Callable[[int, int], None]],
) -> tuple[str, list[str], dict[str, bytes]]:
    batch_id, upload_url = await _apply_upload_url(display_name)
    await _upload_file(upload_url, path)
    zip_url = await _poll_batch(batch_id, on_page_progress)
    return await _read_zip_markdown(zip_url)


async def _apply_upload_url(filename: str) -> tuple[str, str]:
    body: dict = {
        "files": [{"name": Path(filename).name or "scan.pdf"}],
        "model_version": MINERU_MODEL_VERSION,
        "is_ocr": True,
        "enable_formula": True,
        "enable_table": True,
        "language": "ch",
    }
    ranges = _page_ranges()
    if ranges:
        body["page_ranges"] = ranges

    url = f"{MINERU_BASE_URL.rstrip('/')}/api/v4/file-urls/batch"
    async with httpx.AsyncClient(timeout=_TIMEOUT) as client:
        resp = await client.post(url, headers=_auth_headers(), json=body)
    payload = _json_or_error(resp, "申请上传链接")
    if int(payload.get("code", -1)) != 0:
        raise MineruError(_api_error(payload))
    data = payload.get("data") or {}
    batch_id = str(data.get("batch_id") or "").strip()
    urls = data.get("file_urls") or []
    if not batch_id or not urls:
        raise MineruError("MinerU 未返回 batch_id 或上传地址")
    return batch_id, str(urls[0])


async def _upload_file(upload_url: str, path: Path) -> None:
    # MinerU 预签名 URL 对 Content-Type 敏感，不要带这个头。
    data = await asyncio.to_thread(path.read_bytes)
    async with httpx.AsyncClient(timeout=_UPLOAD_TIMEOUT) as client:
        req = client.build_request("PUT", upload_url, content=data)
        req.headers.pop("content-type", None)
        resp = await client.send(req)
    if resp.status_code != 200:
        raise MineruError(f"MinerU 文件上传失败 HTTP {resp.status_code}")


async def _poll_batch(
    batch_id: str,
    on_page_progress: Optional[Callable[[int, int], None]],
) -> str:
    url = f"{MINERU_BASE_URL.rstrip('/')}/api/v4/extract-results/batch/{batch_id}"
    deadline = asyncio.get_running_loop().time() + max(30, MINERU_POLL_TIMEOUT_SEC)
    interval = max(1.0, float(MINERU_POLL_INTERVAL_SEC))

    while asyncio.get_running_loop().time() < deadline:
        async with httpx.AsyncClient(timeout=_TIMEOUT) as client:
            resp = await client.get(url, headers=_auth_headers())
        payload = _json_or_error(resp, "查询解析进度")
        if int(payload.get("code", -1)) != 0:
            raise MineruError(_api_error(payload))
        items = (payload.get("data") or {}).get("extract_result") or []
        item = items[0] if items else {}
        state = str(item.get("state") or "").lower()
        progress = item.get("extract_progress") or {}
        extracted = int(progress.get("extracted_pages") or 0)
        total = int(progress.get("total_pages") or 0)
        if on_page_progress and total:
            on_page_progress(extracted, total)

        if state == "done":
            zip_url = str(item.get("full_zip_url") or "").strip()
            if not zip_url:
                raise MineruError("MinerU 完成但未返回结果压缩包")
            return zip_url
        if state == "failed":
            raise MineruError(item.get("err_msg") or "MinerU 解析失败")
        await asyncio.sleep(interval)

    raise MineruError(f"MinerU 解析超时（{MINERU_POLL_TIMEOUT_SEC}s），batch_id={batch_id}")


async def _read_zip_markdown(zip_url: str) -> tuple[str, list[str], dict[str, bytes]]:
    async with httpx.AsyncClient(timeout=_UPLOAD_TIMEOUT) as client:
        resp = await client.get(zip_url)
    if resp.status_code != 200:
        raise MineruError(f"下载 MinerU 结果失败 HTTP {resp.status_code}")
    return markdown_and_pages_from_zip(resp.content)


def markdown_and_pages_from_zip(
    zip_bytes: bytes,
) -> tuple[str, list[str], dict[str, bytes]]:
    """从 MinerU zip 抽出 Markdown、按页正文和图。"""
    try:
        archive = zipfile.ZipFile(io.BytesIO(zip_bytes))
    except zipfile.BadZipFile as e:
        raise MineruError(f"MinerU 结果不是合法 zip: {e}") from e

    names = archive.namelist()
    md_name = _pick_zip_member(names, "full.md")
    list_name = _pick_zip_member(names, "content_list.json")
    markdown = ""
    if md_name:
        markdown = archive.read(md_name).decode("utf-8", errors="replace")
    page_texts: list[str] = []
    if list_name:
        try:
            raw = json.loads(archive.read(list_name).decode("utf-8", errors="replace"))
            page_texts = _pages_from_content_list(raw)
        except (json.JSONDecodeError, TypeError, ValueError):
            logger.warning("mineru content_list.json 无法解析，改用 full.md")
    if not page_texts and markdown.strip():
        page_texts = _pages_from_markdown(markdown)
    images = _images_from_zip(archive)
    markdown = rewrite_md_image_refs(markdown)
    page_texts = [rewrite_md_image_refs(page) for page in page_texts]
    return markdown, page_texts, images


def rewrite_md_image_refs(text: str) -> str:
    """把 zip/full.md 里的图片引用统一成 images/{文件名}。"""
    if not text:
        return text

    def _replace(match: re.Match[str]) -> str:
        alt = match.group(1)
        url = match.group(2).strip().strip("\"'")
        if re.match(r"^(https?:|data:|blob:|#|/)", url, re.I):
            return match.group(0)
        name = safe_parsed_image_name(url)
        if not name:
            return match.group(0)
        return f"![{alt}](images/{name})"

    return _MD_IMAGE.sub(_replace, text)


def _images_from_zip(archive: zipfile.ZipFile) -> dict[str, bytes]:
    images: dict[str, bytes] = {}
    for member in archive.namelist():
        if member.endswith("/"):
            continue
        name = safe_parsed_image_name(member)
        if not name:
            continue
        try:
            images[name] = archive.read(member)
        except Exception:
            logger.warning("mineru zip 读图失败: %s", member)
    return images


def _pick_zip_member(names: list[str], suffix: str) -> Optional[str]:
    suffix = suffix.lower()
    for name in names:
        if name.lower().endswith(suffix) and not name.endswith("/"):
            return name
    return None


def _block_text(item: dict) -> str:
    text = ""
    for key in ("text", "md", "content", "table_body", "html"):
        val = item.get(key)
        if isinstance(val, str) and val.strip():
            text = val.strip()
            break
    img = item.get("img_path") or item.get("image_path")
    name = safe_parsed_image_name(str(img)) if img else None
    image_md = f"![](images/{name})" if name else ""
    if text and image_md:
        return f"{text}\n\n{image_md}"
    return text or image_md


def _pages_from_content_list(raw) -> list[str]:
    items = raw
    if isinstance(raw, dict):
        items = raw.get("pdf_info") or raw.get("content_list") or raw.get("data") or []
    if not isinstance(items, list) or not items:
        return []
    # MinerU v2：外层按页
    if isinstance(items[0], list):
        pages: list[str] = []
        for blocks in items:
            parts = [_block_text(b) for b in blocks if isinstance(b, dict)]
            pages.append("\n\n".join(p for p in parts if p))
        return pages
    by_page: dict[int, list[str]] = {}
    for item in items:
        if not isinstance(item, dict):
            continue
        idx = item.get("page_idx", item.get("page_no", item.get("page_index")))
        try:
            page = int(idx)
        except (TypeError, ValueError):
            page = 0
        text = _block_text(item)
        if text:
            by_page.setdefault(page, []).append(text)
    if not by_page:
        return []
    max_page = max(by_page)
    # MinerU page_idx 从 0 起
    return ["\n\n".join(by_page.get(i, [])) for i in range(max_page + 1)]


def _pages_from_markdown(markdown: str) -> list[str]:
    import re

    chunks = re.split(r"(?m)^##\s+第\s*\d+\s*页\s*$", markdown)
    if len(chunks) > 1:
        pages = [c.strip() for c in chunks[1:]]
        return pages or [markdown]
    return [markdown]


def _json_or_error(resp: httpx.Response, action: str) -> dict:
    try:
        payload = resp.json()
    except Exception:
        payload = {}
    if resp.status_code != 200:
        detail = _api_error(payload) if payload else resp.text[:200]
        raise MineruError(f"{action}失败 HTTP {resp.status_code}: {detail}")
    if not isinstance(payload, dict):
        raise MineruError(f"{action}返回无法解析")
    return payload
