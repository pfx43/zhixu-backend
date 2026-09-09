"""按页出题数量：省略时由 Agent 自定，最多 3 道；入库 0 表示自定。"""
from typing import Optional

MAX_QUESTIONS_PER_PAGE = 3


def persist_questions_per_page(value: Optional[int]) -> int:
    """写入 job 表：0 = Agent 自定，1–3 = 固定道数。"""
    if value is None or value <= 0:
        return 0
    return min(MAX_QUESTIONS_PER_PAGE, max(1, int(value)))


def questions_per_page_cap(value: Optional[int]) -> int:
    persisted = persist_questions_per_page(value)
    return MAX_QUESTIONS_PER_PAGE if persisted == 0 else persisted


def count_instruction(count: Optional[int], *, tool: bool = False) -> str:
    submit = "，逐题调用 submit_question 提交" if tool else "，覆盖本页核心知识点"
    persisted = persist_questions_per_page(count)
    if persisted > 0:
        return f"请生成 {persisted} 道练习题{submit}。"
    return (
        f"请根据本页内容自行决定出题数量（1～{MAX_QUESTIONS_PER_PAGE} 道）{submit}。"
        "内容少就少出，不要固定只出 1 道。"
    )
