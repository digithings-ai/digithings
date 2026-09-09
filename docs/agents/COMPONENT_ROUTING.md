# Component routing

When editing paths under **Prefix**, read the **Doc** row first, then run **Tests** when you change behavior.

| Prefix | Agent Guide | Architecture Doc | Service port (Compose) | Tests (examples) |
|--------|-------------|-----------------|-------------------------|------------------|
| `digigraph/` | [digigraph/AGENTS.md](../../digigraph/AGENTS.md) | [digigraph/ARCHITECTURE.md](../../digigraph/ARCHITECTURE.md) | 8000 | `pytest tests/dg/ tests/contracts/ -m unit -v --tb=short` (`agents.yml` / `test-digigraph.yml`) |
| `digiquant/` | [digiquant/AGENTS.md](../../digiquant/AGENTS.md) | [digiquant/ARCHITECTURE.md](../../digiquant/ARCHITECTURE.md) | 8001 | `pytest tests/dq/ -m unit -v --tb=short` |
| `digisearch/` | [digisearch/AGENTS.md](../../digisearch/AGENTS.md) | [digisearch/ARCHITECTURE.md](../../digisearch/ARCHITECTURE.md) | 8002 | `pytest tests/ds/ -m unit -v --tb=short` |
| `digiclaw/` | [digiclaw/AGENTS.md](../../digiclaw/AGENTS.md) | [digiclaw/ARCHITECTURE.md](../../digiclaw/ARCHITECTURE.md) | — (heartbeat profile) | `pytest tests/dc/ -m unit -v --tb=short` |
| `digismith/` | [digismith/AGENTS.md](../../digismith/AGENTS.md) | [digismith/ARCHITECTURE.md](../../digismith/ARCHITECTURE.md) | 8003 | `pytest tests/dsm/ -m unit -v --tb=short` |
| `digikey/` | [digikey/AGENTS.md](../../digikey/AGENTS.md) | [digikey/ARCHITECTURE.md](../../digikey/ARCHITECTURE.md) | 8005 | `pytest tests/dk/ -m unit -v --tb=short` |
| `digibase/` | [digibase/AGENTS.md](../../digibase/AGENTS.md) | [digibase/ARCHITECTURE.md](../../digibase/ARCHITECTURE.md) | TBD (library today) | `pytest tests/db tests/integration/test_request_id_hops.py -m unit -v --tb=short` |
| `digiskills/` | [digiskills/AGENTS.md](../../digiskills/AGENTS.md) | [digiskills/ARCHITECTURE.md](../../digiskills/ARCHITECTURE.md) | — (library) | `pytest tests/dsk/ -m unit -v --tb=short` |
| `digichat/` | [frontend/digichat/AGENTS.md](../../frontend/digichat/AGENTS.md) | [frontend/digichat/ARCHITECTURE.md](../../frontend/digichat/ARCHITECTURE.md) | 3005 (profile) | `npm run test --workspace digichat` |
| `frontend/dashboard/` | — | [frontend/dashboard/README.md](../../frontend/dashboard/README.md) | static export | `cd frontend/dashboard && npm run lint && npm run test && npm run build` (not in `make test-unit`; see `test-dashboard.yml`) |
| `website/` | [AGENTS.md](../../AGENTS.md) (starfield note) | — | static | manual / visual |
| `config/` | — | [config/MODELS.md](../../config/MODELS.md) | LiteLLM 4000 | stack integration |
| `tests/fixtures/` | — | — | — | Shared doubles (e.g. `FakeSupabaseClient` in `fake_supabase.py`) |
| `tests/contracts/` | — | — | — | Cross-service HTTP surface (`test_cross_service_surface.py` — CORS/`/healthz`/`/metrics`; included in digigraph CI) |

Canonical per-component commands live in `agents.yml` `components[].test_cmd` and must match the corresponding `test-*.yml` workflow (#1182).

**Architecture cross-cutting:** [ARCHITECTURE.md](../../ARCHITECTURE.md) for ports, auth, and MCP topology.

**Rules file:** every component has `AGENTS.md` (agent guide + pre-flight checklist) and `ARCHITECTURE.md` (technical reference) — read both under the prefix you touch.
