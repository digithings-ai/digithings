"""Phase D webset service facade + export (#4066, Task 6) — offline unit suite.

Pins the synchronous facade over the landed T1-T5 modules and the polars export
shapes from the spec
(``docs/superpowers/specs/2026-09-14-oss-websearch-phaseD-verify-enrich.md``
§ Interfaces, § Webhook delivery):

- ``create_webset`` persists a ``running`` webset with its initial search, threads
  ``verification_mode`` to the scheduler and rejects bad input with the spec's
  stable codes (``invalid_criteria`` / ``invalid_verification_mode`` /
  ``datatap_websets_disabled`` / ``enrichment_limit_exceeded``);
- the run-scheduler seam is a recording stub here: no test drives a background
  task implicitly (the server lifespan installs the real one at T7);
- ``list_items`` pages newest-first and surfaces ``cursor_not_found``;
  ``add_search`` inherits the webset's criteria; ``add_enrichment`` attaches
  (status ``running``) + schedules the backfill, caps at 10, and
  ``remove_enrichment`` retains resolved item values;
- monitors carry the tick-driven refresh cadence: ``WebsetMonitor`` with the
  ``paused`` switch (and no ``status`` field), ``list_monitors`` newest-first,
  ``set_monitor_paused`` rewriting the monitor, and ``trigger_monitor`` opening
  a new search generation;
- ``add_webhook`` returns a one-time server-generated secret and enforces the
  Phase C SSRF/private-IP rejection (https-only, public addresses), identical
  codes/message text; ``rotate_webhook_secret`` keeps the old secret valid for
  the 24h overlap window;
- ``list_events`` cursor-pages oldest-first with ``after=``;
- ``cancel_webset`` flips the webset and settles every non-terminal search
  ``cancelled``;
- ``export_webset`` returns ``(content, media_type)``: JSON retains per-field
  citations, CSV parses with polars as one row per verified item (rejected items
  excluded, citations column carries URLs);
- the documented error-code mapping: the spec's stable list plus the carried
  ``enrichment_not_found`` / ``webhook_not_found`` / ``item_not_found`` /
  ``webhook_secret_missing``; store-internal ``webset_not_settled`` /
  ``transition_invalid`` never surface.

Offline: the two pinned recall seams (``search_web`` / ``fetch_markdown``) and
the digillm client are stubbed for the end-to-end export flow; every test opens
a real sqlite file under ``tmp_path``. ``@pytest.mark.unit`` on every test.
"""

from __future__ import annotations

import asyncio
import io
import json
import re
import types
from collections.abc import Generator
from datetime import UTC, datetime, timedelta
from typing import Any

import polars as pl
import pytest
from digisearch.monitors.delivery import sign_webhook_body
from digisearch.web_search.models import WebSearchRequest, WebSearchResponse, WebSearchResult
from digisearch.websets import runner as runner_module
from digisearch.websets import service
from digisearch.websets.enrich import ENRICH_MODEL_ENV
from digisearch.websets.events import verify_webhook_signature
from digisearch.websets.models import (
    EnrichedField,
    VerificationCriterion,
    Webset,
    WebsetEvent,
    WebsetItem,
    WebsetMonitor,
    WebsetSearch,
)
from digisearch.websets.runner import run_webset_async
from digisearch.websets.service import WebsetNotFoundError, WebsetServiceError
from digisearch.websets.store import WebsetStore, WebsetStoreError
from digisearch.websets.verify import VERIFY_MODEL_ENV
from pydantic import ValidationError

pytestmark = pytest.mark.unit

_URL_A = "https://alpha.example.com/one"
_URL_B = "https://beta.example.com/two"
_URL_REJECT = "https://reject.example.com/no"
_URL_PUBLIC = "https://93.184.216.34/hooks/one"
_URL_MONITOR = "https://93.184.216.34/hooks/monitor"

_CRITERION = VerificationCriterion(name="photonics", rule="company is a photonics startup")

_MARKDOWN = {
    _URL_A: "# Alpha Photonics\nSeries A closed 2025-07-01.",
    _URL_B: "# Beta Photonics\nSeries A closed 2025-08-01.",
    _URL_REJECT: "# Reject Corp\nUnrelated business.",
}


