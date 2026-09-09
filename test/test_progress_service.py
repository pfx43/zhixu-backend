"""第四期进度服务纯函数测试（不依赖数据库）。"""
from app.services.training import progress_service


def test_accuracy_none_when_no_graded():
    assert progress_service._accuracy(0, 0) is None
    assert progress_service._accuracy(0, 5) == 0
    assert progress_service._accuracy(3, 1) == 75
    assert progress_service._accuracy(2, 2) == 50


def test_counts_from_stats_empty():
    out = progress_service._counts_from_stats([], {})
    assert out == {"answered": 0, "correct": 0, "wrong": 0, "unknown": 0}


def test_counts_from_stats_aggregates():
    question_ids = ["q1", "q2", "q3", "q4", "q5"]
    stats_map = {
        "q1": ("correct", 2),
        "q2": ("wrong", 1),
        "q3": ("unknown", 3),
        "q4": ("correct", 1),
        "q5": (None, 0),  # 未作答
    }
    out = progress_service._counts_from_stats(question_ids, stats_map)
    assert out["answered"] == 4
    assert out["correct"] == 2
    assert out["wrong"] == 1
    assert out["unknown"] == 1


def test_pick_current_chapter_last_practiced():
    from app.schemas.progress import ChapterProgressOut

    chapters = [
        ChapterProgressOut(
            order_index=0, title="一", page_start=1, page_end=4,
            question_count=3, answered_count=3, accuracy_rate=80,
        ),
        ChapterProgressOut(
            order_index=1, title="二", page_start=5, page_end=10,
            question_count=2, answered_count=1, accuracy_rate=50,
        ),
        ChapterProgressOut(
            order_index=2, title="三", page_start=11, page_end=20,
            question_count=0, answered_count=0,
        ),
    ]
    cur = progress_service._pick_current_chapter(chapters)
    assert cur and cur.title == "二"
    nxt = progress_service._pick_document_next(chapters)
    assert nxt and nxt.action == "generate" and nxt.title == "三"


def test_pick_document_next_weak_chapter():
    from app.schemas.progress import ChapterProgressOut

    chapters = [
        ChapterProgressOut(
            order_index=0, title="一", page_start=1, page_end=4,
            question_count=4, answered_count=4, accuracy_rate=40,
        ),
        ChapterProgressOut(
            order_index=1, title="二", page_start=5, page_end=10,
            question_count=2, answered_count=2, accuracy_rate=90,
        ),
    ]
    nxt = progress_service._pick_document_next(chapters)
    assert nxt and nxt.title == "一" and nxt.action == "quiz"
    assert nxt.reason == "这一章还需要巩固"