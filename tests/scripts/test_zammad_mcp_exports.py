"""Oversized Zammad retrievals go to the artifact store, not to the model.

When a listing tool returns more than ``EXPORT_ROW_LIMIT`` rows the rows stop
going back through the MCP response. The model receives metadata only -- count,
id list, created/updated ranges, state/priority/group histograms and field
coverage -- plus a few rows as an explicitly labelled preview. The full set
becomes ONE ``table`` artifact in the DigiChat artifact store, reached through a
conversation-scoped ingest grant.

The first cut of this (DIG-2638, ``82395706``) spooled the rows inside the
container and served them from a second stdlib HTTP server on :8771 behind the
Worker's ``zammad-export`` edge route under a fixed 24h TTL. Chris reversed that
on DIG-2638: a fixed TTL keeps serving a link after the session that owns it is
gone. Those tests travelled with the code and pinned the transport; they are
gone here and replaced by pins that assert the reversal.

Two kinds of test live in this file:

  * behaviour, against real bytes and a real bound socket;
  * *wiring pins* asserted on SOURCE TEXT. ``server.py`` cannot be imported in
    this lane -- it imports ``mcp``, which CI does not install -- so the wiring
    is pinned by reading the file rather than by calling it.
"""

from __future__ import annotations

import json
import re
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

import pytest

from scripts.zammad_mcp import artifact_store
from scripts.zammad_mcp.exports import (
    ARTIFACT_KIND,
    ARTIFACT_MEDIA_TYPE,
    EXPORT_ID_LIST_LIMIT,
    EXPORT_ROW_LIMIT,
    ExportError,
    artifact_name,
    build_artifact,
    new_artifact_token,
    render_metadata_only,
    summarize,
)

REPO_ROOT = Path(__file__).resolve().parents[2]
SERVER = REPO_ROOT / "scripts" / "zammad_mcp" / "server.py"
EXPORTS_PY = REPO_ROOT / "scripts" / "zammad_mcp" / "exports.py"
STORE_PY = REPO_ROOT / "scripts" / "zammad_mcp" / "artifact_store.py"
STACK_DIR = REPO_ROOT / "apps" / "digithings-stack-cloudflare"
STACK_INDEX = STACK_DIR / "src" / "index.ts"
SUPERVISORD = STACK_DIR / "container" / "supervisor" / "supervisord.conf"
MCP_DOCKERFILE = REPO_ROOT / "scripts" / "zammad_mcp" / "Dockerfile.mcp"

# Markers that must never reach model-visible text. Every test that asserts an
# absence quotes these, so a render that grows a new leak has a value to trip on.
SECRET_TITLE = "Quarterly escalation for acme"
SECRET_CUSTOMER = "acme-billing@example.com"


def _row(index: int) -> dict:
    return {
        "id": 1000 + index,
        "number": f"T-{index:05d}",
        "title": SECRET_TITLE if index == 0 else f"Routine ticket {index}",
        "state": "open" if index % 2 else "closed",
        "priority": "2 normal" if index % 3 else "3 high",
        "group": "sales" if index % 2 else "billing",
        "customer": SECRET_CUSTOMER if index == 1 else f"user{index}@example.com",
        "owner": "agent@example.com",
        "created_at": f"2026-09-{(index % 27) + 1:02d}T10:00:00Z",
        "updated_at": f"2026-10-{(index % 9) + 1:02d}T08:30:00Z",
        "close_at": None,
        "custom_field": f"value-{index}",
    }


def _rows(count: int) -> list[dict]:
    return [_row(i) for i in range(count)]


def _oversized() -> list[dict]:
    return _rows(EXPORT_ROW_LIMIT + 5)


def _code_lines(path: Path) -> str:
    return path.read_text(encoding="utf-8")


# --------------------------------------------------------------------------
# summarize() - unchanged from the first cut, and still the model's whole view
# --------------------------------------------------------------------------


