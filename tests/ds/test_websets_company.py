"""Phase D company enrichment (#4066, Task 4) — funding merge + entity merge.

Pins the company-tracking contract from the spec
(``docs/superpowers/specs/2026-09-14-oss-websearch-phaseD-verify-enrich.md``
§ Company/people enrichment) against the T0-vendored live EXA sample
(``tests/ds/fixtures/websets/s5_category_company.json``) and the vendored ECB
snapshot (``tests/ds/fixtures/websets/fx_ecb_snapshot.json``). Values are read
from the fixtures, never invented, and no scratch paths are referenced:

- round events merge by ``(name, date)`` after lowercasing the name, normalizing
  the date to an ISO month, and converting the amount to USD with the ECB
  snapshot; a non-USD amount with no snapshot rate is unresolved, never guessed;
- a round is admitted on quorum (>= 2 independent page citations, or 1 citation
  from the company's own domain); single third-party mentions stay unresolved;
- ``funding_total`` is the sum of admitted rounds; when at least one page claims
  an explicit total, the median claimed total must be within 1% of the sum or the
  total is unresolved with reasoning; with no claimed totals the sum stands;
- entity merge groups candidates by normalized domain + name similarity, keeps
  the scalar value with more independent citations, and records losers in
  ``alternatives[]`` with their own citations;
- every ``CompanyEntity`` scalar carries a ``provenance[field]`` entry and
  ``company_profile_field`` bundles the entity into one resolved ``EnrichedField``
  (union of provenance citations) or ``unresolved`` without resolved scalars.
"""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

import pytest
from digisearch.web_search.citation import Citation
from digisearch.websets.enrich import (
    FX_SNAPSHOT_ENV,
    PROVENANCE_SCALARS,
    CompanyCandidate,
    FundingObservation,
    RawFundingRound,
    company_profile_field,
    load_fx_snapshot,
    merge_company_entities,
    reconcile_funding_history,
)
from digisearch.websets.models import CompanyEntity

pytestmark = pytest.mark.unit

_FIXTURES = Path(__file__).parent / "fixtures" / "websets"
_COMPANY_FIXTURE = _FIXTURES / "s5_category_company.json"
_FX_FIXTURE = _FIXTURES / "fx_ecb_snapshot.json"

_PRESS_URL = "https://finsmes.test/nucicer-raises-11-5m"

#: ``- Series a (2025-07-01): USD 11.5M`` — the fixture's funding-history bullets.
_ROUND_LINE = re.compile(
    r"-\s*(?P<name>[A-Za-z][A-Za-z ]*?)\s*\((?P<date>\d{4}-\d{2}-\d{2})\)"
    r"(?::\s*USD\s*(?P<amount>[\d,]+(?:\.\d+)?)(?P<unit>[MKB])?)?"
)
_AMOUNT_UNITS = {"K": 1_000.0, "M": 1_000_000.0, "B": 1_000_000_000.0}


def _rounds_from_highlight(highlight: str, *, page_url: str) -> list[RawFundingRound]:
    """Parse the vendored funding-history bullet block (fixture values, not prose)."""
    rounds: list[RawFundingRound] = []
    for match in _ROUND_LINE.finditer(highlight):
        amount: float | None = None
        if match.group("amount"):
            amount = float(match.group("amount").replace(",", ""))
            amount *= _AMOUNT_UNITS.get(match.group("unit") or "", 1.0)
        rounds.append(
            RawFundingRound(
                name=match.group("name").strip(),
                date=match.group("date"),
                amount=amount,
                currency="USD",
                citations=[Citation(url=page_url, excerpt=match.group(0).strip())],
            )
        )
    return rounds


@pytest.fixture(scope="module")
def company_sample() -> dict[str, Any]:
    return json.loads(_COMPANY_FIXTURE.read_text(encoding="utf-8"))


@pytest.fixture(scope="module")
def fx_rates() -> dict[str, float]:
    return load_fx_snapshot(_FX_FIXTURE)


@pytest.fixture(scope="module")
def nucicer_properties(company_sample: dict[str, Any]) -> dict[str, Any]:
    return company_sample["results"][0]["entities"][0]["properties"]


