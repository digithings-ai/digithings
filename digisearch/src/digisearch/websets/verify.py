"""Phase D verification engine (#4066, Task 3) — rules + llm verdicts.

The admission gate of a webset: each candidate page (the ``fetch_markdown``
output, R2 — never indexed) is evaluated against every ``VerificationCriterion``
and returns one ``CriterionResult`` per rule (spec
``docs/superpowers/specs/2026-09-14-oss-websearch-phaseD-verify-enrich.md``,
§ Verification gate). An item is admitted only when every rule passes; on any
verification failure the caller settles the item ``rejected`` — never silently
admitted, never left ``pending`` (fail-closed, flag I9).

Modes:

- ``llm`` (production default): one digillm structured (json_schema) completion
  per candidate. The candidate markdown is truncated to
  ``MARKDOWN_TRUNCATION_CHARS`` (6000) before the call — a deliberate
  divergence from Phase B's synthesis budgets, because verification needs a
  fuller page. Every verdict carries ``references: list[Citation]`` (the shared
  web-grounding atom, R1 — never forked); a payload that does not yield exactly
  one usable verdict per criterion raises :class:`VerificationUnavailableError`.
- ``rules`` (deterministic, offline): the rule text is a compact DSL,
  ``<kind>: <expression>``, implementing exactly three kinds —
  ``domain: acme.example, other.example`` (host allowlist; a host passes when it
  equals a listed domain or is a subdomain of it), ``keyword: photonics, series
  a`` (comma-separated terms; all must appear case-insensitively in
  ``title + markdown``), and ``recency: 30`` / ``recency: 30d`` (the newest
  ISO-8601 ``YYYY-MM-DD`` date on the page must be within N days of today; a
  page with no parseable date fails). Any other kind, or a malformed
  expression, raises ``ValueError`` — an unknown kind never silently passes.
  Rules mode needs no model and stays green on key-less installs.

The settlement seam consumed by the runner: :func:`settle_pending_item` maps
verdicts onto ``WebsetItem.verification`` (``verified`` iff all rules pass, else
``rejected``) and :func:`settlement_results` writes one synthetic fail-closed
result per criterion (``passed=False``,
``reasoning="verification unavailable: <reason>"``, empty references) for
verification that errored or was never attempted at candidate-pass end.
"""

# score:allow untyped any
# The digillm client and its duck-typed ChatCompletion response cross this module's
# seam; Any is the honest annotation at that provider boundary.
from __future__ import annotations

import json
import os
import re
from collections.abc import Sequence
from datetime import date, datetime, timezone
from typing import Any, Literal
from urllib.parse import urlsplit

from pydantic import ValidationError

from digisearch.web_search.citation import Citation
from digisearch.websets.models import CriterionResult, VerificationCriterion, WebsetItem

__all__ = [
    "MARKDOWN_TRUNCATION_CHARS",
    "MAX_CRITERIA",
    "RULE_KINDS",
    "VERIFY_MODEL_ENV",
    "VerificationUnavailableError",
    "settle_pending_item",
    "settlement_results",
    "verify_item",
]

VerificationMode = Literal["llm", "rules"]

#: Candidate page markdown budget handed to a verification LLM call
#: (spec § Verification gate: full-page verification, not a synthesis snippet).
MARKDOWN_TRUNCATION_CHARS = 6000

#: 1-5 rules per search (spec § Verification gate + ``WebsetSearch.criteria``).
MAX_CRITERIA = 5

#: The only rule kinds rules mode implements (anything else raises ``ValueError``).
RULE_KINDS = ("domain", "keyword", "recency")

#: digillm model id env var for llm-mode verification (unset ⇒ unavailable).
VERIFY_MODEL_ENV = "DIGISEARCH_VERIFY_MODEL"

#: digillm ``usage_kind`` label so verification spend is attributable per call.
_USAGE_KIND = "webset_verify"

_VERIFICATION_SCHEMA_NAME = "webset_verification"

