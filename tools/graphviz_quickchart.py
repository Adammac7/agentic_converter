"""
Render Graphviz DOT to SVG via the QuickChart Graphviz HTTP API.

Same DOT text and options always produce the same request payload (deterministic
client behavior). Remote SVG bytes may change if the service or Graphviz
version changes upstream.
"""

from __future__ import annotations

from typing import Literal

import requests

QUICKCHART_GRAPHVIZ_URL = "https://quickchart.io/graphviz"

LayoutName = Literal["dot", "neato", "fdp", "sfdp", "twopi", "circo", "osage", "patchwork"]
OutputFormat = Literal["svg", "png", "jpg", "pdf"]


class GraphvizRenderError(Exception):
    """Raised when the QuickChart Graphviz API returns an error or invalid body."""

    def __init__(self, message: str, *, status_code: int | None = None, body: str | None = None):
        super().__init__(message)
        self.status_code = status_code
        self.body = body


def normalize_dot(dot_source: str) -> str:
    """
    Normalize DOT text for stable requests: Unix newlines, no leading/trailing
    outer whitespace on the whole graph.
    """
    text = dot_source.replace("\r\n", "\n").replace("\r", "\n")
    return text.strip()


def _validated_graph(dot_source: str) -> str:
    """Return normalized DOT or raise on invalid input."""
    if not isinstance(dot_source, str):
        raise TypeError(f"dot_source must be str, got {type(dot_source).__name__}")
    graph = normalize_dot(dot_source)
    if not graph:
        raise ValueError("DOT source is empty or whitespace only")
    return graph


def _check_timeout(timeout_sec: float) -> None:
    if isinstance(timeout_sec, bool) or not isinstance(timeout_sec, (int, float)):
        raise TypeError("timeout_sec must be a number")
    if timeout_sec <= 0:
        raise ValueError("timeout_sec must be positive")


def render_dot(
    dot_source: str,
    *,
    layout: LayoutName = "dot",
    format: OutputFormat = "svg",
    timeout_sec: float = 60.0,
) -> str:
    """
    POST DOT source to QuickChart and return the rendered payload as text.

    For ``format="svg"`` the response body is XML/SVG. For raster formats,
    the response may be binary; use ``render_dot_bytes`` instead.

    Raises:
        TypeError: if ``dot_source`` is not a string.
        ValueError: if DOT is empty/whitespace-only or ``timeout_sec`` is invalid.
        GraphvizRenderError: on network failure, HTTP error, decode error, or invalid body.
    """
    graph = _validated_graph(dot_source)
    _check_timeout(timeout_sec)
    body = {"graph": graph, "layout": layout, "format": format}
    try:
        r = requests.post(
            QUICKCHART_GRAPHVIZ_URL,
            json=body,
            timeout=timeout_sec,
        )
    except requests.RequestException as e:
        raise GraphvizRenderError(f"Graphviz request failed: {e}") from e

    if not r.content:
        raise GraphvizRenderError(
            "Empty response from Graphviz API",
            status_code=r.status_code,
            body=None,
        )

    try:
        text = r.content.decode("utf-8-sig")
    except UnicodeDecodeError as e:
        raise GraphvizRenderError(
            f"Graphviz response is not valid UTF-8: {e}",
            status_code=r.status_code,
            body=None,
        ) from e

    if not r.ok:
        raise GraphvizRenderError(
            f"Graphviz API error: HTTP {r.status_code}",
            status_code=r.status_code,
            body=text[:2000] if text else None,
        )
    stripped = text.lstrip()
    if not stripped or not stripped.startswith("<"):
        # SVG / XML should start with '<'; catch obvious API error JSON/text
        raise GraphvizRenderError(
            "Unexpected Graphviz response (expected SVG/XML markup)",
            status_code=r.status_code,
            body=text[:2000] if text else None,
        )
    return text


def render_dot_to_svg(
    dot_source: str,
    *,
    layout: LayoutName = "dot",
    timeout_sec: float = 60.0,
) -> str:
    """Convenience wrapper: DOT → SVG string (same as ``render_dot`` with ``format=\"svg\"``)."""
    return render_dot(dot_source, layout=layout, format="svg", timeout_sec=timeout_sec)


def render_dot_bytes(
    dot_source: str,
    *,
    layout: LayoutName = "dot",
    format: OutputFormat = "png",
    timeout_sec: float = 60.0,
) -> bytes:
    """
    Return raw response bytes (use for PNG/JPG/PDF).

    Raises:
        TypeError / ValueError: same input rules as :func:`render_dot`.
        GraphvizRenderError: on network failure, HTTP error, or empty body on success.
    """
    graph = _validated_graph(dot_source)
    _check_timeout(timeout_sec)
    body = {"graph": graph, "layout": layout, "format": format}
    try:
        r = requests.post(
            QUICKCHART_GRAPHVIZ_URL,
            json=body,
            timeout=timeout_sec,
        )
    except requests.RequestException as e:
        raise GraphvizRenderError(f"Graphviz request failed: {e}") from e

    if not r.ok:
        err_text = r.text[:2000] if r.text else None
        raise GraphvizRenderError(
            f"Graphviz API error: HTTP {r.status_code}",
            status_code=r.status_code,
            body=err_text,
        )

    if not r.content:
        raise GraphvizRenderError(
            "Empty response body from Graphviz API",
            status_code=r.status_code,
            body=None,
        )
    return r.content
