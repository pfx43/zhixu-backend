"""
扫描型 PDF OCR — 渲染页面为图片后识别，输出 Markdown 影子文档

流程：
    1. PyMuPDF 渲染每页为 PNG
    2. 按 OCR_BACKEND 调用 ocr_service（默认本地 PaddleOCR）
    3. 并行 OCR（ThreadPoolExecutor，max_workers 来自 config）
    4. 按页码排序拼接为带页标题的 Markdown
"""
import logging
import threading
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from typing import Callable, Optional

from app.core.config import (
    OCR_BACKEND,
    OCR_MAX_PARALLEL_PAGES,
    PDF_MAX_PAGES,
    PDF_OCR_MAX_PAGES,
    PDF_OCR_RENDER_DPI,
)
from app.services.ocr_service import (
    extract_text_from_image_bytes,
    is_baidu_ocr_configured,
    is_paddle_ocr_available,
    ocr_unavailable_message,
)

logger = logging.getLogger(__name__)

# 百度 OCR 单图约 4MB 限制（base64 前）
_BAIDU_OCR_MAX_BYTES = 3_800_000


def _ocr_page_limit(total_pages: int) -> int:
    if PDF_OCR_MAX_PAGES > 0:
        return min(total_pages, PDF_OCR_MAX_PAGES)
    if PDF_MAX_PAGES > 0:
        return min(total_pages, PDF_MAX_PAGES)
    return total_pages


def _render_page_png(doc, page_index: int, dpi: int) -> bytes:
    import fitz

    page = doc[page_index]
    scale = dpi / 72.0
    matrix = fitz.Matrix(scale, scale)
    pix = page.get_pixmap(matrix=matrix, alpha=False)
    png_bytes = pix.tobytes("png")

    if len(png_bytes) > _BAIDU_OCR_MAX_BYTES:
        reduced_dpi = max(72, int(dpi * 0.7))
        logger.info(
            "pdf_ocr - 第 %d 页图片过大 (%d bytes)，降 DPI %d→%d",
            page_index + 1,
            len(png_bytes),
            dpi,
            reduced_dpi,
        )
        return _render_page_png(doc, page_index, reduced_dpi)

    return png_bytes


def _ocr_page_image(png_bytes: bytes) -> tuple[Optional[str], Optional[str]]:
    """
    对单页 PNG 执行 OCR。

    Returns:
        (text, error): text 为 None 表示 OCR 引擎失败；空字符串表示本页无字
    """
    text = extract_text_from_image_bytes(png_bytes)
    if text is not None:
        return text, None

    if OCR_BACKEND == "local":
        if not is_paddle_ocr_available():
            return None, "PaddleOCR 未安装，请运行: pip install paddleocr"
        return None, "PaddleOCR 识别失败"

    if OCR_BACKEND == "baidu":
        if not is_baidu_ocr_configured():
            return None, ocr_unavailable_message()
        return None, "百度 OCR 调用失败，请检查凭据与网络"

    # auto
    return None, ocr_unavailable_message()


def _ocr_single_page(
    file_path: str, page_index: int, dpi: int
) -> tuple[int, str, Optional[str]]:
    """独立打开 PDF 处理单页，便于线程池并行。"""
    import fitz

    doc = fitz.open(file_path)
    try:
        logger.info("pdf_ocr - 正在 OCR 第 %d 页…", page_index + 1)
        png_bytes = _render_page_png(doc, page_index, dpi)
        page_text, page_err = _ocr_page_image(png_bytes)
        return page_index, page_text, page_err
    finally:
        doc.close()


def build_shadow_markdown(original_filename: str, page_texts: list[str]) -> str:
    """构造 OCR 影子 Markdown 文档。"""
    name = Path(original_filename).name if original_filename else "document.pdf"
    total = len(page_texts)
    lines = [
        f"# {name}",
        "",
        f"> OCR 提取，共 {total} 页",
        "",
    ]
    for i, text in enumerate(page_texts, 1):
        lines.append(f"## 第 {i} 页")
        lines.append("")
        body = text.strip() if text and text.strip() else "（本页未识别到文字）"
        lines.append(body)
        lines.append("")
    return "\n".join(lines).strip() + "\n"


