"""Open WebUI stream formatter: <details> blocks and markdown tables. Use when client sends X-Response-Format: openwebui (or model sitaas-rag, etc.)."""

from __future__ import annotations

import base64
import json
import re
from pathlib import Path

from tabulate import tabulate

from digigraph.orchestration import builtin  # noqa: F401 - register built-in tools
from digigraph.orchestration import list_tool_names

_DELEGATE_TOOL_NAMES = frozenset(list_tool_names(tag="delegate"))

# Display limits for search result table (full data is stored; UI shows a preview)
MAX_TABLE_ROWS = 5
MAX_CELL_CHARS = 80


def _cell_safe(v: object, max_chars: int | None = None) -> str:
    """One-line, pipe-safe cell for markdown table. Newlines → space; pipe escaped. Optionally truncate to max_chars."""
    if v is None:
        return ""
    s = str(v).strip()
    s = re.sub(r"[\r\n\t\u2028\u2029]+", " ", s)
    s = s.replace("|", "\\|")
    if max_chars is not None and len(s) > max_chars:
        s = s[: max_chars - 1].rstrip() + "…"
    return s


def _results_to_markdown_table(results: list[dict]) -> str:
    """Format raw DigiSearch-style results as markdown table: all columns, top MAX_TABLE_ROWS rows, cells truncated to MAX_CELL_CHARS."""
    if not results:
        return "No results."
    all_keys: set[str] = set()
    for r in results:
        for k in (r.get("metadata") or {}).keys():
            if not k.startswith("@"):
                all_keys.add(k)
    meta_cols = sorted(all_keys)
    headers = ["Rank", "Score", "doc_id"] + meta_cols + ["Content"]
    safe_headers = [_cell_safe(h) for h in headers]
    rows: list[list[str]] = []
    for i, r in enumerate(results[:MAX_TABLE_ROWS], 1):
        score = r.get("score", 0)
        score_str = f"{score:.2f}" if isinstance(score, (int, float)) else str(score)
        doc_id = _cell_safe(r.get("doc_id", ""), MAX_CELL_CHARS)
        meta = r.get("metadata") or {}
        content = _cell_safe(r.get("content", ""), MAX_CELL_CHARS)
        cells: list[str] = [str(i), score_str, doc_id]
        cells.extend(_cell_safe(meta.get(k), MAX_CELL_CHARS) for k in meta_cols)
        cells.append(content)
        rows.append(cells)
    table = tabulate(rows, headers=safe_headers, tablefmt="github")
    if len(results) > MAX_TABLE_ROWS:
        table += f"\n\n*Showing top {MAX_TABLE_ROWS} of {len(results)} results. Full data is stored for analytics.*"
    return table


def _legacy_content_to_markdown_table(content: str) -> str:
    """Convert legacy [1] (score=0.5) content lines to markdown table. Top 5 rows, cells truncated."""
    lines = content.strip().split("\n")
    if not lines:
        return content
    rows: list[list[str]] = []
    for line in lines[:MAX_TABLE_ROWS]:
        m = re.match(r"\s*\[(\d+)\]\s*\(score=([\d.]+)\)\s*(.*)", line)
        if m:
            rows.append([m.group(1), m.group(2), _cell_safe(m.group(3).strip(), MAX_CELL_CHARS)])
    if not rows:
        return content
    return tabulate(rows, headers=["Rank", "Score", "Content"], tablefmt="github")


def _image_to_base64_markdown(image_path: str, alt: str = "Chart") -> str:
    """Read image from path, base64-encode, return markdown image. On failure return plain text."""
    try:
        p = Path(image_path)
        if not p.is_file():
            return f"Image: {image_path}"
        raw = p.read_bytes()
        b64 = base64.b64encode(raw).decode("ascii")
        ext = p.suffix.lower()
        if ext == ".svg":
            mime = "image/svg+xml"
        elif ext == ".png":
            mime = "image/png"
        elif ext in (".jpg", ".jpeg"):
            mime = "image/jpeg"
        else:
            mime = "image/png"
        return f'![{alt}](data:{mime};base64,{b64})'
    except Exception:
        return f"Image: {image_path}"


def _matrix_to_markdown(matrix: dict) -> str:
    """Render correlation-style dict of dict as markdown table (rows/cols = column names)."""
    if not matrix:
        return ""
    cols = sorted(matrix.keys())
    headers = [""] + cols
    rows: list[list[str]] = []
    for r in cols:
        row = [r]
        for c in cols:
            v = matrix.get(r, {}).get(c) if isinstance(matrix.get(r), dict) else None
            row.append(f"{v:.3f}" if isinstance(v, (int, float)) else str(v) if v is not None else "")
        rows.append(row)
    return tabulate(rows, headers=headers, tablefmt="github")