# ── stubs + fixtures ─────────────────────────────────────────────────────────


class _RecordingScheduler:
    """Records schedule intent instead of spawning background tasks (T7 seam)."""

    def __init__(self) -> None:
        self.runs: list[tuple[str, str]] = []
        self.backfills: list[tuple[str, str]] = []

    def schedule_run(self, webset_id: str, *, verification_mode: str = "llm") -> None:
        self.runs.append((webset_id, verification_mode))

    def schedule_backfill(self, webset_id: str, enrichment_id: str) -> None:
        self.backfills.append((webset_id, enrichment_id))


@pytest.fixture
def scheduler() -> Generator[_RecordingScheduler]:
    recorder = _RecordingScheduler()
    service.set_scheduler(recorder)
    try:
        yield recorder
    finally:
        service.set_scheduler(None)


@pytest.fixture
def llm_env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv(VERIFY_MODEL_ENV, "test/verify-model")
    monkeypatch.setenv(ENRICH_MODEL_ENV, "test/enrich-model")


def _response(content: str) -> Any:
    message = types.SimpleNamespace(content=content)
    return types.SimpleNamespace(choices=[types.SimpleNamespace(message=message)])


def _candidate_url(content: str) -> str:
    match = re.search(r"CANDIDATE URL: (\S+)", content)
    return match.group(1) if match else ""


def _criteria_count(content: str) -> int:
    block = content.split("CRITERIA:\n", 1)[-1].split("\n\nCANDIDATE PAGE", 1)[0]
    return len(re.findall(r"^\d+\. \[", block, re.MULTILINE))


class _StubLLM:
    """Duck-typed digillm boundary for the export flow (rejects *reject* URLs)."""

    def __init__(self) -> None:
        self.calls: list[tuple[str, str]] = []

    def completion(self, model: str, messages: list[dict[str, str]], **kwargs: Any) -> Any:
        schema_name = kwargs["response_format"]["json_schema"]["name"]
        content = messages[-1]["content"]
        url = _candidate_url(content)
        self.calls.append((schema_name, url))
        if schema_name == "webset_verification":
            passed = "reject" not in url
            verdicts = [
                {
                    "criterion_index": index,
                    "passed": passed,
                    "reasoning": f"stub verdict for {url}",
                    "references": [{"url": url, "title": "", "excerpt": "stub"}],
                }
                for index in range(max(1, _criteria_count(content)))
            ]
            return _response(json.dumps({"verdicts": verdicts}))
        if schema_name == "webset_enrichment":
            value: Any = 42 if "'score'" in content else "resolved by stub"
            return _response(
                json.dumps(
                    {
                        "value": value,
                        "citations": [{"url": url, "title": "", "excerpt": "stub quote"}],
                        "reasoning": "stub",
                    }
                )
            )
        raise AssertionError(f"unexpected digillm schema {schema_name!r}")


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


def _store(tmp_path: Any) -> WebsetStore:
    return WebsetStore(db_path=str(tmp_path / "websets.sqlite3"))


def _event(store: WebsetStore, webset_id: str, search_id: str, item_id: str) -> WebsetEvent:
    return store.append_event(
        WebsetEvent(
            webset_id=webset_id,
            type="item.created",
            search_id=search_id,
            item_id=item_id,
            payload={"item_id": item_id},
        )
    )


# ── create_webset ────────────────────────────────────────────────────────────


def test_create_webset_returns_running_with_initial_search(tmp_path, scheduler):
    store = _store(tmp_path)
    webset = service.create_webset(
        query="photonics startups",
        count=5,
        criteria=[{"name": "photonics", "rule": "company is a photonics startup"}],
        enrichments=[{"name": "blurb", "type": "text"}],
        workspace_id="acme",
        store=store,
    )

    assert webset.status == "running"
    assert webset.workspace_id == "acme"
    assert webset.backend == "oss"
    assert len(webset.searches) == 1
    assert webset.searches[0].query == "photonics startups"
    assert webset.searches[0].count == 5
    assert webset.searches[0].criteria[0].name == "photonics"
    assert [d.name for d in webset.enrichments] == ["blurb"]
    assert scheduler.runs == [(webset.id, "llm")]

    stored = service.get_webset(webset.id, store=store)
    assert stored.searches[0].id == webset.searches[0].id
    assert stored.enrichments[0].status == "running"


