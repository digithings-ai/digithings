"""Phase D webset models (#4066, Task 1).

Pins the Websets-like verify + enrich envelope that the store / verify /
enrich / runner tasks consume: the shared ``Citation`` atom is imported (never
redefined), request shapes forbid unknown keys while EXA-normalized reads
ignore vendor extras, ``count`` is the 1..100 verified-item target, the
``backend`` label defaults to ``"oss"`` (R4 — no ``provider``/``auto`` field
exists), ``WebsetSearch.status`` includes ``cancelled``, and every id is a
``{prefix}_`` + uuid4-hex string. Pure model tests — no network, no store.
"""

from __future__ import annotations

import inspect
import re
from typing import Any, get_args

import pytest
from digisearch.web_search.citation import Citation
from digisearch.websets import models as webset_models
from digisearch.websets.models import (
    CompanyEntity,
    CriterionResult,
    EnrichedField,
    EnrichmentDef,
    VerificationCriterion,
    WebhookConfig,
    Webset,
    WebsetEvent,
    WebsetItem,
    WebsetMonitor,
    WebsetSearch,
)
from pydantic import ValidationError

pytestmark = pytest.mark.unit

_WS_ID = "ws_" + "1" * 32
_WSS_ID = "wss_" + "2" * 32
_ID_RE = re.compile(r"^(ws|wss|wsi|wse|wsm)_[0-9a-f]{32}$")

_CRITERIA: list[dict[str, str]] = [
    {"name": "photonics", "rule": "company is a photonics startup"},
    {"name": "founded", "rule": "company was founded after 2018"},
]

_ENRICHMENTS: list[dict[str, Any]] = [
    {"name": "fit", "type": "options", "options": ["strong", "weak"]},
    {"name": "profile", "type": "company_profile", "description": "merged company profile"},
]


def _webset(**overrides: Any) -> Webset:
    payload: dict[str, Any] = {"criteria": _CRITERIA, "enrichments": _ENRICHMENTS}
    payload.update(overrides)
    return Webset.model_validate(payload)


def _search(**overrides: Any) -> WebsetSearch:
    payload: dict[str, Any] = {
        "webset_id": _WS_ID,
        "query": "photonics startups",
        "criteria": _CRITERIA,
    }
    payload.update(overrides)
    return WebsetSearch.model_validate(payload)


def test_webset_defaults_and_nested_shapes():
    webset = _webset()
    assert webset.object == "webset"
    assert webset.status == "running"
    assert webset.backend == "oss"
    assert webset.workspace_id is None
    assert webset.searches == []
    assert webset.created_at is None
    assert webset.updated_at is None
    assert [c.name for c in webset.criteria] == ["photonics", "founded"]
    assert [e.type for e in webset.enrichments] == ["options", "company_profile"]
    assert webset.enrichments[0].options == ["strong", "weak"]
    assert webset.enrichments[0].status == "running"


def test_webset_item_defaults():
    item = WebsetItem(webset_id=_WS_ID, url="https://nucicer.test/")
    assert item.verification == "pending"
    assert item.criteria_results == []
    assert item.enrichments == {}
    assert item.title == ""
    assert item.created_at is None


def test_ids_are_prefixed_uuid4_hex_across_entities():
    webset = _webset()
    search = _search()
    item = WebsetItem(webset_id=_WS_ID, url="https://nucicer.test/")
    enrichment = EnrichmentDef(name="profile", type="company_profile")
    monitor = WebsetMonitor(webset_id=_WS_ID)
    ids = [webset.id, search.id, item.id, enrichment.id, monitor.id]
    assert [obj_id.split("_", 1)[0] for obj_id in ids] == ["ws", "wss", "wsi", "wse", "wsm"]
    for obj_id in ids:
        assert _ID_RE.match(obj_id), obj_id
        assert obj_id == obj_id.lower()
    assert len(set(ids)) == 5
    assert webset.id != _webset().id


