"""Migration 127 drop pin + runtime straggler inventory (#4053 T5).

`127_drop_market_data_tables.sql` drops the two views (`price_history_tickers`,
`public_price_latest`) and the two tables (`price_history`, `price_technicals`).
Every market read must go through the R2 seam (or the live fetch); a
reintroduced Supabase reference means the rollback-by-flag era was restored,
which the drop ended (rollback is restore-from-generation + replay).

Two pins:

1. ``test_no_unaccounted_runtime_references`` — every quoted relation literal
   (or raw SQL reference) in the runtime tree must be listed in
   :data:`ACCOUNTED` with its exact count and a disposition. A new reference,
   or a count change in an inventoried file, fails until it is re-accounted.
2. ``test_no_unaccounted_table_access`` — the stricter subset: actual
   ``.table(...)`` / ``.from_(...)`` / ``.from(...)`` accesses must match
   :data:`TABLE_CALLS` exactly. Turning an identifier-only mention into a real
   read keeps the count in (1) the same but fails this pin.

``get_price_technicals`` is scrubbed before matching (the reader's own name,
not a table reference) — same convention as ``tests/dq/research/test_r2_only``.
"""

from __future__ import annotations

import re
import tomllib
from pathlib import Path

import pytest

pytestmark = pytest.mark.unit

REPO_ROOT = Path(__file__).resolve().parents[2]
MIGRATION = REPO_ROOT / "digiquant" / "supabase" / "migrations" / "127_drop_market_data_tables.sql"
WRANGLER = REPO_ROOT / "cloudflare" / "digithings-stack-cloudflare" / "wrangler.toml"

# Runtime tree only: tests, docs, historical migrations, openwiki and worktrees
# are out of scope (tests legitimately seed the retired shapes; migrations are
# the historical record).
RUNTIME_ROOTS: tuple[str, ...] = (
    "digiquant/src",
    "digiquant/scripts",
    "scripts",
    "digigraph/src",
    "digibase/src",
    "digisearch/src",
    "digikey/src",
    "digismith/src",
    "digiclaw/src",
    "digivault/src",
    ".github/workflows",
    "cloudflare/dashboard/lib",
    "cloudflare/digiquant-web/lib",
    "cloudflare/digithings-stack-cloudflare/src",
)
_SUFFIXES = frozenset(
    {".py", ".ts", ".tsx", ".js", ".jsx", ".mjs", ".sh", ".sql", ".json", ".yml", ".yaml"}
)
_RELATIONS = r"(price_history|price_technicals|price_history_tickers|public_price_latest)"
_LITERAL_RE = re.compile(rf"""["']{_RELATIONS}["']""")
_SQL_RE = re.compile(
    rf"\b(?:FROM|INTO|UPDATE|JOIN|TABLE)\s+(?:public\.)?{_RELATIONS}\b", re.IGNORECASE
)
_TABLE_CALL_RE = re.compile(
    rf"""\.(?:table|from_?)\(\s*(?:["']{_RELATIONS}["']|_(?:PRICE_HISTORY|PRICE_TECHNICALS))"""
)
_SCRUB = ("get_price_technicals",)

