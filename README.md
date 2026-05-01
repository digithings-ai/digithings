<p align="center">
  <strong>digithings</strong>
</p>
<p align="center">
  <strong>digithings.ai</strong> — Open-core agentic stack for chat-driven workflows, RAG, and domain apps
</p>

<p align="center">
  <a href="./LICENSE"><img src="https://img.shields.io/badge/license-MIT-blue.svg" alt="License: MIT" /></a>
  <a href="https://www.python.org/downloads/"><img src="https://img.shields.io/badge/python-3.12+-green.svg" alt="Python 3.12+" /></a>
</p>

---

## What is this?

**DigiThings** is a modular, self-hosted platform for building **conversational agents** that research, search, analyze, and act. Chat goes in; agents call tools, hit your RAG index, run backtests, or drive custom workflows.

Flagship vertical: **quantitative finance** — a "hedge-fund in a box" where one operator runs strategy research, backtesting, optimization, and execution monitoring through a single chat. The same stack powers RAG over your data, document search, and general agent apps.

**Design principles**

- **MCP-first** — every capability is a discoverable tool; DigiGraph orchestrates.
- **Run it yourself** — Docker Compose, no vendor lock-in. Loopback by default; use Tailscale or Cloudflare Tunnel for remote.
- **Structured outputs** — Pydantic v2 everywhere, no dicts-over-the-wire.
- **Polars + NautilusTrader** — no pandas; Rust-core backtests when the quant path is on.

## Key docs

| Doc | Description |
|-----|-------------|
| [**docs/VISION.md**](docs/VISION.md) | Vision, strategy, decisions |
| [**ROADMAP.md**](ROADMAP.md) | Phased plan |
| [**ARCHITECTURE.md**](ARCHITECTURE.md) | System diagram and interfaces |
| [**SECURITY.md**](SECURITY.md) | Threat model, non-negotiable defaults, reporting |
| [**AGENTS.md**](AGENTS.md) | Rules for AI coding agents |
| [**CLAUDE.md**](CLAUDE.md) | Claude Code quick reference |
| [**CONTRIBUTING.md**](CONTRIBUTING.md) | How to contribute |
| [**docs/LLM_PROVIDERS.md**](docs/LLM_PROVIDERS.md) | Free-tier + cheap LLM providers, LiteLLM wiring |
| [**docs/providers/**](docs/providers/README.md) | Step-by-step API-key setup per provider |

## Components

| Component | One-liner | Docs |
|-----------|-----------|------|
| **DigiGraph** | LangGraph orchestration brain; OpenAI-compatible API | [digigraph/ARCHITECTURE.md](digigraph/ARCHITECTURE.md) |
| **DigiQuant** | NautilusTrader backtest/optimize, Polars-only | [digiquant/ARCHITECTURE.md](digiquant/ARCHITECTURE.md) |
| **DigiSearch** | RAG + document search; Azure/Chroma backends | [digisearch/ARCHITECTURE.md](digisearch/ARCHITECTURE.md) |
| **DigiChat** | Next.js BFF + chat UI (Auth.js, machine API keys) | `digichat/ARCHITECTURE.md` (nested repo) |
| **DigiKey** | JWT + scoped API-key auth plane | [digikey/ARCHITECTURE.md](digikey/ARCHITECTURE.md) |
| **DigiSmith** | LangSmith-aligned tracing helpers; health + `/v1/status` | [digismith/ARCHITECTURE.md](digismith/ARCHITECTURE.md) |
| **DigiClaw** | Heartbeat, audit, MCP skill → DigiGraph | [digiclaw/ARCHITECTURE.md](digiclaw/ARCHITECTURE.md) |
| **DigiBase** | Shared HTTP/audit library + future data-plane service | [digibase/ARCHITECTURE.md](digibase/ARCHITECTURE.md) |
| **config** | LiteLLM + model modes (test/medium/best) | [config/MODELS.md](config/MODELS.md) |

## Quick start

**Docker (recommended):**

```bash
cp .env.example .env   # edit if needed
make up
```

**Free-tier LLM (no credit card):** set `GROQ_API_KEY` in `.env` (sign up free at https://console.groq.com). LiteLLM routes `digi/fast` → Groq, `digi/balanced` → Cerebras, `digi/best` → OpenRouter (`:free` models), and `digi/multimodal` → Gemini Flash via OpenRouter. Only the Groq key is required to run the full stack. See [docs/providers/groq.md](docs/providers/groq.md) and `.env.example`.

**Stack + DigiChat web UI** (http://127.0.0.1:3005):

```bash
make up-digichat
```

DigiChat is behind the Compose profile `digichat` (not started by `make up` alone). See `digichat/ARCHITECTURE.md` in the nested repo for `AUTH_URL`, dev auth, and API keys.

**Faster UI iteration:** `make up` (core stack only), then `make digichat-dev` — Next.js on port **3000** with hot reload, talking to DigiGraph on **8000**.

**No Docker for backends:** `make stack-local` (Python services + LiteLLM on **8000–8003** / **4000**), then `make digichat-dev`. Stop with `make stack-local-stop`.

**Smoke test:**

```bash
curl -s -X POST http://127.0.0.1:8000/workflow \
  -H "Content-Type: application/json" \
  -d '{"prompt":"Build me a mean-reversion stat-arb on tech","session_id":"test-1"}' \
  | python3 -m json.tool
```

## Services

| Service   | Port | Role              |
|-----------|------|-------------------|
| DigiGraph | 8000 | Orchestration, chat API |
| DigiQuant | 8001 | Backtest, optimize, MCP |
| DigiSearch| 8002 | Document search, RAG |
| DigiSmith | 8003 | Observability status API |
| LiteLLM   | 4000 | LLM routing       |
| DigiKey   | 8005 | API keys + JWT exchange |
| DigiChat  | 3005 | Chat UI + BFF (profile `digichat`) |

All bind to `127.0.0.1`. Use Tailscale or Cloudflare Tunnel for remote access.

## Tests

```bash
make test        # unit + e2e (if stack up)
make test-unit   # unit only
make test-e2e    # e2e (requires make up)
```

With venv: `pytest -v` or `pytest -m unit -v`.

## Repository layout

```
digithings/
├── digigraph/    # LangGraph orchestration, agents, Digistore
├── digiquant/    # Nautilus + Polars, backtest/optimize
├── digisearch/   # RAG, document search, ingestion
├── digichat/     # Next.js BFF + chat UI
├── digikey/      # API keys + JWT
├── digismith/    # Tracing helpers + status API
├── digiclaw/     # Heartbeat, audit, MCP skill
├── digibase/     # Shared HTTP/audit library
├── config/       # LiteLLM, model modes
├── projects/     # Confidential pilots/engagements (gitignored)
├── scripts/      # Makefile-driven helpers
├── tests/        # pytest (dg, dq, ds, dc, ...)
├── docs/         # VISION, ADRs, scoring rubrics, workflow
├── docker-compose.yml
├── Makefile
└── .env.example
```

## For AI coding agents

1. Read [AGENTS.md](AGENTS.md) — rules, scoring gates, workflow.
2. Read [docs/agents/AGENT_WORKFLOW.md](docs/agents/AGENT_WORKFLOW.md) — end-to-end workflow.
3. Before touching a component, read its `ARCHITECTURE.md`.

## License

**DigiThings** is open-core on GitHub under [MIT](LICENSE). Commercial options (managed hosting, Atlas execution layer, multi-tenant DigiBase, client consultancy) are tracked in [docs/VISION.md](docs/VISION.md).
