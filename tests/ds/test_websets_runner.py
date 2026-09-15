"""Phase D webset runner + events (#4066, Task 5a) — offline unit suite.

Pins the async settling loop from the spec
(``docs/superpowers/specs/2026-09-14-oss-websearch-phaseD-verify-enrich.md``
§ Async lifecycle, § Interfaces):

- a due run drives ``candidates -> verify -> enrich -> idle`` and asserts the
  event log as a MULTISET (``item.created`` x2, ``item.enriched`` x2) plus
  ``webset.idle`` strictly last — exact-sequence assertions are banned because
  the semaphore-4 runner does not guarantee inter-item order;
- rejected candidates emit no item event and are setted ``rejected`` at the
  candidate-pass end (never ``pending``), so ``idle`` is always reachable;
- an enrichment failure settles every affected field ``unresolved`` (terminal)
  and the webset still reaches ``idle``;
- ``cancel_webset`` mid-run stops scheduling, settles searches ``cancelled`` and
  marks unattempted fields ``skipped``;
- ``resume_incomplete_websets`` re-drives BOTH union arms (a ``running`` webset
  and a sticky-``idle`` webset holding a ``running`` refresh search) without
  duplicating existing events, and a refresh generation re-emits terminal
  events under the new ``search_id`` while ``Webset.status`` stays ``idle``.

Offline: the two pinned recall seams (``search_web`` / ``fetch_markdown``) and
the digillm client are stubbed; every test opens a real sqlite file under
``tmp_path``. ``@pytest.mark.unit`` on every test.
"""

from __future__ import annotations

import asyncio
import json
import re
import types
from collections import Counter
from typing import Any

import pytest
from digisearch.web_search.citation import Citation
from digisearch.web_search.models import WebSearchRequest, WebSearchResponse, WebSearchResult
from digisearch.websets import runner as runner_module
from digisearch.websets.enrich import ENRICH_MODEL_ENV
from digisearch.websets.events import list_events
from digisearch.websets.models import (
    EnrichedField,
    EnrichmentDef,
    VerificationCriterion,
    Webset,
    WebsetEvent,
    WebsetItem,
    WebsetSearch,
)
from digisearch.websets.runner import (
    WEBSET_TASKS,
    WebsetNotFoundError,
    backfill_enrichment,
    resume_incomplete_websets,
    run_webset_async,
    schedule_webset_task,
)
from digisearch.websets.store import WebsetStore
from digisearch.websets.verify import VERIFY_MODEL_ENV

pytestmark = pytest.mark.unit

_URL_A = "https://alpha.example.com/one"
_URL_B = "https://beta.example.com/two"
_URL_C = "https://gamma.example.com/three"
_URL_REJECT = "https://reject.example.com/no"
_URL_EMPTY = "https://empty.example.com/blank"
_URL_FAIL_ENRICH = "https://fail.example.com/enrich"

_CRITERION = VerificationCriterion(name="photonics", rule="company is a photonics startup")
_DEF_BLURB = EnrichmentDef(name="blurb", type="text")
_DEF_SECTOR = EnrichmentDef(name="sector", type="text")

_MARKDOWN = {
    _URL_A: "# Alpha Photonics\nSeries A closed 2025-07-01.",
    _URL_B: "# Beta Photonics\nSeries A closed 2025-08-01.",
    _URL_C: "# Gamma Photonics\nSeries A closed 2025-09-01.",
    _URL_REJECT: "# Reject Corp\nUnrelated business.",
    _URL_FAIL_ENRICH: "# Fail Photonics\nSeries A closed 2025-09-02.",
}


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
    """Duck-typed digillm boundary for both verification and enrichment calls."""

    def __init__(
        self,
        *,
        reject_markers: tuple[str, ...] = ("reject",),
        fail_enrich: tuple[str, ...] = (),
        on_verify: Any = None,
    ) -> None:
        self.calls: list[tuple[str, str]] = []
        self._reject_markers = reject_markers
        self._fail_enrich = set(fail_enrich)
        self._on_verify = on_verify

    def completion(self, model: str, messages: list[dict[str, str]], **kwargs: Any) -> Any:
        schema_name = kwargs["response_format"]["json_schema"]["name"]
        content = messages[-1]["content"]
        url = _candidate_url(content)
        self.calls.append((schema_name, url))
        if schema_name == "webset_verification":
            if self._on_verify is not None:
                self._on_verify(url)
            passed = not any(marker in url for marker in self._reject_markers)
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
            if url in self._fail_enrich:
                raise RuntimeError("stub enrichment failure")
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