_DATE_RE = re.compile(r"\b(\d{4})-(\d{2})-(\d{2})\b")
_RECENCY_RE = re.compile(r"(\d+)\s*d?", re.IGNORECASE)

_VERIFICATION_SYSTEM_PROMPT = (
    "You verify one candidate web page against a numbered list of admission criteria.\n"
    "Rules:\n"
    "1. Judge the page ONLY from the candidate text supplied; never invent facts.\n"
    "2. Return one verdict per numbered criterion and copy its index verbatim into "
    "`criterion_index`.\n"
    "3. `passed` is true only when the page clearly supports the criterion.\n"
    "4. `reasoning` is a short justification grounded in the page text.\n"
    "5. `references` lists the supporting quotes as `{url, title, excerpt}` objects; "
    "use the candidate url and quote the page verbatim."
)


class VerificationUnavailableError(RuntimeError):
    """No verdicts could be produced for a candidate (fail-closed; flag I9).

    Raised by :func:`verify_item` when llm-mode verification cannot run or its
    payload is unusable. The settlement path catches it and records the terminal
    ``rejected`` state via :func:`settlement_results` — an item is never left
    ``pending`` and never admitted on a partial pass.
    """


def _validate_criteria(criteria: Sequence[VerificationCriterion]) -> None:
    """Reject anything outside 1-``MAX_CRITERIA`` ``VerificationCriterion`` rules."""
    if isinstance(criteria, (str, bytes)) or not isinstance(criteria, Sequence):
        raise ValueError("criteria must be a sequence of VerificationCriterion")
    if not 1 <= len(criteria) <= MAX_CRITERIA:
        raise ValueError(
            f"criteria must carry between 1 and {MAX_CRITERIA} rules, got {len(criteria)}"
        )
    for criterion in criteria:
        if not isinstance(criterion, VerificationCriterion):
            raise ValueError(
                "criteria entries must be VerificationCriterion models, got "
                f"{type(criterion).__name__}"
            )


def _parse_rule(rule_text: str) -> tuple[str, str]:
    """Split ``<kind>: <expression>``; unknown kinds never pass silently."""
    kind, separator, expression = rule_text.partition(":")
    kind = kind.strip().lower()
    if not separator or kind not in RULE_KINDS:
        raise ValueError(
            f"unknown rules-mode rule kind {kind or rule_text.strip()!r}; expected one of "
            f"{', '.join(RULE_KINDS)} followed by ':'"
        )
    expression = expression.strip()
    if not expression:
        raise ValueError(f"rules-mode {kind!r} rule carries no expression")
    return kind, expression


def _rule_domain(url: str, expression: str) -> tuple[bool, str]:
    """Host allowlist: exact domain or subdomain match (case-insensitive)."""
    allowed = [
        domain.strip().lower().lstrip(".") for domain in expression.split(",") if domain.strip()
    ]
    if not allowed:
        raise ValueError("domain rule carries an empty allowlist")
    host = (urlsplit(url).hostname or "").lower()
    for domain in allowed:
        if host == domain or host.endswith(f".{domain}"):
            return True, f"host {host!r} matches allowed domain {domain!r}"
    return False, f"host {host!r} is not in the domain allowlist ({', '.join(allowed)})"


def _rule_keyword(title: str, markdown: str, expression: str) -> tuple[bool, str]:
    """Every comma-separated term must appear case-insensitively in the page text."""
    terms = [term.strip().lower() for term in expression.split(",") if term.strip()]
    if not terms:
        raise ValueError("keyword rule carries no keywords")
    haystack = f"{title}\n{markdown}".lower()
    missing = [term for term in terms if term not in haystack]
    if missing:
        return False, f"missing keyword(s): {', '.join(missing)}"
    return True, f"all keyword(s) present: {', '.join(terms)}"