def test_create_webset_threads_the_verification_mode(tmp_path, scheduler):
    store = _store(tmp_path)
    webset = service.create_webset(
        query="photonics startups",
        criteria=[_CRITERION],
        verification_mode="rules",
        store=store,
    )
    assert scheduler.runs == [(webset.id, "rules")]


def test_create_webset_rejects_out_of_range_count(tmp_path, monkeypatch, scheduler):
    db_path = tmp_path / "never-created.sqlite3"
    monkeypatch.setenv("DIGISEARCH_WEBSETS_DB", str(db_path))
    for bad in (0, 101):
        with pytest.raises(ValidationError):
            service.create_webset(query="q", count=bad, criteria=[_CRITERION])
    assert scheduler.runs == []
    assert not db_path.exists()


def test_create_webset_rejects_invalid_inputs(tmp_path, scheduler):
    store = _store(tmp_path)

    with pytest.raises(WebsetServiceError) as ei:
        service.create_webset(query="q", criteria=[], store=store)
    assert ei.value.code == "invalid_criteria"

    with pytest.raises(WebsetServiceError) as ei:
        service.create_webset(
            query="q", criteria=[dict(name=f"c{i}", rule="r") for i in range(6)], store=store
        )
    assert ei.value.code == "invalid_criteria"

    with pytest.raises(WebsetServiceError) as ei:
        service.create_webset(
            query="q", criteria=[_CRITERION], verification_mode="bogus", store=store
        )
    assert ei.value.code == "invalid_verification_mode"

    with pytest.raises(WebsetServiceError) as ei:
        service.create_webset(
            query="q",
            criteria=[_CRITERION],
            enrichments=[{"name": f"f{i}", "type": "text"} for i in range(11)],
            store=store,
        )
    assert ei.value.code == "enrichment_limit_exceeded"

    assert scheduler.runs == []


def test_create_webset_rejects_datatap_workspace(tmp_path, scheduler):
    store = _store(tmp_path)
    with pytest.raises(WebsetServiceError) as ei:
        service.create_webset(query="q", criteria=[_CRITERION], workspace_id="datatap", store=store)
    assert ei.value.code == "datatap_websets_disabled"
    assert scheduler.runs == []


def test_create_webset_resolves_the_env_store(tmp_path, monkeypatch, scheduler):
    db_path = tmp_path / "env-websets.sqlite3"
    monkeypatch.setenv("DIGISEARCH_WEBSETS_DB", str(db_path))
    webset = service.create_webset(query="q", criteria=[_CRITERION])
    assert db_path.exists()
    assert service.get_webset(webset.id).id == webset.id


# ── get_webset / list_items ──────────────────────────────────────────────────


def test_get_webset_round_trips_and_unknown_raises_not_found(tmp_path):
    store = _store(tmp_path)
    webset = store.create_webset(Webset(criteria=[_CRITERION]))

    assert service.get_webset(webset.id, store=store).id == webset.id
    with pytest.raises(WebsetNotFoundError) as ei:
        service.get_webset("ws_missing", store=store)
    assert ei.value.code == "webset_not_found"


def test_list_items_newest_first_filter_and_cursor_errors(tmp_path):
    store = _store(tmp_path)
    webset = store.create_webset(Webset(criteria=[_CRITERION]))
    base = datetime(2026, 9, 14, 12, 0, tzinfo=UTC)
    seeded = []
    for index in range(3):
        seeded.append(
            store.save_item(
                WebsetItem(
                    webset_id=webset.id,
                    url=f"https://example.com/{index}",
                    verification="verified" if index != 1 else "rejected",
                    created_at=base + timedelta(minutes=index),
                )
            )
        )

    page, cursor = service.list_items(webset.id, limit=2, store=store)
    assert [item.id for item in page] == [seeded[2].id, seeded[1].id]
    assert cursor == seeded[1].id

    page, cursor = service.list_items(webset.id, limit=2, cursor=cursor, store=store)
    assert [item.id for item in page] == [seeded[0].id]
    assert cursor is None

    verified, _ = service.list_items(webset.id, verification="verified", store=store)
    assert {item.id for item in verified} == {seeded[0].id, seeded[2].id}

    with pytest.raises(WebsetServiceError) as ei:
        service.list_items(webset.id, cursor=seeded[1].id + "x", store=store)
    assert ei.value.code == "cursor_not_found"

    with pytest.raises(WebsetNotFoundError):
        service.list_items("ws_missing", store=store)