class _RecallStub:
    """Stubbed ``search_web``: records requests, returns a fixed result set."""

    def __init__(
        self,
        urls: tuple[str, ...] | list[str] = (),
        *,
        by_query: Any = None,
        error: Exception | None = None,
    ) -> None:
        self.urls = list(urls)
        self.by_query = by_query
        self.error = error
        self.requests: list[WebSearchRequest] = []

    def __call__(self, req: WebSearchRequest, config: Any = None) -> WebSearchResponse:
        self.requests.append(req)
        if self.error is not None:
            raise self.error
        urls = self.by_query(req.query) if self.by_query is not None else self.urls
        results = [
            WebSearchResult(url=url, title=url.rstrip("/").rsplit("/", 1)[-1]) for url in urls
        ]
        return WebSearchResponse(query=req.query, results=results, provider="stub")


class _FetchStub:
    """Stubbed non-indexing ``fetch_markdown``: canned markdown per URL."""

    def __init__(
        self,
        markdown: dict[str, str] | None = None,
        *,
        default: str = "",
        error_urls: tuple[str, ...] = (),
    ) -> None:
        self.markdown = dict(markdown or {})
        self.default = default
        self.error_urls = set(error_urls)
        self.requested: list[str] = []

    def __call__(self, url: str, **kwargs: Any) -> str:
        self.requested.append(url)
        if url in self.error_urls:
            raise RuntimeError("stub fetch failure")
        return self.markdown.get(url, self.default)


@pytest.fixture
def llm_env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv(VERIFY_MODEL_ENV, "test/verify-model")
    monkeypatch.setenv(ENRICH_MODEL_ENV, "test/enrich-model")


def _install_seams(monkeypatch: pytest.MonkeyPatch, recall: _RecallStub, fetch: _FetchStub) -> None:
    monkeypatch.setattr(runner_module, "search_web", recall)
    monkeypatch.setattr(runner_module, "fetch_markdown", fetch)


def _store(tmp_path: Any) -> WebsetStore:
    return WebsetStore(db_path=str(tmp_path / "websets.sqlite3"))


def _webset(
    store: WebsetStore,
    *,
    enrichments: tuple[EnrichmentDef, ...] = (),
    criteria: tuple[VerificationCriterion, ...] = (_CRITERION,),
) -> Webset:
    return store.create_webset(Webset(criteria=list(criteria), enrichments=list(enrichments)))


def _search(
    store: WebsetStore,
    webset_id: str,
    *,
    query: str = "photonics startups",
    count: int = 10,
    criteria: tuple[VerificationCriterion, ...] = (_CRITERION,),
) -> WebsetSearch:
    return store.add_search(
        WebsetSearch(webset_id=webset_id, query=query, count=count, criteria=list(criteria))
    )


def _resolved_field(url: str) -> EnrichedField:
    return EnrichedField(value="resolved", citations=[Citation(url=url, title="t", excerpt="e")])


def _event_ids(store: WebsetStore, webset_id: str) -> set[str]:
    events, _ = list_events(store, webset_id)
    return {event.id for event in events}


# ── due run ───────────────────────────────────────────────────────────────────


