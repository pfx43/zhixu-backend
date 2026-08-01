"""

多格式文件解析器

支持 TXT / MD / CSV / JSON / HTML / PDF / DOCX

"""

import logging

import zipfile

from dataclasses import dataclass

from pathlib import Path

from typing import Optional



from app.core.config import DOCUMENT_PIPELINE_ASYNC, PDF_MAX_PAGES



logger = logging.getLogger(__name__)



# 支持的文件类型映射

SUPPORTED_EXTENSIONS = {

    ".txt": "text",

    ".md": "text",

    ".csv": "text",

    ".json": "text",

    ".html": "text",

    ".htm": "text",

    ".pdf": "pdf",

    ".docx": "docx",

    ".png": "image",

    ".jpg": "image",

    ".jpeg": "image",

    ".webp": "image",

    ".bmp": "image",

}



# 图片扩展名集合（需要 OCR 处理）

IMAGE_EXTENSIONS = {".png", ".jpg", ".jpeg", ".webp", ".bmp"}





@dataclass

class ParseOutcome:

    text: Optional[str]

    error: Optional[str] = None

    ocr_used: bool = False

    page_texts: Optional[list[str]] = None





def _read_magic_header(file_path: str, n: int = 12) -> bytes:

    with open(file_path, "rb") as f:

        return f.read(n)





def _detect_ooxml_suffix(file_path: str) -> Optional[str]:

    try:

        with zipfile.ZipFile(file_path, "r") as zf:

            if any(name.startswith("word/") for name in zf.namelist()):

                return ".docx"

    except (zipfile.BadZipFile, OSError) as e:

        logger.debug("file_parser - OOXML 检测失败: %s", e)

    return None





def detect_suffix(file_path: str, original_filename: Optional[str] = None) -> Optional[str]:

    """从原始文件名、路径后缀或 magic bytes 推断扩展名。"""

    if original_filename:

        suffix = Path(original_filename).suffix.lower()

        if suffix in SUPPORTED_EXTENSIONS:

            return suffix



    suffix = Path(file_path).suffix.lower()

    if suffix in SUPPORTED_EXTENSIONS:

        return suffix



    try:

        header = _read_magic_header(file_path)

    except OSError as e:

        logger.warning("file_parser - 无法读取文件头: %s", e)

        return None



    if header.startswith(b"%PDF"):

        return ".pdf"

    if header.startswith(b"\x89PNG"):

        return ".png"

    if header.startswith(b"\xff\xd8\xff"):

        return ".jpeg"

    if header.startswith(b"BM"):

        return ".bmp"

    if len(header) >= 12 and header[:4] == b"RIFF" and header[8:12] == b"WEBP":

        return ".webp"

    if header.startswith(b"PK\x03\x04"):

        return _detect_ooxml_suffix(file_path)



    return None





def parse_file(file_path: str, original_filename: Optional[str] = None) -> Optional[str]:

    """根据文件类型解析内容，返回纯文本；失败返回 None。"""

    return parse_file_detailed(file_path, original_filename).text





def parse_file_detailed(
    file_path: str,
    original_filename: Optional[str] = None,
    *,
    allow_ocr_fallback: bool = True,
) -> ParseOutcome:

    """

    解析文件并返回文本与可读错误信息。



    Returns:

        ParseOutcome: text 为 None 时 error 说明原因（扫描版 PDF、缺依赖等）

    """

    path_obj = Path(file_path)

    if not path_obj.exists():

        msg = f"文件不存在: {file_path}"

        logger.error("file_parser - %s", msg)

        return ParseOutcome(text=None, error=msg)



    suffix = detect_suffix(file_path, original_filename)

    file_type = SUPPORTED_EXTENSIONS.get(suffix) if suffix else None



    if file_type is None:

        msg = f"不支持的文件类型: {suffix or '未知'}"

        logger.warning(

            "file_parser - %s (path=%s, original=%s)",

            msg,

            file_path,

            original_filename,

        )

        return ParseOutcome(text=None, error=msg)



    if file_type == "text":

        text = _parse_text(file_path)

        return ParseOutcome(

            text=text,

            error=None if text is not None else "文本文件读取失败（编码不支持或文件为空）",

        )

    if file_type == "pdf":
        return _parse_pdf(
            file_path, original_filename, allow_ocr_fallback=allow_ocr_fallback
        )

    if file_type == "docx":

        text = _parse_docx(file_path)

        return ParseOutcome(

            text=text,

            error=None if text is not None else "DOCX 解析失败或文档无文字内容",

        )



    return ParseOutcome(text=None, error="不支持的文件类型")





