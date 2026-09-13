"""聊天消息 payload.blocks：正文与卡片按出现顺序交错。"""

from __future__ import annotations

from typing import Any, Optional


def append_text_block(blocks: list[dict], text: str) -> None:
    if not text:
        return
    if blocks and blocks[-1].get("type") == "text":
        blocks[-1]["content"] = (blocks[-1].get("content") or "") + text
    else:
        blocks.append({"type": "text", "content": text})


def append_question_block(blocks: list[dict], question: dict) -> None:
    qid = question.get("question_id")
    if qid and any(
        b.get("type") == "question" and (b.get("question") or {}).get("question_id") == qid
        for b in blocks
    ):
        return
    blocks.append({"type": "question", "question": question})


def append_tip_block(blocks: list[dict], tip: dict) -> None:
    tid = tip.get("id")
    if tid and any(b.get("type") == "tip" and (b.get("tip") or {}).get("id") == tid for b in blocks):
        return
    blocks.append({"type": "tip", "tip": tip})


def append_plot_block(blocks: list[dict], plot: dict) -> None:
    pid = plot.get("id")
    if pid and any(b.get("type") == "plot" and (b.get("plot") or {}).get("id") == pid for b in blocks):
        return
    blocks.append({"type": "plot", "plot": plot})


def append_canvas_block(blocks: list[dict], canvas: dict) -> None:
    cid = canvas.get("id")
    if cid and any(b.get("type") == "canvas" and (b.get("canvas") or {}).get("id") == cid for b in blocks):
        return
    blocks.append({"type": "canvas", "canvas": canvas})


def append_onboarding_block(blocks: list[dict], item: dict) -> None:
    kind = item.get("type")
    if kind not in {"goal_card", "docs_card", "done"}:
        return
    if kind == "goal_card":
        goal = item.get("goal")
        if any(
            b.get("type") == "onboarding"
            and (b.get("item") or {}).get("type") == "goal_card"
            and (b.get("item") or {}).get("goal") == goal
            for b in blocks
        ):
            return
    elif any(b.get("type") == "onboarding" and (b.get("item") or {}).get("type") == kind for b in blocks):
        return
    blocks.append({"type": "onboarding", "item": item})


def pack_assistant_payload(
    *,
    blocks: list[dict],
    questions: list[dict],
    tips: list[dict],
    plots: list[dict],
    canvases: list[dict],
    onboarding: list[dict],
) -> Optional[dict[str, Any]]:
    payload: dict[str, Any] = {}
    if blocks:
        payload["blocks"] = blocks
    if questions:
        payload["questions"] = questions
    if tips:
        payload["tips"] = tips
    if plots:
        payload["plots"] = plots
    if canvases:
        payload["canvases"] = canvases
    if onboarding:
        payload["onboarding"] = onboarding
    return payload or None
