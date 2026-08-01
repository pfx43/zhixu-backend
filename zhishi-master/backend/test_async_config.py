"""
配置与异步 pipeline 冒烟测试
运行: cd backend && python test_async_config.py
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))


def test_app_config_loads():
    from app.core.app_config import get_app_config, config_path

    cfg = get_app_config()
    path = config_path()
    assert path.name == "config.json"
    assert cfg.ocr_max_parallel_pages >= 1
    assert isinstance(cfg.document_pipeline_async, bool)
    assert isinstance(cfg.llm_async, bool)
    assert isinstance(cfg.image_ocr_async, bool)
    print(f"OK app_config: path={path}, parallel={cfg.ocr_max_parallel_pages}")


def test_config_py_reexports():
    from app.core import config

    assert config.OCR_MAX_PARALLEL_PAGES >= 1
    assert config.MAX_QUESTIONS_PER_DOCUMENT >= 1
    assert isinstance(config.LLM_ASYNC, bool)
    assert isinstance(config.IMAGE_OCR_ASYNC, bool)
    print(
        f"OK config.py: pipeline_async={config.DOCUMENT_PIPELINE_ASYNC}, "
        f"question_async={config.QUESTION_GEN_ASYNC}, "
        f"llm_async={config.LLM_ASYNC}, image_ocr_async={config.IMAGE_OCR_ASYNC}"
    )


def test_llm_runner_sync_path():
    from unittest.mock import MagicMock

    from app.services import llm_runner

    llm = MagicMock()
    llm.predict.return_value = {"content": "ok"}
    with __import__("unittest.mock", fromlist=["patch"]).patch(
        "app.services.llm_runner.LLM_ASYNC", False
    ):
        out = llm_runner.llm_predict_no_stream(llm, input_text="hi")
    assert out["content"] == "ok"
    llm.predict.assert_called_once()
    print("OK llm_runner sync fallback")


def test_file_parser_defers_ocr_when_async():
    from unittest.mock import patch

    from app.services.file_parser import parse_file_detailed
    import tempfile
    import fitz

    with tempfile.TemporaryDirectory() as tmp:
        pdf_path = __import__("pathlib").Path(tmp) / "scan.pdf"
        doc = fitz.open()
        doc.new_page()
        doc.save(str(pdf_path))
        doc.close()

        with patch("app.services.file_parser.DOCUMENT_PIPELINE_ASYNC", True):
            with patch("app.services.file_parser.is_scanned_pdf", return_value=(True, 1)):
                outcome = parse_file_detailed(str(pdf_path))

        assert outcome.text is None
        assert outcome.error and "后台 OCR" in outcome.error
        print("OK file_parser defer OCR when async")


def test_parallel_ocr_progress_thread_safe():
    from unittest.mock import patch

    from app.services.pdf_ocr_service import parse_pdf_with_ocr_fallback
    import tempfile

    import fitz

    with tempfile.TemporaryDirectory() as tmp:
        pdf_path = Path(tmp) / "p.pdf"
        doc = fitz.open()
        for _ in range(3):
            doc.new_page()
        doc.save(str(pdf_path))
        doc.close()

        calls = []

        def on_progress(current, total):
            calls.append((current, total))

        with patch("app.core.config.OCR_MAX_PARALLEL_PAGES", 2):
            with patch(
                "app.services.pdf_ocr_service._ocr_page_image",
                return_value=("x", None),
            ):
                outcome = parse_pdf_with_ocr_fallback(
                    str(pdf_path), on_page_progress=on_progress
                )

        assert outcome.text is not None
        assert len(calls) == 4  # 0 + 3 pages
        assert calls[-1][0] == 3
        print("OK parallel OCR progress callbacks")


if __name__ == "__main__":
    test_app_config_loads()
    test_config_py_reexports()
    test_llm_runner_sync_path()
    test_file_parser_defers_ocr_when_async()
    test_parallel_ocr_progress_thread_safe()
    print("\nAll async/config checks passed.")
