"""MinerU 扫描件：OCR_BACKEND=mineru 时异步解析，按页生成影子文档。"""
from __future__ import annotations

import asyncio
import inspect
import io
import json
import zipfile
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

from app.core.job_runner import schedule_coro
from app.services.ocr.mineru_service import (
    markdown_and_pages_from_zip,
    parse_with_mineru,
)
from app.services.ocr.pdf_ocr_service import parse_pdf_with_ocr_fallback


def _zip_bytes(markdown: str, content_list) -> bytes:
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as archive:
        archive.writestr("full.md", markdown)
        archive.writestr(
            "scan_content_list.json",
            json.dumps(content_list, ensure_ascii=False),
        )
    return buf.getvalue()


def test_parse_with_mineru_is_async():
    assert inspect.iscoroutinefunction(parse_with_mineru)


def test_zip_content_list_becomes_page_texts():
    zip_bytes = _zip_bytes(
        "# scan.pdf\n\n页一\n\n页二",
        [
            {"type": "text", "text": "第一页标题", "page_idx": 0},
            {"type": "text", "text": "第一页正文", "page_idx": 0},
            {"type": "text", "text": "第二页", "page_idx": 1},
        ],
    )
    markdown, pages, images = markdown_and_pages_from_zip(zip_bytes)
    assert "页一" in markdown
    assert pages == ["第一页标题\n\n第一页正文", "第二页"]
    assert images == {}


def test_zip_falls_back_to_full_md_when_list_missing():
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as archive:
        archive.writestr("full.md", "## 第 1 页\n\n甲\n\n## 第 2 页\n\n乙")
    markdown, pages, images = markdown_and_pages_from_zip(buf.getvalue())
    assert pages == ["甲", "乙"]
    assert "第 1 页" in markdown
    assert images == {}


def test_zip_embeds_images_into_page_markdown():
    buf = io.BytesIO()
    png = b"\x89PNG\r\n\x1a\n"
    with zipfile.ZipFile(buf, "w") as archive:
        archive.writestr("full.md", "# scan\n\n见图\n\n![](images/fig.png)")
        archive.writestr(
            "scan_content_list.json",
            json.dumps(
                [
                    {"type": "text", "text": "见图", "page_idx": 0},
                    {"type": "image", "img_path": "images/fig.png", "page_idx": 0},
                    {"type": "text", "text": "下一页", "page_idx": 1},
                ],
                ensure_ascii=False,
            ),
        )
        archive.writestr("images/fig.png", png)
    markdown, pages, images = markdown_and_pages_from_zip(buf.getvalue())
    assert pages[0] == "见图\n\n![](images/fig.png)"
    assert pages[1] == "下一页"
    assert "![](images/fig.png)" in markdown
    assert images["fig.png"] == png


def test_save_parsed_pages_writes_images(tmp_path: Path):
    from app.services.knowledge.storage_service import (
        LocalStorage,
        safe_parsed_image_name,
    )

    assert safe_parsed_image_name("images/fig.png") == "fig.png"
    assert safe_parsed_image_name("../secret.png") == "secret.png"
    assert safe_parsed_image_name("readme.txt") is None

    store = LocalStorage(str(tmp_path))
    parsed = store.save_global_parsed_pages(
        "ab" * 16,
        ["见图\n\n![](images/fig.png)"],
        original_filename="scan.pdf",
        images={"fig.png": b"\x89PNG"},
    )
    image_path = Path(parsed) / "images" / "fig.png"
    assert image_path.read_bytes() == b"\x89PNG"
    assert store.parsed_image_path(parsed, "fig.png") == image_path.resolve()
    assert store.parsed_image_path(parsed, "../fig.png") == image_path.resolve()
    assert store.parsed_image_path(parsed, "missing.png") is None
    assert store.parsed_image_path(parsed, "readme.txt") is None


def test_parse_with_mineru_requires_token():
    with patch("app.services.ocr.mineru_service.MINERU_API_TOKEN", ""):
        outcome = asyncio.run(parse_with_mineru("/tmp/missing.pdf"))
    assert outcome.text is None
    assert outcome.ocr_used is True
    assert "MINERU_API_TOKEN" in (outcome.error or "")


class _FakeResponse:
    def __init__(self, status_code=200, payload=None, content=b""):
        self.status_code = status_code
        self._payload = payload if payload is not None else {}
        self.content = content
        self.text = json.dumps(self._payload)

    def json(self):
        return self._payload


