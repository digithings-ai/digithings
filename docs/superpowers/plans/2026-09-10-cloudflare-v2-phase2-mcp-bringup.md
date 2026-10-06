# Cloudflare v2 Phase 2 — first-party MCP bringup behind hosting

- Date: 2026-09-10
- Status: draft spec (no code changes; implement per sub-track)
- Repo: `/Users/chrisstefan/Code/digithings` (stay in-repo; never touch sibling repos such as zeus/apollo)
- Base: cut each worktree with `make task ISSUE=N` once the owner links the Phase 2 tracking issue; the command selects the base from `scripts/project_routing.json`. Do not start on `develop` directly.
- Order of bringup: digisearch `:8765` → digivault (stack slot `:8769`, code default stays `8766`) → digigraph (`:8766`) → digiquant (`:8767`, read scope) → digillm (`:8768`, loopback only, lowest priority)
- Naming: every digi product name in prose is lowercase (`digisearch`, `digivault`, `digigraph`, `digiquant`, `digillm`, `digichat`, `digikey`, `digibase`). Code identifiers keep their language casing (`DigiSearch`, `FastMCP`, `X-Digi-Mcp-Servers`).

## 0. Global constraints (apply to every sub-track)

- [ ] TDD: write the failing test first, watch it fail, then implement. No production code without a red test on the record.
- [ ] Lowercase digi names in prose, docs, commit messages, PR text (root `AGENTS.md` § Naming). Never `DigiSearch`/`DigiQuant` in prose.
- [ ] Update `{component}/ARCHITECTURE.md` after any interface or behavior change, plus root `ARCHITECTURE.md` § 2 (topology) and § 4 (MCP topology) when ports, tools, or hosting change.
- [ ] Gates per component (must be green before and after):
  - digisearch: `pytest tests/ -m unit -k "digisearch" -v` and `ruff check digisearch/ && ruff format --check digisearch/`
  - digivault: `pytest tests/dv -m unit` and `ruff check digivault/src tests/dv && ruff format --check digivault/src tests/dv`
  - digigraph: `pytest tests/ -m unit -k "digigraph" -v` and `ruff check digigraph/ && ruff format --check digigraph/`
  - digiquant: `pytest tests/ -m unit -k "digiquant" -v` and `ruff check digiquant/ && ruff format --check digiquant/`
  - digillm: `pytest digillm/tests -v` and `ruff check digillm/ && ruff format --check digillm/`
  - stack Worker: `npx vitest run` and `npx tsc --noEmit` in `frontend/digithings-stack-cloudflare/`
  - digichat (tenant wiring only): `npm run test` and `npm run lint` from `frontend/digichat/`
  - docs: `make doc-check` (internal markdown links)
- [ ] NEVER ship an unauthenticated `/_stack/mcp/*` forwarder on workers.dev. `frontend/digithings-stack-cloudflare/src/index.ts:14-15` documents this ban; any PR adding such a route is rejected.
- [ ] The `mcp.digithings.ai` route stays commented out (`frontend/digithings-stack-cloudflare/wrangler.toml:35-38`) until the Worker-edge digikey JWT gate (sub-track D2) lands, is tested, and passes human review.
- [ ] Never touch `sleepAfter`, `max_instances`, `instance_type`, or scaling policy. Concretely: `src/index.ts:43` (`sleepAfter = "2h"`), `src/index.ts:144` (`sleepAfter = "24h"`), `wrangler.toml:44-46` and `:66-68`. Bumping `SHARED_STACK_CONTAINER_ID` (`src/ports.ts:28`) only on explicit owner instruction with a proven stale image.
- [ ] Stay in-repo. No edits outside `/Users/chrisstefan/Code/digithings`.
- [ ] Secrets only via `wrangler secret put` on stdin. Never commit values, never write them to files. Because `CLOUDFLARE_API_TOKEN` is also wrangler's own auth variable, run every secret put as:
  `printf '%s' "$VALUE" | env -u CLOUDFLARE_API_TOKEN npx wrangler secret put NAME`
  (per the trap documented in `wrangler.toml:116-132`). Keep `CLOUDFLARE_ACCOUNT_ID` exported.
- [ ] Human gate (root `AGENTS.md`): digikey auth/JWT/crypto changes, new external network exposure, and new external service dependencies stop for human review and do not agent-merge. The edge JWT gate and the `mcp.digithings.ai` route enablement are both gated. PRs into `main` stay human-approved.

## 1. Verified current state (read 2026-09-10; do not re-derive from memory)

| Server | Code | Port | Current hosting | Auth today |
|---|---|---|---|---|
| digisearch MCP | `digisearch/src/digisearch/mcp_server.py` | 8765 | `docker-compose.yml:349-373` profile `digisearch-mcp` only; NOT in Cloudflare stack | none on MCP; HTTP API behind digikey (`digisearch:query`) |
| digivault MCP | `digivault/src/digivault/mcp_server.py` | 8766 (code default) | nowhere (no Dockerfile.mcp, no compose entry, no supervisord program) | none on MCP; HTTP API behind digikey (`digivault:read`/`digivault:write`) |
| digigraph MCP | `digigraph/src/digigraph/mcp_server.py` | 8766 (code default — collides with digivault) | nowhere | opt-in `DIGI_MCP_REQUIRE_AUTH` (`mcp_server.py:148-158`) |
| digiquant MCP | `digiquant/src/digiquant/mcp_server.py` | 8767 | dedicated `DigiQuantMcpContainer` (`wrangler.toml:61-68`, `src/index.ts:136-177`), route commented out | none (edge JWT is sub-track D2) |
| digillm MCP | `digillm/src/digillm/mcp_server.py` | 8768 | nowhere | none (loopback bind only) |

Stack facts:

