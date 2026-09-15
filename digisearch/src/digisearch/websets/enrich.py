"""Phase D enrichment engine (#4066, Task 4) — typed fields + funding/entity merge.

The enrichment half of a webset: every ``EnrichmentDef`` resolves to one
``EnrichedField`` per item, and ``citations`` is mandatory on success — a field
with an empty value or empty citations is ``unresolved``, never silently filled
(spec ``docs/superpowers/specs/2026-09-14-oss-websearch-phaseD-verify-enrich.md``
§ Enrichment engine + per-field citations, § Company/people enrichment).

Extraction is one schema-pinned digillm structured completion per field, mocked
at the ``llm_client`` boundary exactly like ``websets/verify.py`` (unit tests
never reach a live model). The candidate page text is the caller's already-fetched
``fetch_markdown`` output (R2 — never indexed) and is truncated to
``MARKDOWN_TRUNCATION_CHARS`` for prompt-cost parity with the T3 verification
budget. Model payloads are validated strictly (pydantic v2): ``number`` must
parse as a finite float, ``date`` as a full ISO-8601 date, ``url``/``email``/
``phone`` against format validators, ``options`` must equal one of ``options[]``,
and ``company_profile`` must yield a complete ``CompanyEntity`` — a bad value is
``unresolved`` with reasoning, never coerced and never admitted uncited.

Company funding history (spec § Company/people enrichment items 3-7)
--------------------------------------------------------------------

``enrich_item`` extracts one page's company profile; the cross-page work lives in
dedicated, fixture-testable functions:

- :func:`reconcile_funding_history` normalizes raw round events (name lowercased,
  date to ISO month, amount to USD with the ECB snapshot loaded by
  :func:`load_fx_snapshot`) and merges them by ``(name, date)``. A round is
  admitted on quorum — >= 2 independent page citations, or 1 citation from the
  company's own domain (``company_domain``); single third-party mentions stay
  ``unresolved``. ``funding_total`` is the sum of the admitted rounds; when at
  least one page claims an explicit total, the median claimed total must be
  within ``RECONCILIATION_TOLERANCE`` (1%) of the sum or the total is
  unresolved with reasoning; with no claimed totals the sum stands (provenance =
  union of the admitted round citations). A non-USD amount with no snapshot rate
  is unresolved, never guessed. The ECB snapshot is deliberately out-of-tree —
  the vendored copy is ``tests/ds/fixtures/websets/fx_ecb_snapshot.json`` — so
  callers pass ``fx_rates`` explicitly or set ``DIGISEARCH_FX_SNAPSHOT``.
- :func:`merge_company_entities` groups candidates by normalized page domain +
  name similarity, keeps the scalar value with more independent citations,
  records each losing value in ``alternatives[]`` with its own citations, and
  reconciles the group's funding evidence.
- :func:`company_profile_field` bundles a merged ``CompanyEntity`` into one
  ``EnrichedField`` (flag I8) whose citations are the union of the entity's
  provenance citations, or ``unresolved`` when no scalar is resolved.

No store writes, no corpus writes, no indexing: this module is pure extraction
and merge over the T1 models plus the shared ``Citation`` atom (R1, imported
from :mod:`digisearch.web_search.citation` — never redefined).
"""

# score:allow untyped any
# The digillm client, its duck-typed ChatCompletion response, the provider payload
# JSON, and the type-dependent enrichment ``value`` cross this module's seams;
# Any is the honest annotation there.
from __future__ import annotations

import json
import math
import os
import re
import statistics
from collections.abc import Iterable, Mapping, Sequence
from datetime import date
from pathlib import Path
from typing import Any
from urllib.parse import urlsplit

from pydantic import BaseModel, ConfigDict, Field, ValidationError

from digisearch.web_search.citation import Citation, normalize_url
from digisearch.websets.models import (
    CompanyEntity,
    EnrichedField,
    EnrichmentDef,
    FieldAlternative,
    FundingRound,
)

__all__ = [
    "ENRICH_MODEL_ENV",
    "FX_SNAPSHOT_ENV",
    "MARKDOWN_TRUNCATION_CHARS",
    "PROVENANCE_SCALARS",
    "RECONCILIATION_TOLERANCE",
    "CompanyCandidate",
    "FundingObservation",
    "FundingReconciliation",
    "RawFundingRound",
    "company_profile_field",
    "enrich_item",
    "load_fx_snapshot",
    "merge_company_entities",
    "reconcile_funding_history",
]

#: digillm model id env var for field/company extraction (unset ⇒ unresolved).
ENRICH_MODEL_ENV = "DIGISEARCH_ENRICH_MODEL"

#: Env var carrying the ECB snapshot path for FX normalization (see loader).
FX_SNAPSHOT_ENV = "DIGISEARCH_FX_SNAPSHOT"

#: Candidate page markdown budget handed to an extraction LLM call — the same
#: full-page budget T3 verification uses (6000 chars), deliberately not a
#: Phase B synthesis snippet.
MARKDOWN_TRUNCATION_CHARS = 6000

#: Reconciliation guard: the median claimed total must be within this fraction
#: of the summed rounds, else ``funding_total`` is unresolved.
RECONCILIATION_TOLERANCE = 0.01

#: The ``CompanyEntity`` scalars that must carry a ``provenance[field]`` entry.
PROVENANCE_SCALARS: tuple[str, ...] = (
    "name",
    "founded_year",
    "description",
    "workforce_total",
    "hq_city",
    "hq_country",
    "funding_total",
)

