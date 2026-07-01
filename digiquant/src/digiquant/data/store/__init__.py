"""DigiQuant strategy store + shared-data-layer accessor (#1064).

Thin, Polars-friendly helpers over the dedicated DigiQuant Supabase project,
separate from the Olympus/Atlas project. See
``docs/adr/0021-digiquant-supabase-project-topology.md``.
"""

from __future__ import annotations

from digiquant.data.store.client import (
    DIGIQUANT_SERVICE_ROLE_KEY_ENV,
    DIGIQUANT_URL_ENV,
    SupabaseLike,
    build_digiquant_client,
    digiquant_credentials,
)
from digiquant.data.store.strategies import (
    PUBLIC_STRATEGY_COLUMNS,
    WriteResult,
    read_calibration,
    read_signals,
    read_strategies,
    record_trades,
    upsert_calibration,
    upsert_signal,
    upsert_strategies,
    upsert_tearsheet,
)

__all__ = [
    "DIGIQUANT_SERVICE_ROLE_KEY_ENV",
    "DIGIQUANT_URL_ENV",
    "PUBLIC_STRATEGY_COLUMNS",
    "SupabaseLike",
    "WriteResult",
    "build_digiquant_client",
    "digiquant_credentials",
    "read_calibration",
    "read_signals",
    "read_strategies",
    "record_trades",
    "upsert_calibration",
    "upsert_signal",
    "upsert_strategies",
    "upsert_tearsheet",
]
