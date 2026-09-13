"""画布 HTML 清洗。"""

from app.services.chat.canvas_sanitize import sanitize_canvas_html


def test_sanitize_strips_iframe_and_external_script():
    ok, cleaned = sanitize_canvas_html(
        '<div>ok</div><iframe src="https://evil"></iframe>'
        '<script src="https://cdn.example/x.js"></script>'
        '<script>var x=1</script>'
    )
    assert ok
    assert "iframe" not in cleaned.lower()
    assert "cdn.example" not in cleaned
    assert "var x=1" in cleaned


def test_sanitize_rejects_empty():
    ok, msg = sanitize_canvas_html("   ")
    assert not ok
    assert "空" in msg
