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
| `e2e`         | Full stack: DigiGraph + DigiQuant must be up. |
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

- Run `pytest -m "not e2e"` in CI without Docker for fast feedback.
- Optionally run e2e in a job that starts `docker compose up -d` then `pytest -m e2e`.
- Note: No CI workflow is committed yet; add `.github/workflows/test.yml` when setting up CI.