def test_summary_counts_ids_and_bounds_the_id_list():
    summary = summarize(_rows(EXPORT_ID_LIST_LIMIT + 25))
    assert summary["count"] == EXPORT_ID_LIST_LIMIT + 25
    assert len(summary["ids"]) == EXPORT_ID_LIST_LIMIT
    assert summary["ids_shown"] == EXPORT_ID_LIST_LIMIT
    assert summary["ids_omitted"] == 25


def test_summary_reports_histograms_ranges_and_field_coverage():
    summary = summarize(_rows(40))
    assert summary["histograms"]["state"] == {"open": 20, "closed": 20}
    # Ranges are (first, last) tuples.
    assert summary["created_range"] == ("2026-09-01T10:00:00Z", "2026-09-27T10:00:00Z")
    assert summary["updated_range"] == ("2026-10-01T08:30:00Z", "2026-10-09T08:30:00Z")
    # Coverage is preformatted, one line per field that carries a value.
    coverage = summary["field_coverage"]
    assert "  id: 40/40" in coverage
    assert not any(line.startswith("  close_at:") for line in coverage), (
        "a field that is None in every row must not claim coverage"
    )


def test_summary_claims_nothing_beyond_the_rows_it_was_given():
    summary = summarize(_rows(3))
    assert summary["count"] == 3
    assert len(summary["ids"]) == 3
    assert summary["ids_omitted"] == 0


# --------------------------------------------------------------------------
# build_artifact() - ONE table artifact, both formats, no transport
# --------------------------------------------------------------------------


def test_build_artifact_carries_both_formats_in_one_blob():
    artifact = build_artifact(_rows(30), tool="search_tickets", query="kind: complaint")
    assert artifact["kind"] == ARTIFACT_KIND == "table"
    assert artifact["mediaType"] == ARTIFACT_MEDIA_TYPE
    assert artifact["bytes"]
    envelope = json.loads(artifact["bytes"].decode("utf-8"))
    assert envelope["tool"] == "search_tickets"
    assert envelope["query"] == "kind: complaint"
    assert len(envelope["json"]) == 30
    # The CSV half is the same rows, so a reader gets the whole set either way.
    csv_lines = envelope["csv"].strip().splitlines()
    assert csv_lines[0].startswith("id,number,title")
    assert len(csv_lines) == 31  # header + 30 rows


def test_build_artifact_keeps_the_rows_out_of_its_own_metadata():
    artifact = build_artifact(_oversized(), tool="list_tickets")
    # Everything the model is shown comes from `summary`; the bytes stay in
    # `bytes`. A summary carrying a row value would leak through the render.
    assert SECRET_TITLE not in json.dumps(artifact["summary"])
    assert SECRET_CUSTOMER not in json.dumps(artifact["summary"])
    assert SECRET_TITLE in artifact["bytes"].decode("utf-8")


def test_build_artifact_refuses_an_empty_result():
    with pytest.raises(ExportError):
        build_artifact([], tool="search_tickets")


def test_artifact_name_is_derived_from_the_tool_and_says_json():
    assert artifact_name("search_tickets") == "zammad-tickets-search-tickets.json"
    assert artifact_name("list_tickets") == "zammad-tickets-list-tickets.json"


def test_artifact_token_is_unguessable_and_carries_no_row_value():
    tokens = {new_artifact_token() for _ in range(200)}
    assert len(tokens) == 200
    for token in tokens:
        assert re.fullmatch(r"[0-9a-f]{32}", token)
        assert SECRET_TITLE not in token and SECRET_CUSTOMER not in token


# --------------------------------------------------------------------------
# render_metadata_only() - the model-visible contract
# --------------------------------------------------------------------------


