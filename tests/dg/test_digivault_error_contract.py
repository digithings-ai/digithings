"""Cross-package contract: digigraph mirrors digivault no-prefix error strings."""

from __future__ import annotations

from types import SimpleNamespace

import pytest
from digigraph.orchestration.builtin import (
    _DIGIVAULT_GET_NOTE_NO_PREFIX_ERROR,
    _DIGIVAULT_SEARCH_NO_PREFIX_ERROR,
)

from digivault import server as digivault_server

pytestmark = pytest.mark.unit


def _fake_request() -> SimpleNamespace:
    """Stand-in for FastAPI's Request — only `.state.digi_auth` is read."""
    return SimpleNamespace(
        state=SimpleNamespace(digi_auth=SimpleNamespace(scopes=[], tenant_slug=None))
    )


def _set_d1_env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("D1_ACCOUNT_ID", "acct")
    monkeypatch.setenv("D1_API_TOKEN", "tok")
    monkeypatch.setenv("D1_DATABASE_MAP", '{"clients/digithings": "db-1"}')


def test_digivault_no_prefix_error_strings_match_server_literals(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Substitution of either constant must not silently diverge from digivault.

    Was: `assert _CONST in inspect.getsource(digivault_server)` — a bare substring
    check against the module's source text. That proves the literal appears
    SOMEWHERE in the file (a comment, a docstring, dead code) — not that it is the
    error digivault's server actually RETURNS when a caller hits the no-prefix
    path. Rewritten to call the real orchestrator_invoke entrypoint under the exact
    condition that reaches each branch (D1 configured, path_prefix normalizes to
    empty) and assert on the real response, for both digivault_search_notes and
    digivault_get_note.
    """
    monkeypatch.delenv("DIGIVAULT_ROOT", raising=False)
    _set_d1_env(monkeypatch)
    monkeypatch.setattr(
        digivault_server, "_open_d1_store", lambda prefix: pytest.fail("must not open a store")
    )

    search_resp = digivault_server.orchestrator_invoke(
        digivault_server.OrchestratorInvokeRequest(
            tool="digivault_search_notes",
            # No `path_prefix` key at all — which is exactly what digigraph sends
            # when the corpus has no prefix (`args_eff["path_prefix"] =
            # context.vault_path_prefix`, and corpus_routing coalesces an empty
            # prefix to None). A literal `""` used to reach this branch too, but
            # digivault now rejects a *present* prefix that normalizes to empty
            # with a 400 before the D1 check (#2359), so `""` would test the
            # parse-time guard rather than this no-prefix contract.
            arguments={"query": "jwt"},
        ),
        _fake_request(),
    )
    assert search_resp.ok is False
    assert search_resp.error == _DIGIVAULT_SEARCH_NO_PREFIX_ERROR
    assert _DIGIVAULT_SEARCH_NO_PREFIX_ERROR == (
        "path_prefix is required when the D1 backend is configured"
    )

    get_note_resp = digivault_server.orchestrator_invoke(
        digivault_server.OrchestratorInvokeRequest(
            tool="digivault_get_note",
            arguments={"vault_path": "clients/digithings/arch", "path_prefix": ""},
        ),
        _fake_request(),
    )
    assert get_note_resp.ok is False
    assert get_note_resp.error == _DIGIVAULT_GET_NOTE_NO_PREFIX_ERROR
    assert _DIGIVAULT_GET_NOTE_NO_PREFIX_ERROR == "path_prefix is required for digivault_get_note"
