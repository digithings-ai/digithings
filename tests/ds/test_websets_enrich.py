"""Phase D enrichment engine (#4066, Task 4) — offline unit suite.

Pins the per-field extraction contract from the spec
(``docs/superpowers/specs/2026-09-14-oss-websearch-phaseD-verify-enrich.md``
§ Enrichment engine + per-field citations):

- all 8 ``EnrichmentDef.type`` members validate, including ``company_profile``;
- type validation is strict (pydantic v2): a bad ``number``/``date``/``options``
  (or ``url``/``email``/``phone``) value is ``unresolved`` with reasoning, never
  coerced and never silently filled;
- every ``resolved`` field carries at least one shared ``Citation`` (R1 — the
  atom is imported from ``digisearch.web_search.citation``, never forked); an
  empty value or empty citations downgrades to ``unresolved``;
- extraction is one schema-pinned digillm structured completion, mocked at the
  ``llm_client`` boundary exactly like ``websets/verify.py`` — no network.

Funding-history merge, entity merge, and ``company_profile_field`` tests (the
fixture-driven half) live in ``tests/ds/test_websets_company.py``.
"""

from __future__ import annotations

import json
import types
from typing import Any

import pytest
from digisearch.web_search.citation import Citation
from digisearch.websets.enrich import (
    ENRICH_MODEL_ENV,
    MARKDOWN_TRUNCATION_CHARS,
    enrich_item,
)
from digisearch.websets.models import CompanyEntity, EnrichedField, EnrichmentDef

pytestmark = pytest.mark.unit

_URL = "https://nucicer.com/press/series-a"
_TITLE = "NuCicer raises $11.5M Series A"
_MARKDOWN = "# NuCicer\nNuCicer raised an $11.5M Series A in July 2025."


def _citation(url: str = _URL, excerpt: str = "raised an $11.5M Series A") -> dict[str, str]:
    return {"url": url, "title": _TITLE, "excerpt": excerpt}


def _def(name: str, field_type: str, options: list[str] | None = None) -> EnrichmentDef:
    return EnrichmentDef(
        name=name, type=field_type, description=f"{name} extraction", options=options or []
    )


def _payload(value: Any, citations: list[dict[str, str]] | None = None) -> dict[str, Any]:
    return {
        "value": value,
        "citations": [_citation()] if citations is None else citations,
        "reasoning": "quoted from the page",
    }


def _company_payload() -> dict[str, Any]:
    """The ``company_profile`` extraction payload (the CompanyEntity mirror shape)."""
    return {
        "name": "NuCicer",
        "founded_year": 2019,
        "description": "high-protein chickpea platform",
        "workforce_total": 27,
        "hq_city": "Davis",
        "hq_country": "United States",
        "funding_total": 16_000_000,
        "funding_rounds": [
            {
                "name": "Series a",
                "date": "2025-07-01",
                "amount": 11_500_000,
                "currency": "USD",
                "citations": [_citation()],
            }
        ],
        "provenance": {
            field: [_citation()]
            for field in (
                "name",
                "founded_year",
                "description",
                "workforce_total",
                "hq_city",
                "hq_country",
                "funding_total",
            )
        },
        "reasoning": "company profile extracted from the press page",
    }


class _StubLLM:
    """Duck-typed digillm boundary: only ``completion`` is read."""

    def __init__(
        self,
        payload: dict[str, Any] | None = None,
        *,
        raw: str | None = None,
        error: Exception | None = None,
    ) -> None:
        self.raw = raw if raw is not None else json.dumps(payload)
        self.error = error
        self.calls: list[tuple[str, list[dict[str, str]], dict[str, Any]]] = []

    def completion(self, model: str, messages: list[dict[str, str]], **kwargs: Any) -> Any:
        self.calls.append((model, messages, kwargs))
        if self.error is not None:
            raise self.error
        message = types.SimpleNamespace(content=self.raw)
        return types.SimpleNamespace(choices=[types.SimpleNamespace(message=message)])


@pytest.fixture
def enrich_model_env(monkeypatch: pytest.MonkeyPatch) -> str:
    monkeypatch.setenv(ENRICH_MODEL_ENV, "test/enrich-model")
    return "test/enrich-model"


