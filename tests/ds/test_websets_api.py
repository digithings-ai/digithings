"""Phase D websets HTTP + MCP + orchestrator + EXA shim (#4066, Task 7).

Pins the T7 surfaces over the landed T1-T6 stack:

- the § Interfaces HTTP routes (`POST /v1/websets` 202 running, polls to idle;
  items/events cursors; enrichment cap 400 `enrichment_limit_exceeded`; monitor
  create/list/trigger; webhook create/rotate with the one-time secret; cancel;
  CSV/JSON export) plus the shared digibase error envelope on every failure;
- the two T6 carry fixes: the terminal-status gate on `add_search` /
  `trigger_monitor` / `add_enrichment` (`webset_terminal`, 409) and
  `verification_mode` persistence/threading (a `rules` webset stays `rules`
  through refreshes);
- the six unprefixed `websets_*` MCP tools (registration only — the ops
  themselves are exercised through the HTTP/orchestrator round trips);
- the three-part orchestrator wiring: `digisearch_websets_*` manifest entries,
  `ORCHESTRATOR_TOOL_NAMES`, and the `api_orchestrator_invoke` dispatch branches;
- the EXA websets shim (dormant without `EXA_API_KEY`, the vendored
  `401 Upgrade to a Pro plan` fixture mapped to
  ``ExaWebsetsProRequiredError(ExaError)``, and the documented request
  translation recorded against a mocked 201).

Offline only: the pinned recall seams (``search_web`` / ``fetch_markdown``) and
the digillm client are stubbed, every test opens a real sqlite file under
``tmp_path``, and the scheduler seam is an inline test scheduler that drives the
run on the request thread (the real lifespan TaskGroup + ``WEBSET_TASKS``
registry is exercised by ``test_lifespan_scheduler_drives_to_idle``).
``@pytest.mark.unit`` on every test.
"""

from __future__ import annotations

import asyncio
import io
import json
import time as _time
from collections.abc import Generator
from pathlib import Path
from typing import Any

import polars as pl
import pytest
from digisearch.web_search.models import WebSearchRequest, WebSearchResponse, WebSearchResult
from digisearch.websets import runner as runner_module
from digisearch.websets import service
from digisearch.websets.enrich import ENRICH_MODEL_ENV
from digisearch.websets.models import VerificationCriterion, Webset
from digisearch.websets.runner import backfill_enrichment, run_webset_async
from digisearch.websets.store import WebsetStore, WebsetStoreError
from digisearch.websets.verify import VERIFY_MODEL_ENV
from fastapi.testclient import TestClient

from digisearch import web_exa
from tests.digi_test_jwt import auth_headers

pytestmark = pytest.mark.unit

_FIXTURES = Path(__file__).parent / "fixtures" / "websets"

_URL_A = "https://alpha.example.com/one"
_URL_B = "https://beta.example.com/two"
_URL_METADATA = "https://169.254.169.254/latest/meta-data"
_URL_CGNAT = "https://100.64.0.1/hook"
_URL_PUBLIC = "https://93.184.216.34/hooks/one"

_CRITERIA = [{"name": "photonics", "rule": "company is a photonics startup"}]
_RULES_CRITERIA = [{"name": "funding", "rule": "keyword: Series A"}]

_MARKDOWN = {
    _URL_A: "# Alpha Photonics\nSeries A closed 2025-07-01.",
    _URL_B: "# Beta Photonics\nSeries A closed 2025-08-01.",
}

_TOOL_NAMES = {
    "websets_create",
    "websets_get",
    "websets_add_search",
    "websets_list_items",
    "websets_events",
    "websets_export",
}

_ORCHESTRATOR_NAMES = {
    "digisearch_websets_create",
    "digisearch_websets_get",
    "digisearch_websets_add_search",
    "digisearch_websets_list_items",
    "digisearch_websets_events",
    "digisearch_websets_export",
}


# ── stubs + fixtures ─────────────────────────────────────────────────────────


class _RecallStub:
    """Stubbed ``search_web``: records requests, returns a fixed result set."""

    def __init__(self, urls: list[str]) -> None:
        self.urls = urls
        self.requests: list[WebSearchRequest] = []

    def __call__(self, req: WebSearchRequest, config: Any = None) -> WebSearchResponse:
        self.requests.append(req)
        results = [
            WebSearchResult(url=url, title=url.rstrip("/").rsplit("/", 1)[-1]) for url in self.urls
        ]
        return WebSearchResponse(query=req.query, results=results, provider="stub")


