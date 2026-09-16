# score:allow untyped any
# model-boundary payload containers are dynamic JSON; Any is the honest annotation.
"""Phase D webset models — the canonical verify + enrich envelope (#4066).

A webset builds a verified, enriched, citable dataset asynchronously: a caller
submits a query + 1-5 natural-language verification criteria + up to 10 typed
enrichments, and the runner recalls candidates, verifies each candidate against
every rule, and enriches admitted items field-by-field with per-field citations
(spec: ``docs/superpowers/specs/2026-09-14-oss-websearch-phaseD-verify-enrich.md``).

This module is the model layer only; the store (``websets/store.py``),
verification (``websets/verify.py``), enrichment (``websets/enrich.py``), and
runner (``websets/runner.py``) tasks build on these shapes.

Conventions recorded here so later tasks need not re-derive them:

- ``Citation`` is imported from the shared web-grounding atom
  ``digisearch.web_search.citation`` (R1) and is never redefined. ``normalize_url``
  is applied at the comparison seams that need URL identity (the store / runner
  paths import it from that same shared atom, exactly as Phase C's
  ``monitors/store.py`` and ``monitors/dedup.py`` do) — this module deliberately
  does not re-export it, so there is one import site for the atom.
- Request shapes (caller-supplied input validated at the API boundary) use
  ``extra="forbid"``; EXA-normalized read shapes tolerate unknown keys
  (``extra="ignore"``) so the paid shim can validate EXA payloads without
  stripping every vendor field first.
- Ids are ``{prefix}_`` + ``uuid.uuid4().hex`` (``digibase/http.py`` request-id
  precedent). This is a deliberate divergence from Phase C, whose entities use
  ULIDs (``monitors/store.py`` ``new_ulid``): webset ids are not ordered by
  creation and no monotonic property is needed, so the sortable ULID layout buys
  nothing here. Patterns pin the shape so a store round-trip cannot smuggle in a
  foreign id.
- There is no ``provider``/``auto`` field anywhere (R4): the OSS path always
  recalls via ``search_web``; ``backend`` is a label recording which leg answered.
- ``verification_mode`` (``llm`` default | ``rules``) is persisted on both
  ``Webset`` and ``WebsetSearch``. The webset-level value is the default new
  searches inherit; the search-level value is the generation's actual mode, so
  a ``rules`` webset refreshed via ``add_search`` / ``trigger_monitor`` never
  silently falls back to ``llm`` (T6 review carry; previously the mode lived
  only in the in-flight schedule call).
"""

from __future__ import annotations

import uuid
from collections.abc import Callable
from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from digisearch.web_search.citation import Citation

BackendLabel = Literal["oss", "exa"]
WebsetStatus = Literal["running", "idle", "failed", "cancelled"]
SearchStatus = Literal["running", "idle", "failed", "cancelled"]
VerificationMode = Literal["llm", "rules"]
VerificationState = Literal["pending", "verified", "rejected"]
EnrichmentType = Literal[
    "text", "number", "date", "url", "email", "phone", "options", "company_profile"
]
EnrichmentStatus = Literal["running", "idle", "failed"]
EnrichedStatus = Literal["resolved", "unresolved", "skipped"]
EventKind = Literal["item.created", "item.enriched", "webset.idle", "webset.failed"]

_UUID4_HEX = r"[0-9a-f]{32}"


def _new_id(prefix: str) -> Callable[[], str]:
    """Return a factory minting ``{prefix}_<uuid4hex>`` ids (see module note)."""
    return lambda: f"{prefix}_{uuid.uuid4().hex}"


def _is_empty_value(value: Any) -> bool:
    """True when *value* carries no payload (``None``, ``""``, ``[]``, ``{}``).

    ``0`` and ``False`` are real enrichment values, not emptiness.
    """
    if value is None:
        return True
    if isinstance(value, (str, list, dict, tuple, set)):
        return not value
    return False


