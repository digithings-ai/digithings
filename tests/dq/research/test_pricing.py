"""Token-derived cost estimate (#4596) — the fallback when the provider reports no cost.

``run_diagnostics.est_cost_usd`` was always ``0.0`` because the house upstream reports no
per-call cost and the aggregation collapses "unknown" to zero. The column is *named*
``est_cost_usd``, so an estimate was always the intended semantic. This module pins the
estimator's two load-bearing properties: it sums the committed per-model prices over the
tokens actually recorded, and it never fabricates a number for a model it cannot price.

The provenance test is the important one: the committed table is not trusted on its own
word, it is checked against the repo's own ``docs/providers/snapshots/*.yaml``. Editing a
price to a value no snapshot corroborates makes that test fail.

The table itself lives in ``config/digiquant-model-prices.json`` (#5029) so no provider
model id is a string literal in production code. ``TestTheTableLivesInConfig`` is the other
load-bearing half: it pins that the numbers are *read*, with their provenance attached, and
that the module holds no slug literal to fall back on.
"""

from __future__ import annotations

import glob
import json
import logging
import os
from collections.abc import Iterator
from pathlib import Path

import pytest
import yaml
from digiquant.research import pricing
from digiquant.research.pricing import estimate_cost_usd, price_for

pytestmark = pytest.mark.unit

_REPO_ROOT = Path(__file__).resolve().parents[3]
_SNAPSHOTS_GLOB = str(_REPO_ROOT / "docs" / "providers" / "snapshots" / "*.yaml")
_MODELS_CONFIG = _REPO_ROOT / "config" / "digiquant_models.yaml"
_PRICING_MODULE = _REPO_ROOT / "digiquant" / "src" / "digiquant" / "research" / "pricing.py"
_PRICE_CONFIG_NAME = "digiquant-model-prices.json"

_LOGGER = "digiquant.research.pricing"


@pytest.fixture(autouse=True)
def _isolated_price_cache() -> Iterator[None]:
    """Keep the mtime-cached table from leaking between tests.

    ``load_price_table`` caches on ``(path, mtime)``, so a test that repoints
    ``DIGI_CONFIG_PATH`` at a tmp dir must neither inherit the table parsed for an earlier
    test nor leave its own behind for the next. The cache is a plain module global;
    ``hasattr`` guards rather than assigning directly so this file also runs against a
    module that has no loader to reset.
    """
    if hasattr(pricing, "_prices_cache"):
        pricing._prices_cache = None
    try:
        yield
    finally:
        if hasattr(pricing, "_prices_cache"):
            pricing._prices_cache = None


def _snapshot_prices_by_bare_name() -> dict[str, set[tuple[float, float]]]:
    """Bare model name -> the set of (input, output) prices the snapshots corroborate.

    A set rather than a single pair because the same bare name can appear in several
    provider snapshots (a hosted open-weight model is resold at different rates). The house
    rows must match *one* of them, and a wrong edit matches none.
    """
    prices: dict[str, set[tuple[float, float]]] = {}
    for path in sorted(glob.glob(_SNAPSHOTS_GLOB)):
        snapshot = yaml.safe_load(Path(path).read_text())
        if not isinstance(snapshot, dict):
            continue
        paid = snapshot.get("paid_tier") or {}
        for model in paid.get("models") or []:
            if not isinstance(model, dict) or not model.get("name"):
                continue
            cost_in = model.get("cost_per_1m_input")
            cost_out = model.get("cost_per_1m_output")
            if cost_in is None or cost_out is None:
                continue
            prices.setdefault(model["name"], set()).add((float(cost_in), float(cost_out)))
    return prices


def _house_slugs_from_policy() -> set[str]:
    """Every slug the model policy can actually route to, read from the committed config."""
    policy = yaml.safe_load(_MODELS_CONFIG.read_text())
    slugs: set[str] = set()
    for tier in (policy.get("tiers") or {}).values():
        for pool in (tier.get("allowed_models") or {}).values():
            slugs.update(pool)
    return slugs


def _price_entry(prompt: float, completion: float, **extra: object) -> dict[str, object]:
    """A minimal well-formed config price entry; ``extra`` overrides individual keys."""
    entry: dict[str, object] = {
        "prompt_usd_per_1m": prompt,
        "completion_usd_per_1m": completion,
        "source": "docs/providers/snapshots/synthetic.yaml",
    }
    entry.update(extra)
    return entry


def _write_price_config(
    directory: Path,
    payload: dict[str, object],
    *,
    mtime: float = 1_000.0,
) -> Path:
    """Write a price config into *directory* with an explicit mtime.

    The mtime is pinned so "the cache noticed the file changed" is a deterministic
    assertion rather than a race against filesystem timestamp resolution.
    """
    target = directory / _PRICE_CONFIG_NAME
    target.write_text(json.dumps(payload))
    os.utime(target, (mtime, mtime))
    return target