#: Scalars merged across candidate pages; ``funding_total`` comes from the
#: funding reconciliation instead (never a plain citation-count contest).
_MERGE_SCALARS: tuple[str, ...] = PROVENANCE_SCALARS[:-1]

#: digillm ``usage_kind`` label so enrichment spend is attributable per call.
_USAGE_KIND = "webset_enrich"

_FIELD_SCHEMA_NAME = "webset_enrichment"
_COMPANY_SCHEMA_NAME = "webset_company"

#: ISO month prefix of a funding round date (``2025-07`` / ``2025-07-01`` / ISO
#: datetime); anything else is unresolved, never guessed.
_MONTH_PREFIX = re.compile(r"^(\d{4})-(\d{1,2})(?:-\d{1,2})?")

#: Email format check — one @, a dotted domain, no whitespace.
_EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")

#: Dialable phone shape: optional +, digits with common separators.
_PHONE_RE = re.compile(r"^\+?[0-9][0-9()\-\s.]*$")
_PHONE_DIGITS_RE = re.compile(r"\D")

_FIELD_SYSTEM_PROMPT = (
    "You extract one requested field from a candidate web page as a JSON object "
    "with `value`, `citations`, and `reasoning`.\n"
    "Rules:\n"
    "1. Use ONLY the candidate text supplied; never invent values or urls.\n"
    "2. `value` is null when the page does not state the requested field.\n"
    "3. `citations` lists the supporting quotes as `{url, title, excerpt}` objects; "
    "every citation points at the candidate url and quotes the page verbatim. "
    "Never return a value without at least one citation.\n"
    "4. `reasoning` is a short justification grounded in the page text."
)

_COMPANY_SYSTEM_PROMPT = (
    "You extract one company profile from a candidate web page as a JSON object "
    "with the company scalars, `funding_rounds`, `provenance`, and `reasoning`.\n"
    "Rules:\n"
    "1. Use ONLY the candidate text supplied; never invent values or urls.\n"
    "2. `provenance` maps each scalar field name (`name`, `founded_year`, "
    "`description`, `workforce_total`, `hq_city`, `hq_country`, `funding_total`) "
    "to the list of `{url, title, excerpt}` citations that support that scalar.\n"
    "3. `funding_rounds` entries carry `name`, `date` (ISO), `amount`, `currency`, "
    "and their own `citations`; omit a round rather than guessing.\n"
    "4. Never return a scalar without at least one provenance citation."
)


class RawFundingRound(BaseModel):
    """One pre-normalization funding round as extracted from a page.

    ``currency`` travels with the raw amount so the ECB snapshot conversion can
    happen in :func:`reconcile_funding_history` — the landed ``FundingRound``
    model carries USD amounts only, so the raw round is the currency-carrying
    input unit.
    """

    model_config = ConfigDict(extra="ignore")

    name: str = Field(min_length=1)
    date: str | None = None
    amount: float | None = None
    currency: str = "USD"
    citations: list[Citation] = Field(default_factory=list)


class FundingObservation(BaseModel):
    """One page's raw funding evidence: round events + an optional claimed total.

    The claimed total is the page's explicit ``funding total`` statement; it is
    USD-normalized at reconcile time and only validates the summed rounds — it
    never overrides them.
    """

    model_config = ConfigDict(extra="ignore")

    url: str = Field(min_length=1)
    rounds: list[RawFundingRound] = Field(default_factory=list)
    claimed_total: float | None = None
    claim_currency: str = "USD"
    claim_citations: list[Citation] = Field(default_factory=list)


class CompanyCandidate(BaseModel):
    """One candidate page's company extraction (the entity-merge input unit).

    ``funding`` carries the page's raw (currency-bearing) funding evidence when
    the caller has it; when omitted, the entity's already-normalized
    ``funding_rounds`` / ``funding_total`` are reconciled as USD.
    """

    model_config = ConfigDict(extra="ignore")

    url: str = Field(min_length=1)
    entity: CompanyEntity
    funding: FundingObservation | None = None


class FundingReconciliation(BaseModel):
    """The merged funding history plus the reconciliation verdict.

    ``rounds`` holds the quorum-admitted, FX-normalized, ISO-month rounds whose
    amounts sum to ``total`` when reconciliation succeeds; ``unresolved_rounds``
    holds rounds that failed quorum or currency normalization (kept for audit,
    never counted); ``reasoning`` records every failed/dropped decision and is
    ``""`` only when the history reconciled cleanly without caveats.
    """

    model_config = ConfigDict(extra="forbid")

    total: float | None = None
    rounds: list[FundingRound] = Field(default_factory=list)
    total_citations: list[Citation] = Field(default_factory=list)
    unresolved_rounds: list[FundingRound] = Field(default_factory=list)
    reasoning: str = ""


# ── shared helpers ────────────────────────────────────────────────────────────


def _is_empty_value(value: Any) -> bool:
    """True when *value* carries no payload (``None``/empty string).

    ``0`` and ``False`` are real scalar values (the T1 ``EnrichedField``
    precedent); blank strings are not.
    """
    if value is None:
        return True
    if isinstance(value, str):
        return not value.strip()
    return False


def _citation_identity(citation: Citation) -> tuple[str, str, str]:
    """URL identity (via the shared ``normalize_url``) + title + excerpt."""
    try:
        url = normalize_url(citation.url)
    except ValueError:
        url = citation.url
    return (url, citation.title, citation.excerpt)