def _parse_text(file_path: str) -> Optional[str]:

    """解析纯文本文件（TXT/MD/CSV/JSON/HTML），尝试多种编码"""

    encodings = ["utf-8", "gbk", "gb2312", "latin-1"]

    for enc in encodings:

        try:

            with open(file_path, "r", encoding=enc, errors="replace") as f:

                return f.read()

        except UnicodeDecodeError:

            continue

        except Exception as e:

            logger.error(f"file_parser._parse_text 失败 ({enc}): {e}")

            continue

    return None





def _pdf_page_limit(total_pages: int) -> int:

    if PDF_MAX_PAGES > 0:

        return min(total_pages, PDF_MAX_PAGES)

    return total_pages


def get_pdf_page_count(file_path: str) -> int:
    """返回 PDF 总页数；无法读取时返回 0。"""
    try:
        import fitz
    except ImportError:
        return 0
    try:
        doc = fitz.open(file_path)
        try:
            return doc.page_count
        finally:
            doc.close()
    except Exception as e:
        logger.warning("file_parser.get_pdf_page_count 失败: %s", e)
        return 0


def _pdf_parse_result(
    pages_text: list[str],
    *,
    original_filename: Optional[str] = None,
    file_path: str = "",
) -> ParseOutcome:
    """将按页文本转为带页码标记的 markdown 与 page_texts。"""
    from app.services.pdf_ocr_service import build_shadow_markdown

    display_name = original_filename or Path(file_path).name or "document.pdf"
    markdown = build_shadow_markdown(display_name, pages_text)
    return ParseOutcome(text=markdown, page_texts=pages_text)


def is_scanned_pdf(file_path: str) -> tuple[bool, int]:
    """
    判定 PDF 是否为扫描件（无嵌入文本层）。
    返回 (needs_ocr, page_count)。
    """
    try:
        import fitz
    except ImportError:
        return False, 0

    try:
        doc = fitz.open(file_path)
        try:
            total = doc.page_count
            if total == 0:
                return False, 0
            limit = _pdf_page_limit(total)
            for i in range(limit):
                if (doc[i].get_text("text") or "").strip():
                    return False, total
            return True, total
        finally:
            doc.close()
    except Exception as e:
        logger.warning("file_parser.is_scanned_pdf 失败: %s", e)
        return False, 0


def _parse_pdf(
    file_path: str,
    original_filename: Optional[str] = None,
    *,
    allow_ocr_fallback: bool = True,
) -> ParseOutcome:

    """解析 PDF：优先 PyMuPDF，回退 pdfplumber，再回退 PyPDF2。"""

    errors: list[str] = []



    outcome = _parse_pdf_pymupdf(file_path, original_filename)

    if outcome.text:

        return outcome

    if outcome.error:

        errors.append(outcome.error)



    outcome = _parse_pdf_pdfplumber(file_path, original_filename)

    if outcome.text:

        return outcome

    if outcome.error:

        errors.append(outcome.error)



    outcome = _parse_pdf_pypdf2(file_path, original_filename)

    if outcome.text:

        return outcome

    if outcome.error:

        errors.append(outcome.error)



    detail = "；".join(errors) if errors else "所有 PDF 解析器均未能提取文本"

    needs_ocr, page_count = is_scanned_pdf(file_path)
    if needs_ocr and (DOCUMENT_PIPELINE_ASYNC or not allow_ocr_fallback):
        return ParseOutcome(
            text=None,
            error=(
                f"PDF 无嵌入文本层（扫描版，约 {page_count} 页），"
                "已交由后台 OCR pipeline 处理"
            ),
        )

    if not allow_ocr_fallback:
        return ParseOutcome(text=None, error=detail)

    logger.info("file_parser - 常规 PDF 提取无文本，尝试 OCR 回退: %s", file_path)

    from app.services.pdf_ocr_service import parse_pdf_with_ocr_fallback

    ocr_outcome = parse_pdf_with_ocr_fallback(file_path, original_filename)

    if ocr_outcome.text:

        return ocr_outcome

    ocr_err = ocr_outcome.error or "OCR 未识别到文字"

    return ParseOutcome(

        text=None,

        error=(

            f"PDF 无嵌入文本层（扫描版），OCR 也未能提取文字。"

            f"（常规: {detail}；OCR: {ocr_err}）"

        ),

        ocr_used=ocr_outcome.ocr_used,

    )





