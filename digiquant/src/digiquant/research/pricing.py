"""Token-derived USD estimates for the house model slugs (#4596).

The house upstream reports no per-call cost, so ``digigraph.usage`` collapses "unknown" to
``0.0`` and ``digiquant.research.diagnostics``'s ``est_cost_usd`` read ``$0`` on every run —
the spend alert in :mod:`digiquant.research.telemetry` could never fire. This module supplies
the fallback: a small, committed per-model price table and :func:`estimate_cost_usd`, which
sums the tokens actually recorded per model at those prices.

**The table is committed config, not code (#5029).** The prices and their provenance live in
``config/digiquant-model-prices.json`` — :func:`load_price_table` reads it (mtime-cached,
fail-soft), so no provider model id is a string literal in this module and a price is edited
in a data file rather than in source. ``DIGI_CONFIG_PATH`` overrides the directory, exactly as
it does for ``digigraph.model_config``; unset, it resolves against the repo root and falls
back to the CWD-relative ``config/`` the rest of the stack uses.

**Honesty rules.** The table is deliberately tiny and hand-maintained — it is not a live
feed. It prices only the house slugs listed in ``config/digiquant_models.yaml`` and only
those whose price the repo's own committed snapshot corroborates; :func:`estimate_cost_usd`
returns ``None`` when no tokens were priced rather than fabricating ``$0.00``, so "unpriced"
and "genuinely free" stay distinguishable. Unknown models are ignored, not guessed.

**Provenance travels with the numbers.** Each entry in the config file carries the
``docs/providers/snapshots/<provider>.yaml`` it was taken verbatim from, that snapshot's
``last_checked`` date, and — where the committed rate is not the obvious one — the ``rate``
and a ``note`` saying why. That travels onto :class:`ModelPrice`, so the audit trail is
readable from the parsed table and not only by opening the JSON. A price entry without a
``source`` is refused: an uncitable number is the failure this module exists to prevent. A
slug with no price is recorded in the config's ``unpriced_slugs`` with the snapshot that was
checked and why it could not corroborate one — see :func:`unpriced_provenance`. The
"snapshot corroborates the table" direction is enforced from the other side by
``tests/dq/research/test_pricing.py``, which re-derives the snapshots and fails on a mismatch.

**Failing soft, loudly.** This module runs on a telemetry path that must never break a chain
run, so a missing, unreadable or malformed config file yields an *empty* table and a warning
rather than an exception. An empty table means :func:`estimate_cost_usd` returns ``None``
and the caller falls back to the provider's own ``0.0`` — the pre-#4596 behaviour — so the
warning is the signal that spend has gone unmeasured, and it is a warning rather than a
``logger.debug`` for that reason. A single malformed *entry* is dropped by name and the rest
of the table still loads, because one bad row must not under-report every other model's spend.

**Scope.** Prompt + completion tokens only. Cached prompt tokens are billed at the full
prompt rate — cache-hit discounts are provider- and model-specific and not always reported,
so this is a deliberate upper bound rather than a fabricated discount. Prices are USD per
1,000,000 tokens; :func:`estimate_cost_usd` rounds to 6 dp, matching ``cost_usd``.
"""

from __future__ import annotations

import json
import logging
import math
import os
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path
from types import MappingProxyType
from typing import Any

logger = logging.getLogger(__name__)

_CONFIG_FILENAME = "digiquant-model-prices.json"
_SOURCE_PREFIX = "docs/providers/snapshots/"
_STANDARD_RATE = "standard"

# ``digiquant/src/digiquant/research/pricing.py`` -> repo root. Only used when
# ``DIGI_CONFIG_PATH`` is unset, so a wrong CWD cannot silently empty the table; the
# container layout (``/app/src/digiquant/...``) resolves to ``/``, where the file is absent,
# which is the same fail-soft-empty outcome an explicit path would give.
_REPO_ROOT = Path(__file__).resolve().parents[4]


@dataclass(frozen=True)
class ModelPrice:
    """USD per 1,000,000 prompt / completion tokens for one model slug.

    The trailing fields are the provenance carried from the config file — ``source`` names the
    committed snapshot the two numbers were taken verbatim from, ``snapshot_last_checked`` is
    that snapshot's own date, and ``rate`` / ``note`` record a rate that is not the obvious
    one. They default to empty/``"standard"`` so a two-argument construction stays valid.
    """

    prompt_usd_per_1m: float
    completion_usd_per_1m: float
    source: str = ""
    snapshot_last_checked: str = ""
    rate: str = _STANDARD_RATE
    note: str = ""


@dataclass(frozen=True)
class UnpricedModel:
    """A house slug with no committed price, and the snapshot that was checked for one."""

    source: str
    note: str


