"""One-off smoke: probe xAI Agent Tools `web_search` via the Responses API (#650).

Captures the real response/citation shape and whether `web_search` coexists with a
client-defined function tool, to drive the grounding-pre-pass migration. Throwaway —
run via the `xai-websearch-smoke` workflow (needs XAI_API_KEY). Not imported anywhere.
"""

from __future__ import annotations

import json
import os
import sys
from typing import Any


def _dump(label: str, obj: Any) -> None:
    print(f"\n===== {label} =====", flush=True)
    md = getattr(obj, "model_dump", None)
    if callable(md):
        try:
            print(json.dumps(md(), indent=2, default=str)[:6000], flush=True)
            return
        except Exception as exc:  # noqa: BLE001
            print(f"(model_dump failed: {exc})", flush=True)
    print(repr(obj)[:3000], flush=True)


def main() -> int:
    key = os.environ.get("XAI_API_KEY", "").strip()
    if not key:
        print("XAI_API_KEY not set", file=sys.stderr)
        return 1
    from openai import OpenAI

    client = OpenAI(base_url="https://api.x.ai/v1", api_key=key)
    model = os.environ.get("XAI_SMOKE_MODEL", "grok-4.3")
    print(f"model={model}", flush=True)

    # A — web_search alone
    try:
        r = client.responses.create(
            model=model,
            input=[
                {
                    "role": "user",
                    "content": "In two sentences, what were the most recent US CPI print and "
                    "Fed rate decision? Cite sources.",
                }
            ],
            tools=[{"type": "web_search"}],
        )
        print("A web_search ALONE: OK", flush=True)
        for attr in ("output_text", "citations", "output", "status", "usage"):
            print(f"  has .{attr}: {hasattr(r, attr)}", flush=True)
        print("  output_text:", repr(getattr(r, "output_text", None))[:600], flush=True)
        print("  citations:", repr(getattr(r, "citations", None))[:1200], flush=True)
        _dump("A full response", r)
    except Exception as exc:  # noqa: BLE001
        print(
            f"A web_search ALONE FAILED: {type(exc).__name__} "
            f"status={getattr(exc, 'status_code', '')} {str(exc)[:600]}",
            flush=True,
        )

    # B — web_search + a client function tool (coexistence test, Responses flat shape)
    fn_tool = {
        "type": "function",
        "name": "get_price",
        "description": "Return a stock price for a ticker.",
        "parameters": {
            "type": "object",
            "properties": {"ticker": {"type": "string"}},
            "required": ["ticker"],
        },
    }
    try:
        r = client.responses.create(
            model=model,
            input=[
                {
                    "role": "user",
                    "content": "Search the web for today's SPY headline; then call get_price "
                    "for SPY if useful.",
                }
            ],
            tools=[{"type": "web_search"}, fn_tool],
        )
        print("\nB web_search + FUNCTION tool: OK (coexist)", flush=True)
        _dump("B full response", r)
    except Exception as exc:  # noqa: BLE001
        print(
            f"\nB web_search + FUNCTION tool FAILED: {type(exc).__name__} "
            f"status={getattr(exc, 'status_code', '')} {str(exc)[:600]}",
            flush=True,
        )

    # C — web_search with allowed_domains filter
    try:
        r = client.responses.create(
            model=model,
            input=[{"role": "user", "content": "Latest Reuters market headline, one sentence, cite."}],
            tools=[{"type": "web_search", "filters": {"allowed_domains": ["reuters.com"]}}],
        )
        print("\nC web_search allowed_domains filter: OK", flush=True)
        print("  citations:", repr(getattr(r, "citations", None))[:800], flush=True)
    except Exception as exc:  # noqa: BLE001
        print(
            f"\nC allowed_domains FAILED: {type(exc).__name__} "
            f"status={getattr(exc, 'status_code', '')} {str(exc)[:600]}",
            flush=True,
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
