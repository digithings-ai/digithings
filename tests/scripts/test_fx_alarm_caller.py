"""Unit tests for scripts/fx_alarm_caller.py (DIG-2707).

The ruling of record (DIG-877, comment ``4bc812ef``) names one required failing
test and two one-way properties the caller must keep:

* the int-key round trip (``load_watermarks`` MUST restore int keys, contract §3),
* the write order — watermarks are saved only after the board file succeeds (§4),
* the offline blob pin — ``--check-vendor`` recomputes git's blob sha1 (§5).

The board schema (§6, DIG-728) and the state-document read/first-create shape are
pinned here too, all offline: the board seam is monkeypatched, the vendored copy
is asserted by hash in pure Python.
"""

from __future__ import annotations

import hashlib
import importlib.util
import json
import sys
from pathlib import Path
from typing import (  # score:allow untyped any — dynamically loaded module
    Any,
    Optional,
)

import pytest

pytestmark = pytest.mark.unit

REPO_ROOT = Path(__file__).resolve().parents[2]
SCRIPT = REPO_ROOT / "scripts" / "fx_alarm_caller.py"
VENDORED = REPO_ROOT / "scripts" / "vendor" / "twelve_x" / "fx_alarm_watch.py"

BOARD_ENV_VARS = ("PAPERCLIP_API_URL", "PAPERCLIP_API_KEY", "PAPERCLIP_COMPANY_ID")


def _load() -> Any:
    spec = importlib.util.spec_from_file_location("fx_alarm_caller", SCRIPT)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules["fx_alarm_caller"] = module
    spec.loader.exec_module(module)
    return module


mod = _load()

#: One alarm label straight from the pinned reader — the test never spells the
#: vendor token itself, so the only place the gate sees it is the vendored file
#: the allowlist entry covers.
ALARM_LABEL = sorted(mod.ALARM_LABELS)[0]

CFG = {"base": "https://board.example/api", "key": "k", "company": "co"}


def _issue(number: int, comment_id: Any) -> dict[str, Any]:
    """A shaped GitHub issue row whose labels carry one pinned alarm label."""
    return {
        "number": number,
        "title": f"fx-pipeline stopped producing ({number})",
        "html_url": f"https://github.com/digithings-ai/twelve-x/issues/{number}",
        "updated_at": "2026-10-11T09:00:00Z",
        "newest_comment_id": comment_id,
        "labels": [ALARM_LABEL],
    }


def _clear_board_env(monkeypatch: pytest.MonkeyPatch) -> None:
    for name in BOARD_ENV_VARS:
        monkeypatch.delenv(name, raising=False)


# ---------------------------------------------------------------------------
# int-key contract (contract §3 — the ruling's required failing test)
# ---------------------------------------------------------------------------


def test_load_watermarks_restores_int_keys() -> None:
    restored = mod.load_watermarks({"7": "1001", "10": "2026-10-11T09:00:00Z"})
    assert restored == {7: "1001", 10: "2026-10-11T09:00:00Z"}
    for key in restored:
        assert isinstance(key, int)


def test_load_watermarks_empty_document() -> None:
    assert mod.load_watermarks({}) == {}


def test_cursor_round_trip_reports_on_first_tick_only() -> None:
    """The ruling's required failing test, in shape.

    Write a watermarks document, round-trip it through JSON, load it, call
    ``new_alarms`` on a fixed issue list: the first tick reports, a second tick
    on identical input reports nothing. Without int-key restoration the
    string-keyed copy misses every int lookup and the alarm re-files forever —
    exactly the failure this leaf exists to stop.
    """
    issues = [_issue(7, 1001), _issue(11, None)]  # one with, one without a comment
    watermarks = mod.load_watermarks(json.loads(mod.dump_watermarks({})))
    reported, nxt = mod.new_alarms(issues, watermarks)
    assert reported == [7, 11]
    assert nxt == {7: "1001", 11: "2026-10-11T09:00:00Z"}

    persisted = mod.load_watermarks(json.loads(mod.dump_watermarks(nxt)))
    second, again = mod.new_alarms(issues, persisted)
    assert second == []
    assert again == persisted


def test_new_alarms_re_reports_when_the_cursor_moves() -> None:
    watermarks = mod.load_watermarks(json.loads(mod.dump_watermarks({7: "1001"})))
    reported, nxt = mod.new_alarms([_issue(7, 2002)], watermarks)
    assert reported == [7]
    assert nxt == {7: "2002"}