class VerificationCriterion(BaseModel):
    """One natural-language admission rule (1-5 rules per search).

    ``rule`` is the rule text evaluated at the verify seam
    (``websets/verify.py``); ``description`` is an optional human note. The
    ``rules`` verification mode maps these onto the landed ``domain`` /
    ``keyword`` / ``recency`` rule kinds — this model carries the text only.
    """

    model_config = ConfigDict(extra="forbid")

    name: str = Field(min_length=1, max_length=120)
    rule: str = Field(min_length=1, max_length=500)
    description: str = ""


class CriterionResult(BaseModel):
    """Verdict for one criterion: pass/fail + reasoning + grounding references.

    ``criterion`` is the full rule that was evaluated, so each result is a
    self-contained audit record; ``references`` is ``list[Citation]`` (the
    shared atom, R1) with ``title`` defaulting to ``""`` and ``excerpt``
    carrying the supporting quote. Rejected items retain the failing reasons;
    the fail-closed settlement writes one synthetic result per criterion with
    ``passed=False`` and empty references (flag I9).
    """

    model_config = ConfigDict(extra="ignore")

    criterion: VerificationCriterion
    passed: bool
    reasoning: str = ""
    references: list[Citation] = Field(default_factory=list)


class EnrichmentDef(BaseModel):
    """A typed per-item enrichment request (max 10 active per webset).

    ``options`` is populated only for ``type="options"`` (enforced here: an
    ``options`` def needs a non-empty choice list, and no other type may carry
    one). ``status`` tracks the attach/backfill lifecycle: ``running`` while the
    def is being attached or backfilled (``add_enrichment``), ``idle`` once
    settled, ``failed`` when that run failed.
    """

    model_config = ConfigDict(extra="forbid")

    id: str = Field(default_factory=_new_id("wse"), pattern=rf"^wse_{_UUID4_HEX}$")
    name: str = Field(min_length=1, max_length=120)
    type: EnrichmentType
    description: str = ""
    options: list[str] = Field(default_factory=list)
    status: EnrichmentStatus = "running"

    @model_validator(mode="after")
    def _check_options(self) -> EnrichmentDef:
        if self.type == "options":
            if not self.options:
                raise ValueError("options is required when type='options'")
        elif self.options:
            raise ValueError("options is only valid when type='options'")
        return self


class EnrichedField(BaseModel):
    """One enrichment field's value plus its citations (auditable by construction).

    ``citations`` is mandatory on success: a field with an empty ``value`` or
    empty ``citations`` validates as ``unresolved`` (downgraded here rather than
    left to callers) and ``error`` carries the reasoning; nothing is ever
    silently filled. An explicit ``skipped`` — never attempted because the
    webset was cancelled/failed first — is preserved. ``value`` is ``Any``
    because the shape is type-dependent (text/number/ISO date/option/entity
    payload); ``EnrichmentDef.type`` documents what to expect, and ``0``/
    ``False`` are values, never emptiness.
    """

    model_config = ConfigDict(extra="ignore")

    value: Any = None
    citations: list[Citation] = Field(default_factory=list)
    status: EnrichedStatus = "resolved"
    error: str | None = None

    @model_validator(mode="after")
    def _downgrade_uncited(self) -> EnrichedField:
        if self.status != "skipped" and (_is_empty_value(self.value) or not self.citations):
            self.status = "unresolved"
        return self


class FundingRound(BaseModel):
    """One funding round extracted from a page (merged by ``(name, date)``).

    ``date`` is an ISO month (``"2025-07"``); ``amount`` is USD-normalized via
    the ECB snapshot at the enrich seam (T4). ``citations`` keeps per-round
    provenance so ``funding_total`` can union the round citations when no page
    claims an explicit total. A non-USD round with no snapshot rate is recorded
    unresolved with reasoning by the enrich task — never guessed.
    """

    model_config = ConfigDict(extra="ignore")

    name: str = Field(min_length=1)
    date: str | None = None
    amount: float | None = None
    citations: list[Citation] = Field(default_factory=list)


class FieldAlternative(BaseModel):
    """A losing scalar value kept for audit (its own citations, no silent overwrite).

    Entity merge keeps the value with more independent citations and records
    the loser here with the citations that supported it.
    """

    model_config = ConfigDict(extra="ignore")

    field: str = Field(min_length=1)
    value: Any = None
    citations: list[Citation] = Field(default_factory=list)


