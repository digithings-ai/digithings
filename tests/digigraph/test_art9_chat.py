"""Art. 9 admission on the digigraph chat route (DIG-1082, leaf 9).

The gate in this leaf is **not** "the response was an error". A refused chat
request has to be proven to have stopped *before* the LangGraph checkpointer,
because ``chat_completions`` never raises on a workflow failure: it returns a
200 whose content is ``Error: ...``. So every refusal assertion here is backed by

* a recorder installed on the one place the workflow reads a checkpointer from
  (``graph._checkpointer_instance``, consumed by ``build_workflow_graph``),
* a control proving the recorder is a real saver that does record, and
* a differential pair: the same app, the same recorder, one body refused with
  zero writes and the workflow never entered, one all-prose body admitted and the
  workflow entered.

The boundary is field names, not free text. v1 has no lawful free-text
screening (§5.6), so an all-prose chat body is admitted and must stay admitted.
"""

from __future__ import annotations

from typing import Any

import pytest
from digibase.art9 import check_route, screen_request
from digigraph.graph import graph as graph_mod
from digigraph.models import WorkflowResult
from fastapi.testclient import TestClient
from langgraph.checkpoint.memory import InMemorySaver

from digigraph import server as digigraph_server
from tests.digi_test_jwt import auth_headers

pytestmark = pytest.mark.unit

_CHAT_PATH = "/v1/chat/completions"
_CHAT_SCOPE = ["digigraph:chat"]

#: A key whose NAME alone trips the health category. `diagnosis` is a `health`
#: field-name token and the match is a substring test over the lowercased key, so
#: the value is irrelevant. `ChatCompletionRequest` is ``extra="forbid"``, which
#: means the same body would be a 422 without admission in front of validation —
#: so a 403 here also proves admission runs first.
_REFUSED_BODY: dict[str, Any] = {
    "model": "digigraph-rag",
    "messages": [{"role": "user", "content": "Summarise the quarter."}],
    "patient_diagnosis": "type 2 diabetes",
}

#: An all-prose body made only of fields the model declares. It must be admitted:
#: there is no lawful free-text screening in v1.
_PROSE_BODY: dict[str, Any] = {
    "model": "digigraph-rag",
    "messages": [{"role": "user", "content": "Summarise the trading desk's last quarter."}],
}

#: The three keys the registry deliberately keeps allowed because they only
#: *contain* a section 5.5 name without being one: `health_status`, `trade_union`
#: and `diagnosis` are the names on file, and these three keys match none.
_STAY_ALLOWED_KEYS = ("healthcheck_url", "trades", "undiagnosed")


class _RecordingCheckpointer(InMemorySaver):
    """A real ``BaseCheckpointSaver`` that records every write handed to it.

    It has to be a genuine saver rather than a duck-typed stand-in: LangGraph's
    ``ensure_valid_checkpointer`` rejects anything that is not an instance of
    ``BaseCheckpointSaver``, and a rejected checkpointer surfaces as a compile
    ``TypeError`` — which would make "zero checkpointer writes" true for the
    wrong reason.
    """

    def __init__(self) -> None:
        super().__init__()
        self.writes: list[str] = []

    def put(self, config, checkpoint, metadata, new_versions):
        self.writes.append("put")
        return super().put(config, checkpoint, metadata, new_versions)

    async def aput(self, config, checkpoint, metadata, new_versions):
        self.writes.append("aput")
        return await super().aput(config, checkpoint, metadata, new_versions)

    def put_writes(self, config, writes, task_id, task_path=""):
        self.writes.append("put_writes")
        return super().put_writes(config, writes, task_id, task_path)

    async def aput_writes(self, config, writes, task_id, task_path=""):
        self.writes.append("aput_writes")
        return await super().aput_writes(config, writes, task_id, task_path)


@pytest.fixture
def recording_checkpointer(monkeypatch: pytest.MonkeyPatch) -> _RecordingCheckpointer:
    """Install the recorder on the single interception point the workflow uses.

    ``build_workflow_graph`` is the only caller of ``get_checkpointer`` in
    ``digigraph/src``; it reads the module global, so seeding that global is the
    interception. The compiled-graph cache is a module global too and is reset
    here (and restored by monkeypatch) so no test can compile against another
    test's checkpointer.
    """
    spy = _RecordingCheckpointer()
    monkeypatch.setattr(graph_mod, "_checkpointer_instance", spy)
    monkeypatch.setattr(graph_mod, "get_store", lambda: None)
    monkeypatch.setattr(graph_mod, "_workflow_graph_cache", None)
    return spy


@pytest.fixture
def client() -> TestClient:
    return TestClient(digigraph_server.app)


def _stub_workflow(calls: list[Any]):
    """Stand in for the workflow entry point and record that it was reached."""

    def _run(req: Any) -> WorkflowResult:
        calls.append(req)
        return WorkflowResult(success=True, message="stubbed")

    return _run


def _post(client: TestClient, body: dict[str, Any], *, auth: bool = True):
    headers = auth_headers(scopes=_CHAT_SCOPE) if auth else {}
    return client.post(_CHAT_PATH, json=body, headers=headers)


# --------------------------------------------------------------------------- #
# the gate
# --------------------------------------------------------------------------- #