class _FetchStub:
    """Stubbed non-indexing ``fetch_markdown``: canned markdown per URL."""

    def __init__(self, markdown: dict[str, str]) -> None:
        self.markdown = dict(markdown)
        self.requested: list[str] = []

    def __call__(self, url: str, **kwargs: Any) -> str:
        self.requested.append(url)
        return self.markdown.get(url, "")


def _response(content: str) -> Any:
    import types

    message = types.SimpleNamespace(content=content)
    return types.SimpleNamespace(choices=[types.SimpleNamespace(message=message)])


class _StubLLM:
    """Duck-typed digillm boundary: every verdict passes, enrichments resolve."""

    def completion(self, model: str, messages: list[dict[str, str]], **kwargs: Any) -> Any:
        schema_name = kwargs["response_format"]["json_schema"]["name"]
        content = messages[-1]["content"]
        url = content.split("CANDIDATE URL: ", 1)[-1].split("\n", 1)[0].strip()
        if schema_name == "webset_verification":
            verdicts = [
                {
                    "criterion_index": index,
                    "passed": True,
                    "reasoning": f"stub verdict for {url}",
                    "references": [{"url": url, "title": "", "excerpt": "stub"}],
                }
                for index in range(max(1, len(self._criteria(content))))
            ]
            return _response(json.dumps({"verdicts": verdicts}))
        if schema_name == "webset_enrichment":
            return _response(
                json.dumps(
                    {
                        "value": "resolved by stub",
                        "citations": [{"url": url, "title": "", "excerpt": "stub quote"}],
                        "reasoning": "stub",
                    }
                )
            )
        raise AssertionError(f"unexpected digillm schema {schema_name!r}")

    @staticmethod
    def _criteria(content: str) -> list[str]:
        import re

        block = content.split("CRITERIA:\n", 1)[-1].split("\n\nCANDIDATE PAGE", 1)[0]
        return re.findall(r"^\d+\. \[", block, re.MULTILINE)


class _InlineScheduler:
    """Test scheduler: drives each pass inline on the calling (request) thread.

    ``schedule_run`` / ``schedule_backfill`` execute the real runner with the
    stubbed seams and the stub digillm client, so a route request observes the
    settled webset on the next read without spawning background tasks (the real
    lifespan TaskGroup + ``WEBSET_TASKS`` registry is pinned separately).
    """

    def __init__(self) -> None:
        self.runs: list[tuple[str, str]] = []
        self.backfills: list[tuple[str, str]] = []
        self.llm_client = _StubLLM()

    def schedule_run(self, webset_id: str, *, verification_mode: str = "llm") -> None:
        self.runs.append((webset_id, verification_mode))
        asyncio.run(
            run_webset_async(
                webset_id, verification_mode=verification_mode, llm_client=self.llm_client
            )
        )

    def schedule_backfill(self, webset_id: str, enrichment_id: str) -> None:
        self.backfills.append((webset_id, enrichment_id))
        asyncio.run(backfill_enrichment(webset_id, enrichment_id, llm_client=self.llm_client))


@pytest.fixture(autouse=True)
def llm_env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv(VERIFY_MODEL_ENV, "test/verify-model")
    monkeypatch.setenv(ENRICH_MODEL_ENV, "test/enrich-model")


@pytest.fixture
def api(monkeypatch, tmp_path) -> Generator[tuple[TestClient, _InlineScheduler]]:
    """Authenticated client over a tmp-file store with stubbed seams + inline runs."""
    import digisearch.server as srv

    db = tmp_path / "websets.sqlite3"
    monkeypatch.setenv("DIGISEARCH_WEBSETS_DB", str(db))
    monkeypatch.setattr(runner_module, "search_web", _RecallStub([_URL_A, _URL_B]))
    monkeypatch.setattr(runner_module, "fetch_markdown", _FetchStub(_MARKDOWN))
    scheduler = _InlineScheduler()
    service.set_scheduler(scheduler)
    try:
        yield TestClient(srv.app, headers=auth_headers()), scheduler
    finally:
        service.set_scheduler(None)
        runner_module.WEBSET_TASKS.clear()


def _create(client: TestClient, **overrides: object) -> dict:
    body: dict[str, Any] = {"query": "photonics startups", "count": 2, "criteria": _CRITERIA}
    body.update(overrides)
    r = client.post("/v1/websets", json=body)
    assert r.status_code == 202, r.text
    return r.json()


def _seed_running_webset(tmp_path) -> Webset:
    """Store-level seed: a ``running`` webset with no searches (gate tests)."""
    store = WebsetStore(db_path=str(tmp_path / "websets.sqlite3"))
    return store.create_webset(Webset(criteria=[VerificationCriterion(name="c", rule="r")]))