def _dedup_citations(citations: Iterable[Citation]) -> list[Citation]:
    """Drop exact duplicate citations, keeping first-seen order.

    Identity is ``(normalized url, title, excerpt)``: the same url with a
    different quote is a distinct piece of evidence and is retained.
    """
    seen: set[tuple[str, str, str]] = set()
    deduped: list[Citation] = []
    for citation in citations:
        identity = _citation_identity(citation)
        if identity in seen:
            continue
        seen.add(identity)
        deduped.append(citation)
    return deduped


def _distinct_url_count(citations: Sequence[Citation]) -> int:
    """Independent page citations: distinct normalized citation urls."""
    return len({_citation_identity(citation)[0] for citation in citations})


def _host(url: str) -> str:
    """Lowercased hostname without a leading ``www.`` (empty when unparseable)."""
    host = (urlsplit(url).hostname or "").lower()
    return host[4:] if host.startswith("www.") else host


def _domain_matches(host: str, domain: str) -> bool:
    """Exact host or subdomain match against *domain* (both lowercased)."""
    normalized = domain.strip().lower().lstrip(".")
    if normalized.startswith("www."):
        normalized = normalized[4:]
    if not host or not normalized:
        return False
    return host == normalized or host.endswith(f".{normalized}")


def _resolve_rates(fx_rates: Mapping[str, float] | None) -> dict[str, float] | None:
    """Explicit rates win; else the ``DIGISEARCH_FX_SNAPSHOT`` file; else None."""
    if fx_rates is not None:
        rates = {str(code).upper(): float(rate) for code, rate in fx_rates.items()}
        if "USD" not in rates:
            raise ValueError("FX rates mapping carries no USD rate")
        return rates
    env_path = os.environ.get(FX_SNAPSHOT_ENV, "").strip()
    return load_fx_snapshot(env_path) if env_path else None


def _normalize_amount(
    amount: float | None,
    currency: str | None,
    rates: Mapping[str, float] | None,
) -> tuple[float | None, str]:
    """Convert a raw amount to USD with the ECB snapshot; never guessed.

    The snapshot convention (documented in the vendored file) is ``rates[c]``
    units of *c* per 1 EUR; EUR is the base and has no entry. An unknown
    currency with no rate is unresolved with reasoning.
    """
    if amount is None:
        return None, ""
    code = str(currency or "USD").strip().upper() or "USD"
    if code == "USD":
        return float(amount), ""
    if rates is None:
        return None, f"no FX snapshot configured to convert {code} to USD"
    if code == "EUR":
        return float(amount) * rates["USD"], ""
    rate = rates.get(code)
    if rate is None or rate <= 0:
        return None, f"no ECB snapshot rate for currency {code}; amount left unresolved"
    return float(amount) * rates["USD"] / rate, ""


def _iso_month(value: str | None) -> tuple[str | None, str]:
    """Normalize a round date to ``YYYY-MM``; unparseable dates are unresolved."""
    if value is None:
        return None, ""
    text = str(value).strip()
    if not text:
        return None, ""
    match = _MONTH_PREFIX.match(text)
    if match is None or not 1 <= int(match.group(2)) <= 12:
        return None, f"unparseable funding round date {value!r}; expected an ISO month"
    return f"{match.group(1)}-{int(match.group(2)):02d}", ""


def _normalize_round(
    raw: RawFundingRound, rates: Mapping[str, float] | None
) -> tuple[FundingRound | None, str]:
    """Normalize one raw round; a non-empty reason marks it unresolved.

    Returns ``(None, reason)`` when the round cannot be represented at all
    (unparseable date) and ``(round, reason)`` with the amount left ``None``
    when only the currency conversion failed — callers exclude either form from
    the admitted history and keep the reasoning.
    """
    name = raw.name.strip().lower()
    month, date_reason = _iso_month(raw.date)
    if date_reason:
        return None, date_reason
    currency = (raw.currency or "USD").strip().upper() or "USD"
    amount, amount_reason = _normalize_amount(raw.amount, currency, rates)
    normalized = FundingRound(
        name=name,
        date=month,
        amount=amount,
        citations=_dedup_citations(raw.citations),
    )
    if amount_reason:
        return normalized, f"round {name!r} ({currency}): {amount_reason}"
    return normalized, ""


# ── funding history merge ─────────────────────────────────────────────────────


def load_fx_snapshot(path: str | Path | None = None) -> dict[str, float]:
    """Load the ECB reference-rate snapshot as ``{currency: units per EUR}``.

    Resolution: explicit *path* → the ``DIGISEARCH_FX_SNAPSHOT`` env var →
    ``FileNotFoundError`` naming the env var. The vendored snapshot is
    ``tests/ds/fixtures/websets/fx_ecb_snapshot.json``; the file is deliberately
    out-of-tree, so callers point the env var (or ``fx_rates``) at it rather
    than production code reaching into the test tree.
    """
    resolved = Path(path) if path is not None else None
    if resolved is None:
        env_path = os.environ.get(FX_SNAPSHOT_ENV, "").strip()
        if not env_path:
            raise FileNotFoundError(f"no FX snapshot path given and {FX_SNAPSHOT_ENV} is not set")
        resolved = Path(env_path)
    payload = json.loads(resolved.read_text(encoding="utf-8"))
    rates_raw = payload.get("rates") if isinstance(payload, dict) else None
    if not isinstance(rates_raw, dict) or not rates_raw:
        raise ValueError(f"FX snapshot {resolved} carries no rates object")
    rates = {str(code).upper(): float(rate) for code, rate in rates_raw.items()}
    if rates.get("USD", 0) <= 0:
        raise ValueError(f"FX snapshot {resolved} carries no positive USD rate")
    return rates


