"""Unit tests for tools.graphviz_quickchart (HTTP calls mocked)."""

from unittest.mock import MagicMock, patch

import pytest

from tools.graphviz_quickchart import (
    GraphvizRenderError,
    normalize_dot,
    render_dot,
    render_dot_bytes,
    render_dot_to_svg,
)


def test_normalize_dot_unifies_newlines_and_strips():
    assert normalize_dot("  digraph x { a -> b }\n\r\n  ") == "digraph x { a -> b }"


def test_render_dot_rejects_empty_dot():
    with pytest.raises(ValueError, match="empty"):
        render_dot("   \n  ")


def test_render_dot_rejects_non_string():
    with pytest.raises(TypeError, match="str"):
        render_dot(None)  # type: ignore[arg-type]


def test_render_dot_rejects_invalid_timeout():
    with pytest.raises(ValueError, match="positive"):
        render_dot("digraph G { }", timeout_sec=0)


def test_render_dot_success_returns_svg_text():
    mock_resp = MagicMock()
    mock_resp.content = b"<svg xmlns=\"http://www.w3.org/2000/svg\"></svg>"
    mock_resp.ok = True
    mock_resp.status_code = 200

    with patch("tools.graphviz_quickchart.requests.post", return_value=mock_resp) as post:
        out = render_dot('digraph G { a -> b }')

    assert out.startswith("<")
    post.assert_called_once()
    call_kw = post.call_args.kwargs
    assert call_kw["json"]["layout"] == "dot"
    assert call_kw["json"]["format"] == "svg"
    assert "digraph G" in call_kw["json"]["graph"]


def test_render_dot_to_svg_delegates_to_render_dot():
    mock_resp = MagicMock()
    mock_resp.content = b"<svg></svg>"
    mock_resp.ok = True
    mock_resp.status_code = 200

    with patch("tools.graphviz_quickchart.requests.post", return_value=mock_resp):
        out = render_dot_to_svg("digraph G { }")

    assert out.startswith("<")


def test_render_dot_http_error_raises_with_body():
    mock_resp = MagicMock()
    mock_resp.content = b'{"error":"bad graph"}'
    mock_resp.ok = False
    mock_resp.status_code = 400

    with patch("tools.graphviz_quickchart.requests.post", return_value=mock_resp):
        with pytest.raises(GraphvizRenderError) as exc_info:
            render_dot("digraph G { }")

    err = exc_info.value
    assert err.status_code == 400
    assert err.body is not None


def test_render_dot_empty_response_raises():
    mock_resp = MagicMock()
    mock_resp.content = b""
    mock_resp.ok = True
    mock_resp.status_code = 200

    with patch("tools.graphviz_quickchart.requests.post", return_value=mock_resp):
        with pytest.raises(GraphvizRenderError, match="Empty response"):
            render_dot("digraph G { }")


def test_render_dot_non_xml_success_body_raises():
    mock_resp = MagicMock()
    mock_resp.content = b"not svg"
    mock_resp.ok = True
    mock_resp.status_code = 200

    with patch("tools.graphviz_quickchart.requests.post", return_value=mock_resp):
        with pytest.raises(GraphvizRenderError, match="Unexpected"):
            render_dot("digraph G { }")


def test_render_dot_request_exception_wrapped():
    import requests

    with patch("tools.graphviz_quickchart.requests.post", side_effect=requests.ConnectionError("boom")):
        with pytest.raises(GraphvizRenderError, match="Graphviz request failed"):
            render_dot("digraph G { }")


def test_render_dot_bytes_success():
    mock_resp = MagicMock()
    mock_resp.content = b"\x89PNG\r\n\x1a\n"
    mock_resp.ok = True
    mock_resp.status_code = 200
    mock_resp.text = ""

    with patch("tools.graphviz_quickchart.requests.post", return_value=mock_resp):
        data = render_dot_bytes("digraph G { }", format="png")

    assert data == mock_resp.content


def test_render_dot_bytes_http_error():
    mock_resp = MagicMock()
    mock_resp.content = b""
    mock_resp.ok = False
    mock_resp.status_code = 503
    mock_resp.text = "unavailable"

    with patch("tools.graphviz_quickchart.requests.post", return_value=mock_resp):
        with pytest.raises(GraphvizRenderError) as exc_info:
            render_dot_bytes("digraph G { }")

    assert exc_info.value.status_code == 503


def test_render_dot_bytes_empty_body_on_success_raises():
    mock_resp = MagicMock()
    mock_resp.content = b""
    mock_resp.ok = True
    mock_resp.status_code = 200

    with patch("tools.graphviz_quickchart.requests.post", return_value=mock_resp):
        with pytest.raises(GraphvizRenderError, match="Empty response body"):
            render_dot_bytes("digraph G { }", format="png")
