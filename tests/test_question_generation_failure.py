import json
import sys
import types
import unittest
from types import SimpleNamespace
from unittest.mock import patch

from app.crud import question as question_crud
from app.services.quiz import question_gen_service
from app.services.quiz.question_generation_guard import (
    FallbackTemplateRejected,
    is_fixed_fallback_template,
    is_quarantined_question,
)


FALLBACK_OPTIONS = [
    {"key": "A", "text": "真实资料片段"},
    {"key": "B", "text": "与原文无关的干扰项"},
    {"key": "C", "text": "片面或不完整的描述"},
    {"key": "D", "text": "明显错误的描述"},
]


class _FailOnWriteDb:
    def __init__(self):
        self.written = False

    def add(self, _row):
        self.written = True
        raise AssertionError("fixed fallback must be rejected before db.add")

    def flush(self):
        self.written = True
        raise AssertionError("fixed fallback must be rejected before db.flush")


class _FlushOnlyDb:
    def __init__(self):
        self.flush_count = 0

    def flush(self):
        self.flush_count += 1


class QuestionGenerationFailureTests(unittest.TestCase):
    def test_exact_fallback_signature_is_detected(self):
        self.assertTrue(
            is_fixed_fallback_template(
                stem="关于「第一章」，以下哪项最符合原文内容？",
                options=FALLBACK_OPTIONS,
                answer="A",
                question_type="single_choice",
                explanation="请参考原文段落。",
            )
        )

    def test_similar_keywords_without_full_signature_are_not_detected(self):
        options = [dict(item) for item in FALLBACK_OPTIONS]
        options[3] = {"key": "D", "text": "根据原文可以推导出的结论"}
        self.assertFalse(
            is_fixed_fallback_template(
                stem="关于「第一章」，以下哪项最符合原文内容？",
                options=options,
                answer="A",
                question_type="single_choice",
                explanation="请参考原文段落。",
            )
        )

    def test_fixed_fallback_is_rejected_before_global_question_write(self):
        db = _FailOnWriteDb()
        with self.assertRaises(FallbackTemplateRejected):
            question_crud.create_global_question(
                db,
                content_hash="hash",
                stem="关于「第一章」，以下哪项最符合原文内容？",
                question_type="single_choice",
                options_json=json.dumps(FALLBACK_OPTIONS, ensure_ascii=False),
                answer="A",
                explanation="请参考原文页面。",
                tags_json="[]",
                source_type="generated",
            )
        self.assertFalse(db.written)

    def test_historical_fallback_is_quarantined_from_reads(self):
        question = SimpleNamespace(
            source_type="generated",
            stem="关于「第一章」，以下哪项最符合原文内容？",
            question_type="single_choice",
            options=json.dumps(FALLBACK_OPTIONS, ensure_ascii=False),
            answer="A",
            explanation="请参考原文段落。",
        )
        self.assertTrue(is_quarantined_question(question))

    def test_agent_failure_marker_does_not_reach_legacy_llm_or_template(self):
        segment = SimpleNamespace(
            id="segment-1",
            title="第一章",
            content="真实资料内容",
        )
        original_module = sys.modules.get(
            "app.services.quiz.question_gen_agent"
        )
        try:
            for reason in (
                "agent_unavailable",
                "llm_timeout",
                "llm_error",
                "invalid_output",
            ):
                fake_module = types.ModuleType(
                    "app.services.quiz.question_gen_agent"
                )
                fake_module.agent_generate_for_segment = (
                    lambda _segment, *, tag_hint="", _reason=reason: [
                        {"_question_generation_failure": _reason}
                    ]
                )
                sys.modules[
                    "app.services.quiz.question_gen_agent"
                ] = fake_module

                with patch.object(
                    question_gen_service,
                    "_get_llm",
                    side_effect=AssertionError(
                        "legacy LLM/template fallback must not run"
                    ),
                ):
                    result = question_gen_service._llm_generate(segment)

                self.assertEqual(
                    result,
                    [{"_question_generation_failure": reason}],
                )
                self.assertIsNone(
                    question_gen_service._normalize_question(result[0])
                )
        finally:
            if original_module is None:
                sys.modules.pop(
                    "app.services.quiz.question_gen_agent", None
                )
            else:
                sys.modules[
                    "app.services.quiz.question_gen_agent"
                ] = original_module

    def test_failed_generation_sets_failed_and_never_persists(self):
        document = SimpleNamespace(
            id="document-1",
            zone="study",
            segment_status="completed",
            question_gen_status="not_started",
        )
        segment = SimpleNamespace(
            id="segment-1",
            title="第一章",
            content="真实资料内容",
        )

        for reason in (
            "agent_unavailable",
            "llm_timeout",
            "llm_error",
            "invalid_output",
        ):
            with self.subTest(reason=reason):
                db = _FlushOnlyDb()
                document.question_gen_status = "not_started"
                with (
                    patch.object(
                        question_gen_service.kb_crud,
                        "get_document_by_id_or_dify",
                        return_value=document,
                    ),
                    patch.object(
                        question_gen_service.segment_crud,
                        "list_segments_for_document",
                        return_value=[segment],
                    ),
                    patch.object(
                        question_gen_service.tag_crud,
                        "list_tags_for_user",
                        return_value=[],
                    ),
                    patch.object(
                        question_gen_service,
                        "_llm_generate",
                        return_value=[
                            {"_question_generation_failure": reason}
                        ],
                    ),
                    patch.object(
                        question_gen_service,
                        "_persist_question",
                        side_effect=AssertionError(
                            "failed generation must not persist"
                        ),
                    ),
                ):
                    response = question_gen_service.generate_questions(
                        db,
                        user_id=1,
                        document_id=document.id,
                    )

                self.assertEqual(response.question_gen_status, "failed")
                self.assertEqual(response.total_questions, 0)
                self.assertEqual(response.questions_created, 0)
                self.assertEqual(response.questions_reused, 0)
                self.assertEqual(document.question_gen_status, "failed")
                self.assertGreaterEqual(db.flush_count, 2)

    def test_provider_exception_sets_failed_and_never_persists(self):
        document = SimpleNamespace(
            id="document-1",
            zone="study",
            segment_status="completed",
            question_gen_status="not_started",
        )
        segment = SimpleNamespace(
            id="segment-1",
            title="第一章",
            content="真实资料内容",
        )
        db = _FlushOnlyDb()

        def timeout_provider(_segment):
            raise TimeoutError("provider timed out")

        with (
            patch.object(
                question_gen_service.kb_crud,
                "get_document_by_id_or_dify",
                return_value=document,
            ),
            patch.object(
                question_gen_service.segment_crud,
                "list_segments_for_document",
                return_value=[segment],
            ),
            patch.object(
                question_gen_service.tag_crud,
                "list_tags_for_user",
                return_value=[],
            ),
            patch.object(
                question_gen_service,
                "_persist_question",
                side_effect=AssertionError(
                    "provider failure must not persist"
                ),
            ),
        ):
            response = question_gen_service.generate_questions(
                db,
                user_id=1,
                document_id=document.id,
                provider=timeout_provider,
            )

        self.assertEqual(response.question_gen_status, "failed")
        self.assertEqual(response.total_questions, 0)
        self.assertEqual(document.question_gen_status, "failed")

    def test_page_batch_discards_failure_marker(self):
        pages = [
            {
                "page_number": 1,
                "title": "第一页",
                "content": "真实资料内容",
            }
        ]
        pairs = question_gen_service.batch_generate_questions(
            pages,
            provider=lambda _page: [
                {"_question_generation_failure": "invalid_output"}
            ],
        )
        self.assertEqual(pairs, [])


if __name__ == "__main__":
    unittest.main()