def _newest_page_date(markdown: str) -> date | None:
    """Newest parseable ISO-8601 date on the page (``None`` when there is none)."""
    newest: date | None = None
    for year, month, day in _DATE_RE.findall(markdown):
        try:
            candidate = date(int(year), int(month), int(day))
        except ValueError:
            continue
        if newest is None or candidate > newest:
            newest = candidate
    return newest


def _rule_recency(markdown: str, expression: str, *, today: date) -> tuple[bool, str]:
    """Published-date window: newest page date within N days of *today*."""
    match = _RECENCY_RE.fullmatch(expression)
    if match is None or int(match.group(1)) <= 0:
        raise ValueError(f"recency rule expression {expression!r} is not a positive day count")
    days = int(match.group(1))
    newest = _newest_page_date(markdown)
    if newest is None:
        return False, "no ISO-8601 date (YYYY-MM-DD) found on the page"
    age = (today - newest).days
    if age < 0:
        return False, f"newest page date {newest.isoformat()} is in the future"
    if age <= days:
        return True, f"newest page date {newest.isoformat()} is within {days} day(s)"
    return False, f"newest page date {newest.isoformat()} is older than {days} day(s)"


def _verify_rules(
    url: str,
    title: str,
    markdown: str,
    criteria: Sequence[VerificationCriterion],
) -> list[CriterionResult]:
    """Evaluate every criterion deterministically (full markdown, no model budget)."""
    today = datetime.now(timezone.utc).date()
    results: list[CriterionResult] = []
    for criterion in criteria:
        kind, expression = _parse_rule(criterion.rule)
        if kind == "domain":
            passed, reasoning = _rule_domain(url, expression)
        elif kind == "keyword":
            passed, reasoning = _rule_keyword(title, markdown, expression)
        else:  # recency
            passed, reasoning = _rule_recency(markdown, expression, today=today)
        results.append(CriterionResult(criterion=criterion, passed=passed, reasoning=reasoning))
    return results


def _response_format() -> dict[str, Any]:
    """digillm ``response_format`` descriptor: one indexed verdict per criterion."""
    citation = {
        "type": "object",
        "properties": {
            "url": {"type": "string"},
            "title": {"type": "string"},
            "excerpt": {"type": "string"},
        },
        "required": ["url"],
        "additionalProperties": False,
    }
    verdict = {
        "type": "object",
        "properties": {
            "criterion_index": {"type": "integer"},
            "passed": {"type": "boolean"},
            "reasoning": {"type": "string"},
            "references": {"type": "array", "items": citation},
        },
        "required": ["criterion_index", "passed", "reasoning", "references"],
        "additionalProperties": False,
    }
    return {
        "type": "json_schema",
        "json_schema": {
            "name": _VERIFICATION_SCHEMA_NAME,
            "schema": {
                "type": "object",
                "properties": {"verdicts": {"type": "array", "items": verdict}},
                "required": ["verdicts"],
                "additionalProperties": False,
            },
        },
    }


def _criteria_block(criteria: Sequence[VerificationCriterion]) -> str:
    """Numbered criteria rendering (index is the model's ``criterion_index``)."""
    lines = []
    for index, criterion in enumerate(criteria):
        note = f" — {criterion.description}" if criterion.description else ""
        lines.append(f"{index}. [{criterion.name}] {criterion.rule}{note}")
    return "\n".join(lines)


def _verification_messages(
    url: str,
    title: str,
    markdown: str,
    criteria: Sequence[VerificationCriterion],
) -> list[dict[str, str]]:
    """The two-message digillm prompt; markdown is truncated before this point."""
    content = (
        f"CANDIDATE URL: {url}\n"
        f"CANDIDATE TITLE: {title or '(untitled)'}\n\n"
        f"CRITERIA:\n{_criteria_block(criteria)}\n\n"
        f"CANDIDATE PAGE (markdown, truncated to {MARKDOWN_TRUNCATION_CHARS} chars):\n"
        f"{markdown[:MARKDOWN_TRUNCATION_CHARS]}"
    )
    return [
        {"role": "system", "content": _VERIFICATION_SYSTEM_PROMPT},
        {"role": "user", "content": content},
    ]