# ── HTTP create / read ───────────────────────────────────────────────────────


@pytest.mark.unit
def test_create_returns_202_running_and_polls_to_idle(api):
    client, scheduler = api
    created = _create(client)
    assert created["object"] == "webset"
    assert created["status"] == "running"
    assert created["id"].startswith("ws_")
    assert len(created["searches"]) == 1
    assert scheduler.runs == [(created["id"], "llm")]

    got = client.get(f"/v1/websets/{created['id']}")
    assert got.status_code == 200, got.text
    body = got.json()
    assert body["status"] == "idle"
    assert [s["status"] for s in body["searches"]] == ["idle"]


@pytest.mark.unit
def test_routes_require_auth(monkeypatch, tmp_path):
    import digisearch.server as srv

    client = TestClient(srv.app)  # no JWT
    r = client.post("/v1/websets", json={"query": "q", "criteria": _CRITERIA})
    assert r.status_code in (401, 403), r.text


@pytest.mark.unit
def test_get_unknown_webset_and_unknown_monitor(api):
    client, _ = api
    missing = client.get("/v1/websets/ws_00000000000000000000000000000000")
    assert missing.status_code == 404
    assert missing.json()["error"]["code"] == "webset_not_found"

    real = _create(client)
    no_monitor = client.post(f"/v1/websets/{real['id']}/monitors/wsm_x/trigger")
    assert no_monitor.status_code == 404
    assert no_monitor.json()["error"]["code"] == "monitor_not_found"


@pytest.mark.unit
def test_items_list_newest_first_and_unknown_cursor(api):
    client, _ = api
    created = _create(client)

    items = client.get(f"/v1/websets/{created['id']}/items")
    assert items.status_code == 200, items.text
    body = items.json()
    assert body["next_cursor"] is None
    assert {item["url"] for item in body["items"]} == {_URL_A, _URL_B}
    assert {item["verification"] for item in body["items"]} == {"verified"}

    bad = client.get(f"/v1/websets/{created['id']}/items?cursor=nope")
    assert bad.status_code == 404
    assert bad.json()["error"]["code"] == "cursor_not_found"


@pytest.mark.unit
def test_events_oldest_first_and_unknown_cursor(api):
    client, _ = api
    created = _create(client)

    events = client.get(f"/v1/websets/{created['id']}/events")
    assert events.status_code == 200, events.text
    body = events.json()
    kinds = [event["type"] for event in body["events"]]
    assert kinds.count("item.created") == 2
    assert kinds[-1] == "webset.idle"
    assert body["next_cursor"] is None

    last = body["events"][-1]["id"]
    tail = client.get(f"/v1/websets/{created['id']}/events?after={last}")
    assert tail.status_code == 200
    assert tail.json()["events"] == []

    bad = client.get(f"/v1/websets/{created['id']}/events?after=nope")
    assert bad.status_code == 404
    assert bad.json()["error"]["code"] == "cursor_not_found"


# ── HTTP writes ──────────────────────────────────────────────────────────────


@pytest.mark.unit
def test_add_search_and_trigger_are_202(api):
    client, _ = api
    created = _create(client)

    search = client.post(
        f"/v1/websets/{created['id']}/searches", json={"query": "more photonics", "count": 1}
    )
    assert search.status_code == 202, search.text
    assert search.json()["object"] if "object" in search.json() else True
    assert search.json()["status"] == "running"
    assert search.json()["query"] == "more photonics"

    monitor = client.post(f"/v1/websets/{created['id']}/monitors", json={"interval_seconds": 60})
    assert monitor.status_code == 201, monitor.text
    assert monitor.json()["webset_id"] == created["id"]

    listed = client.get(f"/v1/websets/{created['id']}/monitors")
    assert listed.status_code == 200
    assert [m["id"] for m in listed.json()["monitors"]] == [monitor.json()["id"]]

    triggered = client.post(f"/v1/websets/{created['id']}/monitors/{monitor.json()['id']}/trigger")
    assert triggered.status_code == 202, triggered.text
    assert triggered.json()["status"] == "idle"  # sticky: refresh is observed via searches
    stored = client.get(f"/v1/websets/{created['id']}").json()
    assert len(stored["searches"]) == 3  # initial + add_search + monitor refresh


