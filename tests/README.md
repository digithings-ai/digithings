# Digi Ecosystem – Testing

Production-grade test layout for Phase 0+. See CONTRIBUTING.md for requirements.

## Layout

- **`tests/`** (root) – All tests.
  - **`tests/dq/`** – Unit + API tests for DigiQuant (models, backtest, data, optimize, export, pipeline, brokers, FastAPI). Phase 2 complete.
  - **`tests/dg/`** – Unit + API tests for DigiGraph (models, workflow, graph, LLM, FastAPI).
  - **`tests/dc/`** – Unit tests for DigiClaw (audit). Phase 3.
  - **`tests/test_e2e.py`** – E2E tests (require stack: `docker compose up` or local servers).

## Markers

| Marker        | Meaning |
|---------------|--------|
| `unit`        | No network, no Docker. Safe to run anywhere. |
| `integration` | Uses HTTP (TestClient or live server). |
| `e2e`         | Full stack: DigiGraph + DigiQuant must be up (LiteLLM checked on **127.0.0.1:4000** or **`LITELLM_URL`**). |
| `slow`        | Slow tests (e.g. full Nautilus backtest). |

## Run tests

From **repo root** (recommended):

```bash
# All unit tests (no stack required)
pytest -m unit -v

# All tests except e2e (no Docker required)
pytest -m "not e2e" -v

# E2E only (start stack first)
docker compose up -d
pytest -v -m e2e

# Full suite (e2e will skip if stack not up)
pytest -v
```

Per package:

```bash
# DigiQuant only
pytest tests/dq -v

# DigiGraph only
pytest tests/dg -v
```

## E2E

1. Start the stack:
   ```bash
   docker compose up -d
   ```
2. Wait for health (or use `docker compose ps`).
3. Run e2e:
   ```bash
   pytest -v -m e2e
   ```
4. Or use env to point at existing servers:
   ```bash
   export DIGIQUANT_URL=http://127.0.0.1:8001
   export DIGIGRAPH_URL=http://127.0.0.1:8000
   pytest -v -m e2e
   ```

If the stack is not up, e2e tests are **skipped** (no failure).

## CI

Per-component workflows live under `.github/workflows/` and are orchestrated by `ci.yml`:

| Job | Workflow | Notes |
|-----|----------|-------|
| Component tests | `test-digibase.yml`, `test-digikey.yml`, … | Path-filtered; callable via `workflow_call` |
| Ruff + scripts | `ci.yml` → `ruff-and-scripts` | Baseline, contracts, integration hops |
| Score gate | `test-score.yml` | Heuristic diff scan via `scripts/score.py` |
| Nautilus smoke | `test-nautilus.yml` | Linux `digiquant[nautilus]` parser tests |
| Olympus | `test-olympus.yml` | Vitest + static export build (`frontend/olympus/`) |
| Stack smoke | `smoke-stack.yml` | Nightly/manual Compose `/healthz` (REM-128) |
| E2E contract | `test-e2e.yml` → `ci.yml` | `test_e2e_contract.py` without full stack |
| E2E stack | `test-e2e.yml` on `develop` | `pytest -m e2e`; needs `E2E_BEARER_TOKEN` |
| Pandas boundary | `ci.yml` → `ruff-and-scripts` | `scripts/check_pandas_boundary.sh` |

Run locally before push:

```bash
make test-unit
make test-baseline
python3 scripts/score.py
python3 scripts/agents_init.py --check
```