@pytest.fixture(scope="module")
def nucicer_url(company_sample: dict[str, Any]) -> str:
    return company_sample["results"][0]["url"]


@pytest.fixture(scope="module")
def nucicer_rounds(company_sample: dict[str, Any], nucicer_url: str) -> list[RawFundingRound]:
    return _rounds_from_highlight(
        company_sample["results"][0]["highlights"][0], page_url=nucicer_url
    )


def _own_page_observation(
    nucicer_rounds: list[RawFundingRound],
    nucicer_properties: dict[str, Any],
    nucicer_url: str,
    *,
    claimed: bool = True,
) -> FundingObservation:
    """NuCicer's own page: the vendored rounds, optionally the vendored total claim."""
    return FundingObservation(
        url=nucicer_url,
        rounds=nucicer_rounds,
        claimed_total=float(nucicer_properties["financials"]["fundingTotal"]) if claimed else None,
        claim_citations=[Citation(url=nucicer_url, excerpt="Total Funding: USD 16,000,000")]
        if claimed
        else [],
    )


def _press_observation(
    *,
    claimed_total: float | None = 16_000_000.0,
    date: str = "2025-07-15",
    amount: float = 11_500_000.0,
) -> FundingObservation:
    """A third-party press page reporting the same Series A in the same month."""
    return FundingObservation(
        url=_PRESS_URL,
        rounds=[
            RawFundingRound(
                name="Series A",
                date=date,
                amount=amount,
                currency="USD",
                citations=[Citation(url=_PRESS_URL, excerpt="NuCicer Raises $11.5M")],
            )
        ],
        claimed_total=claimed_total,
        claim_citations=[Citation(url=_PRESS_URL)] if claimed_total is not None else [],
    )


def _candidate_from_sample(
    company_sample: dict[str, Any], index: int, *, funding: FundingObservation | None = None
) -> CompanyCandidate:
    """One vendored sample row as a merge candidate (fixture scalars only)."""
    result = company_sample["results"][index]
    properties = result["entities"][0]["properties"]
    citation = Citation(url=result["url"])
    entity = CompanyEntity(
        name=properties["name"],
        founded_year=properties["foundedYear"],
        workforce_total=properties["workforce"]["total"],
        hq_city=properties["headquarters"]["city"],
        hq_country=properties["headquarters"]["country"],
        provenance={
            field: [citation]
            for field in ("name", "founded_year", "workforce_total", "hq_city", "hq_country")
        },
    )
    return CompanyCandidate(url=result["url"], entity=entity, funding=funding)


# ── fixture + ECB snapshot plumbing ───────────────────────────────────────────


def test_vendored_snapshot_carries_the_ecb_reference_rates(fx_rates: dict[str, float]) -> None:
    assert fx_rates["USD"] == pytest.approx(1.1539)
    assert {"GBP", "JPY", "CHF", "CAD"} <= set(fx_rates)