def test_a_chat_body_tripping_a_field_name_is_refused_before_the_checkpointer(
    client: TestClient,
    recording_checkpointer: _RecordingCheckpointer,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls: list[Any] = []
    monkeypatch.setattr(digigraph_server, "run_digigraph_workflow", _stub_workflow(calls))

    response = _post(client, _REFUSED_BODY)

    assert response.status_code == 403
    envelope = response.json()["error"]
    # The reason is the detector's own, not a constant copied into this test.
    assert screen_request(_REFUSED_BODY).reason == "art9:health:field_name"
    assert envelope["code"] == "art9:health:field_name"
    assert envelope["service"] == "digigraph"
    # THE GATE: nothing was checkpointed, and the workflow was never entered.
    assert recording_checkpointer.writes == []
    assert calls == []


def test_admission_runs_ahead_of_authentication_on_the_chat_route(
    client: TestClient,
    recording_checkpointer: _RecordingCheckpointer,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Art. 9 must wrap DigiAuthMiddleware, or a 401 masks the refusal.

    ``DigiAuthMiddleware`` answers an unauthenticated chat request with 401
    before the router runs. Were admission mounted inside it, the refused body
    would come back 401 and "the response was an error" would be satisfied while
    the checkpointer assertion went untested — a refusal nobody can see is not a
    refusal. FastAPI inserts each ``add_middleware`` at index 0, so the LAST call
    is the OUTERMOST; the property that matters is therefore the relative order of
    the two named middlewares, not an absolute index. Index 0 belongs to the
    ``@app.middleware("http")`` decorators that run later in ``server.py``
    (lines 106, 150, 277, 302), which are transparent context wrappers and cannot
    mask anything.
    """
    calls: list[Any] = []
    monkeypatch.setattr(digigraph_server, "run_digigraph_workflow", _stub_workflow(calls))

    order = [m.cls.__name__ for m in digigraph_server.app.user_middleware]
    assert order.count("Art9AdmissionMiddleware") == 1
    assert order.count("DigiAuthMiddleware") == 1
    assert order.index("Art9AdmissionMiddleware") < order.index("DigiAuthMiddleware")

    response = _post(client, _REFUSED_BODY, auth=False)

    assert response.status_code == 403
    assert response.json()["error"]["code"] == "art9:health:field_name"
    assert recording_checkpointer.writes == []
    assert calls == []


# --------------------------------------------------------------------------- #
# the zero has to be non-vacuous
# --------------------------------------------------------------------------- #


def test_the_recorder_is_the_one_the_workflow_reads_and_it_records(
    recording_checkpointer: _RecordingCheckpointer,
) -> None:
    """Control: the spy is reachable AND a write through it is recorded."""
    assert graph_mod.get_checkpointer() is recording_checkpointer

    config = {"configurable": {"thread_id": "art9-probe", "checkpoint_ns": ""}}
    checkpoint = {
        "v": 1,
        "id": "chk-art9-probe",
        "ts": "2026-10-10T00:00:00+00:00",
        "channel_values": {},
        "channel_versions": {},
        "versions_seen": {},
    }
    recording_checkpointer.put(config, checkpoint, {}, {})

    assert recording_checkpointer.writes == ["put"]


def test_the_compiled_workflow_graph_carries_the_recording_checkpointer(
    recording_checkpointer: _RecordingCheckpointer,
) -> None:
    """Control: the graph the chat handler would run checkpoints into the spy.

    This is what makes ``writes == []`` above a statement about the real
    workflow rather than about an object nothing was ever going to use.
    """
    compiled = graph_mod.build_workflow_graph()

    assert compiled.checkpointer is recording_checkpointer


# --------------------------------------------------------------------------- #
# the boundary: field names, never free text
# --------------------------------------------------------------------------- #


def test_an_all_prose_chat_body_is_admitted_and_reaches_the_workflow(
    client: TestClient,
    recording_checkpointer: _RecordingCheckpointer,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Differential pair for the gate: same app, same spy, admitted body.

    Here the workflow entry point IS reached. So the zero writes asserted for the
    refused body are attributable to the refusal, not to the stub short-circuiting
    a checkpointer that would never have been used.
    """
    calls: list[Any] = []
    monkeypatch.setattr(digigraph_server, "run_digigraph_workflow", _stub_workflow(calls))

    assert screen_request(_PROSE_BODY).decision == "allow"
    response = _post(client, _PROSE_BODY)

    assert response.status_code == 200
    assert len(calls) == 1


def test_keys_that_only_contain_a_section_5_5_name_stay_allowed_in_a_chat_body(
    client: TestClient,
    recording_checkpointer: _RecordingCheckpointer,
) -> None:
    """`healthcheck_url`, `trades` and `undiagnosed` are not refusals.

    They arrive as EXTRA keys the model forbids, so the honest reading of a 422
    here is "admission let it through and validation caught it" — which is the
    boundary this leaf draws. A 403 would mean Art. 9 over-matched.
    """
    for key in _STAY_ALLOWED_KEYS:
        assert screen_request({key: "probe"}).decision == "allow", key

    response = _post(client, {**_PROSE_BODY, **{k: "probe" for k in _STAY_ALLOWED_KEYS}})

    assert response.status_code == 422
    assert response.json() != {"error": {"code": "art9:health:field_name"}}


# --------------------------------------------------------------------------- #
# why the body is screened at all
# --------------------------------------------------------------------------- #


def test_the_chat_route_is_screened_through_the_concrete_path_fallback() -> None:
    """Pin the mechanism, so the gate is not accidentally routed around.

    digigraph mounts its whole ``/v1`` router, so the chat route is not a flat
    entry on the app and the middleware's route-template lookup yields
    ``<unmatched>``. Screening only happens because it re-takes ``check_route``
    on the CONCRETE path, which the registry knows. If a future FastAPI flattens
    the router this test fails loudly rather than letting the fallback rot into a
    claim nobody re-checks.
    """
    decision = check_route("digigraph", _CHAT_PATH)

    assert decision.prefix == "/v1/chat"
    assert decision.refused is False

    flat = [
        route.path
        for route in digigraph_server.app.router.routes
        if getattr(route, "path", None) == _CHAT_PATH
    ]
    assert flat == []
