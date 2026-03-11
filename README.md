<p align="center">
  <strong>DigiThings</strong>
</p>
<p align="center">
  <strong>digithings.ai</strong> — Open-core agentic stack for chat-driven workflows, RAG & domain apps
</p>

<p align="center">
  <a href="./LICENSE"><img src="https://img.shields.io/badge/license-MIT-blue.svg" alt="License: MIT" /></a>
  <a href="https://www.python.org/downloads/"><img src="https://img.shields.io/badge/python-3.12+-green.svg" alt="Python 3.12+" /></a>
</p>

---

## What is this?

**DigiThings** is a modular, self-hosted platform to build **conversational agents** that research, search, analyze, and act. Chat in → agents call tools, hit your RAG index, run backtests, or drive custom workflows. One prominent use case is the **quant pipeline** (idea → backtest → optimize → monitor); the same stack also powers **RAG over your data**, document search, and arbitrary agent apps.

- **MCP-first** — Every capability is a discoverable tool; DigiGraph orchestrates, DigiClaw is the gateway.
- **Run it yourself** — Docker Compose, no vendor lock-in. Bind to loopback; use Tailscale or Cloudflare for remote.
- **Polars + NautilusTrader** — No pandas. High-performance quant path when you need it.

| Doc | Description |
|-----|--------------|
| [**DIGI.md**](./DIGI.md) | Vision, strategy, monetization |
| [**ARCHITECTURE.md**](./ARCHITECTURE.md) | System diagram & interfaces |
| [**AGENTS.md**](./AGENTS.md) | Rules for AI coding agents |
| [**ROADMAP.md**](./ROADMAP.md) | Phases (if present) |

---

## Features

| | |
|:---|:---|
| **LangGraph orchestration** | Research → backtest (and more); supervisor + sub-graphs, optional checkpoints. |
| **DigiSearch** | RAG, ingestion, chunking, multi-backend search (e.g. Azure AI Search, Chroma). |
| **DigiQuant** | NautilusTrader backtest/optimize, Polars-only, MCP tools for the graph. |
| **DigiClaw** | Gateway (OpenClaw), heartbeat, audit; one custom skill to run DigiGraph. |
| **LiteLLM** | One config, many providers (Ollama, OpenAI, etc.); mode-based model selection. |

---

## Components

| Component | One-liner | Docs |
|-----------|-----------|------|
| **DigiClaw** | Gateway, heartbeat, audit, MCP skill → DigiGraph | [DIGICLAW.md](digiclaw/DIGICLAW.md) |
| **DigiGraph** | LangGraph brain: `/workflow`, chat API, DigiSearch + DigiQuant tools | [DIGIGRAPH.md](digigraph/DIGIGRAPH.md) |
| **DigiQuant** | Backtest/optimize (Nautilus, Polars), MCP for DigiGraph | [DIGIQUANT.md](digiquant/DIGIQUANT.md) |
| **DigiSearch** | RAG + document search, HTTP + MCP | [DIGISEARCH.md](digisearch/DIGISEARCH.md) |
| **config** | LiteLLM + model modes (test/medium/best) | [MODELS.md](config/MODELS.md) |

*Optional:* [DigiFlow](digiflow/DIGIFLOW.md) (Langflow prototyping), [DigiKey](digikey/DIGIKEY.md) (security/identity placeholder).

---

## Quick start

**Docker (recommended):**

```bash
cp .env.example .env   # edit if needed
make up
```

**Local (dev loop):**

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

Target: backtest result in under ~10s.

---

## Repo layout

```
digithings/
├── digiclaw/     # Gateway, heartbeat, audit
├── digigraph/    # LangGraph orchestration, agents, DigiStore
├── digiquant/    # Nautilus + Polars, backtest/optimize
├── digisearch/   # RAG, document search, ingestion
├── config/       # LiteLLM, model modes
├── scripts/      # run_local.sh, package.sh, etc.
├── tests/        # pytest (dg, dq, ds, dc)
├── docker-compose.yml
├── Makefile      # build, up, down, test, package
└── .env.example
```

Project-specific config lives in **projects/** (local only, gitignored).

---

## Services

| Service   | Port | Role              |
|-----------|------|-------------------|
| DigiGraph | 8000 | `/workflow`, chat API |
| DigiQuant | 8001 | Backtest, optimize, MCP |
| DigiSearch| 8002 | Document search, RAG |
| LiteLLM   | 4000 | LLM routing       |

All bind to `127.0.0.1`. Use Tailscale or Cloudflare Tunnel for remote access.

---

## Tests

```bash
make test        # unit + e2e (if stack up)
make test-unit   # unit only
make test-e2e   # e2e (requires make up)
```

With venv: `pytest -v` or `pytest -m unit -v`.

---

## For AI coding agents

1. Read this file and [DIGI.md](./DIGI.md).
2. Read the component doc for your area (e.g. [digigraph/DIGIGRAPH.md](digigraph/DIGIGRAPH.md)).
3. Follow [AGENTS.md](./AGENTS.md): Polars only, NautilusTrader for quant, LangGraph supervisor, MCP-first, Pydantic outputs.

---

## Limitations (v0.1)

- **DigiQuant:** Nautilus by default; `NAUTILUS=0` to disable (backtest then 503).
- **Export/brokers:** Stubs only; no live deploy or real Pine/broker artifacts.
- **ADDM:** Drift stub; re-optimization path exists but not triggered.
- **OpenClaw:** Full gateway deferred; heartbeat + audit run standalone.

Full list → [LAUNCH.md](./LAUNCH.md).

---

## License & product

**DigiThings** is open-core on GitHub. Commercial options: DigiQuant packs, consulting (e.g. Montréal AI/FinTech). See [LAUNCH.md](./LAUNCH.md) for Phase 4.

**License:** [MIT](./LICENSE).