@pytest.mark.unit
def test_due_run_drives_idle_with_multiset_events(tmp_path, monkeypatch, llm_env):
    store = _store(tmp_path)
    webset = _webset(store, enrichments=(_DEF_BLURB, _DEF_SECTOR))
    search = _search(store, webset.id, count=2)
    recall = _RecallStub([_URL_A, _URL_REJECT, _URL_B])
    fetch = _FetchStub(_MARKDOWN)
    _install_seams(monkeypatch, recall, fetch)

    result = asyncio.run(run_webset_async(webset.id, store=store, llm_client=_StubLLM()))

    assert result.status == "idle"
    assert store.get_webset(webset.id).status == "idle"
    assert store.get_search(webset.id, search.id).status == "idle"

    page, next_cursor = list_events(store, webset.id)
    assert next_cursor is None
    kinds = [event.type for event in page]
    assert kinds[-1] == "webset.idle"
    assert Counter(kinds[:-1]) == Counter({"item.created": 2, "item.enriched": 2})
    assert {event.search_id for event in page} == {search.id}

    assert store.count_items(webset.id) == {"pending": 0, "verified": 2, "rejected": 1}
    verified, _ = store.list_items(webset.id, verification="verified")
    assert len(verified) == 2
    for item in verified:
        assert set(item.enrichments) == {"blurb", "sector"}
        assert all(
            field.status == "resolved" and field.citations for field in item.enrichments.values()
        )
    rejected, _ = store.list_items(webset.id, verification="rejected")
    assert len(rejected) == 1
    assert rejected[0].criteria_results
    assert all(not verdict.passed for verdict in rejected[0].criteria_results)

    newer, cursor = list_events(store, webset.id, after=page[-2].id)
    assert [event.id for event in newer] == [page[-1].id]
    assert cursor is None

    # R3: count=2 is reached with a single capped recall call (max_results <= 10).
    assert len(recall.requests) == 1
    assert recall.requests[0].max_results <= 10


@pytest.mark.unit
def test_recall_diversifies_queries_with_capped_page_size(tmp_path, monkeypatch, llm_env):
    store = _store(tmp_path)
    webset = _webset(store)
    _search(store, webset.id)
    seen: dict[str, str] = {}

    def _by_query(query: str) -> list[str]:
        seen.setdefault(query, f"https://variant.example.com/{len(seen)}")
        return [seen[query]]

    recall = _RecallStub(by_query=_by_query)
    fetch = _FetchStub(default="# Variant Photonics\nSeries A closed 2025-09-01.")
    _install_seams(monkeypatch, recall, fetch)

    result = asyncio.run(run_webset_async(webset.id, store=store, llm_client=_StubLLM()))

    assert result.status == "idle"
    queries = [request.query for request in recall.requests]
    assert len(queries) >= 2
    assert len(set(queries)) == len(queries)
    assert all(1 <= request.max_results <= 10 for request in recall.requests)
    assert store.count_items(webset.id)["verified"] == len(queries)


@pytest.mark.unit
def test_unverifiable_candidate_settles_rejected_not_pending(tmp_path, monkeypatch, llm_env):
    store = _store(tmp_path)
    webset = _webset(store)
    _search(store, webset.id, count=1)
    _install_seams(monkeypatch, _RecallStub([_URL_EMPTY]), _FetchStub({_URL_EMPTY: ""}))

    result = asyncio.run(run_webset_async(webset.id, store=store, llm_client=_StubLLM()))

    assert result.status == "idle"
    assert store.count_items(webset.id) == {"pending": 0, "verified": 0, "rejected": 1}
    rejected, _ = store.list_items(webset.id, verification="rejected")
    assert len(rejected[0].criteria_results) == 1
    assert rejected[0].criteria_results[0].passed is False
    assert rejected[0].criteria_results[0].reasoning.startswith("verification unavailable:")
    events, _ = list_events(store, webset.id)
    assert [event.type for event in events] == ["webset.idle"]


@pytest.mark.unit
def test_enrichment_failure_settles_fields_unresolved_and_still_idles(
    tmp_path, monkeypatch, llm_env
):
    store = _store(tmp_path)
    webset = _webset(store, enrichments=(_DEF_BLURB, _DEF_SECTOR))
    _search(store, webset.id, count=1)
    _install_seams(monkeypatch, _RecallStub([_URL_FAIL_ENRICH]), _FetchStub(_MARKDOWN))
    llm = _StubLLM(fail_enrich=(_URL_FAIL_ENRICH,))

    result = asyncio.run(run_webset_async(webset.id, store=store, llm_client=llm))

    assert result.status == "idle"
    item = store.list_items(webset.id)[0][0]
    assert item.verification == "verified"
    assert set(item.enrichments) == {"blurb", "sector"}
    assert all(field.status == "unresolved" and field.error for field in item.enrichments.values())
    events, _ = list_events(store, webset.id)
    assert Counter(event.type for event in events) == Counter({"item.created": 1, "webset.idle": 1})