def _table_from_rows(rows: list[dict], columns: list[str] | None = None) -> str:
    """Convert list of dicts to markdown table; top MAX_TABLE_ROWS, MAX_CELL_CHARS per cell."""
    if not rows:
        return "No rows."
    cols = columns or list(rows[0].keys()) if rows else []
    safe_headers = [_cell_safe(h) for h in cols]
    out_rows: list[list[str]] = []
    for r in rows[:MAX_TABLE_ROWS]:
        out_rows.append([_cell_safe(r.get(c), MAX_CELL_CHARS) for c in cols])
    body = tabulate(out_rows, headers=safe_headers, tablefmt="github")
    if len(rows) > MAX_TABLE_ROWS:
        body += f"\n\n*Showing top {MAX_TABLE_ROWS} of {len(rows)} rows.*"
    return body


def _stats_to_markdown(stats: dict) -> str:
    """Render stats dict (column -> {mean, median, ...}) as compact markdown table (stats as rows)."""
    if not stats:
        return ""
    stat_names = ["mean", "median", "std", "min", "max", "null_count"]
    headers = ["Stat"] + [c for c in stats.keys()]
    rows: list[list[str]] = []
    for sn in stat_names:
        row = [sn]
        for col, s in stats.items():
            if isinstance(s, dict) and sn in s:
                v = s[sn]
                row.append(f"{v:.4f}" if isinstance(v, (int, float)) else str(v))
            else:
                row.append("")
        if any(c for c in row[1:]):
            rows.append(row)
    return tabulate(rows, headers=headers, tablefmt="github") if rows else ""


def _format_delegate_result(parsed: dict) -> tuple[str, str]:
    """Format parsed delegate-tool JSON as (summary_line, body_markdown)."""
    err = parsed.get("error")
    if err:
        summary = "Error"
        body = f"> **Error:** {_cell_safe(err)}"
        return summary, body

    parts: list[str] = []
    summary_parts: list[str] = []

    if parsed.get("image_path"):
        img_md = _image_to_base64_markdown(parsed["image_path"], "Chart")
        parts.append(img_md)
        summary_parts.append("Plot")

    if parsed.get("echarts_option") and isinstance(parsed["echarts_option"], dict):
        if not parsed.get("image_path"):
            data_summary = parsed.get("data_summary") or {}
            parts.append(
                "**ECharts chart.** Use `echarts_option` in the response with `echarts.init(dom).setOption(echarts_option)` to render."
                + (f" ({data_summary.get('points', data_summary.get('n', ''))} points)" if data_summary else "")
            )
        summary_parts.append("ECharts")

    if parsed.get("mermaid_source"):
        src = (parsed["mermaid_source"] or "").strip()
        if src:
            parts.append("```mermaid\n" + src + "\n```")
            summary_parts.append("Mermaid diagram")

    if "table" in parsed and isinstance(parsed["table"], list):
        cols = parsed.get("columns")
        if isinstance(cols, list):
            cols = [str(c) for c in cols]
        else:
            cols = list(parsed["table"][0].keys()) if parsed["table"] else []
        parts.append(_table_from_rows(parsed["table"], cols))
        summary_parts.append("table")

    if "matrix" in parsed and isinstance(parsed["matrix"], dict):
        parts.append(_matrix_to_markdown(parsed["matrix"]))
        summary_parts.append("correlation matrix")

    if "stats" in parsed and isinstance(parsed["stats"], dict):
        parts.append(_stats_to_markdown(parsed["stats"]))
        summary_parts.append("summary stats")

    if "equation" in parsed and parsed["equation"]:
        parts.append(f"**Equation:** `{_cell_safe(parsed['equation'])}`")
    if "summary" in parsed and parsed["summary"]:
        s = parsed["summary"]
        if isinstance(s, dict):
            parts.append("**Summary:** " + ", ".join(f"{k}={v}" for k, v in s.items()))
        else:
            parts.append(f"**Summary:** {_cell_safe(s)}")
    if "pairs" in parsed and isinstance(parsed["pairs"], list) and parsed["pairs"]:
        pairs = parsed["pairs"][:MAX_TABLE_ROWS]
        if isinstance(pairs[0], dict):
            parts.append(_table_from_rows(pairs))
        else:
            parts.append("\n".join(f"- {_cell_safe(p, MAX_CELL_CHARS)}" for p in pairs))
        summary_parts.append("pairs")
    if parsed.get("path") and parsed.get("rows") is not None:
        msg = f"Exported **{parsed['rows']}** rows to `{_cell_safe(parsed['path'])}`."
        if parsed.get("download_url"):
            fmt = (parsed.get("format") or "file").upper()
            msg += f" [Download {fmt}]({parsed['download_url']})"
        parts.append(msg)
        summary_parts.append(f"Exported {parsed['rows']} rows")
    if parsed.get("dataset_ref") and parsed.get("rows") is not None:
        parts.append(f"Filtered/sampled to **{parsed['rows']}** rows; `dataset_ref` for downstream.")
        summary_parts.append(f"{parsed['rows']} rows")
    if "graph" in parsed and parsed["graph"]:
        g = parsed["graph"]
        if isinstance(g, dict):
            nodes = g.get("nodes", [])
            edges = g.get("edges", [])
            parts.append(f"Graph: {len(nodes)} nodes, {len(edges)} edges.")
        summary_parts.append("graph")
    if "slope" in parsed and parsed.get("slope") is not None:
        parts.append(f"**Equation:** `{_cell_safe(parsed.get('equation', ''))}` (R² = {parsed.get('r_squared', '')})")
        summary_parts.append("regression")

    extra_lines: list[str] = []
    if parsed.get("path"):
        extra_lines.append(f"path: {_cell_safe(parsed['path'])}")
    if parsed.get("dataset_ref"):
        extra_lines.append(f"dataset_ref: {_cell_safe(parsed['dataset_ref'])}")
    if parsed.get("image_path"):
        extra_lines.append(f"image_path: {_cell_safe(parsed['image_path'])}")
    if parsed.get("echarts_option"):
        extra_lines.append("echarts_option: (use in frontend with echarts.setOption)")
    if parsed.get("download_url"):
        extra_lines.append(f"download_url: {parsed['download_url']}")
    if extra_lines:
        parts.append("<details>\n<summary>Details</summary>\n\n" + "\n".join(extra_lines) + "\n\n</details>")

    summary = summary_parts[0] if summary_parts else "Result"
    body = "\n\n".join(parts) if parts else "No content."
    return summary, body