def _point_at(monkeypatch: pytest.MonkeyPatch, directory: Path) -> None:
    """Repoint the loader at *directory*. An explicit path is authoritative — no fallback."""
    monkeypatch.setenv("DIGI_CONFIG_PATH", str(directory))


class TestThePriceTable:
    def test_every_committed_price_is_corroborated_by_a_committed_snapshot(self) -> None:
        """The table's own provenance claim, enforced: each row must match the value in
        ``docs/providers/snapshots/<provider>.yaml`` for its bare model name.

        This is what makes an arbitrary edit fail — change ``gpt-5.6-luna`` to ``0.20`` and
        no snapshot corroborates ``(0.2, ...)``, so this goes red instead of silently
        shipping a fabricated number.
        """
        snapshots = _snapshot_prices_by_bare_name()
        for slug, price in pricing.MODEL_PRICES_USD_PER_1M.items():
            bare = slug.split("/", 1)[1]
            assert bare in snapshots, f"{slug}: no snapshot prices {bare!r}"
            assert (
                price.prompt_usd_per_1m,
                price.completion_usd_per_1m,
            ) in snapshots[bare], f"{slug}: {price} is not corroborated by any snapshot"

    def test_every_house_slug_is_priced_or_documented_as_unpriced(self) -> None:
        """Policy coverage: a slug the config can route to must be either in the table or in
        the explicit unpriced set — never silently missing from both."""
        house_slugs = _house_slugs_from_policy()
        assert house_slugs, "model policy parsed to nothing — check the config shape"
        for slug in house_slugs:
            assert slug in pricing.MODEL_PRICES_USD_PER_1M or slug in pricing._UNPRICED_SLUGS, slug

    def test_the_unpriced_set_only_holds_house_slugs(self) -> None:
        """Keep the unpriced set honest: it is for slugs the policy routes to but the repo
        cannot price, not a dumping ground for retired names."""
        assert pricing._UNPRICED_SLUGS <= _house_slugs_from_policy()

    def test_an_unknown_model_has_no_price(self) -> None:
        assert price_for("made-up/model") is None

    def test_every_committed_price_is_a_positive_pair(self) -> None:
        for slug, price in pricing.MODEL_PRICES_USD_PER_1M.items():
            assert price.prompt_usd_per_1m > 0, slug
            assert price.completion_usd_per_1m > 0, slug