def test_metadata_only_render_carries_metadata_and_no_row_values():
    artifact = build_artifact(_oversized(), tool="search_tickets")
    text = render_metadata_only(artifact, link="/api/conversations/c1/artifacts/blob?token=abc")
    assert (
        f"{artifact['summary']['count']} tickets" in text
        or str(artifact["summary"]["count"]) in text
    )
    assert "/api/conversations/c1/artifacts/blob?token=abc" in text
    assert SECRET_TITLE not in text
    assert SECRET_CUSTOMER not in text


def test_metadata_only_render_states_that_other_ids_were_omitted():
    artifact = build_artifact(_rows(EXPORT_ID_LIST_LIMIT + 7), tool="list_tickets")
    assert artifact["summary"]["ids_omitted"] == 7
    text = render_metadata_only(artifact, link="/x")
    assert f"Ticket ids ({EXPORT_ID_LIST_LIMIT} shown)" in text
    # The omitted count is carried in the summary, not printed as prose: the
    # render must not invite the model to reconstruct rows it was not given.
    assert str(artifact["summary"]["count"]) in text


def test_metadata_only_render_lists_the_histograms_and_field_coverage():
    artifact = build_artifact(_rows(40), tool="list_tickets")
    text = render_metadata_only(artifact, link="/x")
    assert "State: closed 20, open 20" in text
    assert "Priority: 2 normal 26, 3 high 14" in text
    assert "Group: billing 20, sales 20" in text
    assert "Field coverage:" in text
    assert "  id: 40/40" in text
    # A field outside SUMMARY_FIELDS is not part of the model's contract.
    assert "custom_field" not in text


def test_metadata_only_render_never_names_an_expiry_time():
    """The decision on DIG-2638: no fixed TTL, so nothing may promise one."""
    artifact = build_artifact(_oversized(), tool="list_tickets")
    text = render_metadata_only(artifact, link="/x").lower()
    assert "expires" not in text
    assert "ttl" not in text
    assert "24h" not in text


def test_metadata_only_render_states_the_session_scope():
    artifact = build_artifact(_oversized(), tool="list_tickets")
    text = render_metadata_only(artifact, link="/x").lower()
    assert "session" in text
    assert "reload" in text


def test_rendered_sample_rows_are_only_rows_the_caller_passed_in():
    artifact = build_artifact(_oversized(), tool="list_tickets")
    good = render_metadata_only(artifact, link="/x", sample=["line one", "line two"])
    assert "line one" in good and "line two" in good
    # Positive control: the marker values ARE in the bytes, so a render that
    # showed nothing because the sample was empty would read identically. This
    # arm proves the sample is what put text in the output.
    without = render_metadata_only(artifact, link="/x", sample=[])
    assert "line one" not in without


# --------------------------------------------------------------------------
# artifact_store - the grant, the POST, and the fallback
# --------------------------------------------------------------------------


class _Capture(BaseHTTPRequestHandler):
    received: dict = {}

    def do_POST(self):
        length = int(self.headers.get("Content-Length") or 0)
        raw = self.rfile.read(length)
        type(self).received = {
            "path": self.path,
            "authorization": self.headers.get("Authorization"),
            "content_type": self.headers.get("Content-Type"),
            "conversation": self.headers.get("X-Conversation-Id"),
            "body": json.loads(raw.decode("utf-8")),
        }
        payload = json.dumps(
            {"link": "/api/conversations/c1/artifacts/blob?token=deadbeef"}
        ).encode()
        self.send_response(201)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(payload)))
        self.end_headers()
        self.wfile.write(payload)

    def log_message(self, *_args):
        return


@pytest.fixture()
def store_env(monkeypatch):
    """A live loopback store, and the three env names that reach it."""
    server = ThreadingHTTPServer(("127.0.0.1", 0), _Capture)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    host, port = server.server_address[0], server.server_address[1]
    monkeypatch.setenv("DIGICHAT_ARTIFACT_INGEST_URL", f"http://{host}:{port}/api/artifact-ingest")
    monkeypatch.setenv("DIGICHAT_ARTIFACT_CONVERSATION", "c1")
    monkeypatch.setenv("DIGICHAT_ARTIFACT_GRANT", "grant-token-value")
    try:
        yield f"http://{host}:{port}/api/artifact-ingest"
    finally:
        server.shutdown()
        server.server_close()