class _FakeAsyncClient:
    def __init__(self, zip_bytes: bytes):
        self.zip_bytes = zip_bytes
        self.polls = 0

    async def __aenter__(self):
        return self

    async def __aexit__(self, *args):
        return False

    async def post(self, url, headers=None, json=None):
        assert "file-urls/batch" in url
        assert json["is_ocr"] is True
        return _FakeResponse(
            payload={
                "code": 0,
                "data": {
                    "batch_id": "batch-1",
                    "file_urls": ["https://oss.example/upload"],
                },
            }
        )

    def build_request(self, method, url, content=None):
        req = MagicMock()
        req.headers = {"content-type": "application/octet-stream"}
        req._url = url
        req._content = content
        return req

    async def send(self, req):
        assert "oss.example" in str(req._url)
        return _FakeResponse(status_code=200)

    async def get(self, url, headers=None):
        if "extract-results/batch/" in url:
            self.polls += 1
            if self.polls < 2:
                return _FakeResponse(
                    payload={
                        "code": 0,
                        "data": {
                            "extract_result": [
                                {
                                    "state": "running",
                                    "extract_progress": {
                                        "extracted_pages": 1,
                                        "total_pages": 2,
                                    },
                                }
                            ]
                        },
                    }
                )
            return _FakeResponse(
                payload={
                    "code": 0,
                    "data": {
                        "extract_result": [
                            {
                                "state": "done",
                                "full_zip_url": "https://cdn.example/result.zip",
                            }
                        ]
                    },
                }
            )
        if url.endswith("result.zip"):
            return _FakeResponse(content=self.zip_bytes)
        raise AssertionError(f"unexpected GET {url}")


def test_parse_with_mineru_writes_shadow_pages(tmp_path: Path):
    pdf = tmp_path / "scan.pdf"
    pdf.write_bytes(b"%PDF-1.4 fake")
    zip_bytes = _zip_bytes(
        "ignored",
        [
            {"text": "封面", "page_idx": 0},
            {"text": "目录页", "page_idx": 1},
        ],
    )
    fake = _FakeAsyncClient(zip_bytes)
    progress = []

    with (
        patch("app.services.ocr.mineru_service.MINERU_API_TOKEN", "test-token"),
        patch("app.services.ocr.mineru_service.MINERU_POLL_INTERVAL_SEC", 0.01),
        patch(
            "app.services.ocr.mineru_service.httpx.AsyncClient",
            return_value=fake,
        ),
    ):
        outcome = asyncio.run(
            parse_with_mineru(
                str(pdf),
                original_filename="扫描件.pdf",
                on_page_progress=lambda cur, total: progress.append((cur, total)),
            )
        )

    assert outcome.error is None
    assert outcome.ocr_used is True
    assert outcome.page_texts == ["封面", "目录页"]
    assert "## 第 1 页" in outcome.text
    assert "## 第 2 页" in outcome.text
    assert "封面" in outcome.text
    assert "目录页" in outcome.text
    assert outcome.images in (None, {})
    assert progress == [(1, 2)]


def test_sync_pdf_ocr_does_not_block_on_mineru(tmp_path: Path):
    pdf = tmp_path / "scan.pdf"
    pdf.write_bytes(b"%PDF-1.4 fake")

    with patch("app.services.ocr.pdf_ocr_service.OCR_BACKEND", "mineru"):
        result = parse_pdf_with_ocr_fallback(str(pdf), original_filename="a.pdf")

    assert result.text is None
    assert "后台异步" in (result.error or "")


def test_start_pipeline_schedules_mineru_on_event_loop():
    from app.services.knowledge import kb_service

    doc = SimpleNamespace(id="d1", content_hash="abc", display_name="scan.pdf")
    with (
        patch("app.services.knowledge.kb_service.OCR_BACKEND", "mineru"),
        patch("app.services.knowledge.kb_service.schedule_coro") as scheduled,
        patch("app.services.knowledge.kb_service.run_in_background") as threaded,
    ):
        kb_service._start_document_pipeline(
            doc,
            ocr_mode=True,
            storage_path="/tmp/scan.pdf",
            original_filename="scan.pdf",
            total_pages=2,
        )

    scheduled.assert_called_once()
    threaded.assert_not_called()
    coro = scheduled.call_args[0][0]
    assert asyncio.iscoroutine(coro)
    coro.close()