def _group_admitted(
    groups: dict[tuple[str, str | None], list[tuple[FundingRound, str]]],
    *,
    company_domain: str | None,
    notes: list[str],
) -> tuple[list[FundingRound], list[FundingRound]]:
    """Split merged-by-key round groups into admitted and unresolved rounds.

    A key whose every observation failed currency normalization is unresolved
    outright (spec § Company/people enrichment item 4 — never guessed); a key
    with usable evidence is admitted on quorum, keeping the failed-currency
    reasoning as a note.
    """
    admitted: list[FundingRound] = []
    unresolved: list[FundingRound] = []
    for (name, month), members in groups.items():
        citations = _dedup_citations(
            citation for member, _ in members for citation in member.citations
        )
        reasons = [reason for _, reason in members if reason]
        usable = [member for member, reason in members if not reason]
        independent = _distinct_url_count(citations)
        own_domain = bool(company_domain) and any(
            _domain_matches(_host(citation.url), company_domain or "") for citation in citations
        )
        if not usable:
            unresolved.append(members[0][0].model_copy(update={"citations": citations}))
            notes.extend(reasons)
            continue
        if independent < 2 and not own_domain:
            unresolved.append(members[0][0].model_copy(update={"citations": citations}))
            notes.extend(reasons)
            notes.append(
                f"round {name!r} ({month or 'undated'}) carries {independent} independent "
                "page citation(s) — quorum requires 2 or 1 from the company's own domain"
            )
            continue
        best_amount = usable[0].amount
        best_count = -1
        for member in usable:
            count = _distinct_url_count(member.citations)
            if count > best_count:
                best_count = count
                best_amount = member.amount
        admitted.append(
            FundingRound(name=name, date=month, amount=best_amount, citations=citations)
        )
        notes.extend(reasons)
    return admitted, unresolved


def _within_tolerance(value: float, reference: float) -> bool:
    """``abs(value - reference) <= 1% of reference`` (zero reference needs zero)."""
    if reference == 0:
        return value == 0
    return abs(value - reference) <= RECONCILIATION_TOLERANCE * reference


def reconcile_funding_history(
    observations: Sequence[FundingObservation],
    *,
    company_domain: str | None = None,
    fx_rates: Mapping[str, float] | None = None,
) -> FundingReconciliation:
    """Merge reported funding rounds and reconcile the total (spec § Architecture).

    Round events extracted across pages are normalized (name lowercased, date to
    ISO month, amount to USD) and merged by ``(name, date)``. A round is admitted
    on quorum: >= 2 independent page citations, or 1 citation from
    *company_domain* (``None`` disables the own-domain arm). ``funding_total`` is
    the sum of the admitted rounds; if at least one page claims an explicit total,
    the **median** claim must be within 1% of the sum or the total is
    ``None``/unresolved with reasoning; if no page claims a total, the sum stands
    (provenance = union of the admitted round citations). All decisions — quorum
    failures, unparseable dates, missing rates, failed reconciliation — accumulate
    in ``reasoning``; nothing is guessed and a single page never vetoes a
    quorum-admitted round. An explicit *fx_rates* mapping without a USD rate is
    a caller bug and raises ``ValueError``; with no rates configured at all,
    non-USD amounts are unresolved with reasoning.
    """
    rates = _resolve_rates(fx_rates)
    notes: list[str] = []
    groups: dict[tuple[str, str | None], list[tuple[FundingRound, str]]] = {}
    for observation in observations:
        for raw in observation.rounds:
            normalized, reason = _normalize_round(raw, rates)
            if normalized is None:
                notes.append(reason)
                continue
            groups.setdefault((normalized.name, normalized.date), []).append((normalized, reason))

    admitted, unresolved = _group_admitted(groups, company_domain=company_domain, notes=notes)

    claimed: list[tuple[float, list[Citation]]] = []
    for observation in observations:
        if observation.claimed_total is None:
            continue
        total_usd, reason = _normalize_amount(
            observation.claimed_total, observation.claim_currency, rates
        )
        if total_usd is None:
            notes.append(f"claimed funding total dropped: {reason}")
            continue
        claimed.append((total_usd, list(observation.claim_citations)))

    summed = sum(round_.amount or 0.0 for round_ in admitted)
    round_citations = _dedup_citations(
        citation for round_ in admitted for citation in round_.citations
    )
    total: float | None = None
    total_citations: list[Citation] = []
    if claimed:
        median = statistics.median([value for value, _ in claimed])
        if _within_tolerance(median, summed):
            total = summed
            total_citations = _dedup_citations(
                [citation for _, citations in claimed for citation in citations] + round_citations
            )
        else:
            notes.append(
                f"funding total reconciliation failed: median claimed total {median:,.2f} "
                f"differs from the {summed:,.2f} sum of admitted rounds by more than "
                f"{RECONCILIATION_TOLERANCE:.0%}"
            )
    elif admitted:
        total = summed
        total_citations = round_citations
    else:
        notes.append("no funding evidence to reconcile; funding_total is unresolved")

    return FundingReconciliation(
        total=total,
        rounds=admitted,
        total_citations=total_citations,
        unresolved_rounds=unresolved,
        reasoning="; ".join(notes),
    )


# ── entity merge ──────────────────────────────────────────────────────────────


