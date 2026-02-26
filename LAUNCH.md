# Phase 4 – Launch & Monetization

**Purpose:** Checklist and notes for open-source release, DigiQuant pack, and launch (ROADMAP Phase 4).

## v0.1 limitations (pre-publish)

- **Backtest:** Pass `data_path` or `data_dir` to run on user OHLCV CSVs (any time series). Without it, uses bundled ETHUSDT; user symbols echoed. Set `NAUTILUS=0` to build without Nautilus (endpoints return 503).
- **Export / TradingView / brokers:** Export writes real JSON artifacts; platform deploy (TradingView/Alpaca/QuantConnect) not implemented. Broker adapters raise `NotImplementedError`.
- **ADDM:** Stub; `check_drift` always returns `drift_detected: false`. No production drift detection in v0.1.
- **MCP / Graphiti:** Not implemented; DigiGraph calls DigiQuant via HTTP only.
- **OpenClaw:** Gateway and custom skill deferred; heartbeat and audit run standalone.

## Open-source release (DigiGraph + DigiClaw templates)

- [ ] Create public GitHub repo (or use existing); ensure no secrets in history (`.env` in `.gitignore`).
- [ ] Publish: DigiGraph, DigiClaw (heartbeat + audit + skills contract), config (litellm, model_modes), Docker Compose for open-core stack. Optionally exclude or separate DigiQuant pack (paid).
- [ ] README: Quick start, link to DIGI.md, ARCHITECTURE.md, ROADMAP.md, SECURITY.md, DEPLOY.md.
- [ ] Tag first release (e.g. `v0.1.0`) after first successful `make test-unit` and `make test-e2e` on CI.

## DigiQuant pack (paid, self-hosted)

- **Positioning (from DIGI.md / README):** Open-core DigiGraph + DigiClaw; paid DigiQuant pack for full backtest/optimize/export pipeline (Nautilus, Polars, VectorBT Pro, broker adapters). Pricing placeholder: $199/mo or $4,999 one-time (update in README/DIGI.md when set).
- [ ] Package: `make package` produces `digi-bundle-*.tar.gz`; for paid pack, add optional DigiQuant-only artifact or license gate (document in this file when implemented).
- [ ] Distribution: Self-hosted download or private repo; license key or invoice workflow (out of scope for this repo; track here).

## Montréal AI/FinTech launch & content

- [ ] Event/launch: Montréal AI or FinTech meetup / conference (log date and link in this file).
- [ ] Content: Blog, LinkedIn, or short video on “hedge-fund-in-a-box” and open-core agentic quant stack (link when published).

## Consulting & revenue

- [ ] First consulting clients (note in METRICS.md or here when applicable).
- [ ] Milestone: 10 paying small firms or own live trading capital > $50k (ROADMAP Phase 4 milestone).

## Success metrics (reference)

- Backtest: 10 M rows < 2 s  
- Token reduction: ≥ 70% vs naive LangChain  
- Agent uptime: 99.9% (heartbeat proven)  
- First revenue: within 90 days of open-source release  

Track in **METRICS.md** when created.
