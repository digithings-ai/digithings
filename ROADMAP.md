# Digi Ecosystem Roadmap (February 20, 2026)

**Status:** Living document – update after every phase.  
**Goal:** Ship a working personal agentic hedge fund in < 8 weeks, then productize for small firms.

## Phase 0 – Foundation & Internal Prototype (Now → Feb 27)
- Finalize all documentation (this suite + sub-folder MD files)
- Internal prototype: chat in DigiClaw → simple Nautilus backtest via DigiGraph
- Set up root repo structure, Docker Compose skeleton, LiteLLM router
- Milestone: “Build me a mean-reversion stat-arb on tech” returns backtest results in < 10 s

## Phase 1 – DigiGraph Core (Week of Mar 2 → Mar 20)
- Full LangGraph orchestration with layered agent families
- LiteLLM router + MCP exposure
- GraphRAG with Graphiti (temporal memory)
- One working family (Data Science Family + supervisor)
- DigiClaw custom skill integration
- Milestone: End-to-end idea → researched & cached strategy (no quant engine yet)

## Phase 2 – DigiQuant Pack (Mar 23 → Apr 17)
- NautilusTrader core + Polars data layer
- VectorBT Pro sweeps + Qlib/FinRL ML signals
- TradingView import/export (PyneCore)
- Broker adapters (IB native + Alpaca/QuantConnect stubs)
- ADDM drift detection stub
- Milestone: Full research → backtest → optimize → export pipeline running locally

## Phase 3 – Self-Healing & Production Readiness (Apr 20 → May 15)
- Heartbeat-driven monitoring agents in DigiClaw
- Full self-re-optimization loop
- Security hardening (post-CVE-2026-25253 config)
- One-click Docker packaging for small firms
- Regulatory audit logging (FINRA 2026 compliant)
- Milestone: Run your own 24/7 agentic fund for 7 days without manual intervention

## Phase 4 – Launch & Monetization (May 18 → June 30)
- Open-source DigiGraph + DigiClaw templates on GitHub
- Paid DigiQuant pack release (self-hosted)
- Montréal AI/FinTech launch + content campaign
- First consulting clients & revenue
- Milestone: 10 paying small firms or your own live trading capital > $50k

## Success Metrics (tracked in root `METRICS.md` later)
- Backtest speed: 10 M rows < 2 s
- Token reduction: ≥ 70 % vs naive LangChain
- Agent uptime: 99.9 % (heartbeat proven)
- First revenue: within 90 days of open-source release

**Next Action:** Phase 4 — Launch, monetization, open-source templates; or Phase 1 deferred: MCP tools, DigiClaw (OpenClaw) skill.

---

## Phase 0 Progress (Feb 20, 2026)

- [x] Root repo structure: `docker-compose.yml`, `.env.example`
- [x] LiteLLM config skeleton: `config/litellm.yaml`
- [x] DigiQuant: HTTP server + `run_backtest` (Phase 0 stub < 10s), Pydantic `BacktestResult`
- [x] DigiGraph: HTTP server + `POST /workflow` (run_digigraph_workflow) calling DigiQuant
- [x] DigiClaw: skill contract documented in `digiclaw/skills/README.md`
- [x] **Verify:** Local run: DigiQuant (8001) + DigiGraph (8000) → `curl -X POST http://127.0.0.1:8000/workflow -H "Content-Type: application/json" -d '{"prompt":"Build me a mean-reversion stat-arb on tech"}'` returns backtest result in < 10s. Docker: `docker compose up --build` then same curl.
- [x] Phase 0 tests: `make test-unit` (35 tests), `make test-e2e` (4 tests) passing. Dockerfiles fixed (COPY src before pip install).
- [x] Docker + Ollama setup documented (`DOCKER.md`, `.env.example`).

**Phase 0 complete (Feb 20, 2026).**

---

## Phase 1 – Getting started (Mar 2 → Mar 20)

