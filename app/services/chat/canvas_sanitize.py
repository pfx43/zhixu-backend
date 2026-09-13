"""清洗 Tina 画布 HTML：只保留可内联绘制的片段，禁止外链与嵌套浏览上下文。"""

from __future__ import annotations

import re

MAX_CANVAS_HTML = 80_000

_SCRIPT_SRC = re.compile(r"<script\b[^>]*\bsrc\b[^>]*>[\s\S]*?</script>", re.I)
_SCRIPT_SRC_OPEN = re.compile(r"<script\b[^>]*\bsrc\b[^>]*/?>", re.I)
_FORBIDDEN = re.compile(
    r"<\s*(iframe|object|embed|applet|base|meta|link|form|frame|frameset)\b[^>]*>[\s\S]*?</\s*\1\s*>",
    re.I,
)
_FORBIDDEN_OPEN = re.compile(
    r"<\s*(iframe|object|embed|applet|base|meta|link|form|frame|frameset)\b[^>]*>",
    re.I,
)
_JS_URL = re.compile(r"""(\s(?:href|src)\s*=\s*)(['"]?)\s*javascript:""", re.I)
_BODY = re.compile(r"<body[^>]*>([\s\S]*)</body>", re.I)
_HEAD = re.compile(r"<head[\s\S]*?</head>", re.I)
_DOC = re.compile(r"<!DOCTYPE[^>]*>|</?html\b[^>]*>|</?body\b[^>]*>", re.I)


def sanitize_canvas_html(raw: str) -> tuple[bool, str]:
    html = (raw or "").strip()
    if not html:
        return False, "html 为空"
    if len(html) > MAX_CANVAS_HTML:
        return False, f"html 过长（最多 {MAX_CANVAS_HTML} 字）"
    m = _BODY.search(html)
    if m:
        html = m.group(1).strip()
    else:
        html = _HEAD.sub("", html)
        html = _DOC.sub("", html).strip()
    html = _SCRIPT_SRC.sub("", html)
    html = _SCRIPT_SRC_OPEN.sub("", html)
    html = _FORBIDDEN.sub("", html)
    html = _FORBIDDEN_OPEN.sub("", html)
    html = _JS_URL.sub(r"\1\2#", html)
    html = html.strip()
    if not html:
        return False, "清洗后没有可显示的内容"
    return True, html
