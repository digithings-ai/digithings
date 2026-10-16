"""Phase D webset verification engine (#4066, Task 3) — offline unit suite.

Pins the fail-closed verification contract from the spec
(``docs/superpowers/specs/2026-09-14-oss-websearch-phaseD-verify-enrich.md``
§ Verification gate):

- rules mode implements exactly ``domain`` / ``keyword`` / ``recency`` kinds
  deterministically; an unknown kind raises ``ValueError`` (never silently
  passes);
- llm mode is mocked at the digillm boundary (``verify_item(llm_client=...)``);
  every verdict carries the shared ``Citation`` atom with ``title`` defaulting
  to ``""`` and the supporting quote in ``excerpt``;
- the candidate page markdown is truncated to 6000 chars before the LLM call;
- 0 or >5 criteria raise ``ValueError``;
- verification that cannot produce verdicts settles ``rejected`` (never
  ``pending``, never admitted) with one synthetic ``CriterionResult`` per
  criterion — flag I9.

No network: the digillm seam is a duck-typed stub. Rules-mode tests run with
no model configured (key-less installs stay green).
"""

from __future__ import annotations

import json
import types
from datetime import datetime, timedelta, timezone
from typing import Any

import pytest
from digisearch.web_search.citation import Citation
from digisearch.websets.models import VerificationCriterion, WebsetItem
from digisearch.websets.verify import (
    MARKDOWN_TRUNCATION_CHARS,
    RULE_KINDS,
    VERIFY_MODEL_ENV,
    VerificationUnavailableError,
    settle_pending_item,
    settlement_results,
    verify_item,
)

pytestmark = pytest.mark.unit

_WS_ID = "ws_" + "1" * 32
_URL = "https://www.acme.example/about"
_MARKDOWN = "# Acme\nAcme Corp builds photonics robots for farms. Founded 2019."


def _criterion(name: str, rule: str, description: str = "") -> VerificationCriterion:
    return VerificationCriterion(name=name, rule=rule, description=description)


def _item(url: str = _URL, title: str = "Acme — About") -> WebsetItem:
    return WebsetItem(webset_id=_WS_ID, url=url, title=title)


class _StubLLM:
    """Duck-typed digillm boundary: only ``completion`` is read."""

    def __init__(
        self,
        payload: dict[str, Any] | None = None,
        *,
        raw: str | None = None,
        error: Exception | None = None,
    ) -> None:
        self.payload = payload
        self.raw = raw if raw is not None else json.dumps(payload)
        self.error = error
        self.calls: list[tuple[str, list[dict[str, str]], dict[str, Any]]] = []

    def completion(self, model: str, messages: list[dict[str, str]], **kwargs: Any) -> Any:
        self.calls.append((model, messages, kwargs))
        if self.error is not None:
            raise self.error
        message = types.SimpleNamespace(content=self.raw)
        return types.SimpleNamespace(choices=[types.SimpleNamespace(message=message)])


def _verdicts_payload(
    *passed: bool, references: list[dict[str, str]] | None = None
) -> dict[str, Any]:
    return {
        "verdicts": [
            {
                "criterion_index": index,
                "passed": verdict,
                "reasoning": f"reasoning {index}",
                "references": references or [],
            }
            for index, verdict in enumerate(passed)
        ]
    }


@pytest.fixture
def verify_model_env(monkeypatch: pytest.MonkeyPatch) -> str:
    """The configured digillm model id for llm-mode tests."""
    monkeypatch.setenv(VERIFY_MODEL_ENV, "test/verify-model")
    return "test/verify-model"


# ── rules mode ────────────────────────────────────────────────────────────────


def test_rule_kinds_are_exactly_domain_keyword_recency() -> None:
    assert RULE_KINDS == ("domain", "keyword", "recency")


def test_rules_mode_all_pass_admits() -> None:
    criteria = [
        _criterion("domain", "domain: acme.example"),
        _criterion("photonics", "keyword: photonics"),
    ]
    results = verify_item(_URL, "Acme", _MARKDOWN, criteria, mode="rules")

    assert [result.criterion for result in results] == criteria
    assert [result.passed for result in results] == [True, True]
    assert all(result.reasoning for result in results)
    assert all(result.references == [] for result in results)


def test_rules_mode_keyword_miss_rejects_with_reasoning_referencing_rule() -> None:
    criteria = [_criterion("photonics", "keyword: photonics")]
    results = verify_item(_URL, "Acme", "Acme builds farm robots.", criteria, mode="rules")

    assert results[0].passed is False
    assert "photonics" in results[0].reasoning
    assert "keyword" in results[0].reasoning.lower()