def test_fx_snapshot_loads_from_the_env_var(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv(FX_SNAPSHOT_ENV, str(_FX_FIXTURE))
    assert load_fx_snapshot()["USD"] == pytest.approx(1.1539)


def test_fx_snapshot_requires_a_path_or_env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv(FX_SNAPSHOT_ENV, raising=False)
    with pytest.raises(FileNotFoundError, match=FX_SNAPSHOT_ENV):
        load_fx_snapshot()


def test_fixture_highlight_parses_to_the_vendored_nucicer_rounds(
    nucicer_rounds: list[RawFundingRound], nucicer_properties: dict[str, Any]
) -> None:
    assert nucicer_properties["financials"]["fundingTotal"] == 16_000_000
    assert [round_.name for round_ in nucicer_rounds] == ["Series a", "Seed", "Seed"]
    assert [round_.date for round_ in nucicer_rounds] == [
        "2025-07-01",
        "2022-11-01",
        "2022-03-01",
    ]
    assert [round_.amount for round_ in nucicer_rounds] == [11_500_000.0, None, 4_500_000.0]


# ── funding-history merge + reconciliation ────────────────────────────────────


def test_two_pages_reporting_the_same_series_a_merge_to_one_round(
    nucicer_rounds: list[RawFundingRound],
    nucicer_properties: dict[str, Any],
    nucicer_url: str,
    fx_rates: dict[str, float],
) -> None:
    own = _own_page_observation(nucicer_rounds, nucicer_properties, nucicer_url)
    press = _press_observation()

    result = reconcile_funding_history(
        [own, press], company_domain="nucicer.com", fx_rates=fx_rates
    )

    series_a = [round_ for round_ in result.rounds if round_.name == "series a"]
    assert len(series_a) == 1
    assert series_a[0].date == "2025-07"
    assert series_a[0].amount == 11_500_000.0
    assert {citation.url for citation in series_a[0].citations} == {nucicer_url, _PRESS_URL}
    assert result.total == 16_000_000.0
    assert result.unresolved_rounds == []
    assert result.reasoning == ""


def test_median_claimed_total_beyond_one_percent_is_unresolved(
    nucicer_rounds: list[RawFundingRound],
    nucicer_properties: dict[str, Any],
    nucicer_url: str,
    fx_rates: dict[str, float],
) -> None:
    own = _own_page_observation(nucicer_rounds, nucicer_properties, nucicer_url)
    press = _press_observation(claimed_total=20_000_000.0)

    result = reconcile_funding_history(
        [own, press], company_domain="nucicer.com", fx_rates=fx_rates
    )

    assert result.total is None
    assert result.total_citations == []
    assert "median" in result.reasoning.lower()
    assert "1%" in result.reasoning


def test_reconciliation_tolerance_is_exactly_one_percent(
    nucicer_rounds: list[RawFundingRound],
    nucicer_properties: dict[str, Any],
    nucicer_url: str,
    fx_rates: dict[str, float],
) -> None:
    own = _own_page_observation(nucicer_rounds, nucicer_properties, nucicer_url)
    within = _press_observation(claimed_total=16_320_000.0)  # median +1.0% exactly
    beyond = _press_observation(claimed_total=16_340_000.0)  # median +1.0625%

    accepted = reconcile_funding_history(
        [own, within], company_domain="nucicer.com", fx_rates=fx_rates
    )
    rejected = reconcile_funding_history(
        [own, beyond], company_domain="nucicer.com", fx_rates=fx_rates
    )

    assert accepted.total == 16_000_000.0
    assert rejected.total is None


def test_no_claimed_totals_means_the_sum_stands(
    nucicer_rounds: list[RawFundingRound],
    nucicer_properties: dict[str, Any],
    nucicer_url: str,
    fx_rates: dict[str, float],
) -> None:
    own = _own_page_observation(nucicer_rounds, nucicer_properties, nucicer_url, claimed=False)
    press = _press_observation(claimed_total=None)

    result = reconcile_funding_history(
        [own, press], company_domain="nucicer.com", fx_rates=fx_rates
    )

    assert result.total == 16_000_000.0
    assert {citation.url for citation in result.total_citations} == {nucicer_url, _PRESS_URL}


def test_single_third_party_mention_without_quorum_is_unresolved(
    fx_rates: dict[str, float],
) -> None:
    press = _press_observation(claimed_total=None)

    result = reconcile_funding_history([press], company_domain="nucicer.com", fx_rates=fx_rates)

    assert result.rounds == []
    assert result.total is None
    assert len(result.unresolved_rounds) == 1
    assert result.unresolved_rounds[0].name == "series a"
    assert "quorum" in result.reasoning.lower()


def test_single_own_domain_press_release_admits_the_round(
    nucicer_rounds: list[RawFundingRound],
    nucicer_properties: dict[str, Any],
    nucicer_url: str,
    fx_rates: dict[str, float],
) -> None:
    own = _own_page_observation(nucicer_rounds, nucicer_properties, nucicer_url)

    result = reconcile_funding_history([own], company_domain="nucicer.com", fx_rates=fx_rates)

    assert len(result.rounds) == 3
    assert result.total == 16_000_000.0


def test_non_usd_amounts_normalize_with_the_ecb_snapshot(fx_rates: dict[str, float]) -> None:
    first = "https://press.test/eur-round"
    second = "https://news.test/eur-round"
    observations = [
        FundingObservation(
            url=first,
            rounds=[
                RawFundingRound(
                    name="Series B",
                    date="2024-05-03",
                    amount=10_000_000.0,
                    currency="EUR",
                    citations=[Citation(url=first)],
                )
            ],
        ),
        FundingObservation(
            url=second,
            rounds=[
                RawFundingRound(
                    name="Series B",
                    date="2024-05-20",
                    amount=10_000_000.0,
                    currency="EUR",
                    citations=[Citation(url=second)],
                )
            ],
        ),
    ]

    result = reconcile_funding_history(observations, fx_rates=fx_rates)

    expected_usd = 10_000_000.0 * fx_rates["USD"]  # EUR is the ECB base (= 1 EUR -> rate)
    assert result.rounds[0].date == "2024-05"
    assert result.rounds[0].amount == pytest.approx(expected_usd)
    assert result.total == pytest.approx(expected_usd)


def test_currency_without_a_snapshot_rate_is_unresolved_never_guessed(
    fx_rates: dict[str, float],
) -> None:
    first = "https://press.test/try-round"
    second = "https://news.test/try-round"
    observations = [
        FundingObservation(
            url=first,
            rounds=[
                RawFundingRound(
                    name="Series B",
                    date="2024-05-03",
                    amount=5_000_000.0,
                    currency="XTS",
                    citations=[Citation(url=first)],
                )
            ],
        ),
        FundingObservation(
            url=second,
            rounds=[
                RawFundingRound(
                    name="Series B",
                    date="2024-05-03",
                    amount=5_000_000.0,
                    currency="XTS",
                    citations=[Citation(url=second)],
                )
            ],
        ),
    ]

    result = reconcile_funding_history(observations, fx_rates=fx_rates)

    assert result.rounds == []
    assert result.total is None
    assert len(result.unresolved_rounds) == 1
    assert "XTS" in result.reasoning


# ── entity merge ──────────────────────────────────────────────────────────────


def test_same_domain_candidates_merge_and_losers_land_in_alternatives() -> None:
    own_about = Citation(url="https://nucicer.com/about")
    own_press = Citation(url="https://nucicer.com/press")
    third_party = Citation(url=_PRESS_URL)
    first = CompanyCandidate(
        url="https://nucicer.com/about",
        entity=CompanyEntity(
            name="NuCicer",
            workforce_total=27,
            hq_city="Davis",
            provenance={
                "name": [own_about, third_party],
                "workforce_total": [own_about, third_party],
                "hq_city": [own_about],
            },
        ),
    )
    second = CompanyCandidate(
        url="https://nucicer.com/press",
        entity=CompanyEntity(
            name="NuCicer Inc.",
            workforce_total=42,
            hq_city="Woodland",
            provenance={
                "name": [own_press],
                "workforce_total": [own_press],
                "hq_city": [own_press],
            },
        ),
    )

    merged = merge_company_entities([first, second])

    assert len(merged) == 1
    entity = merged[0]
    assert entity.name == "NuCicer"  # 2 independent citations beat 1
    assert entity.workforce_total == 27
    alternatives = {(alternative.field, alternative.value) for alternative in entity.alternatives}
    assert ("name", "NuCicer Inc.") in alternatives
    assert ("workforce_total", 42) in alternatives
    assert ("hq_city", "Woodland") in alternatives
    loser = next(
        alternative for alternative in entity.alternatives if alternative.field == "workforce_total"
    )
    assert [citation.url for citation in loser.citations] == [own_press.url]
    assert {citation.url for citation in entity.provenance["workforce_total"]} == {
        own_about.url,
        third_party.url,
    }


def test_same_name_candidates_merge_across_domains() -> None:
    own = Citation(url="https://nucicer.com/about")
    own_news = Citation(url="https://nucicer.com/news")
    press = Citation(url=_PRESS_URL)
    first = CompanyCandidate(
        url="https://nucicer.com/about",
        entity=CompanyEntity(
            name="NuCicer",
            founded_year=2019,
            provenance={"name": [own], "founded_year": [own, own_news]},
        ),
    )
    second = CompanyCandidate(
        url=_PRESS_URL,
        entity=CompanyEntity(
            name="NuCicer",
            founded_year=2018,
            provenance={"name": [press], "founded_year": [press]},
        ),
    )

    merged = merge_company_entities([first, second])

    assert len(merged) == 1
    assert merged[0].name == "NuCicer"
    assert merged[0].founded_year == 2019
    assert ("founded_year", 2018) in {
        (alternative.field, alternative.value) for alternative in merged[0].alternatives
    }


def test_distinct_companies_do_not_merge(company_sample: dict[str, Any]) -> None:
    nucicer = _candidate_from_sample(company_sample, 0)
    pollen = _candidate_from_sample(company_sample, 1)

    merged = merge_company_entities([nucicer, pollen])

    assert [entity.name for entity in merged] == ["NuCicer", "Pollen Systems"]


def test_merge_reconciles_funding_across_candidate_pages(
    company_sample: dict[str, Any],
    nucicer_rounds: list[RawFundingRound],
    nucicer_properties: dict[str, Any],
    nucicer_url: str,
    fx_rates: dict[str, float],
) -> None:
    own = _candidate_from_sample(
        company_sample,
        0,
        funding=_own_page_observation(nucicer_rounds, nucicer_properties, nucicer_url),
    )
    press = _candidate_from_sample(company_sample, 0, funding=_press_observation())
    press = press.model_copy(update={"url": _PRESS_URL})

    merged = merge_company_entities([own, press], company_domain="nucicer.com", fx_rates=fx_rates)

    assert len(merged) == 1
    entity = merged[0]
    assert entity.funding_total == 16_000_000.0
    assert [round_.name for round_ in entity.funding_rounds].count("series a") == 1
    assert entity.provenance["funding_total"]


def test_every_scalar_has_a_provenance_entry_after_merge() -> None:
    name_citation = Citation(url="https://nucicer.com/about")
    candidate = CompanyCandidate(
        url="https://nucicer.com/about",
        entity=CompanyEntity(
            name="NuCicer",
            founded_year=2019,
            provenance={"name": [name_citation]},
        ),
    )

    merged = merge_company_entities([candidate])

    assert len(merged) == 1
    entity = merged[0]
    assert set(PROVENANCE_SCALARS) <= set(entity.provenance)
    assert entity.provenance["founded_year"] == []
    assert "founded_year" in entity.reasoning
    assert entity.provenance["funding_total"] == []


# ── company_profile_field (flag I8) ───────────────────────────────────────────


def test_company_profile_field_bundles_the_entity_with_the_provenance_union() -> None:
    press = Citation(url="https://nucicer.com/press", excerpt="Series A")
    secondary = Citation(url=_PRESS_URL)
    same_url_other_quote = Citation(url="https://nucicer.com/press", excerpt="different quote")
    entity = CompanyEntity(
        name="NuCicer",
        funding_total=16_000_000.0,
        provenance={"name": [press, secondary], "funding_total": [same_url_other_quote]},
    )

    field = company_profile_field(entity)

    assert field.status == "resolved"
    assert field.value is entity
    assert {citation.url for citation in field.citations} == {press.url, secondary.url}
    assert len(field.citations) == 3  # exact duplicates dropped, distinct quotes kept


def test_company_profile_field_is_unresolved_without_resolved_scalars() -> None:
    entity = CompanyEntity(name="NuCicer", founded_year=2019, provenance={})

    field = company_profile_field(entity)

    assert field.status == "unresolved"
    assert field.value is None
    assert field.citations == []
    assert field.error and "no resolved scalars" in field.error.lower()


def test_merged_entity_bundles_into_a_resolved_profile_field() -> None:
    citation = Citation(url="https://nucicer.com/")
    candidate = CompanyCandidate(
        url="https://nucicer.com/",
        entity=CompanyEntity(name="NuCicer", provenance={"name": [citation]}),
    )

    (entity,) = merge_company_entities([candidate])
    field = company_profile_field(entity)

    assert field.status == "resolved"
    assert isinstance(field.value, CompanyEntity)
    assert {item.url for item in field.citations} == {citation.url}