@pytest.mark.unit
def test_enrichment_limit_exceeded_is_400(api):
    client, _ = api
    created = _create(client)
    for index in range(10):
        r = client.post(
            f"/v1/websets/{created['id']}/enrichments",
            json={"name": f"field{index}", "type": "text"},
        )
        assert r.status_code == 201, r.text
    eleventh = client.post(
        f"/v1/websets/{created['id']}/enrichments",
        json={"name": "overflow", "type": "text"},
    )
    assert eleventh.status_code == 400, eleventh.text
    assert eleventh.json()["error"]["code"] == "enrichment_limit_exceeded"


@pytest.mark.unit
def test_remove_enrichment_204(api):
    client, _ = api
    created = _create(client)
    attached = client.post(
        f"/v1/websets/{created['id']}/enrichments", json={"name": "blurb", "type": "text"}
    )
    assert attached.status_code == 201, attached.text
    removed = client.delete(f"/v1/websets/{created['id']}/enrichments/{attached.json()['id']}")
    assert removed.status_code == 204, removed.text

    missing = client.delete(f"/v1/websets/{created['id']}/enrichments/wse_missing")
    assert missing.status_code == 404
    assert missing.json()["error"]["code"] == "enrichment_not_found"


@pytest.mark.unit
def test_webhook_create_rotate_and_ssrf_rejections(api):
    client, _ = api
    created = _create(client)

    hook = client.post(
        f"/v1/websets/{created['id']}/webhooks",
        json={"url": _URL_PUBLIC, "events": ["webset.idle"]},
    )
    assert hook.status_code == 201, hook.text
    body = hook.json()
    assert body["url"] == _URL_PUBLIC
    assert body["secret"]
    assert body["previous_secret"] is None

    rotated = client.post(f"/v1/websets/{created['id']}/webhooks/{body['webhook_id']}/rotate")
    assert rotated.status_code == 200, rotated.text
    assert rotated.json()["secret"] != body["secret"]
    assert rotated.json()["previous_secret"] == body["secret"]
    assert rotated.json()["previous_expires_at"] is not None

    for private in (_URL_METADATA, _URL_CGNAT):
        rejected = client.post(
            f"/v1/websets/{created['id']}/webhooks",
            json={"url": private, "events": ["webset.idle"]},
        )
        assert rejected.status_code == 422, rejected.text
        assert rejected.json()["error"]["code"] == "webhook_url_private"

    malformed = client.post(
        f"/v1/websets/{created['id']}/webhooks", json={"url": "http://example.com/x"}
    )
    assert malformed.status_code == 422
    assert malformed.json()["error"]["code"] == "webhook_url_private"

    missing = client.post(f"/v1/websets/{created['id']}/webhooks", json={"url": "", "events": []})
    assert missing.status_code == 422
    assert missing.json()["error"]["code"] in ("webhook_url_required", "validation_error")

    unknown = client.post(
        "/v1/websets/ws_00000000000000000000000000000000/webhooks",
        json={"url": _URL_PUBLIC, "events": []},
    )
    assert unknown.status_code == 404
    assert unknown.json()["error"]["code"] == "webset_not_found"

    # The T6 review nit: rotation on an unknown webset is webset_not_found.
    rotate_unknown = client.post(
        f"/v1/websets/ws_00000000000000000000000000000000/webhooks/{body['webhook_id']}/rotate"
    )
    assert rotate_unknown.status_code == 404
    assert rotate_unknown.json()["error"]["code"] == "webset_not_found"


@pytest.mark.unit
def test_cancel_stays_idle_sticky_and_export(api):
    client, _ = api
    created = _create(client)

    exported = client.get(f"/v1/websets/{created['id']}/export?format=csv")
    assert exported.status_code == 200, exported.text
    assert exported.headers["content-type"].startswith("text/csv")
    frame = pl.read_csv(io.StringIO(exported.text))
    assert frame.height == 2
    assert set(frame["url"].to_list()) == {_URL_A, _URL_B}

    as_json = client.get(f"/v1/websets/{created['id']}/export?format=json")
    assert as_json.status_code == 200
    assert as_json.headers["content-type"].startswith("application/json")
    assert {item["url"] for item in as_json.json()["items"]} == {_URL_A, _URL_B}

    # Cancel on an already-idle webset keeps the sticky success terminal (T2);
    # the running-webset cancel path is covered by the terminal-gate test.
    cancelled = client.post(f"/v1/websets/{created['id']}/cancel")
    assert cancelled.status_code == 200, cancelled.text
    assert cancelled.json()["status"] == "idle"


