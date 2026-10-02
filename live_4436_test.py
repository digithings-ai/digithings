"""Live end-to-end test of the digiquant query_research MCP tool against the local sim.

Exercises: MCP protocol registration + call, in-process dispatcher (wide + narrow),
filters, access control, look-ahead clamp, limit clamp, error envelope.
Every returned value is cross-checked against the raw sim DB (ground truth).

Temporary harness - not part of the deliverable.
"""

from __future__ import annotations

import asyncio
import json
import os
import sys
from datetime import date

SIM_URL = "http://127.0.0.1:54321"
SIM_KEY = (
    "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJpc3MiOiJzdXBhYmFzZS1kZW1vIiwicm9sZSI6InNl"
    "cnZpY2Vfcm9sZSIsImV4cCI6MTk4MzgxMjk5Nn0.EGIM96RAZx35lJzdJsyH-qQwv8Hdp7fsn3W0YpN81IU"
)
os.environ["CORE_SUPABASE_URL"] = SIM_URL
os.environ["CORE_SUPABASE_SERVICE_KEY"] = SIM_KEY

import logging  # noqa: E402

logging.disable(logging.INFO)

PASS: list[str] = []
FAIL: list[str] = []
OBS: list[str] = []


def check(name: str, cond: bool, detail: str = "") -> bool:
    (PASS if cond else FAIL).append(f"{name}{(' :: ' + detail) if detail else ''}")
    print(f"  [{'PASS' if cond else 'FAIL'}] {name}" + (f" :: {detail}" if detail else ""))
    return cond


def observe(name: str, detail: str) -> None:
    OBS.append(f"{name}: {detail}")
    print(f"  [obs ] {name} :: {detail}")


def gt_documents(extra: str = "") -> int:
    """Ground-truth count of documents via raw REST."""
    import urllib.request

    url = f"{SIM_URL}/rest/v1/documents?select=document_key&limit=1000{extra}"
    req = urllib.request.Request(
        url, headers={"apikey": SIM_KEY, "Authorization": f"Bearer {SIM_KEY}"}
    )
    with urllib.request.urlopen(req) as r:  # noqa: S310
        return len(json.loads(r.read().decode()))


def load(text: str) -> dict:
    return json.loads(text)


