"""Stream output formatters. Server uses a formatter only when client requests it (e.g. header X-Response-Format: openwebui)."""

from __future__ import annotations

from typing import Protocol

from digigraph.formatters.neutral import NeutralStreamFormatter
from digigraph.formatters.openwebui import OpenWebUIStreamFormatter

__all__ = ["StreamFormatter", "get_stream_formatter"]


class StreamFormatter(Protocol):
    """Format tool_call and tool_result events for SSE content. Server is independent of presentation."""

    def format_tool_call(self, data: dict) -> str:
        """Return content string for a tool_call event."""
        ...

    def format_tool_result(self, data: dict) -> str:
        """Return content string for a tool_result event."""
        ...

    def format_tool_call_with_result(self, call_data: dict, result_data: dict) -> str:
        """Return one combined block: tool call section with result nested inside (for parallel-call clarity)."""
        ...


def get_stream_formatter(openwebui_format: bool) -> StreamFormatter:
    """Return the formatter to use. openwebui_format=True when client asks for Open WebUI (header or param or model)."""
    if openwebui_format:
        return OpenWebUIStreamFormatter()
    return NeutralStreamFormatter()