def _name_key(name: str) -> str:
    """Case/punctuation-insensitive company name key (``NuCicer, Inc.`` → nucicerinc)."""
    return "".join(character for character in name.casefold() if character.isalnum())


def _names_similar(left: str, right: str) -> bool:
    """Name keys are equal, or one contains the other without being a stub."""
    if not left or not right:
        return False
    if left == right:
        return True
    shorter, longer = sorted((left, right), key=len)
    return shorter in longer and len(shorter) >= 0.5 * len(longer)


def _same_entity(left: CompanyCandidate, right: CompanyCandidate) -> bool:
    """Same normalized name, or same page domain plus similar names."""
    left_name, right_name = _name_key(left.entity.name), _name_key(right.entity.name)
    if left_name and left_name == right_name:
        return True
    left_host, right_host = _host(left.url), _host(right.url)
    return bool(left_host) and left_host == right_host and _names_similar(left_name, right_name)


def _choose_scalar(
    observations: Sequence[tuple[Any, Sequence[Citation]]],
) -> tuple[Any, list[Citation]]:
    """The value with the most independent citations (ties keep first-seen).

    Uncited values never beat cited ones; when nothing is cited the first value
    is kept so the audit slice still shows what was extracted. The returned
    citations are the deduped union of every observation agreeing with the
    winner — two pages asserting the same value are stronger evidence than one.
    """
    if not observations:
        return None, []
    cited = [(value, citations) for value, citations in observations if citations]
    ranked = cited or list(observations)
    best_value = ranked[0][0]
    best_count = -1
    for value, citations in ranked:
        count = _distinct_url_count(citations)
        if count > best_count:
            best_count = count
            best_value = value
    agreeing = [citations for value, citations in observations if value == best_value]
    return best_value, _dedup_citations(
        citation for citations in agreeing for citation in citations
    )


def _funding_observation(candidate: CompanyCandidate) -> FundingObservation:
    """The candidate's raw funding evidence; entity values are trusted as USD."""
    entity = candidate.entity
    return FundingObservation(
        url=candidate.url,
        rounds=[
            RawFundingRound(
                name=round_.name,
                date=round_.date,
                amount=round_.amount,
                currency="USD",
                citations=round_.citations,
            )
            for round_ in entity.funding_rounds
        ],
        claimed_total=entity.funding_total,
        claim_citations=list(entity.provenance.get("funding_total", [])),
    )


def _merge_group(
    group: Sequence[CompanyCandidate],
    *,
    company_domain: str | None,
    rates: Mapping[str, float] | None,
) -> CompanyEntity:
    """One merged entity: scalar winner/alternatives + reconciled funding."""
    notes: list[str] = []
    provenance: dict[str, list[Citation]] = {field: [] for field in PROVENANCE_SCALARS}
    alternatives: list[FieldAlternative] = []
    scalars: dict[str, Any] = {}
    for field in _MERGE_SCALARS:
        observations = [
            (getattr(candidate.entity, field), candidate.entity.provenance.get(field, []))
            for candidate in group
            if not _is_empty_value(getattr(candidate.entity, field))
        ]
        value, citations = _choose_scalar(observations)
        scalars[field] = value
        provenance[field] = citations
        if value is None:
            continue
        if not citations:
            notes.append(f"{field} carries no citations — unresolved for the entity")
        for other_value, other_citations in observations:
            if other_value != value:
                alternatives.append(
                    FieldAlternative(
                        field=field,
                        value=other_value,
                        citations=_dedup_citations(other_citations),
                    )
                )

    funding = reconcile_funding_history(
        [candidate.funding or _funding_observation(candidate) for candidate in group],
        company_domain=company_domain,
        fx_rates=rates,
    )
    scalars["funding_total"] = funding.total
    provenance["funding_total"] = funding.total_citations
    if funding.reasoning:
        notes.append(funding.reasoning)

    return CompanyEntity(
        **scalars,
        funding_rounds=funding.rounds,
        provenance=provenance,
        alternatives=alternatives,
        reasoning="; ".join(notes),
    )


def merge_company_entities(
    candidates: Sequence[CompanyCandidate],
    *,
    company_domain: str | None = None,
    fx_rates: Mapping[str, float] | None = None,
) -> list[CompanyEntity]:
    """Merge candidate pages into one entity per company (first-seen group order).

    Candidates join a group when their normalized names match, or when they share
    a page domain and their names are similar (``NuCicer`` / ``NuCicer, Inc.``).
    Within a group every scalar keeps the value with more independent citations
    and records each losing value in ``alternatives[]`` with its own citations
    (no silent overwrite); ``funding_total``/``funding_rounds`` come from
    :func:`reconcile_funding_history` over the group's evidence. Every scalar
    ends with a ``provenance[field]`` entry — empty when unresolved — and the
    resolving reasoning lands on the entity.
    """
    rates = _resolve_rates(fx_rates)
    groups: list[list[CompanyCandidate]] = []
    for candidate in candidates:
        for group in groups:
            if any(_same_entity(candidate, member) for member in group):
                group.append(candidate)
                break
        else:
            groups.append([candidate])
    return [_merge_group(group, company_domain=company_domain, rates=rates) for group in groups]


# ── company_profile bundling (flag I8) ────────────────────────────────────────


