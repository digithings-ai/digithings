"""Phase D websets live verification record (#4066, Task 8) — offline by default.

Offline legs run the record's assertion helpers against canned values, so the
suite is green with no stack, no key, and no network: the Task 8 brief's inputs
are pinned verbatim, the event contract (kind multiset + ``webset.idle`` last,
never an exact sequence) is exercised on a shuffled log, the live-vs-s5 funding
delta recorder runs on the vendored sample names, the CSV record counts rows +
citation URLs through the landed polars export, and the fx snapshot is pinned
to its documented ECB EUR convention.

Live mode is opt-in behind ``DIGISEARCH_WEBSETS_LIVE=1`` (the Phase B gate
pattern): it drives the real recall (``search_web`` -> searxng/ddgs) + fetch +
verify/enrich pipeline for the Task 8 brief's company query and prints the
record — wall-clock to idle, event multiset, item counts, funding reconciliation
deltas against the vendored s5 sample (``fixtures/websets/s5_category_company.json``),
and the CSV export shape. Those numbers are single-day SCAFFOLDING anchors —
never SLO constants; re-run in a provisioned env and append the date/key tier to
the Phase D live record in ``digisearch/ARCHITECTURE.md`` before quoting them.
The EXA Pro-key shim re-validation is a human precondition and is **not** claimed
by this harness.
"""

from __future__ import annotations

import asyncio
import io
import json
import os
import re
import time
from collections.abc import Mapping, Sequence
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import polars as pl
import pytest
from digisearch.web_search.citation import Citation
from digisearch.websets import service
from digisearch.websets.enrich import ENRICH_MODEL_ENV
from digisearch.websets.export import export_csv
from digisearch.websets.models import (
    CompanyEntity,
    EnrichedField,
    EnrichmentDef,
    VerificationCriterion,
    Webset,
    WebsetEvent,
    WebsetItem,
)
from digisearch.websets.runner import run_webset_async
from digisearch.websets.store import WebsetStore
from digisearch.websets.verify import VERIFY_MODEL_ENV

pytestmark = pytest.mark.unit

_FIXTURES = Path(__file__).parent / "fixtures" / "websets"
_S5_SAMPLE = _FIXTURES / "s5_category_company.json"
_FX_SNAPSHOT = _FIXTURES / "fx_ecb_snapshot.json"

LIVE = os.environ.get("DIGISEARCH_WEBSETS_LIVE") == "1"

#: Task 8 brief inputs — verbatim; the live leg must not drift from the brief.
RECORD_QUERY = "agtech robotics startups Series A 2024-2026"
RECORD_COUNT = 5
RECORD_CRITERIA = (
    VerificationCriterion(name="stage", rule="company raised a Series A between 2024 and 2026"),
    VerificationCriterion(
        name="agtech-robotics",
        rule="company builds agtech robotics hardware or automation",
    ),
)
RECORD_ENRICHMENTS: tuple[dict[str, object], ...] = (
    {"name": "company_profile", "type": "company_profile"},
    {"name": "funding_total", "type": "number"},
    {"name": "description", "type": "text"},
)

#: One 5-count live pass ceiling (recall + fetch + verify + enrich).
LIVE_TIMEOUT_S = 900.0


# ── record helpers (offline-tested; the live leg consumes them) ───────────────


def _load_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def _normalize_name(name: str) -> str:
    return re.sub(r"[^a-z0-9]+", " ", name.lower()).strip()


def _s5_funding_totals(sample: Mapping[str, Any]) -> dict[str, float | None]:
    totals: dict[str, float | None] = {}
    for result in sample["results"]:
        properties = result["entities"][0]["properties"]
        totals[_normalize_name(str(properties["name"]))] = properties.get("financials", {}).get(
            "fundingTotal"
        )
    return totals


def _event_record(events: Sequence[WebsetEvent]) -> dict[str, Any]:
    """Assert the Task 8 event contract and return the record values.

    The contract is the per-kind MULTISET plus ``webset.idle`` strictly last —
    never an exact sequence (the semaphore-4 runner does not guarantee
    inter-item order).
    """
    kinds = [event.type for event in events]
    assert kinds, "event log is empty"
    counts = {kind: kinds.count(kind) for kind in sorted(set(kinds))}
    assert counts.get("webset.idle", 0) == 1, f"expected exactly one webset.idle, got {counts}"
    assert kinds[-1] == "webset.idle", f"webset.idle must be last, got {kinds[-1]!r}"
    assert "webset.failed" not in counts, f"live pass failed: {counts}"
    assert counts.get("item.enriched", 0) <= counts.get("item.created", 0), counts
    return {"events": len(kinds), "kinds": counts, "idle_last": True}