# ── add_search ───────────────────────────────────────────────────────────────


def test_add_search_inherits_criteria_and_schedules(tmp_path, scheduler):
    store = _store(tmp_path)
    webset = service.create_webset(
        query="photonics startups", count=5, criteria=[_CRITERION], store=store
    )

    inherited = service.add_search(webset.id, query="photonics series a", count=5, store=store)
    assert inherited.query == "photonics series a"
    assert inherited.count == 5
    assert [c.name for c in inherited.criteria] == ["photonics"]
    assert scheduler.runs[-1] == (webset.id, "llm")

    explicit = service.add_search(
        webset.id,
        query="photonics round two",
        count=2,
        criteria=[{"name": "series-a", "rule": "closed a Series A"}],
        store=store,
    )
    assert explicit.count == 2
    assert [c.name for c in explicit.criteria] == ["series-a"]
    assert len(service.get_webset(webset.id, store=store).searches) == 3

    with pytest.raises(WebsetServiceError) as ei:
        service.add_search(webset.id, query="q", criteria=[], store=store)
    assert ei.value.code == "invalid_criteria"

    with pytest.raises(WebsetNotFoundError):
        service.add_search("ws_missing", query="q", store=store)


# ── enrichments ──────────────────────────────────────────────────────────────


def test_add_enrichment_attaches_schedules_and_enforces_cap(tmp_path, scheduler):
    store = _store(tmp_path)
    webset = service.create_webset(query="photonics startups", criteria=[_CRITERION], store=store)

    attached = service.add_enrichment(webset.id, {"name": "blurb", "type": "text"}, store=store)
    assert attached.status == "running"
    assert attached.name == "blurb"
    assert scheduler.backfills == [(webset.id, attached.id)]

    for index in range(9):
        service.add_enrichment(webset.id, {"name": f"field{index}", "type": "text"}, store=store)
    with pytest.raises(WebsetServiceError) as ei:
        service.add_enrichment(webset.id, {"name": "one-too-many", "type": "text"}, store=store)
    assert ei.value.code == "enrichment_limit_exceeded"


def test_remove_enrichment_retains_resolved_values(tmp_path, scheduler):
    store = _store(tmp_path)
    webset = service.create_webset(
        query="q",
        criteria=[_CRITERION],
        enrichments=[{"name": "blurb", "type": "text"}],
        store=store,
    )
    definition = webset.enrichments[0]
    item = store.save_item(
        WebsetItem(
            webset_id=webset.id,
            url=_URL_A,
            verification="verified",
            enrichments={
                "blurb": EnrichedField(
                    value="stub", citations=[{"url": _URL_A, "title": "", "excerpt": "e"}]
                )
            },
        )
    )

    service.remove_enrichment(webset.id, definition.id, store=store)

    assert store.list_enrichments(webset.id) == []
    assert store.get_item(webset.id, item.id).enrichments["blurb"].value == "stub"

    with pytest.raises(WebsetServiceError) as ei:
        service.remove_enrichment(webset.id, "wse_missing", store=store)
    assert ei.value.code == "enrichment_not_found"

    with pytest.raises(WebsetNotFoundError):
        service.remove_enrichment("ws_missing", definition.id, store=store)


# ── monitors (tick-driven refresh cadence) ───────────────────────────────────