def company_profile_field(entity: CompanyEntity) -> EnrichedField:
    """Bundle a merged ``CompanyEntity`` into one ``EnrichedField`` (flag I8).

    The field is ``resolved`` when the entity has at least one resolved scalar
    (a value plus provenance citations); its citations are the dedup union of the
    entity's provenance citations (the shared ``Citation`` atom — never a copy).
    Without a resolved scalar the field is ``unresolved`` with reasoning, so an
    evidence-free profile is never presented as fact.
    """
    resolved = [
        field
        for field in PROVENANCE_SCALARS
        if not _is_empty_value(getattr(entity, field)) and entity.provenance.get(field)
    ]
    if not resolved:
        return _unresolved(
            "company profile has no resolved scalars (value plus provenance citations)"
        )
    citations = _dedup_citations(
        citation for field in PROVENANCE_SCALARS for citation in entity.provenance.get(field, [])
    )
    return EnrichedField(value=entity, citations=citations)


# ── field extraction (digillm boundary) ───────────────────────────────────────


def _citation_schema() -> dict[str, Any]:
    return {
        "type": "object",
        "properties": {
            "url": {"type": "string"},
            "title": {"type": "string"},
            "excerpt": {"type": "string"},
        },
        "required": ["url"],
        "additionalProperties": False,
    }


def _value_schema(enrichment: EnrichmentDef) -> dict[str, Any]:
    """The pinned ``value`` schema for the requested enrichment type."""
    if enrichment.type == "number":
        return {"type": ["number", "null"]}
    if enrichment.type == "options":
        return {"type": ["string", "null"], "enum": [*enrichment.options, None]}
    return {"type": ["string", "null"]}


def _single_field_response_format(enrichment: EnrichmentDef) -> dict[str, Any]:
    return {
        "type": "json_schema",
        "json_schema": {
            "name": _FIELD_SCHEMA_NAME,
            "schema": {
                "type": "object",
                "properties": {
                    "value": _value_schema(enrichment),
                    "citations": {"type": "array", "items": _citation_schema()},
                    "reasoning": {"type": "string"},
                },
                "required": ["value", "citations", "reasoning"],
                "additionalProperties": False,
            },
        },
    }


def _company_response_format() -> dict[str, Any]:
    round_schema = {
        "type": "object",
        "properties": {
            "name": {"type": "string"},
            "date": {"type": ["string", "null"]},
            "amount": {"type": ["number", "null"]},
            "currency": {"type": ["string", "null"]},
            "citations": {"type": "array", "items": _citation_schema()},
        },
        "required": ["name", "citations"],
        "additionalProperties": False,
    }
    return {
        "type": "json_schema",
        "json_schema": {
            "name": _COMPANY_SCHEMA_NAME,
            "schema": {
                "type": "object",
                "properties": {
                    "name": {"type": "string"},
                    "founded_year": {"type": ["integer", "null"]},
                    "description": {"type": ["string", "null"]},
                    "workforce_total": {"type": ["integer", "null"]},
                    "hq_city": {"type": ["string", "null"]},
                    "hq_country": {"type": ["string", "null"]},
                    "funding_total": {"type": ["number", "null"]},
                    "funding_total_currency": {"type": ["string", "null"]},
                    "funding_rounds": {"type": "array", "items": round_schema},
                    "provenance": {
                        "type": "object",
                        "additionalProperties": {
                            "type": "array",
                            "items": _citation_schema(),
                        },
                    },
                    "reasoning": {"type": "string"},
                },
                "required": ["name", "funding_rounds", "provenance", "reasoning"],
                "additionalProperties": False,
            },
        },
    }


def _enrichment_messages(
    url: str,
    title: str,
    markdown: str,
    enrichment: EnrichmentDef,
) -> list[dict[str, str]]:
    """The two-message digillm prompt; markdown truncation happens before this."""
    if enrichment.type == "company_profile":
        system_prompt = _COMPANY_SYSTEM_PROMPT
        requested = "the full company profile"
    else:
        system_prompt = _FIELD_SYSTEM_PROMPT
        requested = f"the {enrichment.type!r} field {enrichment.name!r}"
        if enrichment.type == "options":
            requested += "; `value` must be exactly one of: " + ", ".join(enrichment.options)
    if enrichment.description:
        requested += f" ({enrichment.description})"
    content = (
        f"CANDIDATE URL: {url}\n"
        f"CANDIDATE TITLE: {title or '(untitled)'}\n"
        f"REQUESTED FIELD: {requested}\n\n"
        f"CANDIDATE PAGE (markdown, truncated to {MARKDOWN_TRUNCATION_CHARS} chars):\n"
        f"{markdown[:MARKDOWN_TRUNCATION_CHARS]}"
    )
    return [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": content},
    ]


def _import_digillm_client() -> Any:
    """Resolve the default digillm client lazily (base installs stay importable)."""
    try:
        from digillm import client as digillm_client
    except ImportError as exc:
        raise RuntimeError(
            "webset enrichment requires the digillm client, which is not importable"
        ) from exc
    return digillm_client


def _message_text(response: Any) -> tuple[str, str]:
    """The model message text; unusable or empty responses carry a reason."""
    try:
        content = response.choices[0].message.content
    except (AttributeError, IndexError, TypeError) as exc:
        return "", f"enrichment LLM returned an unusable response: {exc}"
    text = str(content or "").strip()
    if not text:
        return "", "enrichment LLM returned an empty response"
    return text, ""


