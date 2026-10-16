"""Neutral stream formatter: minimal text, no UI-specific markup. Default when client does not request Open WebUI format."""

from __future__ import annotations

import json


class NeutralStreamFormatter:
    """Format tool_call and tool_result as plain text/JSON. No <details>, no markdown tables."""

    def format_tool_call(self, data: dict) -> str:
        name = (data.get("name") or data.get("index_name") or "tool").strip()
        args = data.get("arguments") or {}
        return f"Tool: {name}\n```json\n{json.dumps(args, indent=2)}\n```\n\n"

    def format_tool_result(self, data: dict) -> str:
        results = data.get("results")
        dataset_ref = data.get("dataset_ref")
        if isinstance(results, list):
            out = json.dumps(results, indent=2, default=str)
            if dataset_ref:
                out = f"Stored at: {dataset_ref}\n\n" + out
            return out
        content = data.get("content", "")
        if isinstance(content, str):
            return content
        return json.dumps(data, indent=2, default=str)

    def format_tool_call_with_result(self, call_data: dict, result_data: dict) -> str:
        """Single block: tool call content then result content (no separate sections)."""
        return (
            self.format_tool_call(call_data).rstrip()
            + "\n\n"
            + self.format_tool_result(result_data)
        )