def _parse_pdf_pymupdf(
    file_path: str, original_filename: Optional[str] = None
) -> ParseOutcome:

    try:

        import fitz

    except ImportError:

        return ParseOutcome(text=None, error="PyMuPDF 未安装")



    try:

        doc = fitz.open(file_path)

        try:

            total = doc.page_count

            limit = _pdf_page_limit(total)

            pages_text: list[str] = []

            for i in range(limit):

                text = (doc[i].get_text("text") or "").strip()

                pages_text.append(text)

            if limit < total:

                logger.info(

                    "file_parser - PDF 仅解析前 %d/%d 页（PDF_MAX_PAGES=%s）",

                    limit,

                    total,

                    PDF_MAX_PAGES,

                )

            if any(t for t in pages_text):

                return _pdf_parse_result(
                    pages_text,
                    original_filename=original_filename,
                    file_path=file_path,
                )

            if total > 0:

                return ParseOutcome(

                    text=None,

                    error=f"PyMuPDF: {total} 页均无嵌入文本",

                )

            return ParseOutcome(text=None, error="PyMuPDF: PDF 无页面")

        finally:

            doc.close()

    except Exception as e:

        logger.warning("file_parser._parse_pdf_pymupdf 失败: %s", e)

        return ParseOutcome(text=None, error=f"PyMuPDF: {e}")





def _parse_pdf_pdfplumber(
    file_path: str, original_filename: Optional[str] = None
) -> ParseOutcome:

    try:

        import pdfplumber

    except ImportError:

        return ParseOutcome(text=None, error="pdfplumber 未安装")



    try:

        with pdfplumber.open(file_path) as pdf:

            total = len(pdf.pages)

            limit = _pdf_page_limit(total)

            pages_text: list[str] = []

            for page in pdf.pages[:limit]:

                text = (page.extract_text() or "").strip()

                pages_text.append(text)

            if any(t for t in pages_text):

                return _pdf_parse_result(
                    pages_text,
                    original_filename=original_filename,
                    file_path=file_path,
                )

            if total > 0:

                return ParseOutcome(

                    text=None,

                    error=f"pdfplumber: {total} 页均无嵌入文本",

                )

            return ParseOutcome(text=None, error="pdfplumber: PDF 无页面")

    except Exception as e:

        logger.warning("file_parser._parse_pdf_pdfplumber 失败: %s", e)

        return ParseOutcome(text=None, error=f"pdfplumber: {e}")





def _parse_pdf_pypdf2(
    file_path: str, original_filename: Optional[str] = None
) -> ParseOutcome:

    try:

        from PyPDF2 import PdfReader

    except ImportError:

        return ParseOutcome(text=None, error="PyPDF2 未安装")



    try:

        reader = PdfReader(file_path)

        total = len(reader.pages)

        limit = _pdf_page_limit(total)

        pages_text: list[str] = []

        for page in reader.pages[:limit]:

            text = (page.extract_text() or "").strip()

            pages_text.append(text)

        if any(t for t in pages_text):

            return _pdf_parse_result(
                pages_text,
                original_filename=original_filename,
                file_path=file_path,
            )

        if total > 0:

            return ParseOutcome(

                text=None,

                error=f"PyPDF2: {total} 页均无嵌入文本",

            )

        return ParseOutcome(text=None, error="PyPDF2: PDF 无页面")

    except Exception as e:

        logger.error("file_parser._parse_pdf_pypdf2 失败: %s", e)

        return ParseOutcome(text=None, error=f"PyPDF2: {e}")





def _parse_docx(file_path: str) -> Optional[str]:

    """解析 DOCX 文件"""

    try:

        from docx import Document

        doc = Document(file_path)

        paragraphs = [p.text for p in doc.paragraphs if p.text.strip()]

        return "\n".join(paragraphs) if paragraphs else None

    except ImportError:

        logger.error("file_parser - python-docx 未安装，无法解析 DOCX")

        return None

    except Exception as e:

        logger.error(f"file_parser._parse_docx 失败: {e}")

        return None





def get_supported_extensions() -> list:

    """返回支持的文件扩展名列表"""

    return list(SUPPORTED_EXTENSIONS.keys())


