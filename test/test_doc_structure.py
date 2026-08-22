"""功能 B — 文档结构（页范围 / 段→页映射 / 目录提取）纯函数测试。"""
from app.services.knowledge import doc_structure


def test_extract_page_ranges_with_markers():
    text = "## 第 1 页\n\n第一页内容\n\n## 第 2 页\n\n第二页内容\n\n## 第 3 页\n\n第三页"
    ranges = doc_structure.extract_page_ranges(text)
    assert [r["page_number"] for r in ranges] == [1, 2, 3]
    # 每页范围不重叠、首尾正确
    assert ranges[0]["char_start"] == 0
    assert ranges[-1]["char_end"] == len(text)
    for i in range(len(ranges) - 1):
        assert ranges[i]["char_end"] == ranges[i + 1]["char_start"]


def test_extract_page_ranges_single_page_fallback():
    text = "没有任何页标记的普通文本"
    ranges = doc_structure.extract_page_ranges(text)
    assert len(ranges) == 1
    assert ranges[0]["page_number"] == 1
    assert ranges[0]["title"] == "全文"
    assert ranges[0]["char_start"] == 0
    assert ranges[0]["char_end"] == len(text)


def test_map_segment_pages_single_page():
    ranges = [
        {"page_number": 1, "char_start": 0, "char_end": 10},
        {"page_number": 2, "char_start": 10, "char_end": 20},
    ]
    assert doc_structure.map_segment_pages(2, 8, ranges) == (1, 1)


def test_map_segment_pages_cross_page():
    ranges = [
        {"page_number": 1, "char_start": 0, "char_end": 10},
        {"page_number": 2, "char_start": 10, "char_end": 20},
    ]
    # 段跨两页
    assert doc_structure.map_segment_pages(5, 15, ranges) == (1, 2)


def test_map_segment_pages_no_overlap():
    ranges = [
        {"page_number": 1, "char_start": 0, "char_end": 10},
    ]
    assert doc_structure.map_segment_pages(100, 110, ranges) == (None, None)


def test_extract_toc_from_headings():
    text = "# 第一章\n\n## 第 1 页\n\n正文\n\n# 第二章\n\n## 第 2 页\n\n正文\n\n# 第三章\n\n正文"
    ranges = doc_structure.extract_page_ranges(text)
    toc = doc_structure.extract_toc_from_headings(text, ranges)
    titles = [e["title"] for e in toc]
    assert "第一章" in titles
    assert "第二章" in titles
    # 每章有有效页范围
    for e in toc:
        assert e["page_start"] <= e["page_end"]


def test_extract_toc_empty_when_no_headings():
    text = "## 第 1 页\n\n只有正文没有章标题"
    ranges = doc_structure.extract_page_ranges(text)
    assert doc_structure.extract_toc_from_headings(text, ranges) == []


def test_extract_toc_skips_page_headings():
    # `## 第 N 页` 不应被当成章标题，只有 1 个真实标题时返回空
    text = "## 第 1 页\n\n正文\n\n## 第 2 页\n\n正文"
    ranges = doc_structure.extract_page_ranges(text)
    assert doc_structure.extract_toc_from_headings(text, ranges) == []