def test_schedule_coro_does_not_block_running_loop():
    order: list[str] = []

    async def slow():
        await asyncio.sleep(0.05)
        order.append("slow")

    async def main():
        schedule_coro(slow(), name="mineru-test")
        order.append("main")
        await asyncio.sleep(0.12)

    asyncio.run(main())
    assert order == ["main", "slow"]


def test_mineru_does_not_fallback_to_paddle_on_api_error(tmp_path: Path):
    pdf = tmp_path / "scan.pdf"
    pdf.write_bytes(b"%PDF-1.4 fake")

    class _FailClient:
        async def __aenter__(self):
            return self

        async def __aexit__(self, *args):
            return False

        async def post(self, url, headers=None, json=None):
            return _FakeResponse(payload={"code": 401, "msg": "token 无效"})

    with (
        patch("app.services.ocr.mineru_service.MINERU_API_TOKEN", "bad"),
        patch(
            "app.services.ocr.mineru_service.httpx.AsyncClient",
            return_value=_FailClient(),
        ),
        patch("app.services.ocr.ocr_service.extract_text_from_image_bytes") as paddle,
    ):
        outcome = asyncio.run(parse_with_mineru(str(pdf)))

    assert outcome.text is None
    assert "token 无效" in (outcome.error or "")
    paddle.assert_not_called()


def test_ocr_unavailable_message_mineru():
    from app.services.ocr.ocr_service import ocr_unavailable_message

    with (
        patch("app.services.ocr.ocr_service.OCR_BACKEND", "mineru"),
        patch("app.services.ocr.mineru_service.MINERU_API_TOKEN", ""),
    ):
        msg = ocr_unavailable_message()
    assert "MINERU_API_TOKEN" in msg


def test_apply_mineru_outcome_is_async():
    from app.services.knowledge.kb_service import _apply_mineru_outcome

    assert inspect.iscoroutinefunction(_apply_mineru_outcome)


def test_apply_mineru_outcome_writes_segments_via_async_sql():
    from pgutil import make_sessionmaker

    from app.models import Document, DocumentSegment, GlobalDocument, KbCollection, User
    from app.services.knowledge.file_parser import ParseOutcome
    from app.services.knowledge.kb_service import _apply_mineru_outcome

    engine, Session = make_sessionmaker()
    try:
        with Session() as db:
            user = User(
                email="mineru-async@example.com",
                password_hash="hash",
                nickname="Mineru",
                is_active=True,
            )
            db.add(user)
            db.commit()
            db.refresh(user)
            coll = KbCollection(
                user_id=user.id, name="学习区", zone="study", is_default=True
            )
            db.add(coll)
            db.commit()
            db.refresh(coll)
            gdoc = GlobalDocument(
                content_hash="hash-mineru-async",
                original_filename="scan.pdf",
                file_size=10,
                storage_path="/tmp/scan.pdf",
            )
            db.add(gdoc)
            db.flush()
            doc = Document(
                user_id=user.id,
                collection_id=coll.id,
                global_document_id=gdoc.id,
                display_name="scan.pdf",
                zone="study",
                content_hash="hash-mineru-async",
                indexing_status="processing",
                segment_status="not_started",
            )
            db.add(doc)
            db.commit()
            db.refresh(doc)
            doc_id = doc.id

        shadow = "# scan.pdf\n\n## 第 1 页\n\n封面文字\n"
        outcome = ParseOutcome(
            text=shadow, error=None, ocr_used=True, page_texts=["封面文字"]
        )
        with (
            patch(
                "app.services.knowledge.kb_service.storage_service.save_global_parsed_content",
                return_value="/tmp/hash-mineru-async.parsed",
            ),
            patch(
                "app.services.knowledge.segment_service.storage_service.read_text_at_path",
                return_value=shadow,
            ),
        ):
            asyncio.run(
                _apply_mineru_outcome(
                    doc_id, "hash-mineru-async", outcome, "scan.pdf", 1
                )
            )

        with Session() as db:
            doc = db.query(Document).filter(Document.id == doc_id).one()
            assert doc.parsed_cache_key == "/tmp/hash-mineru-async.parsed"
            assert doc.segment_status == "completed"
            segs = (
                db.query(DocumentSegment)
                .filter(DocumentSegment.document_id == doc_id)
                .all()
            )
            assert segs
            assert any("封面" in (s.content or "") for s in segs)
    finally:
        engine.dispose()
