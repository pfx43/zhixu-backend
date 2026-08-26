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