_VALID_SCALAR_CASES = [
    pytest.param("text", None, "NuCicer", "NuCicer", id="text"),
    pytest.param("number", None, 11_500_000, 11_500_000.0, id="number-int"),
    pytest.param("number", None, "11.5", 11.5, id="number-numeric-string"),
    pytest.param("date", None, "2025-07-01", "2025-07-01", id="date"),
    pytest.param("url", None, "https://nucicer.com/news", "https://nucicer.com/news", id="url"),
    pytest.param("email", None, "ir@nucicer.com", "ir@nucicer.com", id="email"),
    pytest.param("phone", None, "+1 (530) 555-0100", "+1 (530) 555-0100", id="phone"),
    pytest.param("options", ["series_a", "seed"], "series_a", "series_a", id="options"),
]


# ── the 8 typed fields validate ───────────────────────────────────────────────


@pytest.mark.parametrize(("field_type", "options", "raw", "expected"), _VALID_SCALAR_CASES)
def test_scalar_enrichment_types_validate(
    field_type: str,
    options: list[str] | None,
    raw: Any,
    expected: Any,
    enrich_model_env: str,
) -> None:
    stub = _StubLLM(_payload(raw))
    field = enrich_item(
        _URL, _TITLE, _MARKDOWN, _def("field", field_type, options), llm_client=stub
    )

    assert field.status == "resolved"
    assert field.value == expected
    assert field.error is None


def test_company_profile_type_validates_to_a_company_entity(enrich_model_env: str) -> None:
    stub = _StubLLM(_company_payload())
    field = enrich_item(
        _URL, _TITLE, _MARKDOWN, _def("profile", "company_profile"), llm_client=stub
    )

    assert field.status == "resolved"
    entity = field.value
    assert isinstance(entity, CompanyEntity)
    assert entity.name == "NuCicer"
    assert entity.founded_year == 2019
    assert entity.funding_total == 16_000_000.0
    assert [round_.name for round_ in entity.funding_rounds] == ["series a"]
    assert entity.funding_rounds[0].amount == 11_500_000.0


@pytest.mark.parametrize(
    ("field_type", "options", "raw", "expected"),
    _VALID_SCALAR_CASES,
)
def test_every_resolved_field_carries_at_least_one_citation(
    field_type: str,
    options: list[str] | None,
    raw: Any,
    expected: Any,
    enrich_model_env: str,
) -> None:
    stub = _StubLLM(_payload(raw))
    field = enrich_item(
        _URL, _TITLE, _MARKDOWN, _def("field", field_type, options), llm_client=stub
    )

    assert field.status == "resolved"
    assert field.citations, "a resolved field without citations must fail the test"
    assert all(type(citation) is Citation for citation in field.citations)
    assert field.citations[0].url == _URL


def test_company_profile_resolved_field_carries_the_provenance_union(enrich_model_env: str) -> None:
    stub = _StubLLM(_company_payload())
    field = enrich_item(
        _URL, _TITLE, _MARKDOWN, _def("profile", "company_profile"), llm_client=stub
    )

    assert field.status == "resolved"
    assert field.citations
    assert all(type(citation) is Citation for citation in field.citations)


# ── strict type validation: bad values are unresolved, never coerced ──────────


@pytest.mark.parametrize(
    ("field_type", "options", "bad_value"),
    [
        pytest.param("number", None, "about eleven million", id="number-prose"),
        pytest.param("number", None, "$11.5M", id="number-currency"),
        pytest.param("number", None, "11,500,000", id="number-grouped"),
        pytest.param("number", None, True, id="number-bool"),
        pytest.param("number", None, "nan", id="number-nan"),
        pytest.param("date", None, "July 2025", id="date-prose"),
        pytest.param("date", None, "2025-07", id="date-month-only"),
        pytest.param("date", None, "2025-13-45", id="date-impossible"),
        pytest.param("url", None, "nucicer.com/only-a-path", id="url-no-scheme"),
        pytest.param("email", None, "ir@nucicer", id="email-no-dot"),
        pytest.param("email", None, "not an email", id="email-prose"),
        pytest.param("phone", None, "call the office", id="phone-prose"),
        pytest.param("phone", None, "+1 555", id="phone-too-short"),
        pytest.param("options", ["series_a"], "series_b", id="options-not-declared"),
    ],
)
def test_invalid_scalar_values_are_unresolved_never_coerced(
    field_type: str,
    options: list[str] | None,
    bad_value: Any,
    enrich_model_env: str,
) -> None:
    stub = _StubLLM(_payload(bad_value))
    field = enrich_item(
        _URL, _TITLE, _MARKDOWN, _def("field", field_type, options), llm_client=stub
    )

    assert field.status == "unresolved"
    assert field.value is None
    assert field.error