def _company_profile_of(item: WebsetItem) -> dict[str, Any] | None:
    """The item's ``company_profile`` value as a plain mapping (stored/JSON shape)."""
    field = item.enrichments.get("company_profile")
    if field is None:
        return None
    value = field.value
    if isinstance(value, CompanyEntity):
        return value.model_dump(mode="json")
    if isinstance(value, Mapping):
        return dict(value)
    return None


def _funding_deltas(
    profiles: Sequence[Mapping[str, Any]], sample: Mapping[str, Any]
) -> list[dict[str, Any]]:
    """Record live-vs-s5 funding totals for the companies the two share (exact names)."""
    totals = _s5_funding_totals(sample)
    deltas: list[dict[str, Any]] = []
    for profile in profiles:
        key = _normalize_name(str(profile.get("name") or ""))
        if key not in totals:
            continue
        live_total = profile.get("funding_total")
        s5_total = totals[key]
        delta_pct: float | None = None
        if isinstance(live_total, (int, float)) and isinstance(s5_total, (int, float)) and s5_total:
            delta_pct = (float(live_total) - float(s5_total)) / float(s5_total)
        deltas.append(
            {
                "name": profile.get("name"),
                "live_total": live_total,
                "s5_total": s5_total,
                "delta_pct": delta_pct,
            }
        )
    return deltas


def _csv_export_record(content: str) -> dict[str, Any]:
    """Row count plus the citation URLs carried by the landed CSV export."""
    frame = pl.read_csv(io.StringIO(content))
    urls: set[str] = set()
    for column in (name for name in frame.columns if name.endswith("__citations")):
        for cell in frame[column].drop_nulls().to_list():
            urls.update(
                url
                for url in (part.strip() for part in str(cell).split(";"))
                if url.startswith(("http://", "https://"))
            )
    return {"rows": frame.height, "citation_urls": sorted(urls)}


# ── offline legs ──────────────────────────────────────────────────────────────


def test_record_inputs_match_the_task_8_brief_verbatim() -> None:
    assert RECORD_QUERY == "agtech robotics startups Series A 2024-2026"
    assert RECORD_COUNT == 5
    assert len(RECORD_CRITERIA) == 2
    assert len(RECORD_ENRICHMENTS) == 3
    assert [str(entry["name"]) for entry in RECORD_ENRICHMENTS].count("company_profile") == 1
    assert _S5_SAMPLE.is_file() and _FX_SNAPSHOT.is_file()


def test_event_record_accepts_a_shuffled_multiset_and_pins_idle_last() -> None:
    def event(index: int, kind: str) -> WebsetEvent:
        return WebsetEvent(
            id=f"{index:032x}",
            webset_id="ws_record",
            type=kind,  # type: ignore[arg-type]
            search_id="wss_record",
            item_id=f"wsi_{index}" if kind.startswith("item.") else "",
        )

    shuffled = [
        event(1, "item.created"),
        event(2, "item.enriched"),
        event(3, "item.created"),
        event(4, "item.enriched"),
        event(5, "webset.idle"),
    ]
    assert _event_record(shuffled) == {
        "events": 5,
        "kinds": {"item.created": 2, "item.enriched": 2, "webset.idle": 1},
        "idle_last": True,
    }

    with pytest.raises(AssertionError):  # idle not last
        _event_record([event(5, "webset.idle"), event(3, "item.created")])
    with pytest.raises(AssertionError):  # duplicate idle
        _event_record([event(5, "webset.idle"), event(6, "webset.idle")])
    with pytest.raises(AssertionError):  # failed pass
        _event_record([event(1, "webset.failed"), event(5, "webset.idle")])
    with pytest.raises(AssertionError):  # more enriched than created
        _event_record([event(1, "item.enriched"), event(5, "webset.idle")])


def test_funding_deltas_reconcile_vendored_sample_names() -> None:
    sample = _load_json(_S5_SAMPLE)
    profiles = [
        {"name": "NuCicer", "funding_total": 16_000_000.0},
        {"name": "Pollen Systems", "funding_total": 345_000.0},
        {"name": "Unrelated Robotics", "funding_total": 1.0},
    ]
    deltas = {str(entry["name"]): entry for entry in _funding_deltas(profiles, sample)}
    assert set(deltas) == {"NuCicer", "Pollen Systems"}
    assert deltas["NuCicer"]["s5_total"] == 16_000_000
    assert deltas["NuCicer"]["delta_pct"] == 0.0
    assert deltas["Pollen Systems"]["delta_pct"] == pytest.approx(-0.9)