def _extract_payload(
    url: str,
    title: str,
    markdown: str,
    enrichment: EnrichmentDef,
    llm_client: Any,
) -> tuple[dict[str, Any] | None, str]:
    """One structured digillm completion; any failure is a reasoning string."""
    model = os.environ.get(ENRICH_MODEL_ENV, "").strip()
    if not model:
        return None, (f"{ENRICH_MODEL_ENV} is not set — no model for webset enrichment")
    if not markdown.strip():
        return None, "candidate page markdown is empty"
    if llm_client is not None:
        client = llm_client
    else:
        try:
            client = _import_digillm_client()
        except RuntimeError as exc:
            return None, str(exc)
    messages = _enrichment_messages(url, title, markdown, enrichment)
    response_format = (
        _company_response_format()
        if enrichment.type == "company_profile"
        else _single_field_response_format(enrichment)
    )
    try:
        response = client.completion(
            model,
            messages,
            usage_kind=_USAGE_KIND,
            response_format=response_format,
        )
    except Exception as exc:
        return None, f"digillm completion failed: {exc}"
    text, reason = _message_text(response)
    if not text:
        return None, reason
    try:
        payload = json.loads(text)
    except (TypeError, ValueError) as exc:
        return None, f"enrichment returned unparseable JSON: {exc}"
    if not isinstance(payload, dict):
        return None, "enrichment payload is not a JSON object"
    return payload, ""


def _parse_citations(raw: Any) -> tuple[list[Citation] | None, str]:
    """Validate a citation list against the shared ``Citation`` atom (R1)."""
    if raw is None:
        return [], ""
    if not isinstance(raw, list):
        return None, "citations payload is not a list"
    citations: list[Citation] = []
    for item in raw:
        if not isinstance(item, dict):
            return None, "citations payload carries a non-object entry"
        try:
            citations.append(Citation.model_validate(item))
        except ValidationError as exc:
            return None, f"citations payload carries an invalid citation: {exc}"
    return citations, ""


def _validate_number(raw: Any) -> tuple[float | None, str]:
    if isinstance(raw, bool):
        return None, f"number value {raw!r} is a boolean, not a number"
    if isinstance(raw, (int, float)):
        value = float(raw)
    elif isinstance(raw, str):
        try:
            value = float(raw.strip())
        except ValueError:
            return None, f"number value {raw!r} does not parse as a float"
    else:
        return None, f"number value {raw!r} is not a number"
    if not math.isfinite(value):
        return None, f"number value {raw!r} is not finite"
    return value, ""


def _validate_date(raw: Any) -> tuple[str | None, str]:
    if not isinstance(raw, str):
        return None, f"date value {raw!r} is not a string"
    try:
        return date.fromisoformat(raw.strip()).isoformat(), ""
    except ValueError:
        return None, f"date value {raw!r} is not an ISO-8601 date (YYYY-MM-DD)"


def _validate_url(raw: Any) -> tuple[str | None, str]:
    if not isinstance(raw, str):
        return None, f"url value {raw!r} is not a string"
    text = raw.strip()
    try:
        parts = urlsplit(text)
    except ValueError:
        return None, f"url value {raw!r} is not parseable"
    if parts.scheme.lower() not in ("http", "https") or not parts.hostname:
        return None, f"url value {raw!r} is not an http(s) url"
    return text, ""


def _validate_email(raw: Any) -> tuple[str | None, str]:
    if not isinstance(raw, str) or _EMAIL_RE.fullmatch(raw.strip()) is None:
        return None, f"email value {raw!r} is not a valid address"
    return raw.strip(), ""


def _validate_phone(raw: Any) -> tuple[str | None, str]:
    if not isinstance(raw, str):
        return None, f"phone value {raw!r} is not a string"
    text = raw.strip()
    if _PHONE_RE.fullmatch(text) is None:
        return None, f"phone value {raw!r} is not a dialable number"
    digits = _PHONE_DIGITS_RE.sub("", text)
    if not 7 <= len(digits) <= 15:
        return None, f"phone value {raw!r} carries {len(digits)} digit(s); expected 7-15"
    return text, ""


def _validate_options(enrichment: EnrichmentDef, raw: Any) -> tuple[str | None, str]:
    if not enrichment.options:
        return None, "options enrichment carries no declared options"
    if isinstance(raw, str) and raw in enrichment.options:
        return raw, ""
    return None, (f"options value {raw!r} is not one of the declared options: {enrichment.options}")


def _validate_scalar(enrichment: EnrichmentDef, raw: Any) -> tuple[Any, str]:
    """Strict per-type validation; an invalid value is unresolved, never coerced."""
    if raw is None:
        return None, "the page does not state the requested field (value is null)"
    if enrichment.type == "text":
        if not isinstance(raw, str) or not raw.strip():
            return None, f"text value {raw!r} is not a non-empty string"
        return raw, ""
    if enrichment.type == "number":
        return _validate_number(raw)
    if enrichment.type == "date":
        return _validate_date(raw)
    if enrichment.type == "url":
        return _validate_url(raw)
    if enrichment.type == "email":
        return _validate_email(raw)
    if enrichment.type == "phone":
        return _validate_phone(raw)
    if enrichment.type == "options":
        return _validate_options(enrichment, raw)
    return None, f"unsupported enrichment type {enrichment.type!r}"


def _unresolved(reason: str) -> EnrichedField:
    """An unresolved field carrying the reasoning (never a silent fill)."""
    return EnrichedField(value=None, citations=[], status="unresolved", error=reason)