def test_new_alarms_skips_issues_without_an_alarm_label() -> None:
    plain = _issue(7, 1001)
    plain["labels"] = ["needs-triage"]
    assert mod.new_alarms([plain], {}) == ([], {})


# ---------------------------------------------------------------------------
# write order — save only after the board file succeeded (contract §4)
# ---------------------------------------------------------------------------


def test_run_tick_saves_after_each_successful_deliver() -> None:
    order: list[str] = []
    saved: list[dict[int, str]] = []

    def deliver(number: int) -> None:
        order.append(f"file #{number}")

    def save(watermarks: dict[int, str]) -> None:
        order.append("save")
        saved.append(dict(watermarks))

    assert mod.run_tick([_issue(7, 1001)], {}, deliver=deliver, save=save) == [7]
    assert order == ["file #7", "save"]  # save strictly after the board file
    assert saved == [{7: "1001"}]


def test_run_tick_never_saves_when_the_board_file_fails() -> None:
    order: list[str] = []
    saved: list[dict[int, str]] = []
    issues = [_issue(7, 1001)]

    def deliver(number: int) -> None:
        order.append(f"file #{number}")
        raise RuntimeError("board write failed")

    def save(watermarks: dict[int, str]) -> None:
        order.append("save")
        saved.append(dict(watermarks))

    with pytest.raises(RuntimeError, match="board write failed"):
        mod.run_tick(issues, {}, deliver=deliver, save=save)

    assert saved == []  # nothing was delivered -> the watermark is not recorded


def test_run_tick_records_only_numbers_that_were_delivered() -> None:
    """A board failure mid-batch persists the finished numbers only, so the
    undelivered alarms re-report once on the next tick (contract §4)."""
    order: list[str] = []
    saved: list[dict[int, str]] = []
    issues = [_issue(7, 1001), _issue(11, 1002), _issue(12, 1003)]

    def deliver(number: int) -> None:
        order.append(f"file #{number}")
        if number == 11:
            raise RuntimeError("board write failed")

    def save(watermarks: dict[int, str]) -> None:
        order.append("save")
        saved.append(dict(watermarks))

    with pytest.raises(RuntimeError, match="board write failed"):
        mod.run_tick(issues, {}, deliver=deliver, save=save)

    assert order == ["file #7", "file #11", "save"]  # save still ran for the delivered
    assert saved == [{7: "1001"}]  # 11 (and 12, never attempted) are left out


def test_run_tick_saves_nothing_when_nothing_is_new() -> None:
    calls: list[str] = []
    watermarks = mod.load_watermarks(json.loads(mod.dump_watermarks({7: "1001"})))

    reported = mod.run_tick(
        [_issue(7, 1001)],
        watermarks,
        deliver=lambda number: calls.append(f"file #{number}"),
        save=lambda wm: calls.append("save"),
    )
    assert reported == []
    assert calls == []


# ---------------------------------------------------------------------------
# vendored blob pin (contract §5)
# ---------------------------------------------------------------------------


def test_vendored_copy_is_byte_identical_to_the_pinned_blob() -> None:
    data = VENDORED.read_bytes()
    assert len(data) == 2133
    # the pin literal is asserted here, not merely the module constant: a
    # mutant that re-pins ``VENDOR_BLOB_SHA1`` (or re-vendors the bytes and
    # the constant together) must fail this test, not silently pass it.
    assert mod.VENDOR_BLOB_SHA1 == "0bbd3527e8359c2192f4cdc4837b38a202d132ae"
    assert mod.blob_sha1(data) == mod.VENDOR_BLOB_SHA1


def test_blob_sha1_is_git_blob_hash_not_plain_sha1() -> None:
    data = b"hello\n"
    blob_header = hashlib.sha1(b"blob %d\0" % len(data) + data).hexdigest()
    plain = hashlib.sha1(data).hexdigest()
    assert mod.blob_sha1(data) == blob_header
    assert mod.blob_sha1(data) != plain


def test_check_vendor_passes_on_the_pinned_copy(
    capsys: pytest.CaptureFixture[str],
) -> None:
    assert mod.check_vendor() == 0
    assert "pinned blob" in capsys.readouterr().out


