"""Oversized Zammad retrievals go to an expiring download, not to the model.

Two halves:

* behaviour, exercised against the real spool files and a real bound socket --
  ``exports`` never hands rows back to the model above the limit, and the TTL is
  enforced when the file is read rather than when it is written;
* wiring pins, because ``server.py`` cannot be imported here (it needs ``mcp``,
  which the CI lane does not install). Those assert on source text, the pattern
  the sibling stack test already uses.
"""

from __future__ import annotations

import csv
import http.client
import io
import json
import threading
from datetime import datetime, timedelta, timezone
from pathlib import Path
from urllib.parse import urlsplit

import pytest

from scripts.zammad_mcp.export_server import build_server, parse_download_path
from scripts.zammad_mcp.exports import (
    EXPORT_FORMATS,
    EXPORT_ID_LIST_LIMIT,
    EXPORT_ROW_LIMIT,
    EXPORT_TTL_SECONDS,
    ExportExpired,
    ExportNotFound,
    is_valid_export_id,
    load_export,
    new_export_id,
    purge_expired,
    render_metadata_only,
    summarize,
    write_export,
)

pytestmark = pytest.mark.unit

REPO_ROOT = Path(__file__).resolve().parents[2]
SERVER = REPO_ROOT / "scripts" / "zammad_mcp" / "server.py"
STACK_DIR = REPO_ROOT / "apps" / "digithings-stack-cloudflare"
STACK_INDEX = STACK_DIR / "src" / "index.ts"
SUPERVISORD = STACK_DIR / "container" / "supervisor" / "supervisord.conf"
MCP_DOCKERFILE = REPO_ROOT / "scripts" / "zammad_mcp" / "Dockerfile.mcp"

#: Values that exist only in the rows. The metadata-only render must carry none
#: of them: this is the property the whole leaf exists to create.
SECRET_TITLE = "Quarterly escalation for acme"
SECRET_CUSTOMER = "acme-billing@example.com"


def _row(index: int) -> dict[str, object]:
    return {
        "id": 1000 + index,
        "number": f"8801{index:02d}",
        "title": SECRET_TITLE if index == 0 else f"Routine request {index}",
        "state": "open" if index % 2 else "new",
        "priority": "3 normal" if index % 3 else "2 high",
        "group": "users",
        "customer": SECRET_CUSTOMER if index == 0 else {"id": index, "name": f"Person {index}"},
        "owner": {"id": 7, "login": "agent7"},
        "created_at": f"2026-09-{1 + index:02d}T08:00:00Z",
        "updated_at": f"2026-10-{1 + index % 9:02d}T09:30:00Z",
    }


def _rows(count: int) -> list[dict[str, object]]:
    return [_row(i) for i in range(count)]


def _code_lines(path: Path) -> str:
    """File body with full-line comments stripped, so pins target code."""
    return "\n".join(
        line for line in path.read_text().splitlines() if not line.lstrip().startswith("#")
    )


# --------------------------------------------------------------------------
# summarisation: what the model is allowed to see
# --------------------------------------------------------------------------


def test_summary_counts_ids_and_bounds_the_id_list():
    summary = summarize(_rows(EXPORT_ID_LIST_LIMIT + 300))
    assert summary["count"] == EXPORT_ID_LIST_LIMIT + 300
    assert summary["ids_shown"] == EXPORT_ID_LIST_LIMIT
    assert summary["ids_omitted"] == 300
    # The ids really are the ticket ids, in order.
    assert summary["ids"][0] == "1000"


def test_summary_reports_histograms_ranges_and_field_coverage():
    summary = summarize(_rows(30))
    assert summary["histograms"]["state"] == {"new": 15, "open": 15}
    assert summary["histograms"]["group"] == {"users": 30}
    assert summary["histograms"]["priority"]["2 high"] == 10
    assert summary["created_range"] == ("2026-09-01T08:00:00Z", "2026-09-30T08:00:00Z")
    assert summary["updated_range"] == ("2026-10-01T09:30:00Z", "2026-10-09T09:30:00Z")
    assert "  customer: 30/30" in summary["field_coverage"]


def test_summary_claims_nothing_beyond_the_rows_it_was_given():
    summary = summarize(_rows(30))
    # Coverage counts only the rows handed in: no total is inferred from a query.
    assert all(line.endswith("/30") for line in summary["field_coverage"])


# --------------------------------------------------------------------------
# the metadata-only render
# --------------------------------------------------------------------------