def test_csv_export_record_counts_rows_and_citation_urls() -> None:
    webset = Webset(
        criteria=[RECORD_CRITERIA[0]],
        enrichments=[EnrichmentDef(name="company_profile", type="company_profile", status="idle")],
    )
    items = [
        WebsetItem(
            webset_id=webset.id,
            url="https://nucicer.com/",
            verification="verified",
            enrichments={
                "company_profile": EnrichedField(
                    value={"name": "NuCicer"}, citations=[Citation(url="https://nucicer.com/")]
                )
            },
        ),
        WebsetItem(
            webset_id=webset.id,
            url="https://pollensystems.com/",
            verification="verified",
            enrichments={
                "company_profile": EnrichedField(
                    value={"name": "Pollen Systems"},
                    citations=[Citation(url="https://pollensystems.com/")],
                )
            },
        ),
    ]
    record = _csv_export_record(export_csv(webset, items))
    assert record["rows"] == len(items)
    assert record["citation_urls"] == ["https://nucicer.com/", "https://pollensystems.com/"]


def test_vendored_fx_snapshot_is_carried_on_the_ecb_eur_convention() -> None:
    snapshot = _load_json(_FX_SNAPSHOT)
    rates = snapshot["rates"]
    assert snapshot["base"] == "EUR"
    assert "per 1 EUR" in snapshot["convention"]
    assert all(isinstance(rate, (int, float)) and rate > 0 for rate in rates.values())
    assert rates["USD"] > 0
    assert re.match(r"^\d{4}-\d{2}-\d{2}$", snapshot["reference_date"])


# ── live leg (opt-in scaffolding; never SLOs) ─────────────────────────────────


@pytest.mark.skipif(not LIVE, reason="live websets pass needs DIGISEARCH_WEBSETS_LIVE=1")
def test_live_webset_pass_records_events_funding_and_export(tmp_path: Path) -> None:
    missing = [name for name in (VERIFY_MODEL_ENV, ENRICH_MODEL_ENV) if not os.environ.get(name)]
    assert not missing, (
        f"live websets record needs {missing} (digillm model ids) plus a provider key"
    )

    store = WebsetStore(db_path=str(tmp_path / "websets_live.sqlite3"))
    webset = service.create_webset(
        query=RECORD_QUERY,
        count=RECORD_COUNT,
        criteria=list(RECORD_CRITERIA),
        enrichments=list(RECORD_ENRICHMENTS),
        store=store,
    )

    started = time.monotonic()
    asyncio.run(
        asyncio.wait_for(
            run_webset_async(webset.id, store=store, verification_mode="llm"),
            timeout=LIVE_TIMEOUT_S,
        )
    )
    seconds_to_idle = time.monotonic() - started

    settled = service.get_webset(webset.id, store=store)
    assert settled.status == "idle", f"live pass did not settle: {settled.status}"

    events, _ = service.list_events(webset.id, limit=200, store=store)
    events_record = _event_record(events)
    counts = service.count_items(webset.id, store=store)
    recalled = counts["verified"] + counts["rejected"]
    assert recalled >= 1, "live recall admitted no candidates — is a search backend reachable?"

    verified, _ = service.list_items(webset.id, verification="verified", limit=200, store=store)
    profiles: list[dict[str, Any]] = []
    unresolved_profiles = 0
    for item in verified:
        field = item.enrichments.get("company_profile")
        if field is None or field.status != "resolved":
            unresolved_profiles += 1
            continue
        assert field.citations, f"{item.url}: resolved company_profile without citations"
        profile = _company_profile_of(item)
        if profile is not None:
            profiles.append(profile)

    deltas = _funding_deltas(profiles, _load_json(_S5_SAMPLE))

    content, media_type = service.export_webset(webset.id, fmt="csv", store=store)
    assert media_type == "text/csv"
    csv_record = _csv_export_record(content)
    assert csv_record["rows"] == counts["verified"], "CSV must be one row per verified item"
    if csv_record["rows"]:
        assert csv_record["citation_urls"], "CSV citation columns carry no URLs"
    export_path = tmp_path / "websets_live_export.csv"
    export_path.write_text(content, encoding="utf-8")

    first, last = events[0].created_at, events[-1].created_at
    span_s = (
        (last - first).total_seconds()
        if isinstance(first, datetime) and isinstance(last, datetime)
        else None
    )
    record = {
        "date": datetime.now(UTC).date().isoformat(),
        "query": RECORD_QUERY,
        "count_target": RECORD_COUNT,
        "seconds_to_idle": round(seconds_to_idle, 3),
        "event_span_s": span_s,
        "events": events_record,
        "items": counts,
        "recalled": recalled,
        "unresolved_company_profiles": unresolved_profiles,
        "funding_deltas_vs_s5": deltas,
        "csv": {"rows": csv_record["rows"], "citation_urls": csv_record["citation_urls"]},
        "export_csv_path": str(export_path),
    }
    print(f"websets live record: {json.dumps(record, sort_keys=True)}")