class TestTheTableLivesInConfig:
    """#5029: the numbers and their provenance are read from ``config/``, not hardcoded."""

    def test_no_house_model_slug_appears_anywhere_in_the_module(self) -> None:
        """The issue's actual requirement: no provider model id may appear in the source.

        The slug list comes from the model policy rather than being spelled out here, so
        this stays honest as the policy changes — a slug added to a tier pool and then
        hardcoded into ``pricing.py`` fails without anyone editing the test.
        """
        source = _PRICING_MODULE.read_text()
        for slug in sorted(_house_slugs_from_policy()):
            assert slug not in source, f"{slug} is hardcoded in {_PRICING_MODULE.name}"

    def test_the_prices_are_read_from_the_config_file(self, tmp_path: Path, monkeypatch) -> None:
        """A pointed-at config file *is* the table — including the exclusion of hardcoded rows."""
        _write_price_config(
            tmp_path,
            {
                "prices_usd_per_1m": {"vendor/synthetic": _price_entry(2.0, 8.0)},
                "unpriced_slugs": {},
            },
        )
        _point_at(monkeypatch, tmp_path)

        table = pricing.load_price_table()
        assert list(table) == ["vendor/synthetic"]
        assert table["vendor/synthetic"].prompt_usd_per_1m == 2.0
        assert price_for("vendor/synthetic").completion_usd_per_1m == 8.0
        # A slug that IS hardcoded in the pre-#5029 table must now be unknown, because the
        # only source of truth is the config file this test just pointed at.
        for slug in sorted(_house_slugs_from_policy()):
            assert price_for(slug) is None, slug

    def test_the_estimator_prices_from_the_config_file_too(
        self, tmp_path: Path, monkeypatch
    ) -> None:
        """``estimate_cost_usd`` must go through the same loader as ``price_for``."""
        _write_price_config(
            tmp_path,
            {
                "prices_usd_per_1m": {"vendor/synthetic": _price_entry(1.0, 6.0)},
                "unpriced_slugs": {},
            },
        )
        _point_at(monkeypatch, tmp_path)

        usage = {"prompt_tokens": 1_000_000, "completion_tokens": 1_000_000}
        assert estimate_cost_usd({"vendor/synthetic": usage}) == pytest.approx(7.0)
        assert (
            estimate_cost_usd(
                {"vendor/absent": {"prompt_tokens": 1_000_000, "completion_tokens": 0}}
            )
            is None
        )

    def test_a_changed_config_file_is_picked_up_without_a_restart(
        self, tmp_path: Path, monkeypatch
    ) -> None:
        """The cache is keyed on mtime, not memoised once for the life of the process."""
        _write_price_config(
            tmp_path,
            {"prices_usd_per_1m": {"vendor/first": _price_entry(1.0, 2.0)}, "unpriced_slugs": {}},
            mtime=1_000.0,
        )
        _point_at(monkeypatch, tmp_path)
        assert set(pricing.load_price_table()) == {"vendor/first"}
        # Same path, same process, no cache reset — only the mtime differs.
        _write_price_config(
            tmp_path,
            {"prices_usd_per_1m": {"vendor/second": _price_entry(3.0, 4.0)}, "unpriced_slugs": {}},
            mtime=2_000.0,
        )
        assert set(pricing.load_price_table()) == {"vendor/second"}

    def test_repeated_reads_reuse_one_parsed_table(self, tmp_path: Path, monkeypatch) -> None:
        _write_price_config(
            tmp_path,
            {
                "prices_usd_per_1m": {"vendor/synthetic": _price_entry(1.0, 2.0)},
                "unpriced_slugs": {},
            },
        )
        _point_at(monkeypatch, tmp_path)
        assert pricing.load_price_table() is pricing.load_price_table()

    def test_a_missing_config_file_prices_nothing_rather_than_guessing(
        self, tmp_path: Path, monkeypatch, caplog
    ) -> None:
        """Fail soft, loudly: telemetry must not raise, and "no price" must not read as "$0"."""
        _point_at(monkeypatch, tmp_path / "does-not-exist")
        with caplog.at_level(logging.WARNING, logger=_LOGGER):
            assert pricing.load_price_table() == {}
            assert pricing._UNPRICED_SLUGS == frozenset()
            assert (
                estimate_cost_usd(
                    {"vendor/anything": {"prompt_tokens": 1_000, "completion_tokens": 0}}
                )
                is None
            )
        assert _PRICE_CONFIG_NAME in caplog.text

    def test_a_corrupt_config_file_prices_nothing_instead_of_raising(
        self, tmp_path: Path, monkeypatch, caplog
    ) -> None:
        (tmp_path / _PRICE_CONFIG_NAME).write_text("{not json at all")
        _point_at(monkeypatch, tmp_path)
        with caplog.at_level(logging.WARNING, logger=_LOGGER):
            assert pricing.load_price_table() == {}
            assert estimate_cost_usd({"vendor/x": {"prompt_tokens": 10}}) is None
        assert _PRICE_CONFIG_NAME in caplog.text

    def test_a_sourceless_entry_is_refused_and_the_rest_survive(
        self, tmp_path: Path, monkeypatch, caplog
    ) -> None:
        """Provenance is load-bearing, so an entry without it is dropped — but one bad row
        must not zero the whole table, which would under-report every model's spend."""
        _write_price_config(
            tmp_path,
            {
                "prices_usd_per_1m": {
                    "vendor/good": _price_entry(1.0, 2.0),
                    "vendor/no-source": {"prompt_usd_per_1m": 3.0, "completion_usd_per_1m": 4.0},
                    "vendor/negative": _price_entry(-1.0, 2.0),
                    "vendor/not-a-number": {
                        "prompt_usd_per_1m": "free",
                        "completion_usd_per_1m": 2.0,
                        "source": "docs/providers/snapshots/synthetic.yaml",
                    },
                },
                "unpriced_slugs": {},
            },
        )
        _point_at(monkeypatch, tmp_path)

        with caplog.at_level(logging.WARNING, logger=_LOGGER):
            table = pricing.load_price_table()
        assert set(table) == {"vendor/good"}
        for slug in ("vendor/no-source", "vendor/negative", "vendor/not-a-number"):
            assert slug in caplog.text

    def test_every_committed_entry_carries_its_snapshot_source(self) -> None:
        """Each number must still be traceable to a file, not just be a number in a config."""
        table = pricing.MODEL_PRICES_USD_PER_1M
        assert table, "the committed price table loaded empty — check the config file"
        for slug, price in table.items():
            assert price.source.startswith("docs/providers/snapshots/"), (slug, price.source)
            assert (_REPO_ROOT / price.source).is_file(), (slug, price.source)

    def test_every_unpriced_slug_says_why_it_has_no_price(self) -> None:
        """The unpriced set is a policy decision, so it carries its own audit trail: the
        snapshot that was checked and the reason it could not corroborate a price."""
        slugs = pricing._UNPRICED_SLUGS
        assert slugs, "the committed unpriced set loaded empty — check the config file"
        for slug in sorted(slugs):
            record = pricing.unpriced_provenance(slug)
            assert record is not None, slug
            assert record.source.startswith("docs/providers/snapshots/"), (slug, record.source)
            assert (_REPO_ROOT / record.source).is_file(), (slug, record.source)
            assert record.note.strip(), (slug, "an unpriced slug must record why")

    def test_a_non_standard_rate_is_documented_in_its_own_entry(self) -> None:
        """Generic rule: any rate that is not the obvious one must explain itself in place.

        This is the invariant that stops a future editor mistaking a peak rate for a typo —
        or "correcting" it to the off-peak figure with no record of why it was peak.
        """
        table = pricing.MODEL_PRICES_USD_PER_1M
        for slug, price in table.items():
            if price.rate != "standard":
                assert price.note.strip(), (slug, f"rate={price.rate!r} with no note")

    def test_the_peak_rate_choice_is_recorded_as_a_deliberate_judgement(self) -> None:
        """The one judgement call in the table is pinned by name: the deepseek peak rate,
        chosen over the snapshot's repurposed off-peak fields because an estimate that
        systematically understates the one tripled model would defeat the alert it exists
        to make fire."""
        table = pricing.MODEL_PRICES_USD_PER_1M
        peak = {slug: price for slug, price in table.items() if price.rate == "peak"}
        assert peak, (
            f"no peak-rate entry recorded; rates seen: {sorted({p.rate for p in table.values()})}"
        )
        for slug, price in peak.items():
            assert price.source.endswith("deepseek.yaml"), (slug, price.source)
            assert "off-peak" in price.note, (slug, price.note)