class CompanyEntity(BaseModel):
    """Company profile mirroring EXA ``category=company`` inline entities.

    Every scalar carries per-scalar provenance in
    ``provenance: dict[str, list[Citation]]`` keyed by field name — a single
    flat ``citations[]`` wrapper cannot attribute which citation supports which
    scalar and is banned. A scalar with zero citations keeps an empty list in
    ``provenance`` and is reported in ``reasoning``. Conflicts keep the value
    with more independent citations and record the loser in ``alternatives[]``.
    """

    model_config = ConfigDict(extra="ignore")

    name: str = Field(min_length=1)
    founded_year: int | None = None
    description: str | None = None
    workforce_total: int | None = None
    hq_city: str | None = None
    hq_country: str | None = None
    funding_total: float | None = None
    funding_rounds: list[FundingRound] = Field(default_factory=list)
    provenance: dict[str, list[Citation]] = Field(default_factory=dict)
    alternatives: list[FieldAlternative] = Field(default_factory=list)
    reasoning: str = ""


class WebsetSearch(BaseModel):
    """One settling-pass generation (a webset's initial search or a refresh).

    ``count`` is the target number of VERIFIED items for this search — never a
    backend page size: the landed ``WebSearchRequest.max_results`` page size
    stays at most 10 (``web_search/models.py``) and the runner reaches
    ``count`` by query diversification (R3); there is no paging parameter to
    clamp from (audit D25). ``status`` includes ``cancelled``: ``cancel_webset``
    settles every non-terminal search as ``cancelled`` (flag I6).
    ``criteria`` is the 1-5 rule set (``add_search`` inherits the webset's
    initial criteria when none are given). ``verification_mode`` is the mode
    this generation runs under (persisted, so a ``rules`` webset never silently
    switches to ``llm`` on a refresh — T6 review carry).
    """

    model_config = ConfigDict(extra="ignore")

    id: str = Field(default_factory=_new_id("wss"), pattern=rf"^wss_{_UUID4_HEX}$")
    webset_id: str = Field(min_length=1)
    query: str = Field(min_length=1, max_length=500)
    count: int = Field(default=10, ge=1, le=100)
    status: SearchStatus = "running"
    criteria: list[VerificationCriterion] = Field(min_length=1, max_length=5)
    verification_mode: VerificationMode = "llm"
    backend: BackendLabel = "oss"


class Webset(BaseModel):
    """A webset: criteria + enrichments over asynchronously built items.

    ``status`` is ``running`` during the first pass, sticky ``idle`` after
    completion (a refresh never flips it back — observe refreshes through the
    new ``WebsetSearch`` + events, § Async lifecycle), and terminal
    ``failed``/``cancelled``. ``criteria`` is the initial rule set later
    searches inherit; ``enrichments`` holds at most 10 active defs. ``backend``
    is the R4 label (there is no caller-facing provider parameter).
    ``verification_mode`` is the webset-level default persisted with the row:
    searches created later (``add_search`` / ``trigger_monitor`` refreshes)
    inherit it, so a ``rules`` webset never silently switches to ``llm``
    (T6 review carry; the runner receives the mode per scheduled pass).
    """

    model_config = ConfigDict(extra="ignore")

    id: str = Field(default_factory=_new_id("ws"), pattern=rf"^ws_{_UUID4_HEX}$")
    object: Literal["webset"] = "webset"
    status: WebsetStatus = "running"
    criteria: list[VerificationCriterion] = Field(min_length=1, max_length=5)
    searches: list[WebsetSearch] = Field(default_factory=list)
    enrichments: list[EnrichmentDef] = Field(default_factory=list, max_length=10)
    workspace_id: str | None = None
    backend: BackendLabel = "oss"
    verification_mode: VerificationMode = "llm"
    created_at: datetime | None = None
    updated_at: datetime | None = None