@pytest.mark.unit
def test_export_empty_and_bad_format(api, monkeypatch):
    client, _ = api
    monkeypatch.setattr(runner_module, "search_web", _RecallStub([]))
    created = _create(client, count=1)

    empty = client.get(f"/v1/websets/{created['id']}/export?format=json")
    assert empty.status_code == 200, empty.text
    assert empty.json()["items"] == []

    empty_csv = client.get(f"/v1/websets/{created['id']}/export?format=csv")
    assert empty_csv.status_code == 200
    assert pl.read_csv(io.StringIO(empty_csv.text)).height == 0

    bad = client.get(f"/v1/websets/{created['id']}/export?format=xml")
    assert bad.status_code == 422, bad.text
    assert bad.json()["error"]["code"] == "validation_error"


@pytest.mark.unit
def test_create_rejects_datatap_and_invalid_inputs(api):
    client, _ = api
    datatap = client.post(
        "/v1/websets",
        json={"query": "q", "criteria": _CRITERIA, "workspace_id": "datatap"},
    )
    assert datatap.status_code == 422
    assert datatap.json()["error"]["code"] == "datatap_websets_disabled"

    no_criteria = client.post("/v1/websets", json={"query": "q", "criteria": []})
    assert no_criteria.status_code == 422
    assert no_criteria.json()["error"]["code"] == "invalid_criteria"

    bad_mode = client.post(
        "/v1/websets",
        json={"query": "q", "criteria": _CRITERIA, "verification_mode": "bogus"},
    )
    assert bad_mode.status_code == 422
    assert bad_mode.json()["error"]["code"] == "invalid_verification_mode"


# ── T6 carries ───────────────────────────────────────────────────────────────


@pytest.mark.unit
def test_terminal_webset_rejects_new_work(api, tmp_path):
    client, _ = api
    webset = _seed_running_webset(tmp_path)
    monitor = client.post(f"/v1/websets/{webset.id}/monitors", json={"interval_seconds": 60})
    assert monitor.status_code == 201, monitor.text
    cancelled = client.post(f"/v1/websets/{webset.id}/cancel")
    assert cancelled.status_code == 200, cancelled.text
    assert cancelled.json()["status"] == "cancelled"

    searches = client.post(f"/v1/websets/{webset.id}/searches", json={"query": "more", "count": 1})
    assert searches.status_code == 409, searches.text
    assert searches.json()["error"]["code"] == "webset_terminal"

    enrichments = client.post(
        f"/v1/websets/{webset.id}/enrichments", json={"name": "late", "type": "text"}
    )
    assert enrichments.status_code == 409
    assert enrichments.json()["error"]["code"] == "webset_terminal"

    trigger = client.post(f"/v1/websets/{webset.id}/monitors/{monitor.json()['id']}/trigger")
    assert trigger.status_code == 409
    assert trigger.json()["error"]["code"] == "webset_terminal"


@pytest.mark.unit
def test_failed_webset_rejects_new_work(api, tmp_path):
    client, _ = api
    webset = _seed_running_webset(tmp_path)
    store = WebsetStore(db_path=str(tmp_path / "websets.sqlite3"))
    store.set_webset_status(webset.id, "failed")

    r = client.post(f"/v1/websets/{webset.id}/searches", json={"query": "more", "count": 1})
    assert r.status_code == 409, r.text
    assert r.json()["error"]["code"] == "webset_terminal"


@pytest.mark.unit
def test_verification_mode_persists_and_threads_through_refreshes(api):
    client, scheduler = api
    created = _create(client, verification_mode="rules", criteria=_RULES_CRITERIA)
    assert created["verification_mode"] == "rules"

    got = client.get(f"/v1/websets/{created['id']}").json()
    assert got["verification_mode"] == "rules"
    assert [s["verification_mode"] for s in got["searches"]] == ["rules"]

    search = client.post(
        f"/v1/websets/{created['id']}/searches", json={"query": "more", "count": 1}
    )
    assert search.status_code == 202, search.text
    assert search.json()["verification_mode"] == "rules"

    monitor = client.post(f"/v1/websets/{created['id']}/monitors", json={"interval_seconds": 60})
    assert monitor.status_code == 201
    trigger = client.post(f"/v1/websets/{created['id']}/monitors/{monitor.json()['id']}/trigger")
    assert trigger.status_code == 202, trigger.text
    stored = client.get(f"/v1/websets/{created['id']}").json()
    assert stored["searches"][-1]["verification_mode"] == "rules"

    assert scheduler.runs == [
        (created["id"], "rules"),
        (created["id"], "rules"),
        (created["id"], "rules"),
    ]