def test_rules_mode_domain_allowlist_rejects_foreign_host() -> None:
    criteria = [_criterion("domain", "domain: acme.example, other.example")]
    results = verify_item("https://evil.example/about", "Evil", _MARKDOWN, criteria, mode="rules")

    assert results[0].passed is False
    assert "evil.example" in results[0].reasoning


def test_rules_mode_recency_window() -> None:
    today = datetime.now(timezone.utc).date()
    fresh = (today - timedelta(days=3)).isoformat()
    stale = (today - timedelta(days=400)).isoformat()
    criterion = [_criterion("recent", "recency: 30d")]

    fresh_results = verify_item(
        _URL, "Acme", f"Published {fresh}\nAcme news.", criterion, mode="rules"
    )
    stale_results = verify_item(
        _URL, "Acme", f"Published {stale}\nAcme news.", criterion, mode="rules"
    )
    missing_results = verify_item(_URL, "Acme", "No date on this page.", criterion, mode="rules")

    assert fresh_results[0].passed is True
    assert stale_results[0].passed is False
    assert stale_results[0].reasoning
    assert missing_results[0].passed is False
    assert missing_results[0].reasoning


def test_rules_mode_accepts_plain_day_count_too() -> None:
    today = datetime.now(timezone.utc).date().isoformat()
    criteria = [_criterion("recent", "recency: 30")]
    results = verify_item(_URL, "Acme", f"Published {today}", criteria, mode="rules")

    assert results[0].passed is True


def test_rules_mode_unknown_kind_raises_value_error() -> None:
    criteria = [_criterion("vibes", "vibes: good energy")]
    with pytest.raises(ValueError, match="vibes"):
        verify_item(_URL, "Acme", _MARKDOWN, criteria, mode="rules")


def test_rules_mode_rule_without_kind_raises_value_error() -> None:
    criteria = [_criterion("natural", "company is a photonics startup")]
    with pytest.raises(ValueError, match="domain, keyword, recency"):
        verify_item(_URL, "Acme", _MARKDOWN, criteria, mode="rules")


def test_rules_mode_malformed_expression_raises_value_error() -> None:
    with pytest.raises(ValueError, match="recency"):
        verify_item(_URL, "Acme", _MARKDOWN, [_criterion("r", "recency: soon")], mode="rules")
    with pytest.raises(ValueError, match="expression"):
        verify_item(_URL, "Acme", _MARKDOWN, [_criterion("d", "domain:")], mode="rules")


def test_rules_mode_empty_markdown_still_yields_deterministic_verdicts() -> None:
    criteria = [_criterion("photonics", "keyword: photonics")]
    results = verify_item(_URL, "Acme", "", criteria, mode="rules")

    assert results[0].passed is False
    assert results[0].reasoning


def test_rules_mode_needs_no_model_env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv(VERIFY_MODEL_ENV, raising=False)
    criteria = [_criterion("domain", "domain: acme.example")]
    results = verify_item(_URL, "Acme", _MARKDOWN, criteria, mode="rules")

    assert results[0].passed is True


# ── llm mode (stubbed at the digillm boundary) ────────────────────────────────


def test_markdown_truncation_budget_is_6000_chars() -> None:
    assert MARKDOWN_TRUNCATION_CHARS == 6000


def test_llm_mode_returns_per_rule_verdicts_with_shared_citations(
    verify_model_env: str,
) -> None:
    criteria = [
        _criterion("domain", "domain: acme.example"),
        _criterion("funding", "company raised a Series A after 2023"),
    ]
    payload = {
        "verdicts": [
            {
                "criterion_index": 0,
                "passed": True,
                "reasoning": "host matches the allowlist",
                "references": [
                    {
                        "url": _URL,
                        "excerpt": "Acme Corp builds photonics robots for farms.",
                    }
                ],
            },
            {
                "criterion_index": 1,
                "passed": False,
                "reasoning": "no Series A evidence on the page",
                "references": [{"url": _URL, "title": "Acme — About", "excerpt": "Founded 2019"}],
            },
        ]
    }
    stub = _StubLLM(payload)
    results = verify_item(_URL, "Acme — About", _MARKDOWN, criteria, mode="llm", llm_client=stub)

    assert [result.criterion for result in results] == criteria
    assert [result.passed for result in results] == [True, False]
    assert results[0].reasoning == "host matches the allowlist"

    citation = results[0].references[0]
    assert type(citation) is Citation
    assert citation.url == _URL
    assert citation.title == ""
    assert citation.excerpt == "Acme Corp builds photonics robots for farms."
    assert results[1].references[0].title == "Acme — About"

    assert len(stub.calls) == 1
    model, messages, kwargs = stub.calls[0]
    assert model == verify_model_env
    assert kwargs["usage_kind"] == "webset_verify"
    assert kwargs["response_format"]["json_schema"]["name"] == "webset_verification"
    prompt = messages[-1]["content"]
    assert _URL in prompt
    assert "domain: acme.example" in prompt
    assert "Series A after 2023" in prompt


