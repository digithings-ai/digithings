# Protected scripts (CI, smoke-test, core docs)

Scripts listed here are **do not remove or rename casually**: GitHub Actions, [`scripts/smoke-test.sh`](../../scripts/smoke-test.sh), [`RUNBOOK.md`](../../RUNBOOK.md), [`docs/ops/SCRIPTS.md`](SCRIPTS.md), or [`tests/`](../../tests/) depend on them. Use this list when pruning or moving files (see [`PRE-MIGRATION-CLEANUP.md`](PRE-MIGRATION-CLEANUP.md)).

---

## GitHub Actions (`.github/workflows/`)

### [`ci.yml`](../../.github/workflows/ci.yml)

| Step | Script / command |
|------|------------------|
| Smoke test | `bash scripts/smoke-test.sh` |
| Pytest | `python -m pytest tests/` — imports [`scripts/generate-snapshot.py`](../../scripts/generate-snapshot.py), [`scripts/update_tearsheet.py`](../../scripts/update_tearsheet.py) via [`tests/test_etl.py`](../../tests/test_etl.py) |
| DB types | `bash scripts/check-types-sync.sh` |
| Supabase migrations | `bash scripts/verify-supabase-migrations.sh` |
| Skill frontmatter | `bash scripts/validate-frontmatter.sh` |

### [`daily-price-update.yml`](../../.github/workflows/daily-price-update.yml)

| Script |
|--------|
| [`scripts/preload-history.py`](../../scripts/preload-history.py) |
| [`scripts/compute-technicals.py`](../../scripts/compute-technicals.py) |
| [`scripts/ingest_fred.py`](../../scripts/ingest_fred.py) |
| [`scripts/ingest_fx_frankfurter.py`](../../scripts/ingest_fx_frankfurter.py) |
| [`scripts/ingest_crypto_fng.py`](../../scripts/ingest_crypto_fng.py) |
| [`scripts/ingest_treasury_curve.py`](../../scripts/ingest_treasury_curve.py) |
| [`scripts/refresh_performance_metrics.py`](../../scripts/refresh_performance_metrics.py) |

### [`pipeline-meta-review.yml`](../../.github/workflows/pipeline-meta-review.yml)

| Script |
|--------|
| [`scripts/pipeline_meta_review.py`](../../scripts/pipeline_meta_review.py) |

### [`deploy.yml`](../../.github/workflows/deploy.yml)

No repo `scripts/*` invocations (frontend `npm` build only).

---

## Smoke test (`scripts/smoke-test.sh`)

All `scripts/*.sh` except `smoke-test.sh` itself are invoked with `--help` (or no-op for `check-types-sync.sh` / `validate-frontmatter.sh`).

**Python `--help` list** (must stay valid or CI breaks):

`audit_config_references.py`, `backfill_execution_prices.py`, `backfill-supabase.py`, `compute-technicals.py`, `convert_snapshot_v1.py`, `execute_at_open.py`, `fetch-macro.py`, `fetch-quotes.py`, `fill-entry-prices.py`, `generate-snapshot.py`, `ingest_crypto_fng.py`, `ingest_fred.py`, `ingest_fx_frankfurter.py`, `ingest_treasury_curve.py`, `legacy_delta_to_ops.py`, `materialize_snapshot.py`, `migrate_md_outputs_to_json.py`, `preload-history.py`, `publish_document.py`, `refresh_performance_metrics.py`, `repair_supabase_portfolio_data.py`, `retrofit_delta_requests.py`, `run_db_first.py`, `update_tearsheet.py`, `validate_artifact.py`, `validate_db_first.py`, `verify_supabase_canonical.py`.

---

## RUNBOOK + SCRIPTS.md (DB-first & market data)

Operational truth: [`RUNBOOK.md`](../../RUNBOOK.md) and [`SCRIPTS.md`](SCRIPTS.md) **DB-first publish and validation** and **Market data and metrics** tables. Treat every script named there as **protected**, including chains such as `run_db_first.py` → `sync_positions_from_rebalance.py`, `refresh_performance_metrics.py`, `execute_at_open.py`, `validate_db_first.py`, backfills, and validation helpers (`validate_pipeline_step.py`, `verify_supabase_canonical.py`, etc.).

---

## Tests (`tests/`)

| Test file | Depends on |
|-----------|------------|
| [`tests/test_etl.py`](../../tests/test_etl.py) | [`scripts/generate-snapshot.py`](../../scripts/generate-snapshot.py), [`scripts/update_tearsheet.py`](../../scripts/update_tearsheet.py) |

---

## Heuristic: “unreferenced” Python scripts

From repo root, a **fast** check (text files only: `.md`, `.yml`, `.py`, `.sh`, …) is:

```bash
python3 - <<'PY'
import os
from pathlib import Path
root = Path(".")
scan_ext = {".md", ".yml", ".yaml", ".sh", ".py", ".json", ".toml", ".txt", ".mdc"}
skip_dirs = {".git", "node_modules", ".next", "out", "dist", ".venv", "__pycache__"}
files = []
for dirpath, dirnames, filenames in os.walk(root):
    dirnames[:] = [d for d in dirnames if d not in skip_dirs and not d.startswith(".")]
    for fn in filenames:
        p = Path(dirpath) / fn
        if p.suffix in scan_ext:
            files.append(p)
# ... load text, test basename in file ...
PY
```

**Last run (pre-migration cleanup):** the only `scripts/*.py` basenames with **no** match in that text set were:

| Script | Classification |
|--------|----------------|
| `audit_activity_coverage_api.py` | **Keep** — ops / SQL companion; may be invoked ad hoc with `scripts/sql/`. |
| `backfill_pm_rebalance_and_activity.py` | **Keep** — specialized backfill; referenced implicitly by RUNBOOK-style ops. |
| `backfill_positions_entry_from_events.py` | **Keep** — migration helper. |
| `format_deliberation_transcripts_chat.py` | **Keep** — formatting utility; optional operator use. |
| `position_entry_from_events.py` | **Keep** — helper module. |
| `regen_research_deltas.py` | **Keep** — research delta regeneration. |

Apr 2026 one-off repair scripts (`repair_apr15_*`, `repair_historical_artifacts`, `fix_backfill_lineage`) were **removed** from the repo for the migration baseline (not shipped to DigiThings).

Everything else had at least one **text** reference (docs, workflows, other scripts). Treat “unreferenced” as **candidate only** — dynamic imports, subprocess calls with constructed paths, or docs outside the scanned extensions can still reference a script.

---

## `outputs/` directory

**No** GitHub workflow references `outputs/`. The directory is deprecated (gitignored if recreated); canonical state is Supabase ([`RUNBOOK.md`](../../RUNBOOK.md)).

---

## Optional layout: `scripts/legacy/`

Moving SCRIPTS.md “Migration / legacy” scripts into `scripts/legacy/` is **deferred** to a dedicated PR (update imports, [`SCRIPTS.md`](SCRIPTS.md), and smoke-test list). See [`PRE-MIGRATION-CLEANUP.md`](PRE-MIGRATION-CLEANUP.md) § P5.

---

## Skills cross-reference

See [`SKILLS-AUDIT.md`](SKILLS-AUDIT.md) for skills folders not linked from `skills/orchestrator`, `cowork/tasks`, and `AGENTS.md` (consolidation candidates only — **no** bulk deletion in pre-migration cleanup).