def test_ingest_posts_one_table_artifact_with_the_grant(store_env):
    _Capture.received = {}
    text = artifact_store.export_if_large(_oversized(), tool="search_tickets", query="q")
    assert text is not None
    got = _Capture.received
    assert got["path"] == "/api/artifact-ingest"
    assert got["authorization"] == "Bearer grant-token-value"
    assert got["content_type"] == "application/json"
    assert got["conversation"] == "c1"
    body = got["body"]
    assert body["conversationId"] == "c1"
    assert body["kind"] == "table"
    assert body["mediaType"] == ARTIFACT_MEDIA_TYPE
    assert re.fullmatch(r"[0-9a-f]{32}", body["token"])
    assert body["bytes"] and isinstance(body["bytes"], list)
    assert SECRET_TITLE not in json.dumps(body["summary"])


def test_ingest_returns_the_link_and_the_model_sees_only_metadata(store_env):
    _Capture.received = {}
    text = artifact_store.export_if_large(_oversized(), tool="list_tickets")
    assert "/api/conversations/c1/artifacts/blob?token=deadbeef" in text
    assert SECRET_TITLE not in text
    assert SECRET_CUSTOMER not in text
    assert "ticket" in text.lower()


def test_the_cut_is_opt_in_below_the_limit_and_never_calls_the_store(store_env):
    _Capture.received = {}
    assert artifact_store.export_if_large(_rows(EXPORT_ROW_LIMIT), tool="list_tickets") is None
    assert artifact_store.export_if_large(_rows(1), tool="list_tickets") is None
    assert _Capture.received == {}


def test_a_store_failure_falls_back_to_the_full_render_so_rows_are_never_lost(
    store_env, monkeypatch
):
    """A dead store must not lose rows: the caller falls back to the full render."""
    monkeypatch.setenv("DIGICHAT_ARTIFACT_INGEST_URL", "http://127.0.0.1:9/api/artifact-ingest")
    # The direct call surfaces the failure...
    with pytest.raises(artifact_store.ArtifactStoreError):
        artifact_store._ingest(
            build_artifact(_rows(3), tool="list_tickets"),
            tool="list_tickets",
            query="",
            timeout=0.5,
        )
    # ...and the path the MCP tools actually take returns None instead, which
    # server.py reads as "render the rows normally". That is the property that
    # keeps rows from ever being dropped.
    assert artifact_store.export_if_large(_oversized(), tool="list_tickets") is None


def test_the_grant_names_no_object_store_credential(monkeypatch, caplog):
    """The container gains a grant, not a key: three names, all required."""
    accessors = {
        "DIGICHAT_ARTIFACT_INGEST_URL": artifact_store.ingest_url,
        "DIGICHAT_ARTIFACT_CONVERSATION": artifact_store.conversation_id,
        "DIGICHAT_ARTIFACT_GRANT": artifact_store.ingest_grant,
    }
    # Positive control first: with the env set, every accessor returns it. A
    # zero-length assertion that passed for a broken accessor would be vacuous.
    for name, accessor in accessors.items():
        monkeypatch.setenv(name, "value-for-" + name)
        assert accessor() == "value-for-" + name
    for name in accessors:
        monkeypatch.delenv(name, raising=False)

    with caplog.at_level("WARNING", logger="scripts.zammad_mcp.artifact_store"):
        # Unconfigured is not fatal: the tools fall back to the full render.
        assert artifact_store.export_if_large(_oversized(), tool="list_tickets") is None

    # Each missing name is named in the warning, so a misconfigured container
    # says which one rather than "store unavailable".
    for name in accessors:
        assert name in caplog.text, f"{name} is not named in the warning"