def _import_digillm_client() -> Any:
    """Resolve the default digillm client lazily (base installs stay importable)."""
    try:
        from digillm import client as digillm_client
    except ImportError as exc:
        raise VerificationUnavailableError(
            "webset verification requires the digillm client, which is not importable"
        ) from exc
    return digillm_client


def _message_text(response: Any) -> str:
    """The model message text; unusable or empty responses are unavailable."""
    try:
        content = response.choices[0].message.content
    except (AttributeError, IndexError, TypeError) as exc:
        raise VerificationUnavailableError(
            f"verification LLM returned an unusable response: {exc}"
        ) from exc
    text = str(content or "").strip()
    if not text:
        raise VerificationUnavailableError("verification LLM returned an empty response")
    return text


def _parse_references(raw: Any, index: int) -> list[Citation]:
    """Every reference must validate as the shared ``Citation`` atom (R1)."""
    if raw is None:
        return []
    if not isinstance(raw, list):
        raise VerificationUnavailableError(
            f"verification verdict {index} references are not a list"
        )
    references: list[Citation] = []
    for item in raw:
        if not isinstance(item, dict):
            raise VerificationUnavailableError(
                f"verification verdict {index} carries a non-object reference"
            )
        try:
            references.append(Citation.model_validate(item))
        except ValidationError as exc:
            raise VerificationUnavailableError(
                f"verification verdict {index} carries an invalid reference: {exc}"
            ) from exc
    return references


def _parse_verdicts(raw: str, criteria: Sequence[VerificationCriterion]) -> list[CriterionResult]:
    """Strict verdicts payload → one ``CriterionResult`` per criterion, in order.

    Fail-closed: unparseable JSON, a non-verdicts shape, an out-of-range or
    duplicate ``criterion_index``, a non-boolean ``passed``, a missing verdict,
    or an invalid reference makes the whole payload unusable — the caller
    settles the item rejected rather than admitting it on a partial pass.
    """
    try:
        payload = json.loads(raw)
    except (TypeError, ValueError) as exc:
        raise VerificationUnavailableError(
            f"verification returned unparseable JSON: {exc}"
        ) from exc
    if not isinstance(payload, dict) or not isinstance(payload.get("verdicts"), list):
        raise VerificationUnavailableError("verification payload is not a verdicts object")

    by_index: dict[int, dict[str, Any]] = {}
    for entry in payload["verdicts"]:
        if not isinstance(entry, dict):
            raise VerificationUnavailableError("verification verdict is not an object")
        index = entry.get("criterion_index")
        if not isinstance(index, int) or isinstance(index, bool) or not 0 <= index < len(criteria):
            raise VerificationUnavailableError(
                f"verification verdict carries invalid criterion_index {index!r}"
            )
        if index in by_index:
            raise VerificationUnavailableError(
                f"verification returned duplicate verdicts for criterion {index}"
            )
        if not isinstance(entry.get("passed"), bool):
            raise VerificationUnavailableError(
                f"verification verdict {index} is missing a boolean passed"
            )
        by_index[index] = entry

    missing = [index for index in range(len(criteria)) if index not in by_index]
    if missing:
        raise VerificationUnavailableError(
            f"verification returned no verdict for criterion index(es) {missing}"
        )

    results: list[CriterionResult] = []
    for index, criterion in enumerate(criteria):
        entry = by_index[index]
        results.append(
            CriterionResult(
                criterion=criterion,
                passed=entry["passed"],
                reasoning=str(entry.get("reasoning") or ""),
                references=_parse_references(entry.get("references"), index),
            )
        )
    return results