def test_create_monitor_is_tick_driven_metadata(tmp_path):
    store = _store(tmp_path)
    webset = service.create_webset(query="q", criteria=[_CRITERION], store=store)

    assert "status" not in WebsetMonitor.model_fields
    assert WebsetMonitor.model_fields["paused"].annotation is bool
    with pytest.raises(ImportError):
        from digisearch.websets.models import Monitor  # noqa: F401

    monitor = service.create_monitor(
        webset.id, interval_seconds=120, webhook_url=_URL_MONITOR, store=store
    )
    assert isinstance(monitor, WebsetMonitor)
    assert monitor.interval_seconds == 120
    assert monitor.webhook_url == _URL_MONITOR
    assert monitor.object == "webset_monitor"
    assert monitor.paused is False
    assert monitor.created_at is not None

    with pytest.raises(ValidationError):
        service.create_monitor(webset.id, interval_seconds=30, store=store)

    with pytest.raises(WebsetServiceError) as ei:
        service.create_monitor(webset.id, webhook_url="http://127.0.0.1:3000/hook", store=store)
    assert ei.value.code == "webhook_url_private"


def test_list_monitors_returns_created_monitors(tmp_path):
    store = _store(tmp_path)
    webset = service.create_webset(query="q", criteria=[_CRITERION], store=store)
    monitor = service.create_monitor(webset.id, store=store)

    monitors = service.list_monitors(webset.id, store=store)
    assert [m.id for m in monitors] == [monitor.id]

    with pytest.raises(WebsetNotFoundError):
        service.list_monitors("ws_missing", store=store)


def test_trigger_monitor_opens_a_new_generation_and_schedules(tmp_path, scheduler):
    store = _store(tmp_path)
    webset = service.create_webset(
        query="photonics startups", count=5, criteria=[_CRITERION], store=store
    )
    search = webset.searches[0]
    monitor = service.create_monitor(webset.id, store=store)
    scheduler.runs.clear()

    refreshed = service.trigger_monitor(webset.id, monitor.id, store=store)

    searches = service.get_webset(webset.id, store=store).searches
    assert [s.id for s in searches] == [search.id, searches[-1].id]
    assert searches[-1].id != search.id
    assert searches[-1].query == search.query
    assert searches[-1].count == search.count
    assert searches[-1].status == "running"
    assert refreshed.status == "running"
    assert scheduler.runs == [(webset.id, "llm")]


def test_trigger_monitor_unknown_ids(tmp_path):
    store = _store(tmp_path)
    webset = store.create_webset(Webset(criteria=[_CRITERION]))
    monitor = store.add_monitor(webset.id, WebsetMonitor(webset_id=webset.id))

    with pytest.raises(WebsetServiceError) as ei:
        service.trigger_monitor(webset.id, "wsm_missing", store=store)
    assert ei.value.code == "monitor_not_found"

    with pytest.raises(WebsetNotFoundError):
        service.trigger_monitor("ws_missing", monitor.id, store=store)


def test_handoff_from_watch_is_idempotent_and_schedules_once(tmp_path, scheduler):
    store = _store(tmp_path)
    webset = service.create_webset(
        query="photonics startups", count=5, criteria=[_CRITERION], store=store
    )
    initial = webset.searches[0]
    scheduler.runs.clear()

    first, created = service.handoff_from_watch(
        webset.id, watch_id="watch_1", run_id="run_1", store=store
    )

    assert created is True
    assert first.status == "running"
    assert first.query == initial.query
    assert first.count == initial.count
    assert scheduler.runs == [(webset.id, "llm")]

    second, created_again = service.handoff_from_watch(
        webset.id, watch_id="watch_1", run_id="run_1", store=store
    )

    assert created_again is False
    assert second.id == first.id
    assert scheduler.runs == [(webset.id, "llm")]
    assert [s.id for s in service.get_webset(webset.id, store=store).searches] == [
        initial.id,
        first.id,
    ]

    later, created_later = service.handoff_from_watch(
        webset.id, watch_id="watch_1", run_id="run_2", store=store
    )

    assert created_later is True
    assert later.id != first.id
    assert len(scheduler.runs) == 2


