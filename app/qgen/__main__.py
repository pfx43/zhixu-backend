"""python -m app.qgen

内部出题服务。默认绑定 127.0.0.1:8766，不面向浏览器。
"""
from __future__ import annotations

import logging
import sys
from pathlib import Path

_BACKEND_ROOT = Path(__file__).resolve().parents[2]
if str(_BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(_BACKEND_ROOT))

logging.basicConfig(level=logging.INFO)


def main() -> None:
    import uvicorn

    from app.qgen import settings

    uvicorn.run(
        "app.qgen.app:app",
        host=settings.QGEN_HOST,
        port=settings.QGEN_PORT,
        reload=False,
    )


if __name__ == "__main__":
    main()