def test_id_pattern_rejects_foreign_id_shapes():
    for bad_id in ("ws_not-a-uuid", "wsi_" + "a" * 32, "ws_" + "A" * 32, "ws_" + "a" * 31):
        with pytest.raises(ValidationError):
            _webset(id=bad_id)


def test_citation_is_the_shared_landed_atom():
    assert webset_models.Citation is Citation
    assert inspect.getmodule(Citation).__name__ == "digisearch.web_search.citation"
    assert get_args(EnrichedField.model_fields["citations"].annotation) == (Citation,)
    assert get_args(CriterionResult.model_fields["references"].annotation) == (Citation,)
    assert CompanyEntity.model_fields["provenance"].annotation == dict[str, list[Citation]]


def test_enriched_field_needs_value_and_citations_to_resolve():
    citations = [Citation(url="https://a.test/1"), Citation(url="https://b.test/2")]
    resolved = EnrichedField(value="Series A", citations=citations)
    assert resolved.status == "resolved"
    assert len(resolved.citations) == 2
    assert EnrichedField(value="Series A").status == "unresolved"
    assert EnrichedField(value="", citations=citations).status == "unresolved"
    assert (
        EnrichedField(value="Series A", citations=citations, status="skipped").status == "skipped"
    )
    assert EnrichedField(value=0, citations=citations).status == "resolved"
    assert EnrichedField(value=False, citations=citations).status == "resolved"


def test_webset_item_round_trips_verified_item_with_citations():
    citations = [
        Citation(url="https://nucicer.test/press", title="NuCicer raises", excerpt="raised $11.5M"),
        Citation(url="https://agnews.test/nucicer", excerpt="Series A close"),
    ]
    item = WebsetItem(
        webset_id=_WS_ID,
        url="https://nucicer.test/",
        title="NuCicer",
        verification="verified",
        criteria_results=[
            CriterionResult(
                criterion=VerificationCriterion(**_CRITERIA[0]),
                passed=True,
                reasoning="photonics ingredient platform matches",
                references=[citations[0]],
            )
        ],
        enrichments={"funding_latest": EnrichedField(value="$11.5M Series A", citations=citations)},
    )
    assert item.verification == "verified"
    assert item.enrichments["funding_latest"].status == "resolved"
    assert len(item.enrichments["funding_latest"].citations) == 2
    dumped = item.model_dump(mode="json")
    assert dumped["enrichments"]["funding_latest"]["citations"][1]["url"] == (
        "https://agnews.test/nucicer"
    )
    assert dumped == WebsetItem.model_validate(dumped).model_dump(mode="json")


def test_webset_dump_json_round_trips():
    webset_id = "ws_" + "3" * 32
    payload: dict[str, Any] = {
        "id": webset_id,
        "criteria": _CRITERIA,
        "enrichments": _ENRICHMENTS,
        "workspace_id": "ws-demo",
        "searches": [
            {
                "id": _WSS_ID,
                "webset_id": webset_id,
                "query": "photonics startups",
                "count": 5,
                "criteria": _CRITERIA,
            }
        ],
        "created_at": "2026-09-15T00:00:00Z",
        "updated_at": "2026-09-15T00:00:00Z",
    }
    webset = Webset.model_validate(payload)
    dumped = webset.model_dump(mode="json")
    assert dumped == Webset.model_validate(dumped).model_dump(mode="json")
    assert webset.searches[0].status == "running"
    assert webset.searches[0].backend == "oss"


def test_count_is_the_verified_item_target_with_1_100_bounds():
    assert _search().count == 10
    assert _search(count=1).count == 1
    assert _search(count=100).count == 100
    for bad_count in (0, 101, -1):
        with pytest.raises(ValidationError):
            _search(count=bad_count)
    assert "max_results" not in WebsetSearch.model_fields
    assert "num_results" not in WebsetSearch.model_fields


