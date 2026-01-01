"""DIG-1210: a locked tenant never exposes the session control tools.

DIG-4459: the same lock also needs a carrier. The corpus map's
``lockSessionControls`` value travels map -> override -> request -> graph
state, and each hop needs its own link. The request model has to declare the
key (the streaming path builds the request from the carrier dict, so an
undeclared key raised and the request never ran) and the initial graph state
has to copy it (an omitted key stays sticky across turns on a session).
"""

from __future__ import annotations

from types import SimpleNamespace

import pytest
from digigraph.corpus_routing import TenantCorpusOverride
from digigraph.graph.research import LOCKED_SESSION_TOOLS, _tool_def_name
from digigraph.graph.state import WorkflowState
from digigraph.http_api.context import _digi_fields_from_request
from digigraph.models import WorkflowRequest
from digigraph.workflow import _initial_graph_state

pytestmark = pytest.mark.unit

#: The corpus map names its research-prompt field ``research_system_prompt``;
#: the request/state carrier is ``research_system_prompt_override``. Every other
#: map field carries its own name.
_CARRIER_RENAME = {"research_system_prompt": "research_system_prompt_override"}

#: A locked tenant, in the production map's camelCase spelling.
_LOCKED_TENANT_MAP = '{"tenant-a":{"digisearchIndex":"tenant_docs","lockSessionControls":true}}'

#: An unlocked tenant (the same map without the lock).
_UNLOCKED_TENANT_MAP = '{"tenant-a":{"digisearchIndex":"tenant_docs"}}'


def test_locked_session_tools_cover_model_mcp_and_toggles() -> None:
    assert LOCKED_SESSION_TOOLS == frozenset(
        {
            "session_set_model",
            "session_upsert_mcp",
            "session_remove_mcp",
            "session_toggle_tool",
            "session_set_search_engine",
        }
    )


def test_tool_def_name_reads_dict_forms_and_objects() -> None:
    assert _tool_def_name({"type": "function", "function": {"name": "digisearch"}}) == "digisearch"
    assert _tool_def_name({"name": "session_set_model"}) == "session_set_model"

    class Tool:
        name = "vault_search_notes"

    assert _tool_def_name(Tool()) == "vault_search_notes"


def test_filter_removes_only_session_controls() -> None:
    tools = [
        {"type": "function", "function": {"name": "digisearch"}},
        {"type": "function", "function": {"name": "session_set_model"}},
        {"type": "function", "function": {"name": "ticket_search_tickets"}},
        {"type": "function", "function": {"name": "session_toggle_tool"}},
    ]
    kept = [t for t in tools if _tool_def_name(t) not in LOCKED_SESSION_TOOLS]
    assert [_tool_def_name(t) for t in kept] == ["digisearch", "ticket_search_tickets"]


def _carrier_for(map_field: str) -> str:
    """The request/state carrier name for a corpus map field."""
    return _CARRIER_RENAME.get(map_field, map_field)


def _locked_tenant_request() -> SimpleNamespace:
    """A request shaped like the one the chat endpoint hands the server."""
    return SimpleNamespace(
        state=SimpleNamespace(
            digi_bearer=None,
            digi_auth=SimpleNamespace(
                subject="",
                key_prefix=None,
                tenant_slug="tenant-a",
                tenant_slug_verified=True,
                project_id=None,
                jti=None,
            ),
        ),
        headers={},
    )


def test_the_server_carrier_dict_builds_a_valid_request(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The server's carrier dict must validate against the request model (DIG-4459).

    The streaming path builds ``WorkflowRequest(**wf_kw)`` from the carrier
    dict, so a key the model does not declare raised "Extra inputs are not
    permitted" and the request never ran.
    """
    monkeypatch.setenv("DIGI_TENANT_CORPUS_MAP", _LOCKED_TENANT_MAP)
    updates = _digi_fields_from_request(_locked_tenant_request())
    assert updates["lock_session_controls"] is True

    wf_extras = {k: v for k, v in updates.items() if v is not None}
    request = WorkflowRequest(prompt="hi", **wf_extras)
    assert request.lock_session_controls is True


def test_the_lock_reaches_the_graph_state(monkeypatch: pytest.MonkeyPatch) -> None:
    """A locked tenant's lock must land in the graph state (DIG-4459).

    ``research.py`` reads ``state.get("lock_session_controls")``, so a request
    that carries the value without the state carrying it is a silent no-lock.
    """
    monkeypatch.setenv("DIGI_TENANT_CORPUS_MAP", _LOCKED_TENANT_MAP)
    updates = _digi_fields_from_request(_locked_tenant_request())
    request = WorkflowRequest(prompt="hi", **{k: v for k, v in updates.items() if v is not None})
    state = _initial_graph_state(request, "wf-locked")
    assert state["lock_session_controls"] is True


def test_an_unlocked_tenant_clears_the_lock_in_state(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The key is always written: a prior turn's lock must not stay sticky."""
    monkeypatch.setenv("DIGI_TENANT_CORPUS_MAP", _UNLOCKED_TENANT_MAP)
    updates = _digi_fields_from_request(_locked_tenant_request())
    request = WorkflowRequest(prompt="hi", **{k: v for k, v in updates.items() if v is not None})
    state = _initial_graph_state(request, "wf-unlocked")
    assert "lock_session_controls" in state
    assert state["lock_session_controls"] is False


def test_every_corpus_map_field_has_a_declared_carrier() -> None:
    """A map field without a request + state carrier breaks the chat (DIG-4459).

    The corpus map reaches the graph state through three hand-written hops:
    map entry -> override field -> request field -> WorkflowState key. A field
    added to the map without a carrier on the request model raised on the
    streaming path; a field copied into the state without one on the request
    model was silently dropped. This pins both hops.
    """
    request_fields = set(WorkflowRequest.model_fields)
    state_fields = set(WorkflowState.__annotations__)
    for map_field in TenantCorpusOverride.model_fields:
        carrier = _carrier_for(map_field)
        assert carrier in request_fields, (
            f"corpus map field {map_field!r} has no WorkflowRequest carrier (expected {carrier!r})"
        )
        assert carrier in state_fields, (
            f"corpus map field {map_field!r} has no WorkflowState key (expected {carrier!r})"
        )


def test_the_carrier_rename_table_has_no_stale_entries() -> None:
    """A stale rename entry would exempt a future map field from the pin."""
    map_fields = set(TenantCorpusOverride.model_fields)
    request_fields = set(WorkflowRequest.model_fields)
    for source, carrier in _CARRIER_RENAME.items():
        assert source in map_fields, f"rename source {source!r} is not a corpus map field"
        assert carrier in request_fields, f"rename target {carrier!r} is not a request field"


def test_the_lock_carrier_default_matches_the_map_model() -> None:
    """The request carrier defaults to False, like the map model it mirrors."""
    assert TenantCorpusOverride.model_fields["lock_session_controls"].default is False
    assert WorkflowRequest.model_fields["lock_session_controls"].default is False