def test_handoff_from_watch_rejects_terminal_webset(tmp_path, scheduler):
    store = _store(tmp_path)
    webset = service.create_webset(query="q", criteria=[_CRITERION], store=store)
    service.cancel_webset(webset.id, store=store)

    with pytest.raises(WebsetServiceError) as ei:
        service.handoff_from_watch(webset.id, watch_id="watch_1", run_id="run_1", store=store)
    assert ei.value.code == "webset_terminal"


def test_handoff_from_watch_unknown_webset(tmp_path):
    store = _store(tmp_path)

    with pytest.raises(WebsetNotFoundError):
        service.handoff_from_watch("ws_missing", watch_id="watch_1", run_id="run_1", store=store)


def test_set_monitor_paused_pauses_and_resumes(tmp_path, scheduler):
    store = _store(tmp_path)
    webset = service.create_webset(query="q", criteria=[_CRITERION], store=store)
    monitor = service.create_monitor(webset.id, interval_seconds=120, store=store)
    scheduler.runs.clear()

    paused = service.set_monitor_paused(webset.id, monitor.id, paused=True, store=store)

    assert paused.paused is True
    assert paused.id == monitor.id
    assert paused.interval_seconds == 120
    assert paused.created_at == monitor.created_at
    assert store.get_monitor(webset.id, monitor.id).paused is True
    assert service.list_monitors(webset.id, store=store)[0].paused is True
    assert scheduler.runs == [] and scheduler.backfills == []

    resumed = service.set_monitor_paused(webset.id, monitor.id, paused=False, store=store)

    assert resumed.paused is False
    assert store.get_monitor(webset.id, monitor.id).paused is False


def test_set_monitor_paused_unknown_ids(tmp_path):
    store = _store(tmp_path)
    webset = store.create_webset(Webset(criteria=[_CRITERION]))
    monitor = store.add_monitor(webset.id, WebsetMonitor(webset_id=webset.id))

    with pytest.raises(WebsetServiceError) as ei:
        service.set_monitor_paused(webset.id, "wsm_missing", paused=True, store=store)
    assert ei.value.code == "monitor_not_found"

    with pytest.raises(WebsetNotFoundError):
        service.set_monitor_paused("ws_missing", monitor.id, paused=True, store=store)


# ── webhooks ─────────────────────────────────────────────────────────────────


def test_add_webhook_returns_one_time_secret_and_persists_it(tmp_path, scheduler):
    store = _store(tmp_path)
    webset = service.create_webset(query="q", criteria=[_CRITERION], store=store)
    scheduler.runs.clear()

    webhook = service.add_webhook(
        webset.id, url=_URL_PUBLIC, events=["item.created", "webset.idle"], store=store
    )

    assert webhook.url == _URL_PUBLIC
    assert webhook.events == ["item.created", "webset.idle"]
    assert webhook.webhook_id
    assert webhook.active is True
    assert len(webhook.secret) >= 32
    assert store.get_webhook(webset.id, webhook.webhook_id).secret == webhook.secret
    assert scheduler.runs == [] and scheduler.backfills == []
    assert not hasattr(service, "deliver_webhook")


def test_add_webhook_rejects_private_and_missing_urls(tmp_path, scheduler):
    store = _store(tmp_path)
    webset = service.create_webset(query="q", criteria=[_CRITERION], store=store)

    with pytest.raises(WebsetServiceError) as ei:
        service.add_webhook(webset.id, url="", events=["item.created"], store=store)
    assert ei.value.code == "webhook_url_required"
    assert "[webhook]: Required" in str(ei.value)

    for bad in (
        "http://hooks.example.com/x",
        "https://127.0.0.1:3000/hook",
        "https://localhost/hook",
        "https://192.168.1.10/hook",
        "https://10.0.0.5/hook",
        "https://user:pass@93.184.216.34/hook",
    ):
        with pytest.raises(WebsetServiceError) as ei:
            service.add_webhook(webset.id, url=bad, events=["item.created"], store=store)
        assert ei.value.code == "webhook_url_private"
        assert "[webhook.url]: Webhook URL cannot point to localhost or private IPs" in str(
            ei.value
        )

    assert store.list_webhooks(webset.id) == []

    with pytest.raises(ValidationError):
        service.add_webhook(webset.id, url=_URL_PUBLIC, events=["bogus.kind"], store=store)

    with pytest.raises(WebsetNotFoundError):
        service.add_webhook("ws_missing", url=_URL_PUBLIC, events=["item.created"], store=store)