# Every runtime file with a quoted relation literal / raw-SQL reference after
# T1-T5, with the exact hit count and why it may remain. None of these is a live
# read under the production flag (`DIGIQUANT_MARKET_DATA_BACKEND=r2` in
# .github/digiquant-pipeline.yml): the table bodies sit in the retired
# `r2_backend_enabled()` else branch (or are unreachable legacy/writer/one-shot
# paths), and migration 127 makes the Supabase leg permanently dead.
ACCOUNTED: dict[str, tuple[int, str]] = {
    "digiquant/src/digiquant/cli/prices.py": (
        3,
        "writer status echoes; --supabase writes refuse under r2 and are retired by 127",
    ),
    "digiquant/src/digiquant/data/prices/refresh.py": (
        1,
        "gated recompute body (flag-off); retired by 127",
    ),
    "digiquant/src/digiquant/data/prices/supabase_writer.py": (
        10,
        "writer module body; cannot succeed post-127, kept flag-off (header retired)",
    ),
    "digiquant/src/digiquant/portfolio/h9_cost_evidence.py": (2, "gated body constants (_PRICE_*)"),
    "digiquant/src/digiquant/portfolio/phases/phase7e_risk_sizing.py": (1, "gated body"),
    "digiquant/src/digiquant/portfolio/portfolio_materialize.py": (
        3,
        "legacy off-daily path: 1 gated body + 2 args to the legacy _latest_values",
    ),
    "digiquant/src/digiquant/portfolio/risk_policy.py": (
        1,
        "CovarianceSnapshot.source_table provenance label — not a read",
    ),
    "digiquant/src/digiquant/portfolio/sizing.py": (2, "docstring/comment mention"),
    "digiquant/src/digiquant/portfolio/writers/commit_io.py": (
        5,
        "1 gated body + 2 R2 dispatch keys + 2 R2-branch helper args",
    ),
    "digiquant/src/digiquant/portfolio/writers/ledger_io.py": (1, "gated body constant"),
    "digiquant/src/digiquant/portfolio/writers/opening_snapshot.py": (1, "gated body"),
    "digiquant/src/digiquant/research/attribution.py": (1, "docstring mention"),
    "digiquant/src/digiquant/research/data/queries.py": (
        12,
        "5 gated bodies + R2 envelope keys + MARKET_TABLES_REMOVED refusal tuple",
    ),
    "digiquant/src/digiquant/research/forecast_outcomes.py": (1, "gated body"),
    "digiquant/src/digiquant/research/phases/preflight.py": (
        1,
        "market_context envelope key (R2 path) — not a table read",
    ),
    "digiquant/src/digiquant/research/supabase_io.py": (4, "gated bodies"),
    "digiquant/src/digiquant/research/testing/simulator.py": (
        4,
        "canned test-seed payload keys (runtime module, test-only usage)",
    ),
    "scripts/backfill_market_data_r2.py": (1, "spent one-shot SQL; header retired by 127"),
    "scripts/preload-history.py": (1, "spent writer script; header retired by 127"),
}

# Actual table-access calls that may remain: every one sits in a retired / gated
# body. Path -> count.
TABLE_CALLS: dict[str, int] = {
    "digiquant/src/digiquant/data/prices/refresh.py": 1,
    "digiquant/src/digiquant/data/prices/supabase_writer.py": 2,
    "digiquant/src/digiquant/portfolio/h9_cost_evidence.py": 3,
    "digiquant/src/digiquant/portfolio/phases/phase7e_risk_sizing.py": 1,
    "digiquant/src/digiquant/portfolio/portfolio_materialize.py": 1,
    "digiquant/src/digiquant/portfolio/writers/commit_io.py": 1,
    "digiquant/src/digiquant/portfolio/writers/ledger_io.py": 1,
    "digiquant/src/digiquant/portfolio/writers/opening_snapshot.py": 1,
    "digiquant/src/digiquant/research/data/queries.py": 5,
    "digiquant/src/digiquant/research/forecast_outcomes.py": 1,
    "digiquant/src/digiquant/research/supabase_io.py": 4,
    "scripts/preload-history.py": 1,
}

# Surfaces that must stay free of any quoted relation literal / table access /
# raw-SQL reference: the T1-T4 migrated scripts + the T5 cleanups (workflows,
# dashboard types, MCP tools, digiquant-web). Docstring narration is allowed
# elsewhere, not here.
CLEAN_FILES: tuple[str, ...] = (
    ".github/workflows/pipeline-digiquant-prices.yml",
    ".github/workflows/pipeline-research-metrics.yml",
    "cloudflare/dashboard/lib/database.types.ts",
    "cloudflare/dashboard/lib/queries.ts",
    "cloudflare/dashboard/lib/types.ts",
    "cloudflare/digiquant-web/lib/live/market-data.ts",
    "digiquant/src/digiquant/mcp_server.py",
    "digiquant/scripts/research/backfill_context.py",
    "digiquant/scripts/research/backfill_execution_prices.py",
    "digiquant/scripts/research/execute_at_open.py",
    "digiquant/scripts/research/fill-entry-prices.py",
    "digiquant/scripts/research/finalize_period_accounting.py",
    "digiquant/scripts/research/position_entry_from_events.py",
    "digiquant/scripts/research/refresh_attribution.py",
    "digiquant/scripts/research/refresh_performance_metrics.py",
    "digiquant/scripts/research/verify_nav_replay.py",
)