@pytest.mark.unit
def test_recall_failure_emits_webset_failed(tmp_path, monkeypatch, llm_env):
    store = _store(tmp_path)
    webset = _webset(store)
    search = _search(store, webset.id, count=1)
    _install_seams(
        monkeypatch, _RecallStub(error=RuntimeError("backend down")), _FetchStub(_MARKDOWN)
    )

    result = asyncio.run(run_webset_async(webset.id, store=store, llm_client=_StubLLM()))

    assert result.status == "failed"
    assert store.get_search(webset.id, search.id).status == "failed"
    events, _ = list_events(store, webset.id)
    assert [event.type for event in events] == ["webset.failed"]
    assert events[0].search_id == search.id
    assert "backend down" in events[0].payload["reason"]


@pytest.mark.unit
def test_unknown_verification_mode_surfaces(tmp_path, monkeypatch, llm_env):
    store = _store(tmp_path)
    webset = _webset(store)
    _search(store, webset.id, count=1)
    _install_seams(monkeypatch, _RecallStub([_URL_A]), _FetchStub(_MARKDOWN))

    with pytest.raises(ValueError, match="unknown verification mode"):
        asyncio.run(run_webset_async(webset.id, store=store, verification_mode="bogus"))
    assert store.count_items(webset.id) == {"pending": 0, "verified": 0, "rejected": 0}


@pytest.mark.unit
def test_run_webset_async_raises_webset_not_found(tmp_path, llm_env):
    store = _store(tmp_path)
    ghost = "ws_" + "f" * 32
    with pytest.raises(WebsetNotFoundError):
        asyncio.run(run_webset_async(ghost, store=store))


# ── cancellation ──────────────────────────────────────────────────────────────


@pytest.mark.unit
def test_cancel_webset_mid_run_skips_unattempted_fields(tmp_path, monkeypatch, llm_env):
    store = _store(tmp_path)
    webset = _webset(store, enrichments=(_DEF_BLURB, _DEF_SECTOR))
    search = _search(store, webset.id, count=2)
    _install_seams(monkeypatch, _RecallStub([_URL_A, _URL_B]), _FetchStub(_MARKDOWN))

    async def _run() -> Any:
        loop = asyncio.get_running_loop()
        cancelled = {"done": False}

        def _on_verify(url: str) -> None:
            if not cancelled["done"]:
                cancelled["done"] = True
                loop.call_soon_threadsafe(store.cancel_webset, webset.id)

        llm = _StubLLM(on_verify=_on_verify)
        return await run_webset_async(webset.id, store=store, llm_client=llm, concurrency=1)

    result = asyncio.run(_run())

    assert result.status == "cancelled"
    assert store.get_search(webset.id, search.id).status == "cancelled"
    items, _ = store.list_items(webset.id)
    assert len(items) == 1
    assert items[0].verification == "verified"
    assert set(items[0].enrichments) == {"blurb", "sector"}
    assert all(field.status == "skipped" for field in items[0].enrichments.values())
    events, _ = list_events(store, webset.id)
    assert [event.type for event in events] == ["item.created"]


@pytest.mark.unit
def test_new_search_added_mid_pass_is_driven_before_idle(tmp_path, monkeypatch, llm_env):
    store = _store(tmp_path)
    webset = _webset(store, enrichments=(_DEF_BLURB,))
    first = _search(store, webset.id, count=1)
    _install_seams(monkeypatch, _RecallStub([_URL_A]), _FetchStub(_MARKDOWN))

    async def _run() -> tuple[Any, list[WebsetSearch]]:
        loop = asyncio.get_running_loop()
        created: list[WebsetSearch] = []

        def _add_search() -> None:
            created.append(
                store.add_search(
                    WebsetSearch(
                        webset_id=webset.id,
                        query="photonics refresh",
                        count=1,
                        criteria=[_CRITERION],
                    )
                )
            )

        def _on_verify(url: str) -> None:
            if not created:
                loop.call_soon_threadsafe(_add_search)

        llm = _StubLLM(on_verify=_on_verify)
        return await run_webset_async(webset.id, store=store, llm_client=llm), created

    result, created = asyncio.run(_run())

    # add_search on a running webset is legal and has no task of its own (the
    # duplicate-schedule guard); the in-flight pass must drive the newcomer
    # instead of failing the webset on the idle-flip blocker.
    assert len(created) == 1
    second = created[0]
    assert result.status == "idle"
    assert store.get_webset(webset.id).status == "idle"
    assert store.get_search(webset.id, first.id).status == "idle"
    assert store.get_search(webset.id, second.id).status == "idle"
    events, _ = list_events(store, webset.id)
    assert Counter(event.type for event in events) == Counter(
        {"item.created": 1, "item.enriched": 1, "webset.idle": 2}
    )
    assert [event.type for event in events[-2:]] == ["webset.idle", "webset.idle"]
    assert {event.search_id for event in events if event.type == "webset.idle"} == {
        first.id,
        second.id,
    }