def test_status_literals_pin_terminal_states():
    assert set(get_args(Webset.model_fields["status"].annotation)) == {
        "running",
        "idle",
        "failed",
        "cancelled",
    }
    assert set(get_args(WebsetSearch.model_fields["status"].annotation)) == {
        "running",
        "idle",
        "failed",
        "cancelled",
    }
    assert get_args(WebsetItem.model_fields["verification"].annotation) == (
        "pending",
        "verified",
        "rejected",
    )
    assert get_args(WebsetEvent.model_fields["type"].annotation) == (
        "item.created",
        "item.enriched",
        "webset.idle",
        "webset.failed",
    )
    assert get_args(EnrichedField.model_fields["status"].annotation) == (
        "resolved",
        "unresolved",
        "skipped",
    )
    assert get_args(EnrichmentDef.model_fields["type"].annotation) == (
        "text",
        "number",
        "date",
        "url",
        "email",
        "phone",
        "options",
        "company_profile",
    )
    with pytest.raises(ValidationError):
        _search(status="paused")
    with pytest.raises(ValidationError):
        WebsetItem(webset_id=_WS_ID, url="https://a.test/", verification="maybe")


def test_no_provider_or_auto_field_exists():
    for model in (Webset, WebsetSearch, EnrichmentDef, WebsetItem, WebsetMonitor):
        assert "provider" not in model.model_fields
    for model in (Webset, WebsetSearch):
        args = get_args(model.model_fields["backend"].annotation)
        assert args == ("oss", "exa")
        assert not {"auto", "searxng", "ddgs", "off"} & set(args)


def test_webset_monitor_poll_only_surface():
    monitor = WebsetMonitor(webset_id=_WS_ID, webhook_url="https://hooks.test/websets")
    assert monitor.object == "webset_monitor"
    assert monitor.interval_seconds == 3600
    assert monitor.webhook_url == "https://hooks.test/websets"
    assert "status" not in WebsetMonitor.model_fields
    assert "paused" not in WebsetMonitor.model_fields
    assert not hasattr(monitor, "status")
    assert not hasattr(monitor, "paused")
    assert _ID_RE.match(monitor.id)
    with pytest.raises(ValidationError):
        WebsetMonitor(webset_id=_WS_ID, interval_seconds=59)
    assert WebsetMonitor(webset_id=_WS_ID, interval_seconds=60).interval_seconds == 60


def test_bare_monitor_import_is_banned():
    assert not hasattr(webset_models, "Monitor")
    with pytest.raises(ImportError):
        from digisearch.websets.models import Monitor  # noqa: F401


def test_request_shapes_forbid_unknown_keys():
    with pytest.raises(ValidationError):
        VerificationCriterion(name="n", rule="r", bogus=1)
    with pytest.raises(ValidationError):
        EnrichmentDef(name="e", type="text", bogus=1)
    with pytest.raises(ValidationError):
        WebsetMonitor(webset_id=_WS_ID, bogus=1)
    with pytest.raises(ValidationError):
        WebhookConfig(url="https://hooks.test/w", events=["webset.idle"], bogus=1)


def test_exa_normalized_reads_ignore_unknown_keys():
    citations = [Citation(url="https://nucicer.test/press")]
    entity = CompanyEntity(
        name="NuCicer",
        founded_year=2016,
        funding_total=16_000_000.0,
        webTraffic="1200/mo",
        id="exa-entity-1",
    )
    assert entity.name == "NuCicer"
    assert not hasattr(entity, "webTraffic")
    item = WebsetItem(webset_id=_WS_ID, url="https://nucicer.test/", exa_id="exa-item-1")
    assert item.title == ""
    field = EnrichedField(value="v", citations=citations, exa_confidence=0.91)
    assert field.status == "resolved"
    event = WebsetEvent(
        webset_id=_WS_ID,
        type="webset.idle",
        search_id=_WSS_ID,
        exa_kind="webset.idle",
    )
    assert event.payload == {}