def _verify_llm(
    url: str,
    title: str,
    markdown: str,
    criteria: Sequence[VerificationCriterion],
    llm_client: Any,
) -> list[CriterionResult]:
    """One structured digillm completion; any failure is verification unavailable."""
    if not markdown.strip():
        raise VerificationUnavailableError("candidate page markdown is empty")
    model = os.environ.get(VERIFY_MODEL_ENV, "").strip()
    if not model:
        raise VerificationUnavailableError(
            f"{VERIFY_MODEL_ENV} is not set — no model for webset verification"
        )
    client = llm_client if llm_client is not None else _import_digillm_client()
    messages = _verification_messages(url, title, markdown, criteria)
    try:
        response = client.completion(
            model,
            messages,
            usage_kind=_USAGE_KIND,
            response_format=_response_format(),
        )
    except VerificationUnavailableError:
        raise
    except Exception as exc:
        raise VerificationUnavailableError(f"digillm completion failed: {exc}") from exc
    return _parse_verdicts(_message_text(response), criteria)


def verify_item(
    url: str,
    title: str,
    markdown: str,
    criteria: Sequence[VerificationCriterion],
    *,
    mode: VerificationMode,
    llm_client: Any = None,
) -> list[CriterionResult]:
    """Evaluate every criterion against one candidate page and return the verdicts.

    ``markdown`` is the candidate's ``fetch_markdown`` output (R2); it is
    truncated to ``MARKDOWN_TRUNCATION_CHARS`` before any LLM call and never
    indexed. Returns one ``CriterionResult`` per criterion in input order; the
    item is admitted only when every ``passed`` is true (the caller settles via
    :func:`settle_pending_item`). ``llm_client`` overrides the default digillm
    client (the pinned mock seam). Raises :class:`VerificationUnavailableError`
    when llm-mode verification cannot produce verdicts (fail-closed, flag I9),
    and ``ValueError`` for an invalid criteria list, unknown ``mode``, or an
    unknown/malformed rules-mode rule kind.
    """
    _validate_criteria(criteria)
    if mode == "rules":
        return _verify_rules(url, title, markdown, criteria)
    if mode == "llm":
        return _verify_llm(url, title, markdown, criteria, llm_client)
    raise ValueError(f"unknown verification mode {mode!r}; expected 'llm' or 'rules'")


def settlement_results(
    criteria: Sequence[VerificationCriterion], reason: str
) -> list[CriterionResult]:
    """One synthetic fail-closed result per criterion (spec § Verification gate, I9).

    ``reason`` is the bare unavailability reason; the pinned
    ``"verification unavailable: "`` prefix is added here so the stored audit
    record is uniform across errored candidates and items still pending at
    candidate-pass end.
    """
    return [
        CriterionResult(
            criterion=criterion,
            passed=False,
            reasoning=f"verification unavailable: {reason}",
            references=[],
        )
        for criterion in criteria
    ]


def settle_pending_item(
    item: WebsetItem,
    markdown: str,
    criteria: Sequence[VerificationCriterion],
    *,
    mode: VerificationMode,
    llm_client: Any = None,
) -> WebsetItem:
    """Verify *item* and settle its terminal state in place (returns *item*).

    The settlement seam consumed by the runner: ``verification="verified"`` iff
    every rule passed, else ``"rejected"`` with the criterion results retained.
    Verification-unavailable candidates settle ``rejected`` with the synthetic
    results from :func:`settlement_results`, so a candidate pass can always
    reach ``idle`` (flag I9); an operator-authored malformed rules-mode rule
    (``ValueError``) is equally unverifiable and settles the same way. A
    criteria list outside 1-``MAX_CRITERIA`` propagates ``ValueError`` — it is
    a data-integrity bug unreachable from a validated ``WebsetSearch``, not a
    per-candidate condition. This function never writes to a store or corpus.
    """
    _validate_criteria(criteria)
    try:
        results = verify_item(
            item.url, item.title, markdown, criteria, mode=mode, llm_client=llm_client
        )
    except (VerificationUnavailableError, ValueError) as exc:
        results = settlement_results(criteria, str(exc))
    item.verification = "verified" if all(result.passed for result in results) else "rejected"
    item.criteria_results = results
    return item