_INTERNAL_CODES = (
    "webset_not_settled",
    "transition_invalid",
    "invalid_event_kind",
    "invalid_webhook_delivery",
    "event_not_stored",
    "webhook_id_required",
)


@pytest.mark.unit
@pytest.mark.parametrize("internal_code", _INTERNAL_CODES)
def test_store_internal_codes_never_surface(api, monkeypatch, internal_code):
    client, _ = api

    def boom(self: WebsetStore, webset_id: str) -> Any:
        raise WebsetStoreError("internal invariant", code=internal_code)

    monkeypatch.setattr(WebsetStore, "get_webset", boom)
    r = client.get("/v1/websets/ws_00000000000000000000000000000000")
    assert r.status_code == 500, r.text
    body = r.json()
    assert body["error"]["code"] == "internal_error"
    assert internal_code not in r.text


@pytest.mark.unit
def test_webhook_secret_missing_maps_to_internal_error(api, monkeypatch):
    client, _ = api
    created = _create(client)

    def leak(*args: Any, **kwargs: Any) -> Any:
        raise service.WebsetServiceError("ledger state", code="webhook_secret_missing")

    monkeypatch.setattr(service, "get_webset", leak)
    r = client.get(f"/v1/websets/{created['id']}")
    assert r.status_code == 500, r.text
    assert r.json()["error"]["code"] == "internal_error"
    assert "webhook_secret_missing" not in r.text


@pytest.mark.unit
def test_rate_limit_budgets_key_webset_routes():
    import digisearch.server as srv

    wid = "ws_00000000000000000000000000000000"
    assert srv._rate_limit_for("/v1/websets") == (10, 60)
    assert srv._rate_limit_for(wid.join(["/v1/websets/", ""])) == (30, 60)
    assert srv._rate_limit_for(f"/v1/websets/{wid}/searches") == (10, 60)
    assert srv._rate_limit_for(f"/v1/websets/{wid}/items") == (30, 60)
    assert srv._rate_limit_for(f"/v1/websets/{wid}/events") == (30, 60)
    assert srv._rate_limit_for(f"/v1/websets/{wid}/enrichments") == (30, 60)
    assert srv._rate_limit_for(f"/v1/websets/{wid}/enrichments/wse_x") == (30, 60)
    assert srv._rate_limit_for(f"/v1/websets/{wid}/monitors") == (10, 60)
    assert srv._rate_limit_for(f"/v1/websets/{wid}/monitors/wsm_x/trigger") == (10, 60)
    assert srv._rate_limit_for(f"/v1/websets/{wid}/webhooks") == (10, 60)
    assert srv._rate_limit_for(f"/v1/websets/{wid}/webhooks/wh_x/rotate") == (10, 60)
    assert srv._rate_limit_for(f"/v1/websets/{wid}/cancel") == (10, 60)
    assert srv._rate_limit_for(f"/v1/websets/{wid}/export") == (10, 60)


# ── lifespan scheduler ───────────────────────────────────────────────────────


@pytest.mark.unit
def test_lifespan_scheduler_drives_to_idle(monkeypatch, tmp_path):
    import digisearch.server as srv

    db = tmp_path / "websets.sqlite3"
    monkeypatch.setenv("DIGISEARCH_WEBSETS_DB", str(db))
    monkeypatch.setattr(srv, "get_webset_store", lambda: WebsetStore(db_path=str(db)))
    monkeypatch.setattr(runner_module, "search_web", _RecallStub([_URL_A, _URL_B]))
    monkeypatch.setattr(runner_module, "fetch_markdown", _FetchStub(_MARKDOWN))
    client = TestClient(srv.app, headers=auth_headers())
    with client:
        created = _create(client)
        deadline = _time.monotonic() + 5.0
        status = "running"
        while _time.monotonic() < deadline:
            status = client.get(f"/v1/websets/{created['id']}").json()["status"]
            if status != "running":
                break
            _time.sleep(0.02)
        assert status == "idle"
    assert runner_module.WEBSET_TASKS == {}


# ── MCP tools ────────────────────────────────────────────────────────────────


@pytest.mark.unit
def test_mcp_websets_tools_registered():
    pytest.importorskip("mcp.server.fastmcp")
    from digisearch import mcp_server

    sync_names = {tool.name for tool in mcp_server.mcp._tool_manager.list_tools()}
    assert _TOOL_NAMES <= sync_names
    async_tools = asyncio.run(mcp_server.mcp.list_tools())
    assert _TOOL_NAMES <= {tool.name for tool in async_tools}