# --------------------------------------------------------------------------
# Wiring pins -- source text, because server.py needs `mcp` and CI lacks it
# --------------------------------------------------------------------------


def test_both_listing_tools_go_through_the_export_cut():
    source = _code_lines(SERVER)
    assert source.count("_export_if_large(") >= 3  # def + two call sites
    assert "from scripts.zammad_mcp.artifact_store import export_if_large" in source


def test_the_export_cut_precedes_the_full_render():
    source = _code_lines(SERVER).splitlines()
    for tool, renderer in (
        ("search_tickets", "format_search_results"),
        ("list_tickets", "format_ticket_list"),
    ):
        start = next(i for i, line in enumerate(source) if line.startswith(f"def {tool}("))
        body = "\n".join(source[start : start + 70])
        cut = body.index("_export_if_large(")
        assert body.index(renderer) > cut, f"{tool} renders rows before the cut runs"
        # And the render is reachable only when the cut declined.
        assert "if exported is not None:" in body


def test_the_preview_is_formatted_by_the_tools_own_line_formatter():
    source = _code_lines(SERVER)
    assert "preview = [format_ticket_line(ticket) for ticket in tickets[" in source
    assert "preview=preview" in source


# --------------------------------------------------------------------------
# The reversal: the superseded transport must not come back
# --------------------------------------------------------------------------


def test_no_fixed_ttl_constant_survives_anywhere_in_the_zammad_package():
    """A TTL is the thing Chris reversed. One occurrence anywhere is a defect."""
    for path in (EXPORTS_PY, STORE_PY, SERVER, EXPORTS_PY.parent / "export_server.py"):
        if not path.exists():
            continue
        text = _code_lines(path)
        assert "EXPORT_TTL_SECONDS" not in text, f"{path} still carries a TTL"


def test_the_container_local_spool_and_its_server_are_gone():
    package = EXPORTS_PY.parent
    assert not (package / "export_server.py").exists(), "the :8771 download server is back"
    for name in ("ZAMMAD_EXPORT_DIR", "DEFAULT_SPOOL_DIR", "purge_expired", "load_export"):
        for path in package.glob("*.py"):
            if path.name == __file__.rsplit("/", 1)[-1]:
                continue
            assert name not in _code_lines(path), f"{name} survived in {path.name}"


def test_the_worker_no_longer_maps_a_ticket_download_port():
    source = _code_lines(STACK_INDEX)
    assert "zammad-export" not in source
    assert "8771" not in source


def test_the_container_no_longer_runs_a_ticket_download_program():
    supervisor = _code_lines(SUPERVISORD)
    assert "zammad-export" not in supervisor
    assert "export_server" not in supervisor
    assert "ZAMMAD_EXPORT_DIR" not in supervisor


def test_the_image_no_longer_exposes_the_download_port():
    dockerfile = _code_lines(MCP_DOCKERFILE)
    assert "EXPOSE 8770" in dockerfile
    assert "8771" not in dockerfile


def test_the_grant_lands_on_a_digichat_route_that_rechecks_ownership():
    """The write must pass through the store's own ownership guard."""
    ingest = (
        REPO_ROOT / "apps" / "digichat" / "src" / "app" / "api" / "artifact-ingest" / "route.ts"
    )
    assert ingest.exists()
    text = _code_lines(ingest)
    assert "insertArtifact" in text, "the ingest route bypasses the ownership guard"
    assert "requireDigiChatAuth" in text
    assert "bindLink" in text and "registerSession" in text


def test_the_download_link_is_gated_by_the_live_session():
    blob = (
        REPO_ROOT
        / "apps"
        / "digichat"
        / "src"
        / "app"
        / "api"
        / "conversations"
        / "[id]"
        / "artifacts"
        / "blob"
        / "route.ts"
    )
    assert blob.exists()
    text = _code_lines(blob)
    assert "isLiveSessionLink" in text, "the download route does not check the session"
    assert "serveArtifact" in text