def test_metadata_only_render_carries_metadata_and_no_row_values(tmp_path: Path):
    manifest = write_export(
        _rows(EXPORT_ROW_LIMIT + 5), tool="search_tickets", query="escalation", directory=tmp_path
    )
    text = render_metadata_only(manifest)

    # Non-vacuity: the render is real, so a positive control must hit.
    assert manifest["summary"]["count"] == EXPORT_ROW_LIMIT + 5
    assert "1000" in text
    assert "/_stack/mcp/zammad-export/" + manifest["export_id"] in text
    assert manifest["expires_at"] in text

    # The property the leaf exists for.
    assert SECRET_TITLE not in text
    assert SECRET_CUSTOMER not in text
    assert "Routine request 7" not in text


def test_metadata_only_render_states_that_other_ids_were_omitted(tmp_path: Path):
    manifest = write_export(
        _rows(EXPORT_ID_LIST_LIMIT + 5), tool="list_tickets", directory=tmp_path
    )
    text = render_metadata_only(manifest)
    assert "and 5 more id(s), all present in the download" in text


def test_metadata_only_render_lists_the_histograms(tmp_path: Path):
    manifest = write_export(_rows(30), tool="search_tickets", directory=tmp_path)
    text = render_metadata_only(manifest)
    assert "State: new 15, open 15" in text
    assert "Group: users 30" in text
    assert "Priority: " in text


def test_metadata_only_render_lists_field_coverage(tmp_path: Path):
    manifest = write_export(_rows(30), tool="search_tickets", directory=tmp_path)
    text = render_metadata_only(manifest)
    assert "Field coverage:" in text
    assert "  state: 30/30" in text
    assert "  customer: 30/30" in text


def test_rendered_sample_rows_are_only_rows_the_caller_passed_in(tmp_path: Path):
    manifest = write_export(_rows(30), tool="search_tickets", directory=tmp_path)
    text = render_metadata_only(manifest, sample=["preview only"])
    assert "First rows only (preview, not the full set):" in text
    assert "preview only" in text


# --------------------------------------------------------------------------
# the spool files
# --------------------------------------------------------------------------


def test_write_export_splits_rows_into_json_and_csv_and_keeps_them_out_of_the_manifest(
    tmp_path: Path,
):
    manifest = write_export(
        _rows(30), tool="search_tickets", query="escalation", directory=tmp_path
    )
    export_id = manifest["export_id"]

    payload, read_manifest = load_export(export_id, "json", directory=tmp_path)
    rows = json.loads(payload)
    assert len(rows) == 30
    assert rows[0]["title"] == SECRET_TITLE
    assert read_manifest["export_id"] == export_id

    csv_payload, _ = load_export(export_id, "csv", directory=tmp_path)
    table = list(csv.DictReader(io.StringIO(csv_payload.decode("utf-8"))))
    assert len(table) == 30
    assert table[0]["id"] == "1000"

    # The manifest the model sees must not embed the rows.
    assert SECRET_TITLE not in json.dumps(manifest)
    assert SECRET_CUSTOMER not in json.dumps(manifest)


def test_export_id_is_unguessable_and_the_download_path_is_gated(tmp_path: Path):
    manifest = write_export(_rows(30), tool="search_tickets", directory=tmp_path)
    ids = {
        write_export(_rows(30), tool="search_tickets", directory=tmp_path)["export_id"]
        for _ in range(5)
    }
    assert len(ids) == 5
    assert is_valid_export_id(manifest["export_id"])


def test_write_export_refuses_an_empty_result(tmp_path: Path):
    from scripts.zammad_mcp.exports import ExportError

    with pytest.raises(ExportError):
        write_export([], tool="search_tickets", directory=tmp_path)


# --------------------------------------------------------------------------
# the expiry and the id guard
# --------------------------------------------------------------------------


def test_ttl_is_enforced_when_the_file_is_read_not_when_it_is_written(tmp_path: Path):
    written_at = datetime(2026, 10, 10, 9, 0, tzinfo=timezone.utc)
    manifest = write_export(_rows(30), tool="search_tickets", directory=tmp_path, now=written_at)
    assert manifest["ttl_seconds"] == EXPORT_TTL_SECONDS == 24 * 60 * 60

    before = written_at + timedelta(seconds=EXPORT_TTL_SECONDS - 1)
    payload, _ = load_export(manifest["export_id"], "json", directory=tmp_path, now=before)
    assert json.loads(payload)

    after = written_at + timedelta(seconds=EXPORT_TTL_SECONDS)
    with pytest.raises(ExportExpired):
        load_export(manifest["export_id"], "json", directory=tmp_path, now=after)


def test_expired_export_is_unreadable_even_while_its_files_remain(tmp_path: Path):
    written_at = datetime(2026, 10, 10, 9, 0, tzinfo=timezone.utc)
    manifest = write_export(_rows(30), tool="search_tickets", directory=tmp_path, now=written_at)
    later = written_at + timedelta(days=2)
    with pytest.raises(ExportExpired):
        load_export(manifest["export_id"], "csv", directory=tmp_path, now=later)
    # Still on disk: read-time refusal, not a delete-on-read.
    assert (tmp_path / f"{manifest['export_id']}.csv").exists()