@pytest.mark.unit
def test_new_search_added_mid_pass_on_idle_webset_is_driven(tmp_path, monkeypatch, llm_env):
    store = _store(tmp_path)
    webset = _webset(store, enrichments=(_DEF_BLURB,))
    _search(store, webset.id, count=1)
    recall = _RecallStub([_URL_A])
    _install_seams(monkeypatch, recall, _FetchStub(_MARKDOWN))
    asyncio.run(run_webset_async(webset.id, store=store, llm_client=_StubLLM()))
    assert store.get_webset(webset.id).status == "idle"
    baseline = _event_ids(store, webset.id)

    second = _search(store, webset.id, count=1, query="photonics refresh")

    async def _run() -> tuple[Any, list[WebsetSearch]]:
        loop = asyncio.get_running_loop()
        created: list[WebsetSearch] = []

        def _add_search() -> None:
            created.append(
                store.add_search(
                    WebsetSearch(
                        webset_id=webset.id,
                        query="photonics second refresh",
                        count=1,
                        criteria=[_CRITERION],
                    )
                )
            )

        def _on_verify(url: str) -> None:
            if not created:
                loop.call_soon_threadsafe(_add_search)

        recall.urls = [_URL_B]
        llm = _StubLLM(on_verify=_on_verify)
        return await run_webset_async(webset.id, store=store, llm_client=llm), created

    result, created = asyncio.run(_run())

    # The refresh pass returns the webset to sticky idle, which short-circuits the
    # store's settlement blockers: the newcomer must still be driven by this pass.
    assert len(created) == 1
    third = created[0]
    assert result.status == "idle"
    assert store.get_search(webset.id, second.id).status == "idle"
    assert store.get_search(webset.id, third.id).status == "idle"
    new_events = [event for event in list_events(store, webset.id)[0] if event.id not in baseline]
    assert Counter(event.type for event in new_events) == Counter(
        {"item.created": 1, "item.enriched": 1, "webset.idle": 2}
    )
    assert {event.search_id for event in new_events if event.type == "webset.idle"} == {
        second.id,
        third.id,
    }


