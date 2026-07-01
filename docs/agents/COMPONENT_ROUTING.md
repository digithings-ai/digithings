# Component routing

When editing paths under **Prefix**, read the **Doc** row first, then run **Tests** when you change behavior.

| Prefix | Agent Guide | Architecture Doc | Service port (Compose) | Tests (examples) |
|--------|-------------|-----------------|-------------------------|------------------|
| `digigraph/` | [digigraph/AGENTS.md](../../digigraph/AGENTS.md) | [digigraph/ARCHITECTURE.md](../../digigraph/ARCHITECTURE.md) | 8000 | `pytest -m unit tests/dg* tests/integration` (adjust match) |
| `digiquant/` | [digiquant/AGENTS.md](../../digiquant/AGENTS.md) | [digiquant/ARCHITECTURE.md](../../digiquant/ARCHITECTURE.md) | 8001 | `pytest -m unit tests/dq/` |
| `digisearch/` | [digisearch/AGENTS.md](../../digisearch/AGENTS.md) | [digisearch/ARCHITECTURE.md](../../digisearch/ARCHITECTURE.md) | 8002 | `make test-unit` (includes `pytest -m unit` for `tests/ds/`) or `pytest -m unit tests/ds/` |
| `digiclaw/` | [digiclaw/AGENTS.md](../../digiclaw/AGENTS.md) | [digiclaw/ARCHITECTURE.md](../../digiclaw/ARCHITECTURE.md) | — (heartbeat profile) | `pytest -m unit` (digiclaw tests if present) |
| `digismith/` | [digismith/AGENTS.md](../../digismith/AGENTS.md) | [digismith/ARCHITECTURE.md](../../digismith/ARCHITECTURE.md) | 8003 | `pytest -m unit tests/dsm/` |
| `digikey/` | [digikey/AGENTS.md](../../digikey/AGENTS.md) | [digikey/ARCHITECTURE.md](../../digikey/ARCHITECTURE.md) | 8005 | unit tests under `tests/` for auth contracts |
| `digibase/` | [digibase/AGENTS.md](../../digibase/AGENTS.md) | [digibase/ARCHITECTURE.md](../../digibase/ARCHITECTURE.md) | TBD (library today) | `pytest -m unit` |
| `digichat/` | [frontend/digichat/AGENTS.md](../../frontend/digichat/AGENTS.md) | [frontend/digichat/ARCHITECTURE.md](../../frontend/digichat/ARCHITECTURE.md) | 3005 (profile) | `make test-unit` (Vitest) or `cd frontend/digichat && npm run test` |
| `frontend/olympus/` | — | [frontend/olympus/README.md](../../frontend/olympus/README.md) | static export | `cd frontend/olympus && npm run lint && npm run test && npm run build` (not in `make test-unit`; see `olympus-test.yml`) |
| `website/` | [AGENTS.md](../../AGENTS.md) (starfield note) | — | static | manual / visual |
| `config/` | — | [config/MODELS.md](../../config/MODELS.md) | LiteLLM 4000 | stack integration |

**Architecture cross-cutting:** [ARCHITECTURE.md](../../ARCHITECTURE.md) for ports, auth, and MCP topology.

**Rules file:** every component has `AGENTS.md` (agent guide + pre-flight checklist) and `ARCHITECTURE.md` (technical reference) — read both under the prefix you touch.
