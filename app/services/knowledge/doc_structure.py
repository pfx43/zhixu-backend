"""
文档结构分析 — 页范围、段→页映射、章节目录提取。

只依赖全文文本 / 原始文件名，不触数据库，避免与 page_service 循环 import。
页码一律来自文本中已有的 `## 第 N 页` 标记或 PDF 书签，禁止编造。
"""
import re
from pathlib import Path
from typing import List, Optional, Tuple

from app.services.knowledge.file_parser import get_pdf_page_count

PAGE_HEADING_PATTERN = re.compile(r"^##\s+第\s+(\d+)\s+页\s*$", re.MULTILINE)
HEADING_PATTERN = re.compile(r"^(#{1,3})\s+(.+?)\s*$", re.MULTILINE)
_TITLE_SKIP = re.compile(
    r"(本章小结|重点|考点|关键|核心|总结|练习|习题|思考题|测验|例题|答案|解析)",
    re.IGNORECASE,
)


def extract_page_ranges(text: str) -> List[dict]:
    """按 `## 第 N 页` 切出每页在全文中的字符范围。

    无页标记时返回单页（page_number=1，「全文」）。
    """
    if not text:
        return []

    matches = list(PAGE_HEADING_PATTERN.finditer(text))
    if not matches:
        return [
            {
                "page_number": 1,
                "title": "全文",
                "char_start": 0,
                "char_end": len(text),
            }
        ]

    ranges: List[dict] = []
    for i, match in enumerate(matches):
        page_num = int(match.group(1))
        content_end = matches[i + 1].start() if i + 1 < len(matches) else len(text)
        ranges.append(
            {
                "page_number": page_num,
                "title": f"第 {page_num} 页",
                "char_start": match.start(),
                "char_end": content_end,
            }
        )
    return ranges


def map_segment_pages(
    char_start: int,
    char_end: int,
    page_ranges: List[dict],
) -> Tuple[Optional[int], Optional[int]]:
    """给一个段（字符范围）定位起始/结束页码。一段可跨页。"""
    if not page_ranges:
        return None, None

    start_page = None
    end_page = None
    for pr in page_ranges:
        # 段与该页字符范围有交集即属于该页
        if char_start < pr["char_end"] and char_end > pr["char_start"]:
            if start_page is None:
                start_page = pr["page_number"]
            end_page = pr["page_number"]
    return start_page, end_page


def extract_toc_from_headings(text: str, page_ranges: List[dict]) -> List[dict]:
    """从 Markdown 标题抽取章节目录（章 → 页范围）。

    标题落到哪一页由标题位置在 page_ranges 中的归属决定；
    下一章起始页 - 1 作为上一章结束页，末章直到最后一页。
    标题太少（<=1）或疑似知识点小标题时返回空（不硬造目录）。
    """
    if not text or not page_ranges:
        return []

    heading_matches = [
        m
        for m in HEADING_PATTERN.finditer(text)
        if not _TITLE_SKIP.search(m.group(2))
    ]
    # 注意：`## 第 N 页` 本身会被 HEADING_PATTERN 命中，需剔除
    heading_matches = [
        m for m in heading_matches if not PAGE_HEADING_PATTERN.match(m.group(0))
    ]
    if len(heading_matches) <= 1:
        return []

    def _page_of_char(pos: int) -> int:
        page = page_ranges[0]["page_number"]
        for pr in page_ranges:
            if pr["char_start"] <= pos < pr["char_end"]:
                return pr["page_number"]
        return page

    total_pages = max((pr["page_number"] for pr in page_ranges), default=1)
    entries: List[dict] = []
    for i, m in enumerate(heading_matches):
        start_page = _page_of_char(m.start())
        end_page = (
            _page_of_char(heading_matches[i + 1].start()) - 1
            if i + 1 < len(heading_matches)
            else total_pages
        )
        if end_page < start_page:
            end_page = start_page
        entries.append(
            {
                "title": re.sub(r"\s+", " ", m.group(2)).strip()[:255],
                "page_start": start_page,
                "page_end": end_page,
            }
        )
    return entries


def extract_toc_from_pdf_bookmarks(storage_path: str) -> List[dict]:
    """从 PDF 书签抽取目录（标题 + 页码）。不可用返回空列表。"""
    if not storage_path or not Path(storage_path).is_file():
        return []
    if Path(storage_path).suffix.lower() != ".pdf":
        return []
    try:
        import fitz
    except ImportError:
        return []

    try:
        doc = fitz.open(storage_path)
        try:
            bookmarks = doc.get_toc(simple=True) or []
        finally:
            doc.close()
    except Exception:
        return []

    entries: List[dict] = []
    page_count = get_pdf_page_count(storage_path)
    for i, (level, title, page_num) in enumerate(bookmarks):
        title = (title or "").strip()
        if not title:
            continue
        start_page = int(page_num)
        next_start = None
        for _, _, next_page in bookmarks[i + 1 :]:
            if int(next_page) > start_page:
                next_start = int(next_page)
                break
        end_page = (next_start - 1) if next_start else (page_count or start_page)
        end_page = max(start_page, min(end_page, page_count or end_page))
        entries.append(
            {
                "title": title[:255],
                "page_start": start_page,
                "page_end": end_page,
            }
        )
    return entries