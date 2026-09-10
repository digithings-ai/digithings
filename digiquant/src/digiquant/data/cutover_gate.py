"""Post-cutover database size gate for the R2 market-data cutover (#3780).

PASS = ``pg_database_size`` total <= ``POST_CUTOVER_SIZE_GATE_MB`` after
migration 122 drops ``price_history`` + ``price_technicals``.

Derivation (spec §7.4, ruling 2026-09-09): 512MB measured 2026-09-09 minus
~48MB deferred documents-vacuum minus ~172MB price tables = ~292MB
projected + margin → 320MB. ``macro_series_observations`` (~104MB) stays
per the carve-out, so the gate reads the database total only — never a
per-table macro figure.
"""

from __future__ import annotations

POST_CUTOVER_SIZE_GATE_MB = 320
POST_CUTOVER_SIZE_GATE_BYTES = POST_CUTOVER_SIZE_GATE_MB * 1024 * 1024


def cutover_size_gate_passes(size_bytes: int) -> bool:
    """True when a ``pg_database_size`` byte count is within the budget."""
    return size_bytes <= POST_CUTOVER_SIZE_GATE_BYTES