@dataclass(frozen=True)
class _PriceTable:
    """Parsed config file: the priced rows, the unpriced slugs, and where they came from."""

    path: Path
    prices: Mapping[str, ModelPrice]
    unpriced: Mapping[str, UnpricedModel]


_EMPTY_TABLE = _PriceTable(
    path=Path(_CONFIG_FILENAME),
    prices={},
    unpriced={},
)

# (resolved path, mtime) -> parsed table. The mtime is what makes an edited config file take
# effect without a restart; the path is in the key because DIGI_CONFIG_PATH can move it.
_prices_cache: tuple[str, float, _PriceTable] | None = None

_CONFIG_LOAD_ERRORS = (OSError, ValueError)


def _config_path() -> Path:
    """Where the price config lives.

    An explicit ``DIGI_CONFIG_PATH`` is authoritative and gets no fallback — an operator (or a
    test) that named a directory asked for *that* directory, and quietly reading somewhere
    else would hide a wrong setting. With it unset the repo root is preferred over the
    CWD-relative ``config/`` that ``digigraph.model_config`` reads, so the table does not
    depend on the process's working directory.
    """
    override = (os.environ.get("DIGI_CONFIG_PATH") or "").strip()
    if override:
        return Path(override) / _CONFIG_FILENAME
    repo_root_config = _REPO_ROOT / "config" / _CONFIG_FILENAME
    if repo_root_config.exists():
        return repo_root_config
    return Path("config") / _CONFIG_FILENAME


def _positive_number(value: object) -> float | None:
    """*value* as a strictly positive finite float, or ``None`` if it is not one."""
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    number = float(value)
    return number if math.isfinite(number) and number > 0 else None


def _source_path(value: object) -> str | None:
    """*value* as a committed-snapshot source path, or ``None`` if it is not one.

    An uncitable row is refused rather than priced: the whole reason this table can be trusted
    is that every number names the snapshot it came from, so a row without one has no claim
    to be believed.
    """
    if not isinstance(value, str) or not value.startswith(_SOURCE_PREFIX):
        return None
    return value


def _text(value: object) -> str:
    """*value* as a stripped string; anything else (including ``None``) reads as empty."""
    return value.strip() if isinstance(value, str) else ""


def _parse_price(slug: str, raw: object) -> ModelPrice | None:
    """One ``prices_usd_per_1m`` entry, or ``None`` when it is malformed."""
    if not isinstance(raw, Mapping):
        logger.warning("pricing: %s is not an object — dropped from the price table", slug)
        return None
    source = _source_path(raw.get("source"))
    if source is None:
        logger.warning(
            "pricing: %s has no %s* source — dropped; an uncitable price is not a price",
            slug,
            _SOURCE_PREFIX,
        )
        return None
    prompt = _positive_number(raw.get("prompt_usd_per_1m"))
    completion = _positive_number(raw.get("completion_usd_per_1m"))
    if prompt is None or completion is None:
        logger.warning(
            "pricing: %s needs two positive numbers, got %r / %r — dropped",
            slug,
            raw.get("prompt_usd_per_1m"),
            raw.get("completion_usd_per_1m"),
        )
        return None
    return ModelPrice(
        prompt_usd_per_1m=prompt,
        completion_usd_per_1m=completion,
        source=source,
        snapshot_last_checked=_text(raw.get("snapshot_last_checked")),
        rate=_text(raw.get("rate")) or _STANDARD_RATE,
        note=_text(raw.get("note")),
    )


def _parse_unpriced(slug: str, raw: object) -> UnpricedModel | None:
    """One ``unpriced_slugs`` entry, or ``None`` when it is malformed."""
    if not isinstance(raw, Mapping):
        logger.warning("pricing: unpriced %s is not an object — dropped", slug)
        return None
    source = _source_path(raw.get("source"))
    if source is None:
        logger.warning(
            "pricing: unpriced %s has no %s* source — dropped; an unpriced row must record "
            "the snapshot that was checked",
            slug,
            _SOURCE_PREFIX,
        )
        return None
    return UnpricedModel(source=source, note=_text(raw.get("note")))


def _parse_table(raw: object, path: Path) -> _PriceTable:
    """Build the table from a decoded config document, skipping malformed entries by name."""
    if not isinstance(raw, Mapping):
        logger.warning("%s: expected a JSON object at the top level — pricing nothing", path)
        return _PriceTable(path=path, prices={}, unpriced={})

    prices: dict[str, ModelPrice] = {}
    for slug, entry in (raw.get("prices_usd_per_1m") or {}).items():
        price = _parse_price(slug, entry)
        if price is not None:
            prices[slug] = price

    unpriced: dict[str, UnpricedModel] = {}
    for slug, entry in (raw.get("unpriced_slugs") or {}).items():
        record = _parse_unpriced(slug, entry)
        if record is not None:
            unpriced[slug] = record

    if not prices:
        logger.warning("%s: no usable price entries — every model will read as unpriced", path)
    return _PriceTable(path=path, prices=prices, unpriced=unpriced)