def test_company_entity_carries_two_rounds_and_per_scalar_provenance():
    press = Citation(url="https://nucicer.test/press", title="NuCicer raises Series A")
    secondary = Citation(url="https://agnews.test/nucicer")
    entity = CompanyEntity(
        name="NuCicer",
        founded_year=2016,
        description="Plant-protein ingredient platform",
        workforce_total=42,
        hq_city="Davis",
        hq_country="US",
        funding_total=16_000_000.0,
        funding_rounds=[
            {
                "name": "series-a",
                "date": "2025-07",
                "amount": 11_500_000.0,
                "citations": [press, secondary],
            },
            {"name": "seed", "date": "2022-03", "amount": 4_500_000.0, "citations": [press]},
        ],
        provenance={
            "name": [press],
            "founded_year": [press],
            "description": [press, secondary],
            "workforce_total": [secondary],
            "hq_city": [press],
            "hq_country": [press],
            "funding_total": [press, secondary],
        },
        reasoning="workforce_total rests on a single secondary source",
    )
    scalars = {
        "name",
        "founded_year",
        "description",
        "workforce_total",
        "hq_city",
        "hq_country",
        "funding_total",
    }
    assert scalars <= set(entity.provenance)
    assert len(entity.funding_rounds) == 2
    assert entity.funding_rounds[0].amount == 11_500_000.0
    assert [c.url for c in entity.funding_rounds[0].citations] == [press.url, secondary.url]
    assert "citations" not in CompanyEntity.model_fields
    dumped = entity.model_dump(mode="json")
    assert dumped["provenance"]["funding_total"][0]["url"] == press.url
    assert dumped == CompanyEntity.model_validate(dumped).model_dump(mode="json")


def test_required_fields_rejected_when_missing():
    with pytest.raises(ValidationError):
        Webset()
    with pytest.raises(ValidationError):
        Webset(criteria=[])
    with pytest.raises(ValidationError):
        _search(criteria=[])
    with pytest.raises(ValidationError):
        _search(criteria=_CRITERIA * 3)
    with pytest.raises(ValidationError):
        VerificationCriterion(name="photonics")
    with pytest.raises(ValidationError):
        WebsetEvent(webset_id=_WS_ID, type="webset.idle")
    with pytest.raises(ValidationError):
        WebsetItem(webset_id=_WS_ID)


def test_enrichment_cap_and_options_rule():
    with pytest.raises(ValidationError):
        _webset(enrichments=[{"name": f"e{i}", "type": "text"} for i in range(11)])
    ten = _webset(enrichments=[{"name": f"e{i}", "type": "text"} for i in range(10)])
    assert len(ten.enrichments) == 10
    options_def = EnrichmentDef(name="fit", type="options", options=["strong", "weak"])
    assert options_def.options == ["strong", "weak"]
    with pytest.raises(ValidationError):
        EnrichmentDef(name="fit", type="options")
    with pytest.raises(ValidationError):
        EnrichmentDef(name="band", type="text", options=["a"])


def test_webhook_config_shape():
    hook = WebhookConfig(
        url="https://hooks.test/w", events=["item.enriched", "webset.idle"], secret="s3cret"
    )
    assert hook.active is True
    assert hook.previous_secret is None
    assert hook.previous_expires_at is None
    assert hook.created_at is None
    with pytest.raises(ValidationError):
        WebhookConfig(url="https://hooks.test/w", events=["nope"])


def test_webset_event_carries_the_generation_tuple():
    event = WebsetEvent(
        webset_id=_WS_ID,
        type="item.created",
        search_id=_WSS_ID,
        item_id="wsi_" + "4" * 32,
        payload={"url": "https://nucicer.test/"},
    )
    assert event.id and re.fullmatch(r"[0-9a-f]{32}", event.id)
    assert event.field == ""
    assert event.item_id.startswith("wsi_")
    assert event.payload["url"] == "https://nucicer.test/"
    assert event.created_at is None
