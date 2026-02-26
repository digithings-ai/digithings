# Digi Ecosystem – Agentic Hedge Fund in a Box

**Version 1.0** | **February 20, 2026** | **Status: Living Source of Truth**

The **Digi** project delivers a conversational, self-healing, memory-rich “hedge-fund-in-a-box” for solo quants and small financial firms. Users chat an idea → agents research, backtest, optimize, deploy, and monitor — all autonomously.

**Master Vision** → [`DIGI.md`](./DIGI.md)  
**Architecture** → [`ARCHITECTURE.md`](./ARCHITECTURE.md) (Mermaid diagrams)  
**Roadmap** → [`ROADMAP.md`](./ROADMAP.md)

## Repository Structure
digi/
├── README.md                  ← You are here (entry point)
├── DIGI.md                    ← Canonical 30k-ft vision & business strategy
├── ARCHITECTURE.md            ← System diagrams & data flows
├── ROADMAP.md                 ← Phased delivery plan
├── LAUNCH.md                  ← Phase 4: open-source release & monetization checklist
├── SECURITY.md                ← Hardening & compliance (2026 standards)
├── CONTRIBUTING.md            ← Agent & human contribution rules
├── LICENSE                    ← MIT
│
├── digiclaw/                  ← OpenClaw runtime + gateway + chat + cron
│   └── DIGICLAW.md
│
├── digigraph/                 ← LangGraph orchestration brain + agent families
│   └── DIGIGRAPH.md
│
└── digiquant/                 ← High-perf Nautilus + Polars + ML pipeline
└── DIGIQUANT.md

## Terminal setup (local development)

From the repo root, activate the venv so `python` and the DigiQuant CLI work:

```bash
# One-time: allow direnv (auto-activates venv when you cd into digi/)
direnv allow

# Or manually each session:
source .venv/bin/activate
```

Then run the DigiQuant CLI from repo root:
```bash
python -m digiquant backtest -s bollinger_mr -S BTC-USD -d digiquant/data/BTC-USD.csv -p trade_size=1
```

## Quick Start (Phase 0–3 complete)
```bash
# Option A: Docker
cp .env.example .env   # edit if needed
docker compose up --build

# Option B: Local (fast iteration and debugging)
# One-time: uv pip install -e "./digiquant[nautilus]" -e ./digigraph && python digiquant/scripts/fetch_nautilus_test_data.py
./scripts/run_local.sh
# Then: curl -s -X POST http://127.0.0.1:8000/workflow -H "Content-Type: application/json" -d '{"prompt":"Build me a mean-reversion stat-arb on tech"}' | python3 -m json.tool
```
Milestone: backtest result in &lt; 10s. See `digiclaw/skills/README.md` for the DigiClaw skill contract.

**Tests:** `pytest -v` (unit + e2e if stack is up). Unit only: `pytest -m unit -v`. See `tests/README.md`.

**Local development (no Docker):** Use `./scripts/run_local.sh` to start DigiQuant (8001) and DigiGraph (8000) on your machine. Requires a venv with `pip install -e "./digiquant[nautilus]" -e ./digigraph` and Nautilus test data (`python digiquant/scripts/fetch_nautilus_test_data.py` once). Iterate and debug without rebuilding images.

## Quick Start for Any Coding Agent
1. Read this file + `DIGI.md` first.  
2. Then read the specific sub-directory `DIGIxxx.md` for the component you are working on.  
3. All code **must** be:
   - MCP-first (discoverable tools)
   - Dockerized & self-hosted
   - Token-efficient (LiteLLM caching + structured Pydantic outputs)
   - No pandas anywhere (Polars only)
   - NautilusTrader as the core backtest/execution engine
   - Layered supervisor + sub-graph pattern in LangGraph

**Positioning & Monetization**  
Open-core on GitHub → paid DigiQuant packs ($199/mo or $4,999 one-time) → consulting in the Montréal AI/FinTech ecosystem. See **LAUNCH.md** for Phase 4 release and launch checklist.

**License:** MIT — see [LICENSE](./LICENSE).

## Current limitations (v0.1)

- **Backtest:** DigiQuant runs real NautilusTrader backtests by default (Docker image includes `digiquant[nautilus]`). Set `NAUTILUS=0` when building to omit Nautilus (backtest endpoints then return 503). For local tests: `uv pip install -e "./digiquant[nautilus]"` then run `python digiquant/scripts/fetch_nautilus_test_data.py` to download the test CSV (required for backtest tests).
- **Export, TradingView, brokers:** Export and broker adapters are stubs; the pipeline runs but does not deploy to live platforms or produce real Pine/broker artifacts.
- **ADDM:** Drift detection is a stub; drift is never reported; heartbeat re-optimization path exists but is not triggered.
- **OpenClaw:** Gateway and custom DigiGraph skill are deferred; heartbeat and audit run standalone.

See [LAUNCH.md](./LAUNCH.md) for the full v0.1 limitations list and Phase 4 checklist.

Welcome to the autonomous quant desk of 2026.  
Let’s ship it.