def test_rotate_webhook_secret_overlaps_the_old_secret_24h(tmp_path):
    store = _store(tmp_path)
    webset = service.create_webset(query="q", criteria=[_CRITERION], store=store)
    webhook = service.add_webhook(webset.id, url=_URL_PUBLIC, events=["item.created"], store=store)

    rotated = service.rotate_webhook_secret(webset.id, webhook.webhook_id, store=store)

    assert rotated.secret != webhook.secret
    assert rotated.previous_secret == webhook.secret
    assert rotated.previous_expires_at is not None
    delta = rotated.previous_expires_at - datetime.now(UTC)
    assert timedelta(hours=23, minutes=59) < delta <= timedelta(hours=24, minutes=1)
    assert store.get_webhook(webset.id, webhook.webhook_id).secret == rotated.secret

    payload = b'{"event":"item.created"}'

    assert verify_webhook_signature(rotated, payload, sign_webhook_body(webhook.secret, payload))
    expired = rotated.previous_expires_at + timedelta(seconds=1)
    assert not verify_webhook_signature(
        rotated, payload, sign_webhook_body(webhook.secret, payload), now=expired
    )
    assert verify_webhook_signature(
        rotated, payload, sign_webhook_body(rotated.secret, payload), now=expired
    )

    with pytest.raises(WebsetServiceError) as ei:
        service.rotate_webhook_secret(webset.id, "missing", store=store)
    assert ei.value.code == "webhook_not_found"


# ── events ───────────────────────────────────────────────────────────────────


def test_list_events_oldest_first_cursor_and_errors(tmp_path):
    store = _store(tmp_path)
    webset = store.create_webset(Webset(criteria=[_CRITERION]))
    search_id = store.add_search(
        WebsetSearch(webset_id=webset.id, query="q", criteria=[_CRITERION])
    ).id
    emitted = [_event(store, webset.id, search_id, f"wsi_{index:032x}") for index in range(3)]

    page, cursor = service.list_events(webset.id, limit=2, store=store)
    assert [event.id for event in page] == [emitted[0].id, emitted[1].id]
    assert cursor == emitted[1].id

    page, cursor = service.list_events(webset.id, after=cursor, limit=2, store=store)
    assert [event.id for event in page] == [emitted[2].id]
    assert cursor is None

    with pytest.raises(WebsetServiceError) as ei:
        service.list_events(webset.id, after="0" * 32, store=store)
    assert ei.value.code == "cursor_not_found"

    with pytest.raises(WebsetServiceError) as ei:
        service.list_events(webset.id, after="not-a-cursor", store=store)
    assert ei.value.code == "cursor_not_found"

    with pytest.raises(WebsetNotFoundError):
        service.list_events("ws_missing", store=store)


# ── cancel ───────────────────────────────────────────────────────────────────


def test_cancel_webset_flips_status_and_settles_searches(tmp_path):
    store = _store(tmp_path)
    webset = service.create_webset(query="q", criteria=[_CRITERION], store=store)

    cancelled = service.cancel_webset(webset.id, store=store)

    assert cancelled.status == "cancelled"
    stored = service.get_webset(webset.id, store=store)
    assert stored.status == "cancelled"
    assert [s.status for s in stored.searches] == ["cancelled"]

    assert service.cancel_webset(webset.id, store=store).status == "cancelled"

    with pytest.raises(WebsetNotFoundError):
        service.cancel_webset("ws_missing", store=store)


# ── export ───────────────────────────────────────────────────────────────────


def _settled_webset(tmp_path, monkeypatch, scheduler, llm_env):
    store = _store(tmp_path)
    monkeypatch.setattr(runner_module, "search_web", _RecallStub([_URL_A, _URL_REJECT, _URL_B]))
    monkeypatch.setattr(runner_module, "fetch_markdown", _FetchStub(_MARKDOWN))
    webset = service.create_webset(
        query="photonics startups",
        count=2,
        criteria=[_CRITERION],
        enrichments=[
            {"name": "blurb", "type": "text"},
            {"name": "score", "type": "number"},
        ],
        store=store,
    )
    result = asyncio.run(run_webset_async(webset.id, store=store, llm_client=_StubLLM()))
    assert result.status == "idle"
    return store, service.get_webset(webset.id, store=store)


