"""payload.blocks 按出现顺序交错。"""

from app.services.chat.chat_blocks import (
    append_canvas_block,
    append_plot_block,
    append_text_block,
    append_tip_block,
    pack_assistant_payload,
)


def test_blocks_interleave_text_and_cards():
    blocks: list[dict] = []
    append_text_block(blocks, "先看这张图：")
    append_plot_block(blocks, {"id": "p1", "expressions": ["sin(x)"]})
    append_text_block(blocks, "再解释一下。")
    append_tip_block(blocks, {"id": "t1", "title": "提示"})
    append_canvas_block(blocks, {"id": "c1", "html": "<svg></svg>"})

    assert [b["type"] for b in blocks] == ["text", "plot", "text", "tip", "canvas"]
    assert blocks[0]["content"] == "先看这张图："
    assert blocks[2]["content"] == "再解释一下。"


def test_append_text_merges_adjacent():
    blocks: list[dict] = []
    append_text_block(blocks, "a")
    append_text_block(blocks, "b")
    assert blocks == [{"type": "text", "content": "ab"}]


def test_pack_assistant_payload_includes_blocks():
    blocks = [{"type": "text", "content": "hi"}, {"type": "plot", "plot": {"id": "p1"}}]
    payload = pack_assistant_payload(
        blocks=blocks,
        questions=[],
        tips=[],
        plots=[{"id": "p1"}],
        canvases=[],
        onboarding=[],
    )
    assert payload is not None
    assert payload["blocks"] == blocks
    assert payload["plots"] == [{"id": "p1"}]