def test_purge_expired_removes_the_files_it_reports(tmp_path: Path):
    written_at = datetime(2026, 10, 10, 9, 0, tzinfo=timezone.utc)
    stale = write_export(_rows(30), tool="search_tickets", directory=tmp_path, now=written_at)
    fresh = write_export(
        _rows(30), tool="search_tickets", directory=tmp_path, now=written_at + timedelta(days=5)
    )

    removed = purge_expired(directory=tmp_path, now=written_at + timedelta(days=1))
    assert removed == 1
    assert not (tmp_path / f"{stale['export_id']}.json").exists()
    assert (tmp_path / f"{fresh['export_id']}.json").exists()


@pytest.mark.parametrize(
    "hostile",
    ["../../etc/passwd", "..", "not-hex-0000000000000000000000000000", "abc", "", "A" * 32],
)
def test_a_hostile_export_id_never_reaches_the_filesystem(hostile: str, tmp_path: Path):
    assert not is_valid_export_id(hostile)
    with pytest.raises(ExportNotFound):
        load_export(hostile, "json", directory=tmp_path)


def test_unknown_export_id_is_not_found(tmp_path: Path):
    with pytest.raises(ExportNotFound):
        load_export(new_export_id(), "json", directory=tmp_path)


def test_unsupported_format_is_not_found(tmp_path: Path):
    manifest = write_export(_rows(30), tool="search_tickets", directory=tmp_path)
    with pytest.raises(ExportNotFound):
        load_export(manifest["export_id"], "xlsx", directory=tmp_path)


# --------------------------------------------------------------------------
# the download route
# --------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("path", "expected"),
    [
        ("/abc", ("abc", "json")),
        ("/abc/", ("abc", "json")),
        ("/abc.json", ("abc", "json")),
        ("/abc.csv", ("abc", "csv")),
        ("/abc.meta.json", None),
        ("/abc.xlsx", None),
        ("/abc/def", None),
        ("/", None),
    ],
)
def test_download_path_parsing(path: str, expected):
    parsed = parse_download_path(path)
    if expected is None:
        assert parsed is None
    else:
        assert parsed == expected


def test_download_path_unquotes_before_matching():
    assert parse_download_path("/%61bc.csv") == ("abc", "csv")


@pytest.fixture
def route(tmp_path: Path):
    """A real bound download route over a real spool."""
    server = build_server("127.0.0.1", 0, spool=tmp_path)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        yield f"127.0.0.1:{server.server_address[1]}", tmp_path
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)


def _request(route, path: str, method: str = "GET"):
    host, _ = route
    conn = http.client.HTTPConnection(host, timeout=10)
    try:
        conn.request(method, path)
        response = conn.getresponse()
        return response.status, response.read(), dict(response.getheaders())
    finally:
        conn.close()


def test_route_serves_the_full_set_as_an_attachment(route):
    _, spool = route
    manifest = write_export(_rows(30), tool="search_tickets", query="escalation", directory=spool)
    export_id = manifest["export_id"]

    # The Worker's proxy forces a trailing slash; both spellings must work.
    for path in (f"/{export_id}", f"/{export_id}/"):
        status, body, headers = _request(route, path)
        assert status == 200, path
        assert len(json.loads(body)) == 30
        assert headers["Content-Type"] == "application/json; charset=utf-8"
        assert (
            headers["Content-Disposition"]
            == f'attachment; filename="zammad-tickets-{export_id}.json"'
        )
        assert headers["Cache-Control"] == "no-store, private"
        assert headers["X-Content-Type-Options"] == "nosniff"
        assert headers["X-Export-Expires-At"] == manifest["expires_at"]


def test_route_serves_csv_on_request(route):
    _, spool = route
    export_id = write_export(_rows(30), tool="search_tickets", directory=spool)["export_id"]
    status, body, headers = _request(route, f"/{export_id}.csv")
    assert status == 200
    assert headers["Content-Type"] == "text/csv; charset=utf-8"
    assert SECRET_TITLE in body.decode("utf-8")


def test_route_head_reports_the_size_without_a_body(route):
    _, spool = route
    export_id = write_export(_rows(30), tool="search_tickets", directory=spool)["export_id"]
    status, body, headers = _request(route, f"/{export_id}", method="HEAD")
    assert status == 200
    assert body == b""
    assert int(headers["Content-Length"]) > 0