# ── startup resume (both union arms) ─────────────────────────────────────────
@pytest.mark.unit
def test_resume_incomplete_websets_drives_both_union_arms(tmp_path, monkeypatch, llm_env):
    store = _store(tmp_path)
    # Arm 1: a first pass that crashed on a `running` webset; A already settled,
    # B saved `pending`, and no `webset.idle` ever emitted.
    crashed = _webset(store, enrichments=(_DEF_BLURB,))
    search = _search(store, crashed.id, count=2)
    done = store.save_item(
        WebsetItem(
            webset_id=crashed.id,
            url=_URL_A,
            title="A",
            verification="verified",
            enrichments={"blurb": _resolved_field(_URL_A)},
        )
    )
    store.append_event(
        WebsetEvent(webset_id=crashed.id, type="item.created", search_id=search.id, item_id=done.id)
    )
    store.append_event(
        WebsetEvent(
            webset_id=crashed.id, type="item.enriched", search_id=search.id, item_id=done.id
        )
    )
    store.save_item(WebsetItem(webset_id=crashed.id, url=_URL_B, title="B"))

    # Arm 2: a sticky-`idle` webset holding a crashed refresh generation; its
    # first generation completed normally, idle event included.
    sticky = _webset(store, enrichments=(_DEF_BLURB,))
    first = _search(store, sticky.id, count=1, query="photonics startups")
    store.settle_search(sticky.id, first.id, "idle")
    store.set_webset_idle(sticky.id)
    seeded = store.append_event(
        WebsetEvent(webset_id=sticky.id, type="webset.idle", search_id=first.id)
    )
    refresh = _search(store, sticky.id, count=1, query="photonics refresh")

    _install_seams(monkeypatch, _RecallStub([_URL_A, _URL_B, _URL_C]), _FetchStub(_MARKDOWN))
    llm = _StubLLM()

    driven = asyncio.run(resume_incomplete_websets(store=store, llm_client=llm))

    assert set(driven) == {crashed.id, sticky.id}

    crashed_events, _ = list_events(store, crashed.id)
    assert Counter(event.type for event in crashed_events) == Counter(
        {"item.created": 3, "item.enriched": 3, "webset.idle": 1}
    )
    assert crashed_events[-1].type == "webset.idle"
    settled_a = [event for event in crashed_events if event.item_id == done.id]
    assert len(settled_a) == 2
    assert {event.type for event in settled_a} == {"item.created", "item.enriched"}
    assert store.get_webset(crashed.id).status == "idle"
    assert store.get_search(crashed.id, search.id).status == "idle"

    sticky_new = [event for event in list_events(store, sticky.id)[0] if event.id != seeded.id]
    assert {event.search_id for event in sticky_new} == {refresh.id}
    assert Counter(event.type for event in sticky_new) == Counter(
        {"item.created": 3, "item.enriched": 3, "webset.idle": 1}
    )
    assert sticky_new[-1].type == "webset.idle"
    assert store.get_webset(sticky.id).status == "idle"
    assert store.get_search(sticky.id, refresh.id).status == "idle"


@pytest.mark.unit
def test_resume_skips_already_verified_items_without_rebilling(tmp_path, monkeypatch, llm_env):
    store = _store(tmp_path)
    webset = _webset(store, enrichments=(_DEF_BLURB,))
    search = _search(store, webset.id, count=1)
    store.save_item(
        WebsetItem(
            webset_id=webset.id,
            url=_URL_A,
            title="A",
            verification="verified",
            enrichments={"blurb": _resolved_field(_URL_A)},
        )
    )
    recall = _RecallStub([_URL_A])
    fetch = _FetchStub(_MARKDOWN)
    _install_seams(monkeypatch, recall, fetch)
    llm = _StubLLM()

    asyncio.run(run_webset_async(webset.id, store=store, llm_client=llm))

    # Re-settle guard (T3 carry): no repeated billable verification/enrichment
    # call and no re-fetch for an item that is already verified and fully
    # enriched; the generation still settles idle under its own search id.
    assert llm.calls == []
    assert fetch.requested == []
    assert store.get_webset(webset.id).status == "idle"
    assert store.get_search(webset.id, search.id).status == "idle"
    events, _ = list_events(store, webset.id)
    assert [event.type for event in events] == ["webset.idle"]


@pytest.mark.unit
def test_resume_recovers_lost_idle_event_after_crash(tmp_path, monkeypatch, llm_env):
    store = _store(tmp_path)
    webset = _webset(store)
    search = _search(store, webset.id, count=1)
    # Crashed pass: the search settled idle but the webset flip / idle event
    # never happened, so the resuming pass has no running search to drive.
    store.settle_search(webset.id, search.id, "idle")
    _install_seams(monkeypatch, _RecallStub([_URL_A]), _FetchStub(_MARKDOWN))

    driven = asyncio.run(resume_incomplete_websets(store=store, llm_client=_StubLLM()))

    assert driven == [webset.id]
    assert store.get_webset(webset.id).status == "idle"
    events, _ = list_events(store, webset.id)
    assert [event.type for event in events] == ["webset.idle"]
    assert events[0].search_id == search.id