def test_null_value_is_unresolved_without_coercion(enrich_model_env: str) -> None:
    stub = _StubLLM(_payload(None))
    field = enrich_item(_URL, _TITLE, _MARKDOWN, _def("field", "text"), llm_client=stub)

    assert field.status == "unresolved"
    assert field.value is None
    assert field.error


# ── citations are mandatory on success ────────────────────────────────────────


def test_empty_citations_downgrade_to_unresolved(enrich_model_env: str) -> None:
    stub = _StubLLM(_payload("NuCicer", citations=[]))
    field = enrich_item(_URL, _TITLE, _MARKDOWN, _def("field", "text"), llm_client=stub)

    assert field.status == "unresolved"
    assert field.value is None
    assert field.citations == []
    assert field.error and "citation" in field.error.lower()


def test_invalid_citation_payload_is_unresolved(enrich_model_env: str) -> None:
    stub = _StubLLM(_payload("NuCicer", citations=[{"title": "no url at all"}]))
    field = enrich_item(_URL, _TITLE, _MARKDOWN, _def("field", "text"), llm_client=stub)

    assert field.status == "unresolved"
    assert field.citations == []
    assert field.error


def test_company_payload_without_provenance_is_unresolved(enrich_model_env: str) -> None:
    payload = _company_payload()
    payload["provenance"] = {}
    stub = _StubLLM(payload)
    field = enrich_item(
        _URL, _TITLE, _MARKDOWN, _def("profile", "company_profile"), llm_client=stub
    )

    assert field.status == "unresolved"
    assert field.citations == []
    assert field.error


# ── extraction unavailability is unresolved with reasoning ────────────────────