@pytest.mark.unit
def test_mcp_websets_round_trip(api, monkeypatch, tmp_path):
    from digisearch import mcp_server

    db = tmp_path / "websets.sqlite3"
    monkeypatch.setattr(mcp_server, "get_webset_store", lambda: WebsetStore(db_path=str(db)))
    created = json.loads(
        mcp_server.websets_create(
            query="photonics startups",
            count=2,
            criteria_json=json.dumps(_CRITERIA),
        )
    )
    assert created["status"] == "running"
    assert created["id"].startswith("ws_")

    got = json.loads(mcp_server.websets_get(created["id"]))
    assert got["counts"]["verified"] == 2

    search = json.loads(
        mcp_server.websets_add_search(created["id"], query="more photonics", count=1)
    )
    assert search["status"] == "running"

    items = mcp_server.websets_list_items(created["id"])
    assert _URL_A in items and _URL_B in items

    events = mcp_server.websets_events(created["id"])
    assert "item.created" in events

    exported = mcp_server.websets_export(created["id"], format="json")
    assert _URL_A in exported

    missing = mcp_server.websets_get("ws_00000000000000000000000000000000")
    assert "webset_not_found" in missing

    bad_json = mcp_server.websets_create(query="q", criteria_json="{not json}")
    assert "criteria_json" in bad_json


# ── orchestrator wiring ──────────────────────────────────────────────────────


@pytest.mark.unit
def test_orchestrator_constants_and_manifest():
    from digisearch.orchestrator_tools import (
        ORCHESTRATOR_TOOL_NAMES,
        build_orchestrator_tool_manifest,
    )

    assert _ORCHESTRATOR_NAMES <= set(ORCHESTRATOR_TOOL_NAMES)
    tools = {t["function"]["name"]: t for t in build_orchestrator_tool_manifest()}
    assert _ORCHESTRATOR_NAMES <= set(tools)
    assert tools["digisearch_websets_create"]["function"]["parameters"]["required"] == ["query"]
    assert tools["digisearch_websets_get"]["function"]["parameters"]["required"] == ["webset_id"]
    assert tools["digisearch_websets_add_search"]["function"]["parameters"]["required"] == [
        "webset_id",
        "query",
    ]


@pytest.mark.unit
def test_orchestrator_websets_round_trip(api):
    client, _ = api
    created = client.post(
        "/v1/orchestrator_invoke",
        json={
            "tool": "digisearch_websets_create",
            "arguments": {"query": "photonics startups", "count": 2, "criteria": _CRITERIA},
        },
    )
    assert created.status_code == 200, created.text
    assert created.json()["ok"] is True
    webset = created.json()["data"]
    assert webset["status"] == "running"

    got = client.post(
        "/v1/orchestrator_invoke",
        json={"tool": "digisearch_websets_get", "arguments": {"webset_id": webset["id"]}},
    )
    assert got.status_code == 200, got.text
    assert got.json()["ok"] is True
    assert got.json()["data"]["counts"]["verified"] == 2

    search = client.post(
        "/v1/orchestrator_invoke",
        json={
            "tool": "digisearch_websets_add_search",
            "arguments": {"webset_id": webset["id"], "query": "more photonics", "count": 1},
        },
    )
    assert search.status_code == 200, search.text
    assert search.json()["ok"] is True
    assert search.json()["data"]["status"] == "running"

    items = client.post(
        "/v1/orchestrator_invoke",
        json={"tool": "digisearch_websets_list_items", "arguments": {"webset_id": webset["id"]}},
    )
    assert items.status_code == 200, items.text
    assert items.json()["ok"] is True
    assert len(items.json()["data"]["items"]) == 2

    events = client.post(
        "/v1/orchestrator_invoke",
        json={"tool": "digisearch_websets_events", "arguments": {"webset_id": webset["id"]}},
    )
    assert events.status_code == 200, events.text
    assert events.json()["ok"] is True
    assert any(e["type"] == "webset.idle" for e in events.json()["data"]["events"])

    exported = client.post(
        "/v1/orchestrator_invoke",
        json={
            "tool": "digisearch_websets_export",
            "arguments": {"webset_id": webset["id"], "format": "csv"},
        },
    )
    assert exported.status_code == 200, exported.text
    assert exported.json()["ok"] is True
    assert exported.json()["data"]["format"] == "csv"
    assert _URL_A in exported.json()["data"]["content"]