# ── refresh generation ────────────────────────────────────────────────────────
@pytest.mark.unit
def test_refresh_generation_reemits_events_under_new_search(tmp_path, monkeypatch, llm_env):
    store = _store(tmp_path)
    webset = _webset(store, enrichments=(_DEF_BLURB,))
    _search(store, webset.id, count=1)
    recall = _RecallStub([_URL_A])
    _install_seams(monkeypatch, recall, _FetchStub(_MARKDOWN))
    llm = _StubLLM()

    asyncio.run(run_webset_async(webset.id, store=store, llm_client=llm))
    baseline = _event_ids(store, webset.id)

    second = _search(store, webset.id, count=1, query="photonics refresh")
    recall.urls = [_URL_A, _URL_B]
    result = asyncio.run(run_webset_async(webset.id, store=store, llm_client=llm))

    assert result.status == "idle"
    assert store.get_webset(webset.id).status == "idle"
    assert store.get_search(webset.id, second.id).status == "idle"

    new_events = [event for event in list_events(store, webset.id)[0] if event.id not in baseline]
    assert Counter(event.type for event in new_events) == Counter(
        {"item.created": 1, "item.enriched": 1, "webset.idle": 1}
    )
    assert {event.search_id for event in new_events} == {second.id}
    assert new_events[-1].type == "webset.idle"
    # A was already enriched: the refresh re-emitted nothing for it (generation
    # dedup vs re-emission contract).
    assert (
        sum(
            1
            for event in new_events
            if event.type == "item.created" and event.payload["url"] == _URL_A
        )
        == 0
    )


# ── backfill + scheduling ─────────────────────────────────────────────────────


@pytest.mark.unit
def test_backfill_enrichment_settles_new_field_under_new_generation(tmp_path, monkeypatch, llm_env):
    store = _store(tmp_path)
    webset = _webset(store)
    first_search = _search(store, webset.id, count=1)
    _install_seams(monkeypatch, _RecallStub([_URL_A]), _FetchStub(_MARKDOWN))
    llm = _StubLLM()
    asyncio.run(run_webset_async(webset.id, store=store, llm_client=llm))
    baseline = _event_ids(store, webset.id)

    definition = store.add_enrichment(webset.id, EnrichmentDef(name="blurb", type="text"))
    settled = asyncio.run(
        backfill_enrichment(webset.id, definition.id, store=store, llm_client=llm)
    )

    assert len(settled) == 1
    assert settled[0].enrichments["blurb"].status == "resolved"
    assert store.list_enrichments(webset.id)[0].status == "idle"
    assert store.get_webset(webset.id).status == "idle"

    new_events = [event for event in list_events(store, webset.id)[0] if event.id not in baseline]
    assert Counter(event.type for event in new_events) == Counter(
        {"item.enriched": 1, "webset.idle": 1}
    )
    generations = {event.search_id for event in new_events}
    assert len(generations) == 1
    generation = generations.pop()
    assert generation not in {first_search.id}
    assert store.get_search(webset.id, generation).status == "idle"


@pytest.mark.unit
def test_schedule_webset_task_tracks_registry_and_removes_on_completion(
    tmp_path, monkeypatch, llm_env
):
    store = _store(tmp_path)
    webset = _webset(store, enrichments=(_DEF_BLURB,))
    _search(store, webset.id, count=1)
    _install_seams(monkeypatch, _RecallStub([_URL_A]), _FetchStub(_MARKDOWN))

    async def _run() -> Any:
        async with asyncio.TaskGroup() as group:
            task = schedule_webset_task(group, webset.id, store=store, llm_client=_StubLLM())
            assert WEBSET_TASKS[webset.id] is task
        return task

    task = asyncio.run(_run())

    assert task.done()
    assert task.exception() is None
    assert webset.id not in WEBSET_TASKS
    assert store.get_webset(webset.id).status == "idle"


@pytest.mark.unit
def test_stale_done_callback_keeps_newer_registry_entry():
    async def _run() -> None:
        webset_id = "ws_" + "a" * 32
        loop = asyncio.get_running_loop()
        stale = loop.create_task(asyncio.sleep(0))
        current = loop.create_task(asyncio.sleep(0))
        await asyncio.gather(stale, current)

        # A reschedule registered a newer task before the stale task's callback ran.
        WEBSET_TASKS[webset_id] = current
        runner_module._log_task_done(webset_id, stale)
        assert WEBSET_TASKS[webset_id] is current

        WEBSET_TASKS[webset_id] = stale
        runner_module._log_task_done(webset_id, stale)
        assert webset_id not in WEBSET_TASKS

    asyncio.run(_run())