def parse_pdf_with_ocr_fallback(
    file_path: str,
    original_filename: Optional[str] = None,
    on_page_progress: Optional[Callable[[int, int], None]] = None,
):
    """
    扫描型 PDF OCR：渲染每页 → OCR → Markdown 影子文档。

    Returns:
        ParseOutcome（延迟导入避免与 file_parser 循环依赖）
    """
    from app.services.file_parser import ParseOutcome
    try:
        import fitz
    except ImportError:
        return ParseOutcome(
            text=None,
            error="PyMuPDF 未安装，无法进行 PDF 页 OCR",
            ocr_used=True,
        )

    display_name = original_filename or Path(file_path).name

    try:
        doc = fitz.open(file_path)
    except Exception as e:
        logger.error("pdf_ocr - 打开 PDF 失败: %s", e)
        return ParseOutcome(text=None, error=f"PDF OCR: 无法打开文件 ({e})", ocr_used=True)

    try:
        total = doc.page_count
        if total == 0:
            return ParseOutcome(text=None, error="PDF OCR: PDF 无页面", ocr_used=True)

        limit = _ocr_page_limit(total)
        if limit < total:
            logger.info(
                "pdf_ocr - 仅 OCR 前 %d/%d 页（PDF_OCR_MAX_PAGES=%s）",
                limit,
                total,
                PDF_OCR_MAX_PAGES,
            )

        if on_page_progress:
            on_page_progress(0, limit)

        max_workers = min(OCR_MAX_PARALLEL_PAGES, limit)
        page_texts: list[str] = [""] * limit
        ocr_errors: list[str] = []
        fatal_error: Optional[str] = None
        completed_count = 0
        progress_lock = threading.Lock()

        def _report_progress() -> None:
            nonlocal completed_count
            if not on_page_progress:
                return
            with progress_lock:
                completed_count += 1
                on_page_progress(completed_count, limit)

        if max_workers <= 1:
            for i in range(limit):
                _, text, page_err = _ocr_single_page(
                    file_path, i, PDF_OCR_RENDER_DPI
                )
                if page_err:
                    ocr_errors.append(f"第{i + 1}页: {page_err}")
                    if text is None:
                        break
                page_texts[i] = text or ""
                _report_progress()
        else:
            logger.info(
                "pdf_ocr - 并行 OCR: workers=%d, pages=%d",
                max_workers,
                limit,
            )
            with ThreadPoolExecutor(max_workers=max_workers) as executor:
                futures = {
                    executor.submit(
                        _ocr_single_page, file_path, i, PDF_OCR_RENDER_DPI
                    ): i
                    for i in range(limit)
                }
                for future in as_completed(futures):
                    page_index, text, page_err = future.result()
                    if page_err:
                        ocr_errors.append(f"第{page_index + 1}页: {page_err}")
                        if text is None:
                            fatal_error = page_err
                    page_texts[page_index] = text or ""
                    _report_progress()

            if fatal_error and not any(t.strip() for t in page_texts):
                detail = ocr_errors[0] if ocr_errors else fatal_error
                return ParseOutcome(
                    text=None,
                    error=f"PDF OCR 失败: {detail}",
                    ocr_used=True,
                )

        if not any(t.strip() for t in page_texts) and ocr_errors:
            detail = ocr_errors[0]
            return ParseOutcome(
                text=None,
                error=f"PDF OCR 失败: {detail}",
                ocr_used=True,
            )

        combined = "".join(t.strip() for t in page_texts if t)
        if not combined:
            return ParseOutcome(
                text=None,
                error="PDF OCR 完成但未识别到任何文字",
                ocr_used=True,
            )

        markdown = build_shadow_markdown(display_name, page_texts)
        logger.info(
            "pdf_ocr - 完成: %s, %d 页, %d 字符, parallel=%d",
            display_name,
            len(page_texts),
            len(markdown),
            max_workers,
        )
        return ParseOutcome(
            text=markdown,
            error=None,
            ocr_used=True,
            page_texts=page_texts,
        )
    finally:
        doc.close()
