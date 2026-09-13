"""讲题画布工具：show_plot / show_canvas → pending_ui → SSE。"""

from __future__ import annotations

import re
import threading
import uuid
from typing import List

from tina import Tools

from app.services.chat.canvas_sanitize import sanitize_canvas_html


class CanvasTools:
    """函数图与 HTML 画布。不落独立表；由 chat 路由写入本用户会话 payload。"""

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._pending_ui: List[dict] = []
        self.tools = Tools(name="canvas")
        for fn in (self.show_plot, self.show_canvas):
            self.tools.register_tool(fn)

    def drain_ui(self) -> List[dict]:
        with self._lock:
            items = list(self._pending_ui)
            self._pending_ui.clear()
        return items

    def _emit(self, item: dict) -> None:
        with self._lock:
            self._pending_ui.append(item)

    def get_tools(self) -> Tools:
        return self.tools

    def show_plot(
        self,
        expression: str,
        title: str = "",
        x_min: str = "-10",
        x_max: str = "10",
    ) -> str:
        """在右侧画布画出函数图像。用户要看函数图、对照曲线时必须调用。不要用文字假装已经画了。
        Args:
            expression: 关于 x 的表达式。支持嵌套、sin^2(x)、|x|、\\frac{a}{b}、if(x<0,-x,x)。多条曲线用分号分隔，最多 3 条
            title: 图标题，可空
            x_min: 横坐标左端，默认 -10
            x_max: 横坐标右端，默认 10
        """
        raw = (expression or "").strip()
        if not raw:
            return "缺少 expression。请传入如 sin(x) 或 x^2。"
        exprs = [s.strip() for s in re.split(r"[\n；;]+", raw) if s.strip()][:3]
        if not exprs:
            return "表达式无效。"
        try:
            lo = float(str(x_min).strip() or "-10")
        except ValueError:
            lo = -10.0
        try:
            hi = float(str(x_max).strip() or "10")
        except ValueError:
            hi = 10.0
        if lo == hi:
            lo, hi = lo - 1, hi + 1
        if lo > hi:
            lo, hi = hi, lo
        if hi - lo > 1e6:
            return "横坐标范围过大，请缩小 x_min / x_max。"
        payload = {
            "kind": "show_plot",
            "plot": {
                "id": uuid.uuid4().hex,
                "title": (title or "").strip() or None,
                "expressions": exprs,
                "x_min": lo,
                "x_max": hi,
            },
        }
        self._emit(payload)
        shown = "；".join(f"y={e}" for e in exprs)
        return (
            f"已在右侧画布画出函数图。{shown}，x∈[{lo:g},{hi:g}]。"
            "结合图像讲解即可，不要把图再画成 ASCII，也不要声称「已经画了」来代替这次调用。"
        )

    def show_canvas(self, html: str, title: str = "") -> str:
        """在右侧画布显示一段自包含的 HTML/SVG/JS 图形（圆、参数方程、交互示意等）。
        不要外链、不要 iframe。y=f(x) 的普通函数图请用 show_plot。
        Args:
            html: 片段即可，可用 svg/canvas 和内联 script。禁止外链脚本和 iframe
            title: 画布标题，可空
        """
        ok, cleaned = sanitize_canvas_html(html)
        if not ok:
            return f"无法显示画布：{cleaned}"
        payload = {
            "kind": "show_canvas",
            "canvas": {
                "id": uuid.uuid4().hex,
                "title": (title or "").strip() or None,
                "html": cleaned,
            },
        }
        self._emit(payload)
        return (
            f"已在右侧打开 HTML 画布。标题={payload['canvas']['title'] or '画布'}。"
            "结合图形讲解即可，不要把图再画成 ASCII，也不要声称已经画了来代替这次调用。"
        )