def _load_price_table() -> _PriceTable:
    """Read the config file, reusing the parsed table while its mtime is unchanged.

    Not cached when the file is missing: a later read must still notice it appearing (and the
    warning must not repeat per call in the meantime is not worth the state to suppress it).
    """
    global _prices_cache

    path = _config_path()
    try:
        mtime = path.stat().st_mtime
    except OSError as exc:
        logger.warning(
            "%s is unreadable (%s) — no model can be priced, so est_cost_usd falls back to "
            "the provider's own (zero) cost",
            path,
            exc,
        )
        return _EMPTY_TABLE

    if _prices_cache is not None and _prices_cache[:2] == (str(path), mtime):
        return _prices_cache[2]

    try:
        payload: Any = json.loads(path.read_text(encoding="utf-8"))
    except _CONFIG_LOAD_ERRORS as exc:
        logger.warning("%s could not be parsed (%s) — pricing nothing", path, exc)
        return _EMPTY_TABLE

    table = _parse_table(payload, path)
    _prices_cache = (str(path), mtime, table)
    return table


def load_price_table() -> Mapping[str, ModelPrice]:
    """The committed prices, keyed by house slug. Empty when the config file is unusable."""
    return _load_price_table().prices


def load_unpriced() -> Mapping[str, UnpricedModel]:
    """The house slugs deliberately left unpriced, with the snapshot checked for each."""
    return _load_price_table().unpriced


def unpriced_provenance(model: str) -> UnpricedModel | None:
    """Why *model* has no committed price, or ``None`` when it is not recorded as unpriced."""
    return load_unpriced().get(model)


def price_for(model: str) -> ModelPrice | None:
    """The committed price for *model*, or ``None`` when it is not in the table."""
    return load_price_table().get(model)


def _nonnegative_int(value: object) -> int:
    """Coerce a snapshot token count to a non-negative int; junk and bools become 0."""
    if isinstance(value, bool):
        return 0
    if isinstance(value, int):
        return max(value, 0)
    if isinstance(value, float) and math.isfinite(value):
        return max(int(value), 0)
    return 0


def estimate_cost_usd(by_model: Mapping[str, Mapping[str, object]]) -> float | None:
    """Estimate the USD cost of *by_model*, or ``None`` when no tokens were priced.

    *by_model* is the per-model split from ``digigraph.usage`` — each value carries
    ``prompt_tokens`` / ``completion_tokens``. Only models with a committed price contribute;
    unknown models are ignored, never counted as ``0``. The result keys on **tokens**, not on
    model-name recognition: an input whose only priced entries carry zero (or junk) tokens
    returns ``None``, so a priced-but-empty entry cannot masquerade as a real ``$0.00``.
    """
    if not isinstance(by_model, Mapping):
        return None
    total = 0.0
    priced_tokens = 0
    prices = load_price_table()
    for model, usage in by_model.items():
        if not isinstance(usage, Mapping):
            continue
        price = prices.get(model)
        if price is None:
            continue
        prompt = _nonnegative_int(usage.get("prompt_tokens"))
        completion = _nonnegative_int(usage.get("completion_tokens"))
        priced_tokens += prompt + completion
        total += prompt / 1_000_000 * price.prompt_usd_per_1m
        total += completion / 1_000_000 * price.completion_usd_per_1m
    if priced_tokens == 0:
        return None
    return round(total, 6)


def __getattr__(name: str) -> Any:
    """Lazily expose the two table-shaped module constants (PEP 562).

    ``MODEL_PRICES_USD_PER_1M`` and ``_UNPRICED_SLUGS`` are read on a diagnostics path that
    runs once per chain run, and their values now come from a file. Resolving them on first
    access keeps ``import digiquant`` from doing filesystem I/O at import time and keeps the
    mtime cache honest — a module-level dict would freeze whatever the file said at import.
    A ``MappingProxyType`` rather than the live dict so a caller cannot mutate the cached table.
    """
    if name == "MODEL_PRICES_USD_PER_1M":
        return MappingProxyType(load_price_table())
    if name == "_UNPRICED_SLUGS":
        return frozenset(load_unpriced())
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")


__all__ = [
    # Provided lazily by __getattr__ below, so this is a re-export rather than a binding.
    "MODEL_PRICES_USD_PER_1M",  # noqa: F822
    "ModelPrice",
    "UnpricedModel",
    "estimate_cost_usd",
    "load_price_table",
    "load_unpriced",
    "price_for",
    "unpriced_provenance",
]