def test_llm_mode_truncates_candidate_markdown_to_6000_chars(verify_model_env: str) -> None:
    criteria = [_criterion("needle", "keyword: needle")]
    tail = "TAIL-MARKER-NEVER-SENT"
    markdown = ("a" * MARKDOWN_TRUNCATION_CHARS) + tail
    stub = _StubLLM(_verdicts_payload(True))

    verify_item(_URL, "Acme", markdown, criteria, mode="llm", llm_client=stub)

    prompt = stub.calls[0][1][-1]["content"]
    assert ("a" * MARKDOWN_TRUNCATION_CHARS) in prompt
    assert tail not in prompt


def test_llm_mode_url_title_and_criteria_reach_the_prompt(verify_model_env: str) -> None:
    criteria = [_criterion("domain", "domain: acme.example", description="primary host")]
    stub = _StubLLM(_verdicts_payload(True))

    verify_item(_URL, "Acme — About", _MARKDOWN, criteria, mode="llm", llm_client=stub)

    prompt = stub.calls[0][1][-1]["content"]
    assert "Acme — About" in prompt
    assert "primary host" in prompt
    assert _MARKDOWN in prompt


def test_llm_mode_partial_verdicts_are_unavailable(verify_model_env: str) -> None:
    criteria = [
        _criterion("domain", "domain: acme.example"),
        _criterion("keyword", "keyword: photonics"),
    ]
    stub = _StubLLM({"verdicts": [_verdicts_payload(True)["verdicts"][0]]})

    with pytest.raises(VerificationUnavailableError, match="no verdict"):
        verify_item(_URL, "Acme", _MARKDOWN, criteria, mode="llm", llm_client=stub)


def test_llm_mode_unparseable_payload_is_unavailable(verify_model_env: str) -> None:
    criteria = [_criterion("domain", "domain: acme.example")]
    stub = _StubLLM(raw="not json at all")

    with pytest.raises(VerificationUnavailableError, match="JSON"):
        verify_item(_URL, "Acme", _MARKDOWN, criteria, mode="llm", llm_client=stub)


def test_llm_mode_duplicate_verdict_index_is_unavailable(verify_model_env: str) -> None:
    criteria = [_criterion("domain", "domain: acme.example")]
    duplicate = _verdicts_payload(True)["verdicts"][0]
    stub = _StubLLM({"verdicts": [duplicate, dict(duplicate)]})

    with pytest.raises(VerificationUnavailableError, match="duplicate"):
        verify_item(_URL, "Acme", _MARKDOWN, criteria, mode="llm", llm_client=stub)


def test_llm_mode_empty_markdown_is_unavailable_and_never_calls_llm(
    verify_model_env: str,
) -> None:
    criteria = [_criterion("keyword", "keyword: photonics")]
    stub = _StubLLM(_verdicts_payload(True))

    with pytest.raises(VerificationUnavailableError, match="empty"):
        verify_item(_URL, "Acme", "   \n", criteria, mode="llm", llm_client=stub)

    assert stub.calls == []


