"""Post-cutover database size gate for the R2 market-data cutover (#3780).

PASS = ``pg_database_size`` total <= ``POST_CUTOVER_SIZE_GATE_MB`` after the
``price_history`` + ``price_technicals`` DROP is applied. That DROP is
**deferred** (#3951): migration 124 currently performs no drop, and the real
drop must land as a NEW numbered migration (never by re-editing 124, which the
``olympus_schema_migrations`` ledger records as applied once it runs).

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