class WebsetItem(BaseModel):
    """An admitted (or audit-retained rejected) candidate with verdicts + fields.

    ``verification="pending"`` is the in-flight/queued state only: when a
    search's candidate pass finishes, every still-pending item settles
    ``rejected`` (fail-closed, never admitted) with synthetic criterion
    results, so ``pending`` can never block ``idle`` (flag I9). Enrichments map
    field name -> ``EnrichedField`` (per-field value + citations + terminal
    status).
    """

    model_config = ConfigDict(extra="ignore")

    id: str = Field(default_factory=_new_id("wsi"), pattern=rf"^wsi_{_UUID4_HEX}$")
    webset_id: str = Field(min_length=1)
    url: str = Field(min_length=1)
    title: str = ""
    verification: VerificationState = "pending"
    criteria_results: list[CriterionResult] = Field(default_factory=list)
    enrichments: dict[str, EnrichedField] = Field(default_factory=dict)
    created_at: datetime | None = None


class WebsetMonitor(BaseModel):
    """Refresh-cadence metadata on a webset, executed by the tick driver (#4221).

    ``interval_seconds`` is the cadence the shared driver's tick loop honors
    (``websets/driver.py``: due when ``now - last_tick >= interval_seconds``
    over in-process schedule state re-anchored at the first post-install
    sighting). ``paused`` is the operator switch the tick honors: a paused
    monitor is skipped by the tick while the manual ``trigger_monitor`` route
    still refreshes it on demand — the ``active|paused`` lifecycle (flag I4),
    now observable. A webset monitor is explicitly NOT a Phase C ``Watch``
    (R7e — the bare ``Monitor`` name is banned because it collides with the
    landed Watch/MonitorRun family).
    """

    model_config = ConfigDict(extra="forbid")

    id: str = Field(default_factory=_new_id("wsm"), pattern=rf"^wsm_{_UUID4_HEX}$")
    object: Literal["webset_monitor"] = "webset_monitor"
    webset_id: str = Field(min_length=1)
    interval_seconds: int = Field(default=3600, ge=60)
    webhook_url: str | None = None
    paused: bool = False
    created_at: datetime | None = None


class WebhookConfig(BaseModel):
    """A registered webset webhook (secret-once responses; shared signing R7).

    ``secret`` is server-generated (``secrets.token_urlsafe(32)``) and returned
    in cleartext once (create / rotate); it is stored alongside the record and
    never logged. Rotation keeps ``previous_secret`` valid until
    ``previous_expires_at`` (24h overlap). Delivery signs with the shared
    Phase C core so the ``X-digi-signature`` bytes are identical across both
    egresses; delivery state lives in the ``webhook_deliveries`` ledger, never
    on the event row. ``events`` is the subscribed subset of the v1 event
    kinds; ``webhook_id`` is assigned when the record is created (bare
    uuid4-hex — outside the five prefixed id families).
    """

    model_config = ConfigDict(extra="forbid")

    webhook_id: str = ""
    url: str = Field(min_length=1)
    events: list[EventKind] = Field(default_factory=list)
    secret: str = ""
    previous_secret: str | None = None
    previous_expires_at: datetime | None = None
    active: bool = True
    created_at: datetime | None = None


class WebsetEvent(BaseModel):
    """One append-only event row (oldest-first tailing; delivery state never here).

    The deterministic idempotency key is NOT carried here: the store builds it
    from ``(webset_id, type, search_id, item_id or "", field or "")`` (flag I3)
    and enforces a UNIQUE ``(webset_id, dedup_key)`` index with INSERT OR
    IGNORE, so a resumed runner within one generation cannot duplicate an event
    while a new generation (each ``add_search`` / backfill / ``trigger_monitor``
    pass) legitimately re-emits terminal events. ``search_id`` is the
    ``WebsetSearch`` generation that produced the event; ``item_id`` is empty
    for webset-level events; ``field`` is reserved for field-scoped kinds
    (none in v1). ``id`` is a bare uuid4-hex (deliberately outside the five
    prefixed id families); ``payload`` is the delivery/consumer body and never
    a full page body.
    """

    model_config = ConfigDict(extra="ignore")

    id: str = Field(default_factory=lambda: uuid.uuid4().hex)
    webset_id: str = Field(min_length=1)
    type: EventKind
    search_id: str = Field(min_length=1)
    item_id: str = ""
    field: str = ""
    payload: dict[str, Any] = Field(default_factory=dict)
    created_at: datetime | None = None
