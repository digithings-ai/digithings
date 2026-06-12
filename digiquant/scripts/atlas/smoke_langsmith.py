"""LangSmith readiness smoke (#687): validate the LANGSMITH_API_KEY secret + tracing.

Three checks, from the actual CI environment:
  1. AUTH — the key authenticates (no 403/401).
  2. TRACING — LANGSMITH_TRACING actually produces run trees (key alone does not).
  3. NESTING — @traceable calls nest under the LangGraph root across parallel node
     threads → one trace per graph invoke (the basis for "3 traces/run", free tier).

Never prints the API key. Dispatch-only; not imported by runtime code.
"""

from __future__ import annotations

import operator
import os
from typing import Annotated, Any, TypedDict


class S(TypedDict, total=False):
    results: Annotated[list, operator.add]


_RECORDS: list[dict[str, Any]] = []


def _auth_ok() -> str | None:
    """Probe each LangSmith region; return the working endpoint or None.

    A 403 on the US endpoint is usually an EU-workspace key. Probing both turns
    'NOT READY, unclear why' into an actionable verdict: which endpoint to set.
    """
    from langsmith import Client

    key = os.environ["LANGSMITH_API_KEY"]
    regions = [
        ("US (default)", "https://api.smith.langchain.com"),
        ("EU", "https://eu.api.smith.langchain.com"),
    ]
    for label, url in regions:
        try:
            list(Client(api_key=key, api_url=url).list_projects(limit=1))
            print(f"AUTH: OK — key accepted on {label} ({url})")
            return url
        except Exception as exc:  # noqa: BLE001
            print(f"AUTH: FAIL on {label} — {type(exc).__name__}: {str(exc)[:120]}")
    return None


def _nesting_ok() -> bool:
    from digigraph.graph.pipeline_builder import NodeSpec, PipelinePhase, build_pipeline
    from digismith.trace import LANGSMITH_SDK_AVAILABLE, traceable

    if not LANGSMITH_SDK_AVAILABLE:
        print("NESTING: FAIL — langsmith SDK not importable")
        return False
    try:
        from langsmith.run_helpers import get_current_run_tree
    except ImportError:
        from langsmith.run_trees import get_current_run_tree  # type: ignore

    @traceable("inner_llm_call")
    def inner(tag: str) -> str:
        rt = get_current_run_tree()
        _RECORDS.append(
            {
                "has_parent": bool(getattr(rt, "parent_run_id", None)) if rt else False,
                "trace_id": str(getattr(rt, "trace_id", None)) if rt else None,
                "rt_seen": rt is not None,
            }
        )
        return tag

    def make_node(name: str):
        def _n(_state: S) -> dict[str, Any]:
            inner(name)
            return {"results": [name]}

        return _n

    phase = PipelinePhase(
        name="fan", nodes=[NodeSpec(name=f"n{i}", run=make_node(f"n{i}")) for i in range(3)]
    )
    g = build_pipeline(S, [phase])

    spans: list[set] = []
    for _ in range(2):
        b = len(_RECORDS)
        g.invoke({"results": []})
        recs = _RECORDS[b:]
        nested = sum(1 for r in recs if r["has_parent"])
        tids = {r["trace_id"] for r in recs}
        print(
            f"  invoke: inner={len(recs)} rt_seen={sum(r['rt_seen'] for r in recs)} "
            f"nested={nested} trace_ids={len(tids)}"
        )
        spans.append(tids)
    try:
        from langchain_core.tracers.langchain import wait_for_all_tracers

        wait_for_all_tracers()
    except Exception:  # noqa: BLE001
        pass

    all_nested = all(r["has_parent"] for r in _RECORDS) and len(_RECORDS) > 0
    one_per_invoke = all(len(t) == 1 for t in spans) and spans[0] != spans[1]
    ok = all_nested and one_per_invoke
    print(
        f"NESTING: {'OK — 1 trace per invoke, no orphaning' if ok else 'FAIL — orphaning/no tracing'}"
    )
    return ok


def main() -> int:
    if not os.environ.get("LANGSMITH_API_KEY"):
        print("FAIL: LANGSMITH_API_KEY not set (secret missing)")
        return 1
    os.environ.setdefault("LANGSMITH_PROJECT", "atlas-langsmith-smoke")
    endpoint = _auth_ok()
    nesting = _nesting_ok()
    if endpoint and nesting:
        extra = (
            ""
            if endpoint.endswith("api.smith.langchain.com") and "eu." not in endpoint
            else f" — set LANGSMITH_ENDPOINT={endpoint} on the workflows"
        )
        print(f"\nVERDICT: READY — enable LANGSMITH_TRACING on the workflows{extra}")
        return 0
    print("\nVERDICT: NOT READY — fix the above before enabling")
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