def _build_company_entity(
    payload: dict[str, Any],
    *,
    rates: Mapping[str, float] | None,
) -> tuple[CompanyEntity | None, str]:
    """Validate one company payload into a provenance-complete ``CompanyEntity``.

    Every scalar ends with a ``provenance[field]`` entry; a value without
    citations is kept but flagged — the entity's ``reasoning`` records it
    (spec § Company/people enrichment item 3). A scalar with a wrong JSON type,
    or a round whose date/currency cannot be normalized, is dropped with
    reasoning rather than coerced or guessed.
    """
    name = payload.get("name")
    if not isinstance(name, str) or not name.strip():
        return None, "company payload is missing a non-empty name"

    notes: list[str] = []
    provenance: dict[str, list[Citation]] = {field: [] for field in PROVENANCE_SCALARS}
    raw_provenance = payload.get("provenance")
    if raw_provenance is None:
        notes.append("company payload carries no provenance block")
    elif not isinstance(raw_provenance, dict):
        notes.append("company payload provenance is not an object")
    else:
        for field, raw_citations in raw_provenance.items():
            if field not in PROVENANCE_SCALARS:
                continue
            citations, reason = _parse_citations(raw_citations)
            if citations is None:
                notes.append(f"{field}: {reason}")
                continue
            provenance[field] = _dedup_citations(citations)

    scalars: dict[str, Any] = {"name": name.strip()}
    for field in ("description", "hq_city", "hq_country"):
        value = payload.get(field)
        if value is None:
            continue
        if not isinstance(value, str):
            notes.append(f"{field} value {value!r} is not a string — field unresolved")
            continue
        scalars[field] = value
    for field in ("founded_year", "workforce_total"):
        value = payload.get(field)
        if value is None:
            continue
        if isinstance(value, bool) or not isinstance(value, int):
            notes.append(f"{field} value {value!r} is not an integer — field unresolved")
            continue
        scalars[field] = value

    raw_total = payload.get("funding_total")
    if raw_total is not None:
        if isinstance(raw_total, bool) or not isinstance(raw_total, (int, float)):
            notes.append(f"funding_total value {raw_total!r} is not a number — field unresolved")
        elif not math.isfinite(float(raw_total)):
            notes.append(f"funding_total value {raw_total!r} is not finite — field unresolved")
        else:
            total_usd, reason = _normalize_amount(
                float(raw_total), payload.get("funding_total_currency"), rates
            )
            if total_usd is None:
                notes.append(f"funding_total: {reason}")
            else:
                scalars["funding_total"] = total_usd

    rounds: list[FundingRound] = []
    raw_rounds = payload.get("funding_rounds")
    if raw_rounds is not None:
        if not isinstance(raw_rounds, list):
            notes.append("funding_rounds is not a list")
        else:
            for entry in raw_rounds:
                if not isinstance(entry, dict):
                    notes.append("funding_rounds carries a non-object entry")
                    continue
                try:
                    raw_round = RawFundingRound.model_validate(entry)
                except ValidationError as exc:
                    notes.append(f"funding round payload is invalid: {exc}")
                    continue
                normalized, reason = _normalize_round(raw_round, rates)
                if normalized is None:
                    notes.append(reason)
                    continue
                if reason:
                    notes.append(reason)
                    continue
                rounds.append(normalized)

    for field in PROVENANCE_SCALARS:
        if not _is_empty_value(scalars.get(field)) and not provenance[field]:
            notes.append(f"{field} carries no citations — unresolved for the entity")

    raw_reasoning = payload.get("reasoning")
    if isinstance(raw_reasoning, str) and raw_reasoning.strip():
        notes.append(raw_reasoning.strip())

    return (
        CompanyEntity(
            **scalars,
            funding_rounds=rounds,
            provenance=provenance,
            reasoning="; ".join(notes),
        ),
        "",
    )


def enrich_item(
    url: str,
    title: str,
    markdown: str,
    enrichment: EnrichmentDef,
    *,
    llm_client: Any = None,
    fx_rates: Mapping[str, float] | None = None,
) -> EnrichedField:
    """Resolve one enrichment field for one item; never returns a silent fill.

    ``markdown`` is the caller's already-fetched ``fetch_markdown`` output (R2 —
    never indexed); it is truncated to ``MARKDOWN_TRUNCATION_CHARS`` before the
    structured digillm call. ``llm_client`` overrides the default client (the
    pinned mock seam, same pattern as ``websets/verify.py``); ``fx_rates``
    supplies the ECB snapshot rates for non-USD company amounts (see
    :func:`load_fx_snapshot`). Returns ``resolved`` only with a valid typed value
    **and** at least one shared ``Citation``; every validation failure,
    unavailability, or empty extraction is ``unresolved`` with reasoning in
    ``error``. A ``company_profile`` extraction is validated into a
    ``CompanyEntity`` and bundled through :func:`company_profile_field`.
    """
    payload, reason = _extract_payload(url, title, markdown, enrichment, llm_client)
    if payload is None:
        return _unresolved(reason)
    if enrichment.type == "company_profile":
        entity, reason = _build_company_entity(payload, rates=_resolve_rates(fx_rates))
        if entity is None:
            return _unresolved(reason)
        return company_profile_field(entity)

    citations, reason = _parse_citations(payload.get("citations"))
    if citations is None:
        return _unresolved(reason)
    if not citations:
        return _unresolved("enrichment returned no citations; an uncited value is never admitted")
    value, reason = _validate_scalar(enrichment, payload.get("value"))
    if value is None:
        return EnrichedField(value=None, citations=citations, status="unresolved", error=reason)
    return EnrichedField(value=value, citations=citations)