@pytest.mark.unit
def test_orchestrator_websets_errors_are_ok_false(api):
    client, _ = api
    for tool in _ORCHESTRATOR_NAMES:
        r = client.post(
            "/v1/orchestrator_invoke",
            json={"tool": tool, "arguments": {"webset_id": "ws_missing"}},
        )
        assert r.status_code == 200, r.text
        assert r.json()["ok"] is False, f"{tool} did not reach its branch"
        assert "Unknown orchestrator tool" not in r.text

    missing_id = client.post(
        "/v1/orchestrator_invoke",
        json={"tool": "digisearch_websets_get", "arguments": {}},
    )
    assert missing_id.status_code == 200
    assert missing_id.json()["ok"] is False
    assert "webset_id" in missing_id.json()["error"]


# ── EXA websets shim ─────────────────────────────────────────────────────────


@pytest.mark.unit
def test_shim_dormant_without_key(monkeypatch):
    from digisearch.websets.providers import exa_websets

    monkeypatch.delenv("EXA_API_KEY", raising=False)
    assert exa_websets.is_exa_websets_configured() is False
    with pytest.raises(web_exa.ExaNotConfiguredError):
        exa_websets.create_webset("q", criteria=_CRITERIA)


@pytest.mark.unit
def test_shim_401_pro_required_is_exa_error_subclass(monkeypatch):
    from digisearch.websets.providers import exa_websets

    body = json.loads((_FIXTURES / "exa_401_pro_required.json").read_text(encoding="utf-8"))
    monkeypatch.setenv("EXA_API_KEY", "test-key")

    class FakeResp:
        status_code = 401
        text = json.dumps(body)

        def json(self) -> dict:
            return body

    seen: dict[str, Any] = {}

    def fake_request(method, url, json=None, headers=None, timeout=None):
        seen["method"] = method
        seen["url"] = url
        seen["payload"] = json
        seen["headers"] = headers
        return FakeResp()

    monkeypatch.setattr(exa_websets.httpx, "request", fake_request)

    assert issubclass(exa_websets.ExaWebsetsProRequiredError, web_exa.ExaError)
    with pytest.raises(exa_websets.ExaWebsetsProRequiredError):
        exa_websets.create_webset("agtech startups", criteria=_CRITERIA)
    try:
        exa_websets.create_webset("agtech startups", criteria=_CRITERIA)
        raise AssertionError("expected ExaWebsetsProRequiredError")
    except web_exa.ExaError:
        pass  # existing `except ExaError` handlers keep catching it

    assert seen["method"] == "POST"
    assert seen["url"].endswith("/websets/v0/websets")
    assert seen["payload"]["search"]["query"] == "agtech startups"
    assert seen["payload"]["search"]["count"] == 10
    assert seen["payload"]["search"]["criteria"] == [{"description": c["rule"]} for c in _CRITERIA]
    assert seen["headers"]["x-api-key"] == "test-key"


@pytest.mark.unit
def test_shim_normalizes_create_response(monkeypatch):
    from digisearch.websets.providers import exa_websets

    monkeypatch.setenv("EXA_API_KEY", "test-key")
    payload = {
        "id": "exa_webset_1",
        "object": "webset",
        "status": "running",
        "searches": [
            {
                "id": "exa_search_1",
                "object": "webset_search",
                "status": "running",
                "websetId": "exa_webset_1",
                "query": "agtech startups",
                "count": 5,
                "criteria": [{"description": "US company", "successRate": 0}],
            }
        ],
        "enrichments": [],
        "createdAt": "2026-09-14T00:00:00Z",
        "updatedAt": "2026-09-14T00:00:00Z",
    }

    class FakeResp:
        status_code = 201
        text = ""

        def json(self) -> dict:
            return payload

    monkeypatch.setattr(
        exa_websets.httpx,
        "request",
        lambda method, url, json=None, headers=None, timeout=None: FakeResp(),
    )
    webset = exa_websets.create_webset(
        "agtech startups",
        count=5,
        criteria=[{"name": "us", "rule": "US company"}],
        enrichments=[{"name": "size", "type": "number"}],
    )
    assert webset.status == "running"
    assert webset.backend == "exa"
    assert len(webset.searches) == 1
    assert webset.searches[0].status == "running"
    assert webset.searches[0].query == "agtech startups"
    assert webset.searches[0].count == 5

    got = exa_websets.get_webset("exa_webset_1")
    assert got.status == "running"

    idle_payload = dict(payload, status="idle")
    monkeypatch.setattr(
        exa_websets.httpx,
        "request",
        lambda method, url, json=None, headers=None, timeout=None: type(
            "R", (), {"status_code": 200, "text": "", "json": lambda self: idle_payload}
        )(),
    )
    assert exa_websets.get_webset("exa_webset_1").status == "idle"