def test_llm_mode_without_model_env_is_unavailable(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv(VERIFY_MODEL_ENV, raising=False)
    criteria = [_criterion("domain", "domain: acme.example")]
    stub = _StubLLM(_verdicts_payload(True))

    with pytest.raises(VerificationUnavailableError, match=VERIFY_MODEL_ENV):
        verify_item(_URL, "Acme", _MARKDOWN, criteria, mode="llm", llm_client=stub)

    assert stub.calls == []


# ── criteria + mode validation ────────────────────────────────────────────────


def test_zero_criteria_raise_value_error() -> None:
    with pytest.raises(ValueError, match="1 and 5"):
        verify_item(_URL, "Acme", _MARKDOWN, [], mode="rules")


def test_six_criteria_raise_value_error() -> None:
    criteria = [_criterion(f"rule-{index}", f"keyword: kw{index}") for index in range(6)]
    with pytest.raises(ValueError, match="1 and 5"):
        verify_item(_URL, "Acme", _MARKDOWN, criteria, mode="rules")


def test_unknown_mode_raises_value_error() -> None:
    criteria = [_criterion("domain", "domain: acme.example")]
    with pytest.raises(ValueError, match="vibes"):
        verify_item(_URL, "Acme", _MARKDOWN, criteria, mode="vibes")  # type: ignore[arg-type]


# ── settlement path (flag I9) ─────────────────────────────────────────────────


def test_settlement_admits_when_all_rules_pass(verify_model_env: str) -> None:
    criteria = [
        _criterion("domain", "domain: acme.example"),
        _criterion("keyword", "keyword: photonics"),
    ]
    stub = _StubLLM(_verdicts_payload(True, True, references=[{"url": _URL, "excerpt": "quote"}]))
    item = _item()

    settled = settle_pending_item(item, _MARKDOWN, criteria, mode="llm", llm_client=stub)

    assert settled is item
    assert item.verification == "verified"
    assert len(item.criteria_results) == len(criteria)
    assert all(result.passed for result in item.criteria_results)
    assert item.criteria_results[0].references[0].excerpt == "quote"


def test_settlement_rejects_when_a_rule_fails_keeping_real_verdicts(
    verify_model_env: str,
) -> None:
    criteria = [
        _criterion("domain", "domain: acme.example"),
        _criterion("keyword", "keyword: photonics"),
    ]
    stub = _StubLLM(_verdicts_payload(True, False))
    item = _item()

    settled = settle_pending_item(item, _MARKDOWN, criteria, mode="llm", llm_client=stub)

    assert settled is item
    assert item.verification == "rejected"
    assert [result.passed for result in item.criteria_results] == [True, False]
    assert "verification unavailable" not in item.criteria_results[1].reasoning


def test_llm_error_settles_rejected_with_one_synthetic_result_per_criterion(
    verify_model_env: str,
) -> None:
    criteria = [
        _criterion("domain", "domain: acme.example"),
        _criterion("keyword", "keyword: photonics"),
    ]
    stub = _StubLLM(error=RuntimeError("provider exploded"))
    item = _item()

    settled = settle_pending_item(item, _MARKDOWN, criteria, mode="llm", llm_client=stub)

    assert settled is item
    assert item.verification == "rejected"
    assert len(item.criteria_results) == len(criteria)
    for result, criterion in zip(item.criteria_results, criteria, strict=True):
        assert result.criterion == criterion
        assert result.passed is False
        assert result.reasoning.startswith("verification unavailable: ")
        assert "provider exploded" in result.reasoning
        assert result.references == []


def test_empty_markdown_settles_rejected_without_an_llm_call(verify_model_env: str) -> None:
    criteria = [_criterion("keyword", "keyword: photonics")]
    stub = _StubLLM(error=AssertionError("must not be called"))
    item = _item()

    settled = settle_pending_item(item, "", criteria, mode="llm", llm_client=stub)

    assert settled.verification == "rejected"
    assert len(settled.criteria_results) == 1
    assert settled.criteria_results[0].reasoning.startswith("verification unavailable: ")
    assert settled.criteria_results[0].references == []
    assert stub.calls == []


def test_malformed_rules_rule_settles_rejected_not_pending() -> None:
    criteria = [_criterion("vibes", "vibes: good energy")]
    item = _item()

    settled = settle_pending_item(item, _MARKDOWN, criteria, mode="rules")

    assert settled.verification == "rejected"
    assert len(settled.criteria_results) == 1
    assert settled.criteria_results[0].passed is False
    assert settled.criteria_results[0].reasoning.startswith("verification unavailable: ")
    assert "vibes" in settled.criteria_results[0].reasoning


def test_settlement_results_cover_never_attempted_items() -> None:
    criteria = [
        _criterion("domain", "domain: acme.example"),
        _criterion("keyword", "keyword: photonics"),
    ]
    reason = "candidate pass ended with verification pending"

    results = settlement_results(criteria, reason)

    assert len(results) == len(criteria)
    for result, criterion in zip(results, criteria, strict=True):
        assert result.criterion == criterion
        assert result.passed is False
        assert result.reasoning == f"verification unavailable: {reason}"
        assert result.references == []