def test_export_json_keeps_per_field_citations(tmp_path, monkeypatch, scheduler, llm_env):
    store, webset = _settled_webset(tmp_path, monkeypatch, scheduler, llm_env)

    content, media_type = service.export_webset(webset.id, fmt="json", store=store)

    assert media_type == "application/json"
    document = json.loads(content)
    assert document["webset_id"] == webset.id
    items = document["items"]
    assert {item["url"] for item in items} == {_URL_A, _URL_B}
    assert all(item["verification"] == "verified" for item in items)
    for item in items:
        field = item["enrichments"]["blurb"]
        assert field["status"] == "resolved"
        assert field["citations"][0]["url"] == item["url"]
        assert item["criteria_results"][0]["passed"] is True


def test_export_csv_is_one_row_per_verified_item(tmp_path, monkeypatch, scheduler, llm_env):
    store, webset = _settled_webset(tmp_path, monkeypatch, scheduler, llm_env)

    content, media_type = service.export_webset(webset.id, fmt="csv", store=store)

    assert media_type == "text/csv"
    frame = pl.read_csv(io.StringIO(content))
    assert frame.columns[:5] == ["item_id", "webset_id", "url", "title", "verification"]
    assert "enrichment__blurb__value" in frame.columns
    assert "enrichment__blurb__citations" in frame.columns
    assert frame.height == 2
    rows = {row["url"]: row for row in frame.to_dicts()}
    assert set(rows) == {_URL_A, _URL_B}
    assert _URL_REJECT not in rows
    assert {row["verification"] for row in rows.values()} == {"verified"}
    for url, row in rows.items():
        assert row["enrichment__blurb__value"] == "resolved by stub"
        assert row["enrichment__blurb__citations"] == url
    assert frame["enrichment__score__value"].dtype == pl.Float64
    assert frame["enrichment__score__value"].to_list() == [42.0, 42.0]


def test_export_unknown_webset_and_bad_format(tmp_path):
    store = _store(tmp_path)
    webset = service.create_webset(query="q", criteria=[_CRITERION], store=store)

    with pytest.raises(WebsetNotFoundError):
        service.export_webset("ws_missing", store=store)

    with pytest.raises(ValueError):
        service.export_webset(webset.id, fmt="xml", store=store)


# ── error-code mapping ───────────────────────────────────────────────────────


def test_service_reexports_the_async_entry_point():
    assert service.run_webset_async is run_webset_async


def test_documented_error_code_mapping():
    assert set(service.SPEC_ERROR_CODES) == {
        "webset_not_found",
        "search_not_found",
        "monitor_not_found",
        "enrichment_limit_exceeded",
        "cursor_not_found",
        "invalid_criteria",
        "invalid_verification_mode",
        "datatap_websets_disabled",
        "webhook_url_required",
        "webhook_url_private",
        "webset_terminal",
        "rate_limit_exceeded",
    }
    assert {"enrichment_not_found", "webhook_secret_missing"} <= set(service.CARRIED_ERROR_CODES)
    assert service.INTERNAL_ERROR_CODE not in service.SPEC_ERROR_CODES
    assert service.INTERNAL_ERROR_CODE not in service.CARRIED_ERROR_CODES


def test_store_internal_codes_never_surface(tmp_path, monkeypatch):
    store = _store(tmp_path)

    def boom(webset_id: str, *, code: str) -> Webset:
        raise WebsetStoreError("internal state", code=code)

    for internal in ("webset_not_settled", "transition_invalid"):
        monkeypatch.setattr(
            store, "get_webset", lambda webset_id, code=internal: boom(webset_id, code=code)
        )
        with pytest.raises(WebsetServiceError) as ei:
            service.get_webset("ws_any", store=store)
        assert ei.value.code == service.INTERNAL_ERROR_CODE
        assert internal not in str(ei.value)