def test_missing_model_env_is_unresolved_without_calling_the_llm(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv(ENRICH_MODEL_ENV, raising=False)
    stub = _StubLLM(_payload("NuCicer"))
    field = enrich_item(_URL, _TITLE, _MARKDOWN, _def("field", "text"), llm_client=stub)

    assert field.status == "unresolved"
    assert field.error and ENRICH_MODEL_ENV in field.error
    assert stub.calls == []


def test_llm_error_is_unresolved_with_reasoning(enrich_model_env: str) -> None:
    stub = _StubLLM(error=RuntimeError("provider exploded"))
    field = enrich_item(_URL, _TITLE, _MARKDOWN, _def("field", "text"), llm_client=stub)

    assert field.status == "unresolved"
    assert field.error and "provider exploded" in field.error


def test_unparseable_payload_is_unresolved(enrich_model_env: str) -> None:
    stub = _StubLLM(raw="not json at all")
    field = enrich_item(_URL, _TITLE, _MARKDOWN, _def("field", "text"), llm_client=stub)

    assert field.status == "unresolved"
    assert field.error and "JSON" in field.error


def test_empty_markdown_never_calls_the_llm(enrich_model_env: str) -> None:
    stub = _StubLLM(_payload("NuCicer"))
    field = enrich_item(_URL, _TITLE, "  \n", _def("field", "text"), llm_client=stub)

    assert field.status == "unresolved"
    assert field.error and "markdown" in field.error.lower()
    assert stub.calls == []


# ── the digillm boundary ──────────────────────────────────────────────────────


def test_extraction_boundary_prompt_schema_and_usage(enrich_model_env: str) -> None:
    enrichment = _def("headline funding total", "text")
    stub = _StubLLM(_payload("NuCicer"))
    enrich_item(_URL, _TITLE, _MARKDOWN, enrichment, llm_client=stub)

    assert len(stub.calls) == 1
    model, messages, kwargs = stub.calls[0]
    assert model == enrich_model_env
    assert kwargs["usage_kind"] == "webset_enrich"
    assert kwargs["response_format"]["json_schema"]["name"] == "webset_enrichment"
    prompt = messages[-1]["content"]
    assert _URL in prompt
    assert _TITLE in prompt
    assert enrichment.name in prompt
    assert enrichment.description in prompt
    assert _MARKDOWN in prompt


def test_company_profile_uses_the_company_schema(enrich_model_env: str) -> None:
    stub = _StubLLM(_company_payload())
    enrich_item(_URL, _TITLE, _MARKDOWN, _def("profile", "company_profile"), llm_client=stub)

    schema = stub.calls[0][2]["response_format"]["json_schema"]["schema"]
    assert stub.calls[0][2]["response_format"]["json_schema"]["name"] == "webset_company"
    assert {"name", "funding_rounds", "provenance", "reasoning"} <= set(schema["properties"])


def test_options_schema_pins_the_declared_choices(enrich_model_env: str) -> None:
    enrichment = _def("round", "options", options=["series_a", "seed"])
    stub = _StubLLM(_payload("series_a"))
    enrich_item(_URL, _TITLE, _MARKDOWN, enrichment, llm_client=stub)

    schema = stub.calls[0][2]["response_format"]["json_schema"]["schema"]
    assert schema["properties"]["value"]["enum"] == ["series_a", "seed", None]


def test_markdown_is_truncated_to_the_6000_char_page_budget(enrich_model_env: str) -> None:
    assert MARKDOWN_TRUNCATION_CHARS == 6000
    tail = "TAIL-MARKER-NEVER-SENT"
    stub = _StubLLM(_payload("NuCicer"))

    enrich_item(
        _URL,
        _TITLE,
        ("a" * MARKDOWN_TRUNCATION_CHARS) + tail,
        _def("field", "text"),
        llm_client=stub,
    )

    prompt = stub.calls[0][1][-1]["content"]
    assert ("a" * MARKDOWN_TRUNCATION_CHARS) in prompt
    assert tail not in prompt


# ── company payload strictness + provenance attachment ────────────────────────


def test_company_payload_without_entity_name_is_unresolved(enrich_model_env: str) -> None:
    payload = _company_payload()
    payload["name"] = ""
    stub = _StubLLM(payload)
    field = enrich_item(
        _URL, _TITLE, _MARKDOWN, _def("profile", "company_profile"), llm_client=stub
    )

    assert field.status == "unresolved"
    assert field.error and "name" in field.error


def test_company_scalar_type_violations_are_not_coerced(enrich_model_env: str) -> None:
    payload = _company_payload()
    payload["founded_year"] = "2019"
    stub = _StubLLM(payload)
    field = enrich_item(
        _URL, _TITLE, _MARKDOWN, _def("profile", "company_profile"), llm_client=stub
    )

    assert field.status == "resolved"
    entity = field.value
    assert entity.founded_year is None
    assert "founded_year" in entity.reasoning


def test_company_uncited_scalar_is_recorded_and_flagged(enrich_model_env: str) -> None:
    payload = _company_payload()
    del payload["provenance"]["workforce_total"]
    stub = _StubLLM(payload)
    field = enrich_item(
        _URL, _TITLE, _MARKDOWN, _def("profile", "company_profile"), llm_client=stub
    )

    assert field.status == "resolved"
    entity = field.value
    assert entity.provenance["workforce_total"] == []
    assert "workforce_total" in entity.reasoning


def test_company_entity_always_carries_a_provenance_entry_per_scalar(
    enrich_model_env: str,
) -> None:
    payload = _company_payload()
    payload["provenance"] = {"name": [_citation()]}
    stub = _StubLLM(payload)
    field = enrich_item(
        _URL, _TITLE, _MARKDOWN, _def("profile", "company_profile"), llm_client=stub
    )

    entity = field.value
    assert isinstance(entity, CompanyEntity)
    assert {
        "name",
        "founded_year",
        "description",
        "workforce_total",
        "hq_city",
        "hq_country",
        "funding_total",
    } <= set(entity.provenance)


def test_company_round_currency_without_a_rate_is_unresolved_in_reasoning(
    enrich_model_env: str,
) -> None:
    payload = _company_payload()
    payload["funding_rounds"][0]["currency"] = "XTS"
    stub = _StubLLM(payload)
    field = enrich_item(
        _URL, _TITLE, _MARKDOWN, _def("profile", "company_profile"), llm_client=stub
    )

    entity = field.value
    assert isinstance(entity, CompanyEntity)
    assert entity.funding_rounds == []
    assert "XTS" in entity.reasoning


def test_enrich_item_returns_an_enriched_field(enrich_model_env: str) -> None:
    stub = _StubLLM(_payload("NuCicer"))
    field = enrich_item(_URL, _TITLE, _MARKDOWN, _def("field", "text"), llm_client=stub)

    assert isinstance(field, EnrichedField)