def _is_excluded(path: Path) -> bool:
    name = path.name
    return (
        name.startswith("test_")
        or name.endswith(".test.ts")
        or name.endswith(".test.tsx")
        or name == "conftest.py"
    )


def _scrubbed(text: str) -> str:
    for token in _SCRUB:
        text = text.replace(token, "")
    return text


def _scan(pattern: re.Pattern[str]) -> dict[str, int]:
    counts: dict[str, int] = {}
    for root in RUNTIME_ROOTS:
        base = REPO_ROOT / root
        if not base.exists():
            continue
        for path in sorted(base.rglob("*")):
            if not path.is_file() or path.suffix not in _SUFFIXES or _is_excluded(path):
                continue
            hits = pattern.findall(_scrubbed(path.read_text(encoding="utf-8", errors="replace")))
            if hits:
                counts[str(path.relative_to(REPO_ROOT))] = len(hits)
    return counts


def _scan_references() -> dict[str, int]:
    counts = _scan(_LITERAL_RE)
    for path, count in _scan(_SQL_RE).items():
        counts[path] = counts.get(path, 0) + count
    return counts


def _diff(found: dict[str, int], expected: dict[str, int]) -> str:
    lines: list[str] = []
    for path in sorted(set(found) | set(expected)):
        got = found.get(path)
        want = expected.get(path)
        if got != want:
            lines.append(f"  {path}: found={got} expected={want}")
    return "\n".join(lines) or "  (none)"


def test_migration_127_file_content() -> None:
    assert MIGRATION.is_file(), f"missing {MIGRATION.relative_to(REPO_ROOT)}"
    sql = MIGRATION.read_text(encoding="utf-8")
    statements = [
        "DROP VIEW IF EXISTS public.price_history_tickers;",
        "DROP VIEW IF EXISTS public.public_price_latest;",
        "DROP TABLE IF EXISTS price_history;",
        "DROP TABLE IF EXISTS price_technicals;",
    ]
    positions = [sql.index(s) for s in statements]
    assert positions == sorted(positions), "views must drop before tables (dependency order)"
    for kept in ("macro_series_observations", "trading_calendar", "prices_live"):
        assert f"DROP TABLE IF EXISTS {kept}" not in sql
        assert f"DROP VIEW IF EXISTS public.{kept}" not in sql


def test_stack_wrangler_pins_r2_market_data_backend() -> None:
    """The hosted MCP container must receive the R2 flag from the stack `[vars]`.

    `src/index.ts` forwards `DIGIQUANT_MARKET_DATA_BACKEND` verbatim
    (`?? ""`), so the stack Worker's `[vars]` is what keeps the drop-relevant
    host off the Supabase legs 127 removes. An edit that removes or changes
    this pin restores the flag-off behavior on the hosted container.
    """
    assert WRANGLER.is_file(), f"missing {WRANGLER.relative_to(REPO_ROOT)}"
    config = tomllib.loads(WRANGLER.read_text(encoding="utf-8"))
    assert config.get("vars", {}).get("DIGIQUANT_MARKET_DATA_BACKEND") == "r2"


def test_no_unaccounted_runtime_references() -> None:
    found = _scan_references()
    expected = {path: count for path, (count, _) in ACCOUNTED.items()}
    assert found == expected, (
        "runtime references to the dropped relations changed — re-account each one "
        "(new reader = fix or retire, never silent):\n" + _diff(found, expected)
    )


def test_no_unaccounted_table_access() -> None:
    found = _scan(_TABLE_CALL_RE)
    assert found == TABLE_CALLS, (
        "runtime table accesses to the dropped relations changed — every access must be a "
        "retired/gated body listed in TABLE_CALLS:\n" + _diff(found, TABLE_CALLS)
    )


def test_clean_surfaces_have_no_dropped_relation() -> None:
    patterns = (_LITERAL_RE, _SQL_RE, _TABLE_CALL_RE)
    offenders: list[str] = []
    for rel in CLEAN_FILES:
        path = REPO_ROOT / rel
        assert path.is_file(), f"missing pinned clean file: {rel}"
        text = _scrubbed(path.read_text(encoding="utf-8", errors="replace"))
        if any(pattern.search(text) for pattern in patterns):
            offenders.append(rel)
    assert not offenders, f"dropped-relation references reappeared in: {offenders}"