class TestEstimateCostUsd:
    def test_sums_prompt_and_completion_tokens_at_the_committed_prices(self) -> None:
        # deepseek-v4-flash: 1M prompt * $0.07 + 1M completion * $0.28 = $0.35
        # gpt-5.6-luna:      2M prompt * $1.00                       = $2.00
        estimate = estimate_cost_usd(
            {
                "deepseek/deepseek-v4-flash": {
                    "calls": 1,
                    "prompt_tokens": 1_000_000,
                    "completion_tokens": 1_000_000,
                },
                "openai/gpt-5.6-luna": {
                    "calls": 1,
                    "prompt_tokens": 2_000_000,
                    "completion_tokens": 0,
                },
            }
        )
        assert estimate == pytest.approx(2.35)

    def test_returns_none_when_no_model_has_a_known_price(self) -> None:
        """Never fabricate: an unpriced run estimates nothing rather than $0.00, so the caller
        can tell "unknown" apart from "genuinely free"."""
        assert (
            estimate_cost_usd(
                {"made-up/model": {"prompt_tokens": 10_000, "completion_tokens": 5_000}}
            )
            is None
        )
        assert estimate_cost_usd({}) is None

    def test_ignores_unknown_models_but_still_sums_the_known_ones(self) -> None:
        estimate = estimate_cost_usd(
            {
                "made-up/model": {"prompt_tokens": 9_999_999, "completion_tokens": 9_999_999},
                "openai/gpt-5.6-sol": {"prompt_tokens": 1_000_000, "completion_tokens": 0},
            }
        )
        assert estimate == pytest.approx(5.00)

    def test_a_priced_model_with_zero_tokens_is_none_not_zero(self) -> None:
        """The result keys on tokens, not on model-name recognition. A priced entry that
        priced no tokens is an absence, not a $0.00 estimate."""
        assert (
            estimate_cost_usd({"openai/gpt-5.6-luna": {"prompt_tokens": 0, "completion_tokens": 0}})
            is None
        )

    @pytest.mark.parametrize(
        "usage",
        [
            {"prompt_tokens": None, "completion_tokens": "x"},
            {"prompt_tokens": -5, "completion_tokens": -5},
            {"prompt_tokens": True, "completion_tokens": False},
            {"prompt_tokens": float("nan"), "completion_tokens": float("inf")},
        ],
    )
    def test_junk_token_values_are_treated_as_zero_not_raised(self, usage: dict) -> None:
        """``by_model`` comes from an untyped fail-soft snapshot, so its values can be absent or
        junk. A telemetry estimate must never raise into the run's exit path — and junk that
        coerces to zero tokens is no estimate at all."""
        assert estimate_cost_usd({"openai/gpt-5.6-luna": usage}) is None

    def test_a_non_mapping_usage_entry_is_skipped(self) -> None:
        assert estimate_cost_usd({"openai/gpt-5.6-luna": "nope"}) is None  # type: ignore[dict-item]

    def test_a_non_mapping_input_is_none(self) -> None:
        assert estimate_cost_usd("nope") is None  # type: ignore[arg-type]
        assert estimate_cost_usd(None) is None  # type: ignore[arg-type]