def test_check_vendor_fails_on_drift(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    drifted = tmp_path / "fx_alarm_watch.py"
    drifted.write_bytes(VENDORED.read_bytes() + b"\n# local edit\n")
    monkeypatch.setattr(mod, "VENDOR_PATH", drifted)
    assert mod.check_vendor() == 1
    assert "DRIFT" in capsys.readouterr().err


def test_check_vendor_reports_an_unreadable_file(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(mod, "VENDOR_PATH", tmp_path / "absent.py")
    assert mod.check_vendor() == 2


def test_cli_check_vendor_exits_zero() -> None:
    assert mod.main(["--check-vendor"]) == 0


# ---------------------------------------------------------------------------
# watermark document serialisation
# ---------------------------------------------------------------------------


def test_dump_watermarks_orders_keys_numerically() -> None:
    payload = mod.dump_watermarks({10: "b", 2: "a"})
    raw = json.loads(payload)
    assert raw == {"2": "a", "10": "b"}
    assert list(raw) == ["2", "10"]  # int sort, not lexicographic (str "10" < "2")
    assert payload.endswith("\n")


def test_dump_watermarks_round_trips_through_json_strings() -> None:
    payload = mod.dump_watermarks({7: "1001"})
    assert list(json.loads(payload)) == ["7"]
    assert mod.load_watermarks(json.loads(payload)) == {7: "1001"}


def test_state_document_holds_the_fenced_json_block() -> None:
    wrapped = mod.render_state_document(mod.dump_watermarks({7: "1001"}))
    assert mod.parse_state_document(wrapped) == {"7": "1001"}


def test_parse_state_document_rejects_an_unfenced_body() -> None:
    with pytest.raises(ValueError, match="no ```json block"):
        mod.parse_state_document("no fence here")
    with pytest.raises(ValueError, match="unterminated"):
        mod.parse_state_document("```json\n{'x': 1}\n")


# ---------------------------------------------------------------------------
# board schema (contract §6, DIG-728)
# ---------------------------------------------------------------------------


def test_board_marker_and_title_follow_the_schema() -> None:
    assert mod.board_marker(42) == "github_issue_number: 42"
    assert mod.STATE_DOCUMENT_KEY == "fx_alarm_watermarks"
    assert mod.board_issue_title(42, "thing broke") == "[FX Alarm] thing broke (#42)"


def test_board_issue_description_carries_the_number_marker() -> None:
    body = mod.board_issue_description(42, "thing broke", "https://x/42")
    assert mod.board_marker(42) in body
    assert "twelve-x" in body  # source_repo side of the (source_repo, number) key
    assert "https://x/42" in body


def _stub_board(
    monkeypatch: pytest.MonkeyPatch,
    rows: list[dict[str, Any]],
    calls: list[tuple[str, str, Any]],
) -> None:
    monkeypatch.setattr(mod, "_list_issues", lambda cfg, query: rows)

    def fake_request(
        cfg: dict[str, str],
        method: str,
        path: str,
        payload: Optional[dict[str, Any]] = None,
    ) -> Any:
        calls.append((method, path, payload))
        return None

    monkeypatch.setattr(mod, "_request", fake_request)


def test_open_board_issue_is_commented_not_refiled(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    rows = [
        {
            "id": "board-1",
            "status": "todo",
            "description": mod.board_issue_description(7, "t", "u"),
        }
    ]
    calls: list[tuple[str, str, Any]] = []
    _stub_board(monkeypatch, rows, calls)
    deliver = mod.build_board_deliver(CFG, {7: {"title": "t", "html_url": "u"}})

    deliver(7)

    assert len(calls) == 1
    (method, path, payload) = calls[0]
    assert (method, path) == ("POST", "/issues/board-1/comments")
    assert "re-raised" in payload["body"]


def test_no_board_issue_files_one_with_the_schema_shape(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls: list[tuple[str, str, Any]] = []
    _stub_board(monkeypatch, [], calls)
    deliver = mod.build_board_deliver(CFG, {7: _issue(7, 1001)})

    deliver(7)

    assert len(calls) == 1
    (method, path, payload) = calls[0]
    assert (method, path) == ("POST", f"/companies/{CFG['company']}/issues")
    assert payload["title"] == "[FX Alarm] fx-pipeline stopped producing (7) (#7)"
    assert payload["priority"] == "high"
    assert payload["labels"] == ["fx-alarm", "twelve-x", "needs-triage"]
    assert mod.board_marker(7) in payload["description"]


def test_closed_board_issue_is_refiled_fresh(monkeypatch: pytest.MonkeyPatch) -> None:
    """§6: comment if the board issue is open, file a fresh one when a human
    closed it. ``done`` is the closed state on this board."""
    rows = [
        {
            "id": "board-1",
            "status": "done",
            "description": mod.board_issue_description(7, "t", "u"),
        }
    ]
    calls: list[tuple[str, str, Any]] = []
    _stub_board(monkeypatch, rows, calls)
    deliver = mod.build_board_deliver(CFG, {7: {"title": "t", "html_url": "u"}})

    deliver(7)

    assert len(calls) == 1
    (method, path, payload) = calls[0]
    assert (method, path) == ("POST", f"/companies/{CFG['company']}/issues")
    assert payload["title"] == "[FX Alarm] t (#7)"


def test_find_board_issue_ignores_loose_query_matches(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The marker is verified client-side: a description without the exact
    ``github_issue_number`` line never counts as the board issue for n."""
    rows = [{"id": "other", "status": "todo", "description": "FX Alarm chatter"}]
    calls: list[tuple[str, str, Any]] = []
    _stub_board(monkeypatch, rows, calls)
    deliver = mod.build_board_deliver(CFG, {7: _issue(7, 1001)})

    deliver(7)

    assert calls[0][0:2] == ("POST", f"/companies/{CFG['company']}/issues")


def test_find_board_issue_requires_the_source_repo_line(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The find-or-create key is (source_repo, github_issue_number): a
    description carrying only the number marker (another vendored repo's
    board issue with colliding numbering) is not the board issue for n."""
    number_only = mod.board_marker(7)
    rows = [
        {
            "id": "foreign",
            "status": "todo",
            "description": f"other repo's alarm\n\n{number_only}\n",
        }
    ]
    calls: list[tuple[str, str, Any]] = []
    _stub_board(monkeypatch, rows, calls)
    deliver = mod.build_board_deliver(CFG, {7: _issue(7, 1001)})

    deliver(7)

    assert calls[0][0:2] == ("POST", f"/companies/{CFG['company']}/issues")
    assert "source_repo: twelve-x" in calls[0][2]["description"]


def test_prefer_open_board_issue_when_a_closed_one_also_matches(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A human closed the board issue, then a duplicate open one exists:
    the caller must comment on the OPEN row, not file a third copy."""
    open_row = {
        "id": "board-open",
        "status": "todo",
        "description": mod.board_issue_description(7, "t", "u"),
    }
    closed_row = {
        "id": "board-closed",
        "status": "done",
        "description": mod.board_issue_description(7, "t", "u"),
    }
    calls: list[tuple[str, str, Any]] = []
    _stub_board(monkeypatch, [closed_row, open_row], calls)
    deliver = mod.build_board_deliver(CFG, {7: {"title": "t", "html_url": "u"}})

    deliver(7)

    assert len(calls) == 1
    (method, path, payload) = calls[0]
    assert (method, path) == ("POST", "/issues/board-open/comments")
    assert "re-raised" in payload["body"]


# ---------------------------------------------------------------------------
# state document store / read
# ---------------------------------------------------------------------------


def test_resolve_state_issue_returns_the_exact_identifier_match(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The host issue is matched on the exact ``identifier`` field, so a loose
    ``?q=`` hit whose identifier merely contains the string is not it."""
    rows = [
        {"id": "noise", "identifier": "DIG-25940"},
        {"id": "host", "identifier": "DIG-2594"},
    ]
    monkeypatch.setattr(mod, "_list_issues", lambda cfg, query: rows)
    assert mod.resolve_state_issue(CFG) == "host"


def test_resolve_state_issue_refuses_an_ambiguous_board(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        mod,
        "_list_issues",
        lambda cfg, query: [
            {"id": "a", "identifier": "DIG-2594"},
            {"id": "b", "identifier": "DIG-2594"},
        ],
    )
    with pytest.raises(RuntimeError, match="found 2"):
        mod.resolve_state_issue(CFG)


def test_resolve_state_issue_refuses_a_missing_host_issue(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        mod,
        "_list_issues",
        lambda cfg, query: [{"id": "other", "identifier": "DIG-2594-xyz"}],
    )
    with pytest.raises(RuntimeError, match="found 0"):
        mod.resolve_state_issue(CFG)


def test_read_state_is_empty_when_the_document_does_not_exist(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(mod, "_request", lambda cfg, method, path, payload=None: [])
    assert mod.read_state(CFG, "host-issue") == {}


def test_read_state_restores_int_keys_from_the_document(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    body = mod.render_state_document(mod.dump_watermarks({7: "1001", 11: "abc"}))
    rows = [{"key": mod.STATE_DOCUMENT_KEY, "body": body}]
    monkeypatch.setattr(mod, "_request", lambda cfg, method, path, payload=None: rows)
    assert mod.read_state(CFG, "host-issue") == {7: "1001", 11: "abc"}


def _store_once(monkeypatch: pytest.MonkeyPatch, rows: list[dict[str, Any]]) -> Any:
    """Run one ``store(payload)`` with a stubbed board; return the PUT payload."""
    calls: list[tuple[str, str, Any]] = []

    def fake_request(
        cfg: dict[str, str],
        method: str,
        path: str,
        payload: Optional[dict[str, Any]] = None,
    ) -> Any:
        calls.append((method, path, payload))
        if method == "GET":
            return rows
        return None

    monkeypatch.setattr(mod, "_request", fake_request)
    store = mod.build_document_store(CFG, "host-issue")
    store(mod.dump_watermarks({8: "2002"}))

    assert len(calls) == 2, calls
    (method, path, sent) = calls[-1]
    assert method == "PUT"
    assert path == f"/issues/host-issue/documents/{mod.STATE_DOCUMENT_KEY}"
    assert sent["format"] == "markdown"
    assert mod.parse_state_document(sent["body"]) == {"8": "2002"}
    return sent


def test_store_first_run_creates_the_document_without_base_revision(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The watermarks document does not exist until the caller's first run
    (contract §1): the create path must not send a ``baseRevisionId``."""
    sent = _store_once(monkeypatch, [])
    assert "baseRevisionId" not in sent


def test_store_sends_base_revision_when_the_document_exists(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    body = mod.render_state_document(mod.dump_watermarks({7: "1001"}))
    rows = [{"key": mod.STATE_DOCUMENT_KEY, "body": body, "latestRevisionId": "rev-1"}]

    sent = _store_once(monkeypatch, rows)

    assert sent["baseRevisionId"] == "rev-1"


# ---------------------------------------------------------------------------
# offline CLI smoke (no gh, no board)
# ---------------------------------------------------------------------------


def test_cli_issues_file_dry_run_needs_no_credentials(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    _clear_board_env(monkeypatch)
    monkeypatch.delenv("PAPERCLIP_RUN_ID", raising=False)
    issues_path = tmp_path / "issues.json"
    issues_path.write_text(json.dumps([_issue(7, 1001)]), encoding="utf-8")

    assert mod.main(["--issues-file", str(issues_path)]) == 0
    assert "would report #7" in capsys.readouterr().out


def test_cli_combined_flags_still_assert_the_vendor_pin(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """``--check-vendor`` next to ``--issues-file`` asserts the pin before
    the run, so a drifted vendored copy can never be evaluated on."""
    issues_path = tmp_path / "issues.json"
    issues_path.write_text(json.dumps([_issue(7, 1001)]), encoding="utf-8")
    assert mod.main(["--check-vendor", "--issues-file", str(issues_path)]) == 0
    out = capsys.readouterr().out
    assert "pinned blob" in out
    assert "would report #7" in out


def test_list_issues_encodes_the_query(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A space in the query must not reach the URL raw: urllib raises
    ``http.client.InvalidURL`` on control characters before any request."""
    seen: list[tuple[str, str, Any]] = []

    def fake_request(cfg, method, path, payload=None):
        seen.append((method, path, payload))
        return []

    monkeypatch.setattr(mod, "_request", fake_request)
    mod._list_issues(CFG, "FX Alarm")
    (method, path, payload) = seen[0]
    assert (method, payload) == ("GET", None)
    assert "q=FX%20Alarm" in path


def test_save_watermarks_round_trip_silences_the_next_tick(
    tmp_path: Path,
) -> None:
    """Full offline shape: ``save_watermarks`` persists through a sink, the
    document loads back through JSON, and the same feed stays silent."""
    issues_path = tmp_path / "issues.json"
    issues_path.write_text(json.dumps([_issue(7, 1001)]), encoding="utf-8")
    state_path = tmp_path / "state.json"

    watermarks = mod.load_watermarks(json.loads(mod.dump_watermarks({})))
    first, nxt = mod.new_alarms(json.loads(issues_path.read_text()), watermarks)
    assert first == [7]

    mod.save_watermarks(lambda payload: state_path.write_text(payload), nxt)

    persisted = mod.load_watermarks(json.loads(state_path.read_text()))
    second, _ = mod.new_alarms(json.loads(issues_path.read_text()), persisted)
    assert second == []