class OpenWebUIStreamFormatter:
    """Format tool_call and tool_result for Open WebUI: <details> with summary, markdown tables."""

    def format_tool_call(self, data: dict) -> str:
        name = (data.get("index_name") or data.get("name") or "digisearch").strip()
        summary = f"Tool call: {name}"
        args = data.get("arguments") or {}
        params_json = json.dumps(args, indent=2)
        params_json = params_json.replace("<", "&lt;").replace(">", "&gt;").replace("&", "&amp;")
        return (
            "<details>\n"
            + f"<summary>{summary}</summary>\n\n"
            + "```json\n"
            + params_json
            + "\n```\n\n"
            + "</details>\n\n"
        )

    def format_tool_call_with_result(self, call_data: dict, result_data: dict) -> str:
        """Single block: tool call with result nested inside."""
        name = (call_data.get("index_name") or call_data.get("name") or "digisearch").strip()
        summary = f"Tool call: {name}"
        args = call_data.get("arguments") or {}
        params_json = json.dumps(args, indent=2)
        params_json = params_json.replace("<", "&lt;").replace(">", "&gt;").replace("&", "&amp;")
        result_block = self.format_tool_result(result_data)
        return (
            "<details>\n"
            + f"<summary>{summary}</summary>\n\n"
            + "```json\n"
            + params_json
            + "\n```\n\n"
            + result_block
            + "\n</details>\n\n"
        )

    def format_tool_result(self, data: dict) -> str:
        name = data.get("name")
        results = data.get("results")

        if name in _DELEGATE_TOOL_NAMES:
            content = (data.get("content") or "").strip()
            if not content:
                body = "| Message |\n| --- |\n| No results. |"
            else:
                try:
                    parsed = json.loads(content)
                    _, body = _format_delegate_result(parsed)
                except (json.JSONDecodeError, TypeError):
                    body = content
            return "<details>\n<summary>Result</summary>\n\n" + body + "\n\n</details>\n\n"

        if isinstance(results, list):
            if not results:
                body = "| Message |\n| --- |\n| No results. |"
            else:
                body = _results_to_markdown_table(results)
            extra_parts: list[str] = []
            dataset_ref = data.get("dataset_ref")
            if dataset_ref:
                extra_parts.append(f"dataset_ref: {_cell_safe(dataset_ref)}")
            if extra_parts:
                body += "\n\n<details>\n<summary>Details</summary>\n\n" + "\n".join(extra_parts) + "\n\n</details>"
            return "<details>\n<summary>Result</summary>\n\n" + body + "\n\n</details>\n\n"

        content = (data.get("content") or "").strip()
        if not content:
            body = "| Message |\n| --- |\n| No results. |"
        elif "No results found" in content or content == "No results found.":
            body = "| Message |\n| --- |\n| No results found. |"
        else:
            body = _legacy_content_to_markdown_table(content)
            if body == content:
                body = content
        return "<details>\n<summary>Result</summary>\n\n" + body + "\n\n</details>\n\n"