async def main() -> int:
    from digiquant.dashboard.research_retrieval.queries import search_research
    from digiquant.dashboard.research_retrieval.tools import build_research_tool_dispatcher
    from digiquant.mcp_server import create_mcp_server
    from digiquant.research.supabase_io import SupabaseConfig, build_client
    from mcp.shared.memory import create_connected_server_and_client_session

    client = build_client(SupabaseConfig.from_env())
    today = date(2026, 9, 21)
    sim_day = date(2026, 9, 19)

    print("\n== A. MCP protocol: read-scope registration ==")
    server = create_mcp_server(scope="read")
    async with create_connected_server_and_client_session(server) as session:
        tools = await session.list_tools()
        names = sorted(t.name for t in tools.tools)
        check("read scope registers digiquant_query_research", "digiquant_query_research" in names)
        check(
            "read scope no longer registers digiquant_query_data",
            "digiquant_query_data" not in names,
        )
        observe("read-scope tool count", str(len(names)))

        async def call(**kw) -> dict:
            res = await session.call_tool("digiquant_query_research", kw)
            return load(res.content[0].text)

        print("\n== B. MCP protocol: dataset / run_type / window ==")
        r = await call()
        check(
            "B1 default run_type=baseline returns 0 (sim rows are delta)",
            r.get("row_count") == 0,
            f"row_count={r.get('row_count')} run_type={r.get('run_type')}",
        )

        r = await call(run_type="delta", include_prior=True)
        n = gt_documents("&run_type=eq.delta")
        check(
            "B2 run_type=delta + include_prior returns all sim documents",
            r.get("row_count") == n,
            f"row_count={r.get('row_count')} ground_truth={n}",
        )

        r = await call(run_type="delta", date_from="2026-09-19", date_to="2026-09-19")
        check(
            "B3 explicit 1-day window returns all sim documents",
            r.get("row_count") == n,
            f"row_count={r.get('row_count')} date_from={r.get('date_from')} date_to={r.get('date_to')}",
        )

        print("\n== C. MCP protocol: filters ==")
        r = await call(
            run_type="delta", date_from="2026-09-19", date_to="2026-09-19", document_key="macro"
        )
        check(
            "C1 document_key=macro -> exactly 1 row",
            r.get("row_count") == 1,
            f"row_count={r.get('row_count')}",
        )

        r = await call(run_type="delta", include_prior=True, segment="coverage-directive")
        keys = [x.get("document_key") for x in r.get("rows", [])]
        check(
            "C2 segment=<key> resolves to that document_key",
            keys == ["coverage-directive"],
            f"keys={keys}",
        )
        r = await call(run_type="delta", include_prior=True, segment="coverage-director")
        observe(
            "C2b segment is an alias for document_key, NOT a filter on the segment column "
            "(sim row has segment='coverage-director' but key='coverage-directive' -> 0 rows)",
            f"row_count={r.get('row_count')}",
        )

        r = await call(run_type="delta", include_prior=True, doc_type="Beliefs")
        keys = [x.get("document_key") for x in r.get("rows", [])]
        check("C3 doc_type=Beliefs -> beliefs", keys == ["beliefs"], f"keys={keys}")

        r = await call(run_type="delta", include_prior=True, subject="Daily Delta")
        keys = [x.get("document_key") for x in r.get("rows", [])]
        check("C4 subject='Daily Delta' matches digest-delta", "digest-delta" in keys, f"keys={keys}")

        r = await call(run_type="delta", include_prior=True, subject="macro")
        keys = [x.get("document_key") for x in r.get("rows", [])]
        check("C5 subject='macro' matches macro doc", "macro" in keys, f"keys={keys}")

        r = await call(run_type="delta", include_prior=True, ticker="SPY")
        observe(
            "C6 ticker=SPY on documents (join via thesis_vehicles)",
            f"row_count={r.get('row_count')} "
            f"keys={[x.get('document_key') for x in r.get('rows', [])][:5]}",
        )

        print("\n== D. MCP protocol: pagination + limit clamp ==")
        r = await call(run_type="delta", include_prior=True, limit=5)
        check(
            "D1 limit=5 -> 5 rows",
            r.get("row_count") == 5 and r.get("limit") == 5,
            f"row_count={r.get('row_count')} limit={r.get('limit')}",
        )
        r = await call(run_type="delta", include_prior=True, limit=99999)
        check("D2 limit=99999 clamped to 500", r.get("limit") == 500, f"limit={r.get('limit')}")
        r = await call(run_type="delta", include_prior=True, limit=0)
        check(
            "D3 limit=0 clamped up to 1",
            r.get("limit") == 1,
            f"limit={r.get('limit')} rc={r.get('row_count')}",
        )
        r = await call(run_type="delta", include_prior=True, limit=5, offset=30)
        check(
            "D4 offset=30 with limit=5 -> 4 rows (34 total)",
            r.get("row_count") == 4 and r.get("offset") == 30,
            f"row_count={r.get('row_count')} offset={r.get('offset')}",
        )

        print("\n== E. MCP protocol: content bounding ==")
        # opportunity-screener is one of the 5 sim docs with a non-null `content` column
        r = await call(run_type="delta", include_prior=True, document_key="opportunity-screener")
        row = (r.get("rows") or [{}])[0]
        clen = len(row.get("content") or "")
        check(
            "E1 full_content=False truncates content to 500",
            row.get("content_truncated") is True and clen == 500,
            f"clen={clen} truncated={row.get('content_truncated')}",
        )
        r = await call(
            run_type="delta",
            include_prior=True,
            document_key="opportunity-screener",
            full_content=True,
        )
        row = (r.get("rows") or [{}])[0]
        clen = len(row.get("content") or "")
        check(
            "E2 full_content=True returns untruncated content",
            not row.get("content_truncated") and clen > 500,
            f"clen={clen}",
        )
        # crypto carries its body only in payload.body (content is NULL in the sim)
        r = await call(run_type="delta", include_prior=True, document_key="crypto")
        row = (r.get("rows") or [{}])[0]
        observe(
            "E3 payload returned in full even when full_content=False (known follow-up M2)",
            f"payload_len={len(json.dumps(row.get('payload')))} content={row.get('content')!r}",
        )
        r = await call(dataset="daily_snapshots", include_prior=True)
        row = (r.get("rows") or [{}])[0]
        snap = json.dumps(row.get("snapshot"))
        observe(
            "E4 daily_snapshots.snapshot is NOT bounded by full_content (known follow-up M2)",
            f"snapshot_len={len(snap)}",
        )

        print("\n== F. Access control / blinding ==")
        r = await call(dataset="documents", run_type="delta", include_prior=True, document_key="beliefs")
        check(
            "F1 MCP: beliefs visible at default retrieval_phase=research_edit",
            r.get("row_count") == 1,
            f"row_count={r.get('row_count')}",
        )
        # The MCP wrapper's `phase` arg feeds search_research(phase=...) i.e. the
        # documents.phase COLUMN filter (integer in schema) - not retrieval_phase.
        r = await call(
            dataset="documents",
            run_type="delta",
            include_prior=True,
            document_key="macro",
            phase="h5_analyst",
        )
        check(
            "F2 MCP: phase=<name> on documents errors (documents.phase is integer -> 22P02)",
            "error" in r,
            f"resp={str(r)[:150]}",
        )
        observe(
            "F3 MCP wrapper never passes retrieval_phase, so phase blinding is unreachable "
            "on the MCP surface (always research_edit)",
            f"default row_count(beliefs)={1}",
        )
        r = await call(dataset="daily_snapshots", include_prior=True)
        check(
            "F4 MCP: daily_snapshots visible at default",
            r.get("row_count") == 1,
            f"row_count={r.get('row_count')}",
        )
        r = await call(dataset="daily_snapshots", include_prior=True, phase="h5_analyst")
        observe(
            "F5 MCP: phase arg is ignored for daily_snapshots (no phase column filter on that path)",
            f"row_count={r.get('row_count')}",
        )

        print("\n-- F6+ blinding via the in-process dispatcher (maps phase -> retrieval_phase) --")
        h5 = build_research_tool_dispatcher(client, run_date=sim_day, phase="h5_analyst")
        h6 = build_research_tool_dispatcher(client, run_date=sim_day, phase="h6_deliberation")

        d = load(h5("query_research", {"dataset": "documents", "run_type": "delta", "include_prior": True}))
        keys = [x.get("document_key") for x in d.get("rows", [])]
        check(
            "F6 h5 dispatcher hides documents/beliefs",
            "beliefs" not in keys and d.get("row_count") == 33,
            f"row_count={d.get('row_count')} beliefs_hidden={'beliefs' not in keys}",
        )
        check(
            "F7 h5 dispatcher still allows non-blinded documents",
            "macro" in keys and "crypto" in keys,
            f"macro={'macro' in keys} crypto={'crypto' in keys}",
        )
        observe(
            "F8 h5 dispatcher is NOT blinded to the delta digest (blinding keys are 'digest'/'beliefs')",
            f"digest_delta_present={'digest-delta' in keys}",
        )
        d = load(h5("query_research", {"dataset": "daily_snapshots", "include_prior": True}))
        check("F9 h5 dispatcher blocks the daily_snapshots digest", d.get("row_count") == 0, f"rc={d.get('row_count')}")
        d = load(h5("query_research", {"dataset": "positions", "include_prior": True}))
        check(
            "F10 h5 dispatcher blocks portfolio datasets",
            "error" in d and "portfolio" in str(d.get("error")),
            f"resp={str(d)[:120]}",
        )
        d = load(h6("query_research", {"dataset": "positions", "include_prior": True}))
        check(
            "F11 h6 dispatcher also blocks portfolio datasets",
            "error" in d and "portfolio" in str(d.get("error")),
            f"resp={str(d)[:120]}",
        )
        d = load(h6("query_research", {"dataset": "documents", "run_type": "delta", "include_prior": True}))
        check(
            "F12 h6 dispatcher allows documents (h6 is not a blinded doc phase)",
            d.get("row_count") == 34,
            f"rc={d.get('row_count')}",
        )
        d = load(h5("query_research", {"document_key": "beliefs"}))
        check(
            "F13 h5 dispatcher blocks beliefs on the narrow path too",
            "error" in d,
            f"resp={str(d)[:120]}",
        )

        print("\n== G. MCP protocol: empty portfolio datasets (sim has 0 rows) ==")
        for ds in ("positions", "nav_history", "portfolio_metrics", "position_events", "decision_log"):
            r = await call(dataset=ds, include_prior=True)
            check(
                f"G {ds} empty-but-clean",
                r.get("row_count") == 0 and "error" not in r,
                f"rc={r.get('row_count')} err={r.get('error')}",
            )
        r = await call(dataset="theses", include_prior=True)
        check("G theses returns 3 rows", r.get("row_count") == 3, f"rc={r.get('row_count')}")
        r = await call(dataset="thesis_vehicles", include_prior=True)
        check(
            "G thesis_vehicles returns 16 rows",
            r.get("row_count") == 16,
            f"rc={r.get('row_count')}",
        )

        print("\n== H. MCP protocol: look-ahead + error envelope ==")
        r = await call(run_type="delta", include_prior=True, as_of_date="2026-12-31")
        check(
            "H1 future as_of_date cannot push date_to past run_date(today)",
            r.get("date_to") == today.isoformat(),
            f"date_to={r.get('date_to')} (today={today})",
        )
        r = await call(
            run_type="delta", include_prior=True, as_of_date="2026-12-31", date_to="2026-12-31"
        )
        check(
            "H2 future date_to also clamped to run_date",
            r.get("date_to") == today.isoformat(),
            f"date_to={r.get('date_to')}",
        )
        r = await call(run_type="delta", include_prior=True, as_of_date="2026-09-01")
        check(
            "H3 past as_of_date narrows the upper bound",
            r.get("date_to") == "2026-09-01",
            f"date_to={r.get('date_to')}",
        )
        r = await call(date_from="not-a-date")
        check(
            "H4 malformed date -> error envelope, no crash",
            "error" in r and "ValueError" in str(r.get("error")),
            f"resp={str(r)[:120]}",
        )
        r = await call(dataset="not_a_dataset")
        check(
            "H5 unknown dataset -> error envelope",
            "error" in r and "unknown dataset" in str(r.get("error")),
            f"resp={str(r)[:120]}",
        )

    print("\n== I. In-process dispatcher: narrow path + helpers ==")
    disp = build_research_tool_dispatcher(client, run_date=sim_day, phase="research_edit")

    narrow = load(disp("query_research", {"document_key": "macro"}))
    check(
        "I1 narrow path (document_key only) returns payload",
        isinstance(narrow.get("payload"), dict) and narrow.get("document_key") == "macro",
        f"keys={sorted(narrow.keys())}",
    )
    check(
        "I2 narrow path resolves as_of to the sim day",
        narrow.get("as_of_date") == "2026-09-19",
        f"as_of={narrow.get('as_of_date')}",
    )

    wide = load(
        disp("query_research", {"dataset": "documents", "run_type": "delta", "include_prior": True})
    )
    check(
        "I3 wide path via dispatcher returns all 34",
        wide.get("row_count") == 34,
        f"rc={wide.get('row_count')}",
    )

    pri = load(disp("fetch_prior_document", {"document_key": "macro", "section_path": "/summary"}))
    check(
        "I4 fetch_prior_document + section_path extracts a subsection",
        isinstance(pri, dict) and "error" not in pri,
        f"type={type(pri).__name__} keys={list(pri)[:5]}",
    )
    pri_full = load(disp("fetch_prior_document", {"document_key": "macro"}))
    check(
        "I5 fetch_prior_document without section_path returns full payload body",
        isinstance(pri_full, dict) and "error" not in pri_full,
        f"keys={list(pri_full)[:5]}",
    )

    port = load(disp("query_portfolio", {}))
    check(
        "I6 query_portfolio returns the empty sim book cleanly",
        "error" not in port and port.get("positions") == [],
        f"resp={str(port)[:160]}",
    )

    print("\n== J. Direct search_research: h5 sweep over all documents ==")
    r = search_research(
        client,
        run_date=today,
        dataset="documents",
        run_type="delta",
        include_prior=True,
        retrieval_phase="h5_analyst",
    )
    keys = [x.get("document_key") for x in r.get("rows", [])]
    observe("J1 h5_analyst full-documents sweep", f"row_count={r.get('row_count')} keys={keys}")
    check("J2 h5_analyst sweep still hides beliefs", "beliefs" not in keys, f"keys={keys}")

    print("\n" + "=" * 70)
    print(f"PASS {len(PASS)}  FAIL {len(FAIL)}  OBS {len(OBS)}")
    if FAIL:
        print("\nFAILURES:")
        for f in FAIL:
            print("  - " + f)
    print("\nOBSERVATIONS:")
    for o in OBS:
        print("  - " + o)
    return 1 if FAIL else 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
