# Digi Ecosystem – Agentic Hedge Fund in a Box

**Living source of truth** | **Status: Phase 0–3 complete**

The **Digi** project is a conversational, self-healing, memory-rich “hedge-fund-in-a-box” for solo quants and small firms. Users chat an idea → agents research, backtest, optimize, deploy, and monitor — all via MCP-first, Dockerized services.

**Vision & strategy** → [`DIGI.md`](./DIGI.md)  
**Architecture** → [`ARCHITECTURE.md`](./ARCHITECTURE.md)  
**Roadmap** → [`ROADMAP.md`](./ROADMAP.md) (if present)  
**Agent rules** → [`AGENTS.md`](./AGENTS.md)

---

## Repository structure

```
digi/
├── README.md              ← You are here
├── DIGI.md                ← Vision, mission, monetization
├── ARCHITECTURE.md        ← System diagrams & data flows
├── AGENTS.md              ← Non-negotiable rules for all coding agents
├── CLAUDE.md              ← Claude / Cursor dev guide (commands, config)
├── SECURITY.md            ← Hardening & compliance
├── CONTRIBUTING.md        ← Contribution rules
├── LICENSE                ← MIT
│
├── digiclaw/              ← OpenClaw runtime, gateway, heartbeat, audit
├── digigraph/             ← LangGraph orchestration, agent families, DigiSearch/DigiStore
├── digiquant/             ← NautilusTrader + Polars, backtest/optimize/export
├── digisearch/            ← RAG, document search, ingestion, MCP
├── config/                ← LiteLLM, model modes, shared config
├── docker-compose.yml     ← Multi-service stack
├── Makefile               ← build, up, down, test, package
├── .env.example           ← Environment template
└── tests/                 ← Unit + e2e (pytest)
```

Project-specific config and deployments are **local-only** (not in this repo) for confidentiality.

---

## Quick start

**Docker (recommended):**

```bash
cp .env.example .env   # edit if needed
make up
# Or: docker compose up -d
```

**Local (fast iteration):**

```bash
direnv allow   # or: source .venv/bin/activate
pip install -e "./digiquant[nautilus]" -e ./digigraph
python digiquant/scripts/fetch_nautilus_test_data.py
./scripts/run_local.sh
```

**Smoke test:**

```bash
curl -s -X POST http://127.0.0.1:8000/workflow \
  -H "Content-Type: application/json" \
  -d '{"prompt":"Build me a mean-reversion stat-arb on tech","session_id":"test-1"}' \
  | python3 -m json.tool
```

Target: backtest result in under ~10s. See `digiclaw/skills/README.md` for the DigiClaw skill contract.

---

## Terminal / venv

From repo root, activate the venv so the DigiQuant CLI and Python tooling work:

```bash
direnv allow
# Or each session: source .venv/bin/activate
```

Then, for example:

```bash
python -m digiquant backtest -s bollinger_mr -S BTC-USD -d digiquant/data/BTC-USD.csv -p trade_size=1
```

---

## Tests

| Command        | Description                    |
|----------------|--------------------------------|
| `make test`    | All tests (unit + e2e if stack up) |
| `make test-unit` | Unit only                   |
| `make test-e2e`  | E2e (requires `make up`)   |

From repo root with venv: `pytest -v`, or `pytest -m unit -v`. See `tests/README.md` if present.

---

## For coding agents

1. Read this file and `DIGI.md` first.
2. Read the component `DIGIxxx.md` for the area you’re changing (e.g. `digigraph/DIGIGRAPH.md`).
3. Follow **AGENTS.md**: Polars only (no pandas), NautilusTrader for backtest/execution, LangGraph supervisor + sub-graphs, LiteLLM, MCP-first tools, Pydantic outputs.

---

## Service endpoints

| Service   | Port | Role                          |
|-----------|------|-------------------------------|
| DigiGraph | 8000 | LangGraph API, `/workflow`    |
| DigiQuant | 8001 | Backtest, optimize, MCP       |
| DigiSearch| 8002 | Document search, RAG          |
| LiteLLM   | 4000 | LLM routing                   |

All bind to `127.0.0.1`. Use Tailscale or Cloudflare Tunnel for remote access.

---

## Current limitations (v0.1)

- **Backtest:** DigiQuant uses NautilusTrader by default. Use `NAUTILUS=0` in build to disable; backtest endpoints then return 503.
- **Export / brokers:** Export and broker adapters are stubs; no live deployment or real Pine/broker artifacts.
- **ADDM:** Drift detection is a stub; heartbeat re-optimization path exists but is not triggered.
- **OpenClaw:** Full gateway and custom DigiGraph skill are deferred; heartbeat and audit run standalone.

See [LAUNCH.md](./LAUNCH.md) for full v0.1 limitations and Phase 4 checklist.

---

## Positioning & license

Open-core on GitHub → paid DigiQuant packs and consulting in the Montréal AI/FinTech ecosystem. See **LAUNCH.md** for Phase 4 release.

**License:** MIT — [LICENSE](./LICENSE).
