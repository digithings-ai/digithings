"""One-off smoke: probe xAI Agent Tools `x_search` + discover AI-portfolio X accounts (#658).

Two jobs: (1) validate the x_search Responses-API tool shape / response+citation fields,
and (2) ask Grok (live X access) to enumerate active AI-run stock-portfolio accounts on X
with @handles, what they post, and activity — a verified shortlist for approval before
wiring `alt-ai-portfolios`. Throwaway; run via the xai-xsearch-smoke workflow (needs
XAI_API_KEY). Not imported by runtime code.
"""

from __future__ import annotations

import json
import os
import sys
from typing import Any

DISCOVERY_PROMPT = (
    "List the most active accounts on X that are AI-run or AI-driven investment "
    "portfolios posting STOCK/equity analysis and live holdings (e.g. accounts framed as "
    "a Claude / ChatGPT / Grok / DeepSeek / Gemini managed portfolio, 'AI hedge fund' "
    "experiments, or model-vs-model stock-picking trackers). For each, give: the exact "
    "@handle, which AI model/family it represents, what it posts (picks? full portfolio? "
    "P&L?), rough follower count, and how recently it posted. Prefer accounts that name "
    "individual tickers. Only list real accounts you can find on X; cite them."
)


def _dump(label: str, obj: Any) -> None:
    print(f"\n===== {label} =====", flush=True)
    md = getattr(obj, "model_dump", None)
    if callable(md):
        try:
            print(json.dumps(md(), indent=2, default=str)[:7000], flush=True)
            return
        except Exception as exc:  # noqa: BLE001
            print(f"(model_dump failed: {exc})", flush=True)
    print(repr(obj)[:3000], flush=True)


def _summary(label: str, r: Any) -> None:
    print(f"\n##### {label}: OK #####", flush=True)
    for attr in ("output_text", "citations", "output", "status"):
        print(f"  has .{attr}: {hasattr(r, attr)}", flush=True)
    print("  output_text:\n", (getattr(r, "output_text", "") or "")[:2500], flush=True)
    print("  citations:", repr(getattr(r, "citations", None))[:1500], flush=True)


def main() -> int:
    key = os.environ.get("XAI_API_KEY", "").strip()
    if not key:
        print("XAI_API_KEY not set", file=sys.stderr)
        return 1
    from openai import OpenAI

    client = OpenAI(base_url="https://api.x.ai/v1", api_key=key)
    model = os.environ.get("XAI_SMOKE_MODEL", "grok-4.3")
    print(f"model={model}", flush=True)

    # A — x_search tool (probe shape) + discovery
    try:
        r = client.responses.create(
            model=model,
            input=[{"role": "user", "content": DISCOVERY_PROMPT}],
            tools=[{"type": "x_search"}],
        )
        _summary("A x_search", r)
        _dump("A full response (head)", r)
    except Exception as exc:  # noqa: BLE001
        print(
            f"\nA x_search FAILED: {type(exc).__name__} "
            f"status={getattr(exc, 'status_code', '')} {str(exc)[:600]}",
            flush=True,
        )

    # B — fallback: web_search restricted to x.com (in case x_search type differs)
    try:
        r = client.responses.create(
            model=model,
            input=[{"role": "user", "content": DISCOVERY_PROMPT}],
            tools=[{"type": "web_search", "filters": {"allowed_domains": ["x.com"]}}],
        )
        _summary("B web_search@x.com", r)
    except Exception as exc:  # noqa: BLE001
        print(
            f"\nB web_search@x.com FAILED: {type(exc).__name__} "
            f"status={getattr(exc, 'status_code', '')} {str(exc)[:600]}",
            flush=True,
        )

    # C — baseline: no tools (Grok's native X knowledge), for comparison
    try:
        r = client.responses.create(
            model=model,
            input=[{"role": "user", "content": DISCOVERY_PROMPT}],
        )
        _summary("C no-tools baseline", r)
    except Exception as exc:  # noqa: BLE001
        print(f"\nC no-tools FAILED: {type(exc).__name__} {str(exc)[:400]}", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