- [x] LangGraph skeleton: `digigraph/graph/` (state, nodes: research + backtest, graph builder). Flow: START → research → backtest → END.
- [x] Research node (Data Science Family): LLM extracts strategy + symbols (OpenAI-compatible: Ollama/LiteLLM/OpenAI); heuristic fallback.
- [x] `POST /workflow` runs through graph; same `WorkflowResult` contract; all Phase 0 + e2e tests pass.
- [x] LiteLLM in compose + DigiGraph calls it for chat (OPENAI_API_BASE=http://litellm:4000/v1; LiteLLM default in stack).
- [x] Ollama Cloud + model modes: `config/model_modes.yaml`, `DIGI_LLM_MODE` (test|medium|best), `config/MODELS.md`. `GET /test_llm` for LLM sanity check.
- [ ] **Deferred to Phase 2:** MCP exposure (research, backtest as discoverable MCP tools); DigiClaw custom skill integration (OpenClaw → DigiGraph); Graphiti/GraphRAG stub or design.

**Phase 1 core complete (Feb 2026).** Idea → researched strategy + symbols → stub backtest in &lt; 10s; LLM path verified via LiteLLM/Ollama Cloud.

**Next action:** Phase 2 — NautilusTrader core, Polars data layer, full backtest pipeline; then MCP tools and DigiClaw skill.

---

## Phase 2 – DigiQuant Pack (Mar 23 → Apr 17)

- [x] Polars data layer: `digiquant/data/` — `load_ohlcv_csv`, `generate_synthetic_ohlcv`, `list_symbols_from_dir`. OHLCV contract; no pandas.
- [x] NautilusTrader core: optional `digiquant[nautilus]`; `run_backtest()` runs real backtest when Nautilus installed (bundled test data), maps to `BacktestResult`; else Phase 0 stub.
- [x] ADDM drift detection stub: `digiquant/addm.check_drift()` returns no-drift placeholder.
- [x] Optimize: `run_optimize()` + `OptimizeResult`; grid over backtests; HTTP `POST /run_optimize`.
- [x] Export: `run_export()` + `ExportResult`; stub targets nautilus | tradingview | alpaca | quantconnect; HTTP `POST /run_export`.
- [x] Pipeline: `POST /run_pipeline` runs backtest → optimize → export in sequence.
- [x] Sweep stub: `run_sweep()` (loop over param_grid); VectorBT Pro integration later.
- [x] Broker adapters: `digiquant/brokers/` — protocol + IB, Alpaca, QuantConnect stubs (NotImplementedError).
- [x] TradingView/PyneCore stub: `digiquant/tradingview.py` — `export_to_pine` / `import_from_pine` stubs.
- [x] Milestone: Full research → backtest → optimize → export pipeline running locally (optimize/export stubs; real Nautilus backtest when installed).

**Phase 2 complete (Feb 2026).** Pipeline: backtest → optimize → export with HTTP API; Polars data layer; Nautilus optional; ADDM, brokers, TradingView stubs in place.

**Phase 2 wrap-up (validation):** 98 unit tests pass; 7 e2e pass with stack up; no linter errors; docs (ROADMAP, DIGIQUANT, tests/README) updated. Ready for Phase 3.

**Next action:** Phase 3 — Self-healing, monitoring, security hardening; or Phase 1 deferred: MCP tools, DigiClaw skill.

---

## Phase 3 – Self-Healing & Production Readiness (Apr 20 → May 15)

- [x] **HEARTBEAT.md** — Checklist for heartbeat agent (health, security, ADDM placeholder). Read by runner every 30–60 min.
- [x] **Audit logging** — `digiclaw/audit.py`: `audit_log(event_type, agent_id, payload)` writes JSONL to `AUDIT_LOG_PATH` (FINRA 2026–style trail; secrets redacted).
- [x] **Heartbeat runner** — `python -m digiclaw`: pings DigiGraph/DigiQuant health, logs to audit; run via cron or Docker profile.
- [x] **Docker profile `heartbeat`** — `docker compose --profile heartbeat up` runs heartbeat service (loop every 30 min).
- [x] **Security / Docker** — SECURITY.md and DOCKER.md updated (loopback-only, Phase 3 heartbeat, no public ports).
- [x] Self-re-optimization loop: DigiQuant `GET /check_drift`; heartbeat calls it and triggers `POST /run_optimize` when `drift_detected` (ADDM still stub).
- [x] One-click packaging: `scripts/package.sh` + `make package` → `digi-bundle-YYYYMMDD.tar.gz`; **DEPLOY.md** for small-firm steps.
- [x] Full regulatory audit logging from DigiGraph/DigiQuant: `digigraph/audit.py` and `digiquant/audit.py` (same JSONL format); workflow start/end and run_backtest/run_optimize logged.
- [x] 7-day run: **HEARTBEAT.md** and **DEPLOY.md** document unattended run with heartbeat; milestone = run with `--profile heartbeat` and monitor audit.

**Phase 3 complete (Feb 2026).** Self-re-optimization loop wired; audit from DG/DQ; packaging and 7-day runbook in place.

**Phase 3 validation (pre–Phase 4):** 100 unit + 7 e2e tests pass; no linter errors; HEARTBEAT.md and DIGICLAW.md aligned (run command, ADDM/re-optimize); workflow logs `workflow_end` on error path; audit JSONL format consistent across digiclaw, digigraph, digiquant. Ready for Phase 4.

---

## Phase 4 – Launch & Monetization (May 18 → June 30)

- [x] **Open-source readiness** — LICENSE (MIT) at repo root; README, CONTRIBUTING, AGENTS.md in place; `make package` for bundle; **LAUNCH.md** with release checklist and DigiQuant pack notes.
- [ ] Publish DigiGraph + DigiClaw templates to GitHub (public repo; exclude DigiQuant pack or publish open-core subset).
- [ ] DigiQuant pack: paid self-hosted offering (pricing placeholder in DIGI.md/README; packaging and distribution docs in LAUNCH.md).
- [ ] Montréal AI/FinTech launch + content campaign (out of scope for code; track in LAUNCH.md).
- [ ] First consulting clients & revenue (out of scope for code; track in LAUNCH.md).
- [ ] Milestone: 10 paying small firms or live trading capital > $50k (business outcome; track in LAUNCH.md or METRICS.md).

**Phase 4 started (Feb 2026).** Repo is open-source ready (LICENSE, LAUNCH.md, docs). Next: GitHub publish, DigiQuant pack packaging, launch/monetization execution.

This roadmap is the binding delivery plan for every coding agent.