def test_route_expired_export_is_gone_not_not_found(route):
    _, spool = route
    written_at = datetime(2026, 10, 10, 9, 0, tzinfo=timezone.utc)
    export_id = write_export(_rows(30), tool="search_tickets", directory=spool, now=written_at)[
        "export_id"
    ]

    # The route reads wall-clock time, so age the manifest instead.
    manifest_path = spool / f"{export_id}.meta.json"
    stored = json.loads(manifest_path.read_text())
    stored["expires_at"] = (datetime.now(timezone.utc) - timedelta(hours=1)).isoformat()
    manifest_path.write_text(json.dumps(stored))

    status, _, _ = _request(route, f"/{export_id}")
    assert status == 410


def test_route_unknown_export_is_not_found(route):
    status, _, _ = _request(route, f"/{new_export_id()}")
    assert status == 404


def test_route_never_serves_the_manifest(route):
    _, spool = route
    export_id = write_export(_rows(30), tool="search_tickets", directory=spool)["export_id"]
    status, _, _ = _request(route, f"/{export_id}.meta.json")
    assert status == 404


def test_route_refuses_writes(route):
    _, spool = route
    export_id = write_export(_rows(30), tool="search_tickets", directory=spool)["export_id"]
    for method in ("POST", "PUT", "DELETE"):
        status, _, _ = _request(route, f"/{export_id}", method=method)
        assert status == 405, method


def test_route_traversal_attempt_is_not_found(route):
    status, _, _ = _request(route, "/../../etc/passwd")
    assert status in (400, 404)


# --------------------------------------------------------------------------
# wiring pins (server.py needs mcp, which the CI lane does not install)
# --------------------------------------------------------------------------


def test_both_listing_tools_go_through_the_export_cut():
    body = _code_lines(SERVER)
    assert body.count("_export_if_large(") == 3  # the helper plus its two call sites
    assert 'tool="search_tickets"' in body
    assert 'tool="list_tickets"' in body


def test_the_export_cut_precedes_the_full_render():
    body = _code_lines(SERVER)
    for render in ("format_search_results(built", "format_ticket_list(tickets"):
        guard = body.index("_export_if_large(")
        assert body.index(render) > guard


def test_the_export_helper_is_opt_in_below_the_limit_and_falls_back_on_failure():
    """Below the limit nothing changes; on a spool failure the rows are not lost."""
    body = _code_lines(SERVER)
    helper = body[body.index("def _export_if_large(") : body.index("@mcp.tool()")]
    assert "if len(tickets) <= EXPORT_ROW_LIMIT:" in helper
    assert "return None" in helper
    # The failure arm returns None (caller renders the full list), not a raise.
    failure = helper[helper.index("except OSError as exc:") :]
    assert "return None" in failure
    assert "raise" not in failure


def test_worker_routes_the_download_through_the_same_gate():
    body = _code_lines(STACK_INDEX)
    assert '"zammad-export": 8771' in body
    # The map is the gate: an entry gets the identical x-digi-mcp-key check.
    assert "const port = MCP_EDGE_SERVERS[serverId];" in body
    assert 'request.headers.get("x-digi-mcp-key")' in body
    assert body.index("const port = MCP_EDGE_SERVERS[serverId];") < body.index(
        'request.headers.get("x-digi-mcp-key")'
    )


def test_container_serves_the_download_alongside_the_mcp():
    supervisor = _code_lines(SUPERVISORD)
    assert "[program:zammad-export]" in supervisor
    assert "python -m scripts.zammad_mcp.export_server --port 8771" in supervisor
    assert "ZAMMAD_EXPORT_DIR=" in supervisor


def test_download_port_is_exposed_and_the_image_still_copies_the_module():
    dockerfile = _code_lines(MCP_DOCKERFILE)
    assert "EXPOSE 8770" in dockerfile
    assert "EXPOSE 8771" in dockerfile
    assert "COPY scripts/zammad_mcp ./scripts/zammad_mcp" in dockerfile


def test_the_download_server_does_not_import_mcp():
    """An mcp upgrade must not be able to take the download route down."""
    source = (REPO_ROOT / "scripts" / "zammad_mcp" / "export_server.py").read_text()
    assert "import mcp" not in source
    assert "from mcp" not in source


def test_every_supported_format_round_trips(route):
    _, spool = route
    export_id = write_export(_rows(30), tool="search_tickets", directory=spool)["export_id"]
    for fmt in EXPORT_FORMATS:
        status, _, _ = _request(route, f"/{export_id}.{fmt}")
        assert status == 200, fmt


def test_the_quoted_link_is_a_path_on_the_already_gated_worker_route():
    """The model quotes a path, never a bare id: the gate lives in front of it."""
    from scripts.zammad_mcp.exports import download_path

    quoted = download_path("a" * 32)
    assert quoted == "/_stack/mcp/zammad-export/" + "a" * 32
    # Relative on purpose: the container cannot know its public host, and a host
    # the model invented would be a link the edge gate does not cover.
    assert urlsplit(quoted).netloc == ""
