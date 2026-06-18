# AGENTS.md

Canonical rules for all agents in this repo are in **[CLAUDE.md](CLAUDE.md)** — read that first.

Claude Code loads `CLAUDE.md` at session start. Cursor agents use `.cursor/rules/digithings.mdc`; Copilot uses `.github/copilot-instructions.md` — both generated from `agents.yml` by `make agents-init`.

## Cursor Cloud specific instructions

### Runtime prerequisites (one-time on a fresh VM)

- **Python 3.12+** with `python3.12-venv` (`apt install python3.12-venv`) and **`lsof`** (used by `scripts/run_stack_local.sh`).
- **Node.js 22** (repo CI pin).
- **Docker** is optional. Cursor Cloud VMs may not have Docker; use the host-native stack instead (below).

### Dependency install

The VM update script creates `.venv`, runs `scripts/install-workspace.sh --with-dev` (put `.venv/bin` on `PATH` first — the script calls `python`, not `python3`), installs `digiquant[nautilus]`, `litellm[proxy]`, and root `npm ci` plus Linux native bindings for DigiChat Vitest (see `.github/workflows/digichat-test.yml`).

Activate before Python commands: `source .venv/bin/activate` or `PATH="$PWD/.venv/bin:$PATH"`.

Copy config once per session if missing: `cp .env.example .env` (set `GROQ_API_KEY` for LLM workflow tests).

### Running services without Docker

```bash
PATH="$PWD/.venv/bin:$PATH" make stack-local   # DigiKey :8005, DigiGraph :8000, DigiQuant :8001, DigiSearch :8002, DigiSmith :8003, LiteLLM :4000
PATH="$PWD/.venv/bin:$PATH" ./scripts/stop_stack_local.sh
```

DigiChat dev UI (needs `frontend/digichat/.env.local` + optional `make up-digichat-db` for Postgres): `make digichat-dev` → http://127.0.0.1:3000.

### Lint / test commands (no stack required)

| Command | Purpose |
|---------|---------|
| `make test-baseline` | Fast always-green gate (imports, schemas, CLI) |
| `make test-unit` | Full Python unit + DigiChat Vitest (see caveats) |
| `npm run test --workspace digichat` | DigiChat Vitest only |
| `.venv/bin/ruff check <component>/src` | Python lint |

**Linux caveat:** NautilusTrader can **SIGABRT** when backtest engine tests run under pytest on Linux (tracked #42). `make test-unit` may abort mid-run; use `make test-baseline` and targeted `pytest -m unit tests/dg/ tests/dk/` for a safe subset. Live `POST /run_backtest` against a running DigiQuant may also crash the process on some Linux hosts.

**LLM workflow:** `POST /workflow` on DigiGraph requires a provider key in `.env` (e.g. `GROQ_API_KEY`). JWT exchange via DigiKey works without it.

### Issue a dev API key (stack-local)

```bash
export DIGIKEY_DATABASE_URL="sqlite:////workspace/.local_digikey.sqlite" DIGIKEY_ALLOW_DEV_GLOBAL=1
PATH="$PWD/.venv/bin:$PATH" python -m digikey.cli issue-key --tenant default --label dev --scopes '*' --kind dev_global
# Exchange: POST http://127.0.0.1:8005/v1/oauth/token  {"grant_type":"api_key","api_key":"dgk_live_..."}
```

Standard commands are also documented in root `README.md` and `Makefile`.
