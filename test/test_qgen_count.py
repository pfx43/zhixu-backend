from app.schemas.page import PageGenerateRequest
from app.services.quiz.qgen_count import (
    MAX_QUESTIONS_PER_PAGE,
    count_instruction,
    persist_questions_per_page,
    questions_per_page_cap,
)


def test_omit_questions_per_page_lets_agent_decide():
    req = PageGenerateRequest(document_id="d1", page_numbers=[1])
    assert req.questions_per_page is None
    assert persist_questions_per_page(req.questions_per_page) == 0
    assert questions_per_page_cap(req.questions_per_page) == MAX_QUESTIONS_PER_PAGE
    text = count_instruction(req.questions_per_page, tool=True)
    assert "自行决定" in text
    assert "不要固定只出 1 道" in text


def test_explicit_count_is_capped_and_worded():
    assert persist_questions_per_page(2) == 2
    assert questions_per_page_cap(2) == 2
    assert persist_questions_per_page(9) == MAX_QUESTIONS_PER_PAGE
    assert "请生成 2 道" in count_instruction(2, tool=True)