- `DigiStackContainer` runs supervisord (`frontend/digithings-stack-cloudflare/container/supervisor/supervisord.conf`): redis, digikey `:8005`, digigraph `:8000`, `seed_chroma` oneshot, digivault `:8004` (HTTP), digisearch `:8002` (HTTP via `start_digisearch.sh` seed wait), litellm `:4000`. Zero MCP processes today. digisearch/digivault/litellm are loopback-only; edge ports are digigraph `:8000` + digikey `:8005`.
- Stack deploy is MANUAL: `.github/workflows/` has `deploy-digichat-cloudflare-container.yml`, `deploy-digiquant-cloudflare.yml`, `deploy-digithings-cloudflare.yml` (Pages build check), `deploy-digithings-cron.yml` — there is no `deploy-digithings-stack-*.yml`. Sub-track F specs one.
- `publish-service-images.yml` publishes 7 HTTP images (matrix rows `:71-79`); `digiquant/Dockerfile.mcp` is not published. Sub-track D specs the CI addition. digivault has `digivault/Dockerfile` (HTTP `:8004`) but no MCP image; sub-track B specs one.
- Tenant wiring: digichat deploy YAML `mcp.servers: [{id, url, label, default}]` (`frontend/digichat/src/lib/deploy-config/schema.ts:220-230`) is read BFF-side, filtered by `operatorMcpServersForUpstream` (`frontend/digichat/src/lib/deploy-config/mcp-servers.ts:182-195`), and forwarded as `X-Digi-Mcp-Servers` (`frontend/digichat/src/app/api/chat/route.ts:457`). Client projection strips URLs (`loader.test.ts:267-268` asserts `mcp.servers[0]` has no `url`). digigraph parses with `parse_mcp_servers_json` + SSRF guard `is_allowed_mcp_url` (`digigraph/src/digigraph/orchestration/mcp_client.py:158-233`) and overwrites from the BFF header (`http_api/context.py:108`, `http_api/chat_resolve.py:96`). Corpus blobs: `DIGICHAT_EMBED_TENANTS` backends carry `digisearchIndex`/`vaultPathPrefix` (`infra/digichat-release/compose.profile-a-bundle.override.yml:11`, `infra/digichat-digithings/README.md:100-101`) and the stack carries `DIGI_TENANT_CORPUS_MAP` (`wrangler.toml:175`, `src/index.ts:84-86`) — two blobs synced by comment today. Sub-track G decides unify-vs-check.
- Web search (#3853) lives on branch `task/3853-proprietary-web-search-mcp-tool--digifet`: `digisearch/src/digisearch/web_search/{__init__.py, models.py, ddgs_provider.py, searxng_provider.py, service.py, extractor.py}`, `config/searxng/settings.yml`, `digigraph/src/digigraph/orchestration/web_search_tools.py`. digifetch stays a scraping library: the branch imports only `from digifetch import HttpFetcher, RateLimiter, RetryPolicy, with_retry` (`web_search/service.py:7`) — pass-through usage, no MCP server for digifetch. Sub-track H lands it.

---

## Sub-track A — digisearch MCP `:8765` (first; unblocks RAG tools for every chatbot)

### A. Files

- `digisearch/src/digisearch/mcp_server.py` (tools + `create_mcp_with_indexes` + `run_mcp`)
- `digisearch/src/digisearch/cli.py` (`mcp` command, lines 116-124)
- `digisearch/src/digisearch/client.py` (`DigiSearch`, `as_mcp_server`)
- `digisearch/src/digisearch/core/config.py` (`DigiSearchConfig.from_env`, `get_mcp_port`)
- `digisearch/src/digisearch/server.py` (`_require_real_search_backend`, lines 64-96)
- `digisearch/ARCHITECTURE.md`, root `ARCHITECTURE.md` § 4
- `Dockerfile.digithings-stack-cloudflare`, `frontend/digithings-stack-cloudflare/container/supervisor/supervisord.conf`

### A. Interfaces (frozen unless this spec says otherwise)

- Tools stay: `digisearch_query(text, index_name?, top_k?, mode?)`, `search_strategies(...)`, `digisearch_research_turn(...)` (only with `digisearch[agent]`).
- Stub fallback stays disabled unless `DIGISEARCH_ALLOW_STUB=1` (`mcp_server.py:68-75`), which is unit-tests-only per `digisearch/AGENTS.md` (never set it in any production code path, image, compose file, supervisord program, or wrangler vars).
- Backend precedence stays exactly what `_require_real_search_backend` enforces: `CLOUDFLARE_ACCOUNT_ID`+`CLOUDFLARE_API_TOKEN` (legacy `VECTORIZE_*`/`D1_*` fallback) → Azure (`is_azure_configured()`) → Chroma (`CHROMA_PATH`/`CHROMA_HOST`) → `RuntimeError`. The MCP wiring must agree with this gate byte-for-byte, never a parallel check.

### A. Steps

- [ ] A1 (TDD red): add `tests/ds/test_mcp_wiring.py` asserting that invoking the CLI `mcp` entrypoint wiring without a configured backend fails loud (non-zero exit / `RuntimeError`, never a stub serve). Run `pytest tests/ -m unit -k "digisearch" -v` and watch the new test fail against current `cli.py:116-124` (which calls `run_mcp(port)` with no client).
- [ ] A2: fix the `mcp` command in `digisearch/src/digisearch/cli.py` to build the real client first. Replace the body of `mcp()` (lines 116-124) with:
  ```python
  @app.command()
  def mcp(
      config: Path | None = typer.Option(None, "--config", "-c"),
      port: int = typer.Option(8765, "--port", "-p"),
  ) -> None:
      """Start MCP server (real backend only; fails loud without one)."""
      from digisearch.client import DigiSearch
      from digisearch.core.config import DigiSearchConfig
      from digisearch.mcp_server import create_mcp_with_indexes, run_mcp

      cfg = DigiSearchConfig.from_config(config) if config else DigiSearchConfig.from_env()
      client: DigiSearch = DigiSearch(cfg) if config else DigiSearch()
      create_mcp_with_indexes(client)
      run_mcp(port=port)
  ```
  Then make `run_mcp` itself fail loud: at the top of `run_mcp` in `digisearch/src/digisearch/mcp_server.py` (after line 168), reuse the server startup gate rather than duplicating its logic:
  ```python
  from digisearch.server import _require_real_search_backend

  _require_real_search_backend()
  ```
  If importing `server` from `mcp_server` creates a cycle, extract the gate into `digisearch/backend_require.py` with identical precedence and call it from both `server.py:64` and `mcp_server.py:run_mcp` (keep the two call sites sharing one function — never two copies of the precedence list). Honor `DIGISEARCH_MCP_PORT` in the CLI: `port = port or int(os.environ.get("DIGISEARCH_MCP_PORT", "8765"))` is wrong when typer already defaults; instead default the option to `int(os.environ.get("DIGISEARCH_MCP_PORT", "8765"))` at import. Keep the flag winning over env by resolving inside the body:
  ```python
  import os
  port = port if port != 8765 else int(os.environ.get("DIGISEARCH_MCP_PORT", "8765"))
  ```
  Simpler and explicit: read env only when the flag was not passed. Implement via a `None` default and `port = port or int(os.environ.get("DIGISEARCH_MCP_PORT", "8765"))`.
- [ ] A3: wire `DIGISEARCH_INDEX` default from the environment (already read at `mcp_server.py:24`); no change unless A2 tests demand it. Confirm `CHROMA_PATH=/data/chroma` and `DIGISEARCH_INDEX=digithings_docs` arrive via container env (stack `wrangler.toml:170-173` already sets both; supervisord inherits Worker `envVars`).
- [ ] A4: add supervisord program for the MCP in `frontend/digithings-stack-cloudflare/container/supervisor/supervisord.conf` (loopback only, after digisearch HTTP so the seed wait is not bypassed):
  ```ini
  [program:digisearch-mcp]
  command=python -m digisearch.cli mcp --port 8765
  directory=/app
  autostart=true
  autorestart=true
  priority=45
  startsecs=3
  stdout_logfile=/var/log/supervisor/digisearch-mcp.log
  stderr_logfile=/var/log/supervisor/digisearch-mcp.err.log
  stdout_logfile_maxbytes=10MB
  stderr_logfile_maxbytes=10MB
  ```
  Priority 45 places it after `digisearch` (40) and before `litellm` (50). No new container, no port exposure in the Dockerfile (`EXPOSE 8000 8005` stays). No Worker route (constraint: no `/_stack/mcp/*`, `mcp.digithings.ai` stays off — this process is reachable only from inside the container until a per-server edge auth design lands for it as a later phase).
- [ ] A5: update `digisearch/ARCHITECTURE.md` (MCP section: CLI wiring, fail-loud gate, `:8765`, stub policy) and root `ARCHITECTURE.md` § 4 (digisearch MCP row: hosted loopback `:8765` inside `DigiStackContainer`, no public route yet).
- [ ] A6: gates: `pytest tests/ -m unit -k "digisearch" -v`, `ruff check digisearch/ && ruff format --check digisearch/`, `make doc-check`.

### A. Acceptance

- `DIGISEARCH_ALLOW_STUB=1 python -m digisearch.cli mcp --port 8765` serves tools (dev only); without the flag and without a backend (`env -u CLOUDFLARE_ACCOUNT_ID -u CLOUDFLARE_API_TOKEN -u CHROMA_PATH` and no Azure env) the command exits non-zero with the `_require_real_search_backend` message instead of serving stub results.
- `curl -s http://127.0.0.1:8765/mcp -H 'Accept: application/json'` inside the stack container returns a tool listing containing `digisearch_query` once seeded; `supervisorctl status digisearch-mcp` is `RUNNING`.
- No `DIGISEARCH_ALLOW_STUB` string in any Dockerfile, compose file, supervisord conf, or wrangler file (`grep -rn DIGISEARCH_ALLOW_STUB Dockerfile.digithings-stack-cloudflare docker-compose.yml frontend/digithings-stack-cloudflare/ | grep -v tests` returns nothing).

---

## Sub-track B — digivault MCP (stack slot `:8769`; code default stays `8766`)

Port decision (owner-confirm, default recommended): `digigraph/src/digigraph/mcp_server.py:264-273` and `digivault/src/digivault/mcp_server.py:36-44` both default to `8766`. digigraph keeps `8766` (its docstring at `mcp_server.py:9` advertises it). digivault keeps code default `8766` for standalone local use but binds stack slot `:8769` via a new `DIGIVAULT_MCP_PORT` env (parity with the `DIGILLM_MCP_PORT` pattern in `digillm/src/digillm/mcp_server.py:146`). Rationale: zero churn to local scripts, collision resolved at the deploy layer where both processes coexist.

### B. Files

- `digivault/src/digivault/mcp_server.py`, `digivault/src/digivault/tool_dispatch.py`
- NEW `digivault/Dockerfile.mcp` (repo root build context, mirroring `digiquant/Dockerfile.mcp` convention)
- `docker-compose.yml` (new `digivault-mcp` profile service), `digivault/ARCHITECTURE.md`, root `ARCHITECTURE.md` § 4

### B. Interfaces (frozen)

- Registration stays single-path via `register_mcp_tools(mcp, _open_vault)` (`tool_dispatch.py:181-260`); do not add `@mcp.tool` in `mcp_server.py` (anti-pattern per `digivault/AGENTS.md`).
- MCP-exposed set stays exactly `mcp_tool_names()` == 4 vault-local tools: `digivault_search_tag`, `digivault_backlinks`, `digivault_lint`, `digivault_create_note` (`tool_dispatch.py:47-54`). `digivault_search_notes` / `digivault_get_note` stay orchestrator-only (`RUNTIME_ONLY_TOOL_NAMES`, `tool_dispatch.py:58-63`); any test asserting otherwise must fail.
- `_open_vault` keeps failing loud on empty `DIGIVAULT_ROOT` (`mcp_server.py:25-29`).

### B. Steps

- [ ] B1 (TDD red): add `tests/dv/test_mcp_hosting.py` asserting (a) `mcp_tool_names() == {"digivault_search_tag", "digivault_backlinks", "digivault_lint", "digivault_create_note"}` and excludes `digivault_search_notes`/`digivault_get_note`; (b) `run_mcp` honors `DIGIVAULT_MCP_PORT` when set; (c) missing `DIGIVAULT_ROOT` raises `VaultError` at tool-call time (not import time). Run `pytest tests/dv -m unit` and watch (b) fail (no PORT env today).
- [ ] B2: add `DIGIVAULT_MCP_PORT` parity in `digivault/src/digivault/mcp_server.py`:
  ```python
  def run_mcp(
      transport: str = "streamable-http",
      host: str | None = None,
      port: int | None = None,
  ) -> None:
      """Run the MCP server. Default: streamable HTTP on 127.0.0.1:8766."""
      bind = host or os.environ.get("DIGIVAULT_MCP_HOST", "127.0.0.1")
      resolved = port or int(os.environ.get("DIGIVAULT_MCP_PORT", "8766"))
      mcp.settings.host = bind
      mcp.settings.port = resolved
      mcp.run(transport=transport)
  ```
  Keep the module-level `register_mcp_tools(mcp, _open_vault)` call where it is (line 33). Add a `main()` with `--host/--port/--stdio` argparse mirroring `digillm/src/digillm/mcp_server.py:141-151` so supervisord and compose have a stable entrypoint. Note: this uses the `mcp.settings` + `run(transport)` pattern — if sub-track C standardizes on constructor kwargs instead, apply the same outcome here (see C2; all five servers must end on one pattern).
- [ ] B3: NEW `digivault/Dockerfile.mcp` (build context repo root, comment header required):
  ```dockerfile
  # digivault-mcp — vault-local MCP container.
  # Build context: monorepo root (`docker build -f digivault/Dockerfile.mcp .`).
  # Serves FastMCP streamable-http via digivault.mcp_server:run_mcp on :8766
  # (compose maps/pins the stack slot :8769 where digigraph :8766 coexists).
  # Filesystem vault only (DIGIVAULT_ROOT); search_notes/get_note stay
  # orchestrator-only and are never registered here (tool_dispatch.py).
  FROM python:3.12-slim
  WORKDIR /app
  ENV PYTHONUNBUFFERED=1 \
      PYTHONDONTWRITEBYTECODE=1 \
      PIP_NO_CACHE_DIR=1
  RUN pip install --upgrade pip && pip install uv
  COPY digibase/pyproject.toml digibase/README.md ./digibase/
  COPY digibase/src ./digibase/src
  RUN uv pip install --system -e "./digibase"
  COPY digikey/pyproject.toml digikey/README.md ./digikey/
  COPY digikey/src ./digikey/src
  RUN uv pip install --system -e "./digikey"
  COPY digivault/pyproject.toml digivault/ARCHITECTURE.md ./digivault/
  COPY digivault/src ./digivault/src
  RUN uv pip install --system -e "./digivault[service]"
  ENV DIGIVAULT_MCP_HOST=0.0.0.0 DIGIVAULT_MCP_PORT=8766
  EXPOSE 8766
  CMD ["python", "-c", "from digivault.mcp_server import run_mcp; run_mcp()"]
  ```
- [ ] B4: compose entry in `docker-compose.yml` after the `digisearch-mcp` block (lines 348-373), profile `digivault-mcp`, loopback-only:
  ```yaml
  # ─── digivault MCP server (optional: run with docker compose --profile digivault-mcp up) ───
  digivault-mcp:
    build:
      context: .
      dockerfile: digivault/Dockerfile.mcp
    image: digi-digivault-mcp:latest
    container_name: digi-digivault-mcp
    profiles:
      - digivault-mcp
    ports:
      - "127.0.0.1:8769:8766"
    env_file:
      - .env
    environment:
      - PYTHONUNBUFFERED=1
      - DIGIVAULT_ROOT=${DIGIVAULT_ROOT:-/data/vault}
      - DIGIVAULT_MCP_HOST=0.0.0.0
      - DIGIVAULT_MCP_PORT=8766
    volumes:
      - digivault_data:/data/vault
  ```
  No `DIGIKEY_*` needed (vault-local tools carry no JWT check today; orchestrator-only tools stay out). Document that in the `digivault/ARCHITECTURE.md` update.
- [ ] B5: stack supervisord program (loopback, no Worker route):
  ```ini
  [program:digivault-mcp]
  command=python -c "from digivault.mcp_server import run_mcp; run_mcp(port=8769)"
  directory=/app
  autostart=true
  autorestart=true
  priority=45
  startsecs=2
  stdout_logfile=/var/log/supervisor/digivault-mcp.log
  stderr_logfile=/var/log/supervisor/digivault-mcp.err.log
  stdout_logfile_maxbytes=5MB
  stderr_logfile_maxbytes=5MB
  ```
  Requires `DIGIVAULT_ROOT=/data/vault` (already default in `wrangler.toml:171` and `src/index.ts:82`).
- [ ] B6: docs: `digivault/ARCHITECTURE.md` (tool dispatch diagram + MCP hosting: image, compose profile, stack slot `:8769`, the 4-tool boundary) and root `ARCHITECTURE.md` § 4 (new digivault MCP row).
- [ ] B7: gates: `pytest tests/dv -m unit`, `ruff check digivault/src tests/dv && ruff format --check digivault/src tests/dv`, plus `python -c "import sys, digivault; assert 'fastapi' not in sys.modules"` (import-cost guard from `digivault/AGENTS.md`).

### B. Acceptance

- `tests/dv/test_tool_dispatch.py` still passes unmodified (every tool name dispatches; discovery == `VAULT_HANDLERS` keys).
- `DIGIVAULT_ROOT=/tmp/dv-spec-probe python -m digivault.mcp_server` (after B2 `main()` lands, `python -m digivault.mcp_server --port 8769`) lists exactly 4 tools; `DIGIVAULT_ROOT=""` → tool calls return `[digivault error: DIGIVAULT_ROOT is not configured]`, process exit non-zero on startup probe.
- `docker compose --profile digivault-mcp up -d --build` → `curl -s http://127.0.0.1:8769/mcp -H 'Accept: application/json'` lists the 4 tools; `search_notes`/`get_note` absent.

---

## Sub-track C — digigraph MCP `:8766` (fix `run()` crash; LLM upstream; opt-in auth)

### C. Files

- `digigraph/src/digigraph/mcp_server.py`
- `frontend/digithings-stack-cloudflare/container/supervisor/supervisord.conf`, `Dockerfile.digithings-stack-cloudflare`
- `digigraph/ARCHITECTURE.md`, root `ARCHITECTURE.md` § 4
- `config/litellm.yaml` (read-only reference; LiteLLM itself runs at `:4000` per supervisord `litellm` program)

### C. Interfaces (frozen)

- Tools stay: `workflow`, `chat`, `thread_state`, `list_orchestrator_tools`, `list_orchestrator_tools_detailed` (`mcp_server.py:90-99`).
- `DIGI_MCP_REQUIRE_AUTH=1` gate stays fail-closed without verifier config (`mcp_server.py:148-158` + `_has_digikey_verifier_config`, lines 61-65). In the stack, set `DIGI_MCP_REQUIRE_AUTH=1` with `DIGIKEY_JWKS_URL=http://127.0.0.1:8005/.well-known/jwks.json` (already exported by `entrypoint.sh`).

### C. Steps

- [ ] C1 (repro, no fix yet): print the installed `mcp` 1.x API and reproduce the Phase 0 crash:
  ```bash
  PATH="$PWD/.venv/bin:$PATH" python -c "import inspect; from mcp.server.fastmcp import FastMCP; print(inspect.signature(FastMCP.__init__)); print(inspect.signature(FastMCP.run))"
  PATH="$PWD/.venv/bin:$PATH" python -m digigraph.mcp_server --port 8766
  ```
  Expected per the in-repo evidence: `FastMCP.run()` takes transport only (see the working pattern documented in `digiquant/src/digiquant/mcp_server.py:445-447`: "`host`/`port` go on the server — installed mcp's `run()` takes transport only"), so `digigraph/src/digigraph/mcp_server.py:273` (`mcp.run(transport=transport, host=bind, port=port)`) and the identical `digillm/src/digillm/mcp_server.py:138` call raise `TypeError`. Record the actual traceback in the PR body; if the signature differs, follow the installed signature instead of this spec's default.
- [ ] C2 (TDD red): add `tests/dg/test_mcp_run_bind.py` asserting `run_mcp` binds the expected host/port WITHOUT opening a socket (monkeypatch `FastMCP.run` / `mcp.run` and assert call args; assert `DIGIGRAPH_MCP_HOST` env is honored). Watch it fail against current `run_mcp`.
- [ ] C3: standardize all `run_mcp` implementations on ONE pattern (default: the digiquant pattern — host/port at construction, `run(transport)` only). Concrete edits:
  - `digigraph/src/digigraph/mcp_server.py:264-273`: build `FastMCP("digigraph", host=bind, port=port)` in `create_mcp_server` (thread through `host`/`port` params) and call `mcp.run(transport=transport)`.
  - `digillm/src/digillm/mcp_server.py:48,129-138`: same (construct with host/port; `run(transport=...)`).
  - `digisearch/src/digisearch/mcp_server.py:163-172`: same (replace `mcp.settings` mutation with constructor kwargs) OR keep `mcp.settings` if C1 shows the installed version supports it — either way, one pattern repo-wide, decided by C1 evidence and applied to all five (including B2 and D).
  - Keep `mcp = FastMCP("digillm", ...)` module-singleton shape where tests import it (`digillm/tests/test_mcp_server.py` must keep passing).
- [ ] C4: upstream wiring (no code change expected, verify + pin): digigraph LLM calls go through `OPENAI_API_BASE=http://127.0.0.1:4000/v1` (stack `wrangler.toml:159`, `entrypoint.sh` default). Verify the MCP `workflow`/`chat` path uses `digigraph.llm_client` (never a direct OpenAI client) and works with `DIGI_LLM_MODE=test` + Cheaper Inference overlay when `CHEAPERINFERENCE_API_KEY` is set. If the MCP process needs env the supervisord program lacks, add ONLY `OPENAI_API_BASE`/`DIGI_LLM_MODE`/`DIGI_CONFIG_PATH`/`DIGI_PROJECT_CONFIG` to the program env (all plain vars, never secrets files).
- [ ] C5: supervisord program (loopback only, no Worker route):
  ```ini
  [program:digigraph-mcp]
  command=python -m digigraph.mcp_server --port 8766
  directory=/app
  autostart=true
  autorestart=true
  priority=45
  startsecs=3
  environment=DIGI_ENABLE_THREAD_API="1",DIGI_MCP_REQUIRE_AUTH="1",DIGIKEY_JWKS_URL="http://127.0.0.1:8005/.well-known/jwks.json",OPENAI_API_BASE="http://127.0.0.1:4000/v1"
  stdout_logfile=/var/log/supervisor/digigraph-mcp.log
  stderr_logfile=/var/log/supervisor/digigraph-mcp.err.log
  stdout_logfile_maxbytes=10MB
  stderr_logfile_maxbytes=10MB
  ```
  `DIGI_ENABLE_THREAD_API=1` mirrors the `setdefault` at `mcp_server.py:103`; setting it explicitly keeps behavior identical if the module import order changes. `DIGI_MCP_REQUIRE_AUTH=1` is the opt-in from the task brief (unauthenticated localhost stays refused once verifier config exists).
- [ ] C6: docs: `digigraph/ARCHITECTURE.md` (MCP section: `run()` signature fix, `:8766`, `DIGI_MCP_REQUIRE_AUTH`, LiteLLM upstream) and root `ARCHITECTURE.md` § 4.
- [ ] C7: gates: `pytest tests/ -m unit -k "digigraph" -v`, `ruff check digigraph/ && ruff format --check digigraph/`.

### C. Acceptance

- `PATH="$PWD/.venv/bin:$PATH" python -m digigraph.mcp_server --port 8766` stays up (no `TypeError`); `tests/dg/test_mcp_run_bind.py` green.
- With `DIGI_MCP_REQUIRE_AUTH=1` and no `DIGIKEY_JWKS_URL`/`DIGIKEY_PUBLIC_KEY_PEM`, the `workflow` tool returns the disabled JSON (`mcp_server.py:152-158`); with the stack JWKS URL set, it runs.
- `chat` returns content via the in-process HTTP path; `thread_state` round-trips a known thread id.

---

## Sub-track D — digiquant MCP `:8767` read-scope (edge JWT design + CI publish)

### D. Files

- `digiquant/src/digiquant/mcp_server.py` (`READ_SCOPE_TOOLS`, `create_mcp_server`, `run_mcp`, `__main__`)
- `digiquant/Dockerfile.mcp`, `digiquant/ARCHITECTURE.md` (§ MCP hosting)
- `frontend/digithings-stack-cloudflare/{wrangler.toml,src/index.ts,src/ports.ts}`
- NEW `.github/workflows/deploy-digithings-stack-cloudflare.yml` (with F)
- `.github/workflows/publish-service-images.yml` (CI addition D4)

### D. Interfaces (frozen)

- `READ_SCOPE_TOOLS` stays exactly the 8 names at `mcp_server.py:422-433` (`digiquant_list_strategies`, `digiquant_get_price_technicals`, `digiquant_get_macro_series`, `digiquant_query_data`, `dashboard_get_policy_replay`, `dashboard_get_policy_comparison`, `dashboard_evaluate_policy_gate`, `dashboard_get_policy_gate_evaluation`). The hosted container runs `scope="read"` ONLY (`DIGIQUANT_MCP_SCOPE=read`); `full` never leaves localhost.
- Data backend default stays `supabase` (`research/data/queries.py:43-46`); `DIGIQUANT_MARKET_DATA_BACKEND=r2` opts into the versioned R2 history. Container env passes the flag through empty-by-default (`src/index.ts:152`), never flipping the library default.
- Single replica stays: `max_instances = 1` + `MCP_CONTAINER_ID = "mcp-v1"` (`ports.ts:22`, `wrangler.toml:66`) because the read path holds an in-memory 900s TTL (`mcp_server.py:28-39`).

### D. Steps

- [ ] D1 (TDD red): add `tests/dq/test_mcp_read_scope.py` asserting `create_mcp_server(scope="read")` exposes exactly `READ_SCOPE_TOOLS` (no `digiquant_run_backtest`/`digiquant_run_optimize`/`digiquant_run_pipeline`/`digiquant_export`/fetch/fit/tearsheet tools) and `scope="bogus"` raises `ValueError`. Run `pytest tests/ -m unit -k "digiquant" -v`; the exposure test should already pass (behavior exists) — the red test is the NEW container-default assertion: `DIGIQUANT_MCP_SCOPE` defaults to `read` in the hosted Dockerfile/Worker env (fails today: `Dockerfile.mcp` sets no scope, `__main__` defaults `full` at `mcp_server.py:1113-1117`).
- [ ] D2 (owner-gated, human review required): Worker-edge digikey JWT gate in `frontend/digithings-stack-cloudflare/src/index.ts` (full design in § 4 below; summary of the diff):
  - In the default `fetch()` handler's `isMcpHostname` branch (lines 268-271), before `container.fetch(request)`: extract `Authorization: Bearer <jwt>`, fetch JWKS from `https://key.digithings.ai/.well-known/jwks.json` (== `DIGIKEY_ISSUER`, `wrangler.toml:150`), cache 300s (matches `digikey/src/digikey/jwt_verify.py:24` `_DEFAULT_JWKS_CACHE_SEC`), verify RS256 + `iss` + `aud=digi-ecosystem` + `exp`, require `digiquant:backtest` in `scopes`, then forward. Missing token → 401, wrong scope → 403, JWKS unreachable/invalid → 503 (fail closed). Reject non-HTTPS `mcp.digithings.ai` requests at the edge (the route is `custom_domain`, but belt-and-braces).
  - JWKS fetch uses a Worker-cacheable `fetch` with a 5s timeout; never log tokens (mirrors `mcp_client.py:7` / `mcp-servers.ts` token discipline).
  - Add `vitest` cases in `frontend/digithings-stack-cloudflare/src/` (colocated `index.test.ts` or extend `ports.test.ts` + new `auth.test.ts`): 401/403/503 mapping, scope-present pass-through (mocked JWKS), cache hit (no second JWKS fetch), `mcp.digithings.ai` unknown-path 404 behavior unchanged.
  - Do NOT add any `/_stack/mcp/*` workers.dev forwarder (constraint). The MCP container answers ONLY on `mcp.digithings.ai`, and only after this gate merges.
- [ ] D3: flip hosted defaults to read scope (after D2 merges, same PR or immediate follow-up): `ENV DIGIQUANT_MCP_SCOPE=read` in `digiquant/Dockerfile.mcp:28`, and pass `DIGIQUANT_MCP_SCOPE: env.DIGIQUANT_MCP_SCOPE ?? "read"` in `DigiQuantMcpContainer.envVars` (`src/index.ts:151-158`) + `Env` interface entry. Local `python -m digiquant.mcp_server` keeps default `full` (explicit `--scope read` for local dashboard-chat testing).
- [ ] D4: publish the MCP image. Edit `.github/workflows/publish-service-images.yml`: add `digiquant/Dockerfile.mcp` path trigger (covered by existing `digiquant/**` glob — assert, don't duplicate), add `"digiquant-mcp"` to the `workflow_dispatch` options, and extend the matrix with a `version_from` field so the tag step reads the right pyproject:
  ```python
  all_rows = [
      # ... existing 7 rows unchanged ...
      {"service": "digiquant-mcp", "dockerfile": "digiquant/Dockerfile.mcp",
       "build_args": "", "version_from": "digiquant/pyproject.toml"},
  ]
  ```
  and in the `Read package version` step use `${{ matrix.version_from || matrix.service }}/pyproject.toml`:
  ```yaml
  ver=$(python3 -c "import tomllib,pathlib; p=pathlib.Path('${{ matrix.version_from || matrix.service }}/pyproject.toml'); print(tomllib.loads(p.read_text())['project']['version'])")
  ```
  Tags follow the file's convention: `ghcr.io/digithings-ai/digiquant-mcp:sha-<12>:latest:v<version>`. Verify with `workflow_dispatch(service=digiquant-mcp)` on the task branch before merge.
- [ ] D5: secrets (owner runs; agent specs, never executes with values): `FRED_API_KEY`, `R2_ACCOUNT_ID`, `R2_BUCKET`, `R2_ACCESS_KEY_ID`, `R2_SECRET_ACCESS_KEY` via `wrangler secret put` (with `env -u CLOUDFLARE_API_TOKEN`). Supabase path needs no new secret (default backend). Document the exact five commands in `digiquant/ARCHITECTURE.md` § MCP hosting with `$VALUE` placeholders filled only in the operator's shell history — never in the repo.
- [ ] D6: uncomment the route ONLY in the D2 gate PR after human approval:
  ```toml
  [[routes]]
  pattern = "mcp.digithings.ai"
  zone_name = "digithings.ai"
  custom_domain = true
  ```
  replacing `wrangler.toml:35-38`. Keep the HUMAN GATE comment, updated to point at the gate code.
- [ ] D7: gates: `pytest tests/ -m unit -k "digiquant" -v`, `ruff check digiquant/ && ruff format --check digiquant/`, `npx vitest run && npx tsc --noEmit` in the stack package.

### D. Acceptance

- `DIGIQUANT_MCP_SCOPE=read python -m digiquant.mcp_server --port 8767` lists exactly the 8 read tools; `--scope full` locally still lists all; unknown scope exits non-zero.
- With the route enabled + gate live: no token → 401, token without `digiquant:backtest` → 403, token with scope → tool result; JWKS outage → 503 (prove by pointing the Worker at an invalid JWKS URL in a preview deploy, never prod).
- `ghcr.io/digithings-ai/digiquant-mcp:latest` exists after the workflow runs; stack deploy pulls it (or builds `digiquant/Dockerfile.mcp` from root — state which in the deploy PR; do not mix both silently).
- R2 mode (`DIGIQUANT_MARKET_DATA_BACKEND=r2` + secrets) returns the `{"as_of","rows","stale"}` envelope; Supabase default path byte-identical to today.

---

## Sub-track E — digillm MCP `:8768` (loopback only; lowest priority; do last)

### E. Files

- `digillm/src/digillm/mcp_server.py`, `digillm/tests/test_mcp_server.py`, `digillm/ARCHITECTURE.md`

### E. Interfaces (frozen)

- Exactly 1 tool: `complete(model, messages, temperature?, max_tokens?, json_schema?)` returning `{"content","model"}` (`mcp_server.py:70-126`). `run_tools`/`structured_completion` stay library-only (lines 11-13). Provider routing follows process env (house Cheaper Inference when `CHEAPERINFERENCE_API_KEY` set); errors fail fast, no fallback (lines 15-18).

### E. Steps

- [ ] E1: apply the C3 `run()` unification to `digillm/src/digillm/mcp_server.py:48,129-138` (constructor host/port, `run(transport)` only) as part of C's PR or immediately after — never a separate signature drift. Extend `digillm/tests/test_mcp_server.py` with the same no-socket bind assertion as C2.
- [ ] E2: provider-key check (fail loud, no new auth layer): with no provider key and no `OPENAI_API_BASE` reachable, `complete` returns an MCP error naming the missing key (assert the message names `CHEAPERINFERENCE_API_KEY`/`OPENAI_API_KEY` resolution, not a bare connection refusal). No retry, no fallback.
- [ ] E3: bind loopback only: default stays `127.0.0.1:8768`; no supervisord program in the SHARED stack by default (digillm rides inside digigraph via library calls; the MCP is for trusted local clients/stdio). If a stack program is later wanted, it needs its own edge-auth design first — explicitly out of scope here. Document that in `digillm/ARCHITECTURE.md`.
- [ ] E4: gates: `pytest digillm/tests -v`, `ruff check digillm/ && ruff format --check digillm/`.

### E. Acceptance

- `python -m digillm.mcp_server --help` works; `--stdio` starts without binding a port; streamable-http defaults to `127.0.0.1:8768`.
- `complete` with an empty `messages` list raises `ValueError` (existing `_coerce_messages` behavior, now pinned by test).

---

## Sub-track F — stack hosting + deploy CI (manual today → manual-but-buttoned)

### F. Files

- NEW `.github/workflows/deploy-digithings-stack-cloudflare.yml`
- `Dockerfile.digithings-stack-cloudflare`, `frontend/digithings-stack-cloudflare/{wrangler.toml,src/index.ts,src/ports.ts,container/supervisor/supervisord.conf,container/entrypoint.sh}`, `frontend/digithings-stack-cloudflare/README.md`

### F. Steps

- [ ] F1: extend the stack image with the MCP extras WITHOUT adding new containers: `Dockerfile.digithings-stack-cloudflare:49` installs `digisearch[server,ingestion,chroma]` — assert that set already includes `mcp`/`typer`/`digikey` (per `digisearch/pyproject.toml:17-37` the `[server]` extra carries them; if not, extend to `digisearch[server,ingestion,chroma,mcp]` explicitly). `digivault[service]` (`:53`) must include `mcp` (per `digivault/pyproject.toml:26-29` bounds); if the extra lacks it, add `mcp` to that install line. `digigraph` (`:44`) needs its `[mcp]` extra for the C5 program — change to `pip install --system -e "./digigraph[mcp]"` only if the base install lacks `mcp` (check `digigraph/pyproject.toml:37-39`). Keep `litellm==1.72.6` + `fastapi<0.116` pins (`:56`) untouched.
- [ ] F2: add the three supervisord programs from A4/B5/C5 (digisearch-mcp `:8765`, digivault-mcp `:8769`, digigraph-mcp `:8766`). All bind loopback (`127.0.0.1` via code defaults + explicit port args). No `[program:digillm-mcp]` (E3), no `[program:digiquant-mcp]` (dedicated container already). No `EXPOSE` change.
- [ ] F3: NEW workflow `.github/workflows/deploy-digithings-stack-cloudflare.yml` — manual only:
  ```yaml
  name: "Deploy: digithings-stack (Cloudflare Containers)"
  on:
    workflow_dispatch:
      inputs:
        ref:
          description: "Git ref to deploy (default: develop tip)"
          required: false
          default: ""
    pull_request:
      paths:
        - "Dockerfile.digithings-stack-cloudflare"
        - "frontend/digithings-stack-cloudflare/**"
        - "digiquant/Dockerfile.mcp"
        - "digivault/Dockerfile.mcp"
        - ".github/workflows/deploy-digithings-stack-cloudflare.yml"
  permissions:
    contents: read
  jobs:
    check:
      runs-on: ubuntu-latest
      steps:
        - uses: actions/checkout@v4
        - uses: actions/setup-node@v4
          with: { node-version: "22", cache: npm }
        - run: npm ci
          working-directory: frontend/digithings-stack-cloudflare
        - run: npx tsc --noEmit
          working-directory: frontend/digithings-stack-cloudflare
        - run: npx vitest run
          working-directory: frontend/digithings-stack-cloudflare
    # deploy job: workflow_dispatch only, environment-gated, runs wrangler deploy
    # from frontend/digithings-stack-cloudflare. No auto-deploy on push.
  ```
  The `deploy` job runs ONLY on `workflow_dispatch`, targets a protected `production` environment (human approver), and runs `npx wrangler deploy` from `frontend/digithings-stack-cloudflare/`. PRs run `check` only. Document in the workflow header that stack deploy was manual with no workflow before this file, and stays human-approved after it.
- [ ] F4: update `frontend/digithings-stack-cloudflare/README.md` (programs table, ports, loopback statement, secrets list mirroring `wrangler.toml:91-147`, the `env -u CLOUDFLARE_API_TOKEN` trap).
- [ ] F5: deploy drill (owner): `workflow_dispatch` from the task branch to a preview workers.dev URL; assert `GET /_stack/meta` → `{"ok":true}`, `GET /_stack/key/healthz` → digikey, graph `/healthz` → 200, `mcp.digithings.ai` still 404/unrouted until D6, then promote.

### F. Acceptance

- PR touching only `digisearch/src/**` does NOT trigger the stack `check` (path filter); PR touching `frontend/digithings-stack-cloudflare/**` does.
- Preview deploy shows all three MCP programs `RUNNING` via `wrangler containers ssh` + `supervisorctl status`; no new listening socket on `0.0.0.0` except `:8000`/`:8005` (`ss -ltnp` inside the container).
- `sleepAfter`/`max_instances`/`instance_type` diff is empty in the deploy PR.

---

## Sub-track G — tenant wiring per chatbot + corpus-map unify decision

### G. Files

- `frontend/digichat/config/examples/{digithings-ai-embed.yaml,dashboard-modal.yaml,datatap-mcp.yaml}`, live `DIGICHAT_EMBED_TENANTS` (env, never repo)
- `infra/digichat-release/compose.profile-a-bundle.override.yml:6-11`, `infra/digichat-release/config/digiproject.yaml:9-40`
- `frontend/digithings-stack-cloudflare/{wrangler.toml:175,src/index.ts:84-86}`
- `digigraph/src/digigraph/{corpus_routing.py,http_api/context.py,http_api/chat_resolve.py,orchestration/mcp_client.py}`, `digivault/src/digivault/tenant_scope.py`
- NEW `scripts/check_tenant_corpus_map.py` + `tests/scripts/test_check_tenant_corpus_map.py`, wired into `ci.yml` scripts lane

### G. Steps

- [ ] G1 (dashboard popup chat = digiquant read scope): edit `frontend/digichat/config/examples/dashboard-modal.yaml` `mcp:` block (lines 58-60, today empty `servers: []` default) to declare the read-scope server following the `datatap-mcp.yaml:36-43` shape:
  ```yaml
  mcp:
    allowUserServers: false
    allowAddForm: false
    servers:
      - id: digiquant
        url: https://mcp.digithings.ai/mcp
        label: digiquant market data
        default: true
  ```
  Keep `allowUserServers: false` (public embed). BFF forwards operator URL server-side (`mcp-servers.ts:182-195` + `route.ts:457`); browser projection stays URL-free (pinned by `loader.test.ts:267-268`). Add/extend `frontend/digichat/src/lib/deploy-config/mcp-servers.test.ts` asserting the dashboard example loads with exactly this server and that a session overlay cannot override its URL (operator wins, `mergeMcpSessionOverlay` in `mcp-servers.ts:242-269`). Until D6 enables the route, this entry resolves but its tools list empty at runtime (`_list_tools_blocking` returns `[]` on failure, `mcp_client.py:361-366`) — assert that degradation is silent in the chat path and loud in `tool_choice="required"` force paths per `retrieval.py:6` (document which in the PR).
- [ ] G2 (digithings.ai chat tenants = parameterized storage accounts): no behavior change — pin the contract with tests. `DIGICHAT_EMBED_TENANTS` backends carry `digisearchIndex`/`vaultPathPrefix` (example shape in `infra/digichat-digithings/README.md:100-101` and the local override at `compose.profile-a-bundle.override.yml:11`); the stack's `DIGI_TENANT_CORPUS_MAP` is authoritative server-side (`digigraph/corpus_routing.py:145-179`, `digivault/tenant_scope.py:136-165`, both fail closed with 503/403 on set-but-broken or unmapped tenants). Add `tests/dg/test_tenant_corpus_parity.py` asserting digigraph and digivault parsers accept the same `{"slug": {"digisearchIndex","vaultPathPrefix"}}` entry and agree on unknown-slug behavior (digigraph clears to `None`, digivault 403s — assert the asymmetry explicitly so nobody "fixes" one side).
- [ ] G3 (unify decision — recommended: do NOT unify, add a drift check): the two blobs have different owners and cadences (digichat deploy env vs stack wrangler vars/secrets). Unifying them into one source would couple the digichat deploy to the stack deploy. Instead add NEW `scripts/check_tenant_corpus_map.py` comparing key sets and per-key `digisearchIndex`/`vaultPathPrefix` values across (a) `infra/digichat-release/compose.profile-a-bundle.override.yml` `DIGICHAT_EMBED_TENANTS`, (b) `frontend/digithings-stack-cloudflare/wrangler.toml` `DIGI_TENANT_CORPUS_MAP`, (c) the `src/index.ts:84-86` fallback literal. Non-zero exit + unified diff on drift; wire into the `ci.yml` scripts lane next to `tests/scripts/test_deploy_build_inputs.py`. Owner may overrule toward a single source — if so, the stack map wins (it is the enforcement point) and the digichat blob becomes a tested projection of it; spec that migration separately, not in this phase.
- [ ] G4: gates: digichat `npm run test` + `npm run lint`, `pytest tests/ -m unit -k "digigraph or digivault" -v`, `make doc-check`.

### G. Acceptance

- Dashboard example loads in `loader.test.ts`-style harness with the digiquant server present, URL-free on the client, operator-URL-wins on merge.
- `scripts/check_tenant_corpus_map.py` passes on current tree and fails when either blob's `occ` entry is edited without the other (prove by temporary edit, revert before commit).
- Tenant corpus behavior matrix green: mapped tenant resolves index+prefix; unmapped tenant with map set → 403/503 fail-closed (both services); map unset → headers still select corpus (single-tenant parity, per `corpus_routing.py` + `tenant_scope.py` docstrings).

---

## Sub-track H — web-search landing (#3853 branch `task/3853-proprietary-web-search-mcp-tool--digifet`)

Scope: land the branch's `digisearch/web_search/` package (embedded `ddgs` + `searxng` sidecar) as a digisearch MCP tool. digifetch stays a library — the branch's only digifetch touch is `from digifetch import HttpFetcher, RateLimiter, RetryPolicy, with_retry` in `web_search/service.py:7` (pass-through fetch inside `run_web_search`); no digifetch MCP server, no new digifetch dependency direction.

### H. Files (on the branch; verify with `git ls-tree -r --name-only task/3853-proprietary-web-search-mcp-tool--digifet | grep -E "web_search|searxng"`)

- `digisearch/src/digisearch/web_search/{__init__.py, models.py, ddgs_provider.py, searxng_provider.py, service.py, extractor.py}` + `digisearch/tests/test_web_search_{ddgs,searxng,service,models,extractor}.py`
- `digigraph/src/digigraph/orchestration/web_search_tools.py` + `tests/dg/test_web_search_opt_in.py`
- `config/searxng/settings.yml` (sidecar config), `digisearch/ARCHITECTURE.md`, `digigraph/ARCHITECTURE.md`

### H. Steps

- [ ] H1: rebase the branch onto current `develop` (`git fetch origin`, resolve; the branch tip `cf23e1ce0` touches `digiquant/research/data/web_grounding.py` + `config/digiquant_models.yaml` + `digillm` usage-kind split — expect conflicts in grounding call sites, keep the branch's `digifetch_web_search` primitive + `usage_kind="web_search"` split).
- [ ] H2: land order (stacked PRs, each green): (1) `digisearch/web_search/` package + unit tests (no MCP registration yet); (2) searxng sidecar wiring — `config/searxng/settings.yml` + compose profile (sidecar loopback `127.0.0.1:8080`, matching `WebSearchConfig.searxng_url` default `http://127.0.0.1:8080` in `service.py:26-31`) + `DIGISEARCH_SEARXNG_URL`/`DIGISEARCH_WEB_SEARCH_BACKEND` env docs; (3) MCP tool registration on the digisearch server from sub-track A (new tool next to `digisearch_query`, honoring `create_mcp_with_indexes` wiring and the A2 fail-loud gate); (4) digigraph `web_search_tools.py` consumer (prefer digisearch tool, synthesis fallback) + `test_web_search_opt_in.py`.
- [ ] H3: rate-limit + SSRF discipline: `RateLimiter(min_interval=1.0)` stays (`service.py:34`); searxng stays loopback; ddgs is the embedded fallback (`_search_only` order searxng→ddgs, `service.py:37-48`). Tool args honor domain allowlists from `digiquant/research/config/search_domains.yaml` where the branch wires them — do not invent a second allowlist.
- [ ] H4: gates per landing PR: the component gates from § 0 for every touched component + the branch's own `digisearch/tests/test_web_search_*.py`.

### H. Acceptance

- `DIGISEARCH_WEB_SEARCH_BACKEND=ddgs pytest digisearch/tests/test_web_search_service.py -v` green with no network (ddgs provider mocked at the boundary the branch's tests already use); searxng tests run against the compose sidecar.
- New `digisearch_web_search` MCP tool appears in the `:8765` listing after A4; digigraph force-tool `/web_search` path prefers it per `test_web_search_opt_in.py`.
- `grep -rn "from digifetch" digisearch/src/digisearch/web_search/` shows only the `HttpFetcher/RateLimiter/RetryPolicy/with_retry` import; no `digifetch` MCP, server, or extra dependency added.

---

## 4. Edge-JWT design (digiquant MCP; owner-gated, human review required)

Goal: enable `mcp.digithings.ai` (commented at `wrangler.toml:35-38`) with a Worker-edge digikey JWT check, scope `digiquant:backtest`, before any traffic reaches `DigiQuantMcpContainer`.

- JWKS source at edge: `https://key.digithings.ai/.well-known/jwks.json` (== `DIGIKEY_ISSUER`, `wrangler.toml:150`). The container-side equivalent is `digikey/src/digikey/jwt_verify.py` (`PyJWKClient`, 300s cache); the edge mirrors it with WebCrypto RS256 + a 300s in-Worker cache (Cache API or module-level map with timestamp; single flight on refresh).
- Validation (fail closed, in order): `Authorization: Bearer <jwt>` present else 401 → JWKS fetch/parse fails → 503 → signature invalid → 401 → `iss != DIGIKEY_ISSUER` → 401 → `aud != digi-ecosystem` (== `DIGIKEY_AUDIENCE`, `wrangler.toml:151`) → 401 → `exp` past → 401 → `scopes` lacks `digiquant:backtest` → 403. (`digiquant:backtest` is the existing MCP-relevant scope per `digiquant/ARCHITECTURE.md:151-174`; no digikey change needed.)
- Token acquisition (no new endpoint): clients exchange a `dgk_live_` key at `https://key.digithings.ai/v1/oauth/token` (`grant_type=api_key`) exactly like machine clients in root `ARCHITECTURE.md` § 6 Flow C, then call `https://mcp.digithings.ai/mcp` with the JWT. The browser never holds it (digichat BFF pattern unchanged; dashboard chat goes through digichat, which presents its own exchange).
- Forwarding: on success, `container.fetch(request)` to `MCP_STACK`/`MCP_CONTAINER_ID` unchanged (`src/index.ts:268-271`); forward the `Authorization` header untouched (future container-side `DigiAuthMiddleware` can double-check without a flag day). Never log header values or tokens.
- What is NOT built: per-tool scope narrowing at edge (all 8 read tools share `digiquant:backtest`; narrowing is a digikey scopes migration, out of phase), container-side auth (noted follow-up), any `/_stack/mcp/*` workers.dev route (banned, § 0).
- Tests: mocked-JWKS vitest cases for 401/403/503/pass, cache-hit (one JWKS fetch for N requests inside TTL), wrong-`aud`/`iss` rejection, expired rejection. Plus a preview-deploy drill (D-phase acceptance) before the route uncomment (D6).

---

## 5. Rollback (per sub-track, no scaling knobs touched)

- A/B/C (supervisord programs): `supervisorctl stop digisearch-mcp|digivault-mcp|digigraph-mcp`, revert the `supervisord.conf` hunk, redeploy stack via the F3 workflow `workflow_dispatch`. HTTP services (`:8000/8002/8004/8005/4000`) are untouched by these programs; stopping an MCP program never restarts them.
- D (route + gate): re-comment the `mcp.digithings.ai` route, redeploy; previous Worker version is restored by `wrangler rollback` (owner). `DigiQuantMcpContainer` keeps serving loopback for the cron warm ping; no data migration exists (R2/Supabase reads are stateless + 900s TTL that simply expires).
- D4 (image publish): tags are additive (`sha-*`, `latest`, `v*`); rollback is pinning the previous `sha-*` tag in the deploy ref. Never force-push or delete `ghcr.io` tags.
- G (tenant YAML): revert the example/env edit; BFF forwards whatever the YAML declares on next digichat deploy — no stack deploy needed. `check_tenant_corpus_map.py` failing blocks the revert-proof (fix both blobs together).
- H: revert the landing PR stack top-down (digigraph consumer first, then MCP registration, then package); the branch remains intact.
- Never roll back by editing `sleepAfter`/`max_instances`/`instance_type` or by bumping `SHARED_STACK_CONTAINER_ID` unless the owner proves a stale image (ports.ts:25-28 procedure).

## 6. Risks and open questions (owner-gated items marked ◆)

- ◆ Port assignment `:8769` for digivault stack slot (B): recommended default; confirm or reassign before B5.
- ◆ Edge-JWT gate code + `mcp.digithings.ai` route enablement (D2/D6): human review required (auth + new external exposure). mcp route stays off until then — no exceptions for demos.
- ◆ `publish-service-images.yml` `version_from` edit (D4): touches shared CI; confirm tag scheme `digiquant-mcp:v<digiquant-version>` is acceptable (alternative: independent version file — owner call).
- ◆ Corpus-map unify-vs-check (G3): recommended drift check, not unification. Overrule needs a follow-up spec (stack map authoritative, digichat blob becomes projection).
- Risk: five MCP processes + six HTTP processes in one Firecracker container raises steady-state RAM; mitigation is already the `standard-2` instance type (`wrangler.toml:46`) — if OOM appears, the fix is a follow-up phase with its own spec, NOT an in-phase scaling tweak (constraint).
- Risk: installed `mcp` 1.x API drift (`mcp>=1.0,<2` pins in all five pyprojects; 2.0 removed `fastmcp`). C1 pins the actual signature; if 1.x already changed `run()` semantics, C3 follows evidence, not this spec's default.
- Risk: digigraph↔digivault `:8766` default collision confuses local dev running both standalones; mitigation: B2/C3 `--port` flags + a `make doc-check`-visible note in both ARCHITECTURE MCP sections.
- Open: per-tenant index binding for DIRECT (non-digigraph) MCP clients (G): today `index_name` is caller-supplied; server-side JWT→corpus bind for raw MCP is future work — direct MCP clients are trusted-operator only until then.
- Open: container-side `DigiAuthMiddleware` on the MCP processes (defense in depth behind the edge gate) — follow-up, not this phase.
- Open: digisearch MCP tenant default index: hosted process uses `DIGISEARCH_INDEX=digithings_docs` with per-request `index_name` override; `occ_help` reachability for direct MCP clients is operator-by-param until the bind above exists.

## 7. Verification matrix (run at phase end)

```bash
# component gates (§ 0) — all green
pytest tests/ -m unit -k "digisearch" -v
pytest tests/dv -m unit
pytest tests/ -m unit -k "digigraph" -v
pytest tests/ -m unit -k "digiquant" -v
pytest digillm/tests -v
ruff check digisearch/ digivault/src digigraph/ digiquant/ digillm/ && ruff format --check digisearch/ digivault/src digigraph/ digiquant/ digillm/
make doc-check
# stack package
npm ci && npx tsc --noEmit && npx vitest run --prefix frontend/digithings-stack-cloudflare
# digichat (G only)
npm run test --prefix frontend/digichat && npm run lint --prefix frontend/digichat
# hosting probes (inside preview container)
supervisorctl status
curl -s http://127.0.0.1:8765/mcp -H 'Accept: application/json' | grep -o digisearch_query
curl -s http://127.0.0.1:8769/mcp -H 'Accept: application/json' | grep -o digivault_lint
curl -s http://127.0.0.1:8766/mcp -H 'Accept: application/json' | grep -o list_orchestrator_tools
curl -s http://127.0.0.1:8767/mcp -H 'Accept: application/json' | grep -o digiquant_get_price_technicals
# edge (only after D6)
curl -s -o /dev/null -w "%{http_code}\n" https://mcp.digithings.ai/mcp
# drift check (G3)
python3 scripts/check_tenant_corpus_map.py
```
