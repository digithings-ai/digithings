# Main Workflow Walkthrough: Prompt → Response

Step-by-step flow from user prompt to final response. Run with stack up: `docker compose up -d`.

---

## Step 1: User prompt (entrypoint)

**What happens:** User (or DigiClaw/API client) sends a natural-language request to DigiGraph.

**Example:** `"Build me a mean-reversion stat-arb on tech"`

**How to run:**
```bash
curl -s -X POST http://127.0.0.1:8000/workflow \
  -H "Content-Type: application/json" \
  -d '{"prompt":"Build me a mean-reversion stat-arb on tech","session_id":"walkthrough"}'
```

**Behind the scenes:** DigiGraph `POST /workflow` receives the body, maps it to `WorkflowRequest`, and calls `run_digigraph_workflow(req)`.

---

## Step 2: Audit and graph invocation

**What happens:**
- `workflow_start` is written to the audit log (DigiGraph or shared audit volume).
- The LangGraph workflow is built: **START → research → backtest → END**.
- The graph is invoked with initial state: `{ "prompt", "session_id" }`.

**Code:** `digigraph/workflow.py` → `dg_audit_log("workflow_start", ...)` then `graph.invoke(initial)`.

---

## Step 3: Research node (agentic interaction)

**What happens:**
- The **research** node (Data Science Family) runs.
- DigiGraph calls the LLM via `chat_completion()` (OpenAI-compatible: LiteLLM → Ollama Cloud, OpenAI, etc.).
- **System prompt:** Ask for a JSON with `strategy_name` and `symbols` inferred from the user message.
- **User message:** The original prompt.
- If the LLM returns valid JSON, it is parsed and `strategy_name` and `symbols` are taken from it (`research_note = "LLM-extracted"`).
- If the LLM fails or returns invalid JSON, the **heuristic fallback** runs: keyword rules (e.g. "stat-arb" → `mean_reversion_stat_arb`, "tech" → tech symbols).

**Output state:** `strategy_name`, `symbols`, `research_note` are added to the graph state.

**Code:** `digigraph/graph/nodes.py` → `research_node()`, `digigraph/llm.py` → `chat_completion()`.

---

## Step 4: Backtest node → DigiQuant (data & strategy testing)

**What happens:**
- The **backtest** node runs with state from the research node.
- DigiGraph sends **HTTP POST** to DigiQuant: `POST {DIGIQUANT_URL}/run_backtest` with body `{ "strategy_name", "symbols" }`.
- DigiQuant receives the request and calls `run_backtest(strategy_name, symbols)`.

**Inside DigiQuant:**
- **Data:** Nautilus loads bundled test data (e.g. ETHUSDT). Nautilus is required; if unavailable, DigiQuant returns 503.
- **Strategy testing:** A real NautilusTrader backtest runs. No stub; install `digiquant[nautilus]` and ensure test data.
- **Audit:** DigiQuant writes `run_backtest` to the audit log (run_id, strategy_name, symbols).
- DigiQuant returns the `BacktestResult` (JSON) to DigiGraph.

**Code:** `digigraph/graph/nodes.py` → `backtest_node()` (httpx POST); `digiquant/server.py` → `api_run_backtest()`; `digiquant/backtest.py` → `run_backtest()`.

---

## Step 5: Optimize (optional – not in default workflow)

**What happens:** The default workflow is **research → backtest** only. To include optimization:

- Call **pipeline** or **optimize** explicitly:
  - `POST /run_pipeline` runs: backtest → optimize → export (export writes JSON artifact; platform deploy not implemented).
  - `POST /run_optimize` runs a grid over param sets, each calling `run_backtest`, and returns the best by objective (e.g. Sharpe).

**How to run (after Step 1):**
```bash
# Optimize only (same strategy/symbols as workflow, grid over params)
curl -s -X POST http://127.0.0.1:8001/run_optimize \
  -H "Content-Type: application/json" \
  -d '{"strategy_name":"mean_reversion_stat_arb","symbols":["AAPL","MSFT","GOOGL","NVDA","META"],"param_grid":[{},{}],"objective":"sharpe"}'

# Full pipeline: backtest → optimize → export (export is stub)
curl -s -X POST http://127.0.0.1:8001/run_pipeline \
  -H "Content-Type: application/json" \
  -d '{"strategy_name":"mean_reversion_stat_arb","symbols":["AAPL","MSFT","GOOGL"]}'
```

**Data/strategy:** Same as backtest; optimize runs multiple backtests and picks the best.

---

## Step 6: Response to user

**What happens:**
- The graph finishes; final state contains `backtest_result` (and possibly `error`).
- If there was an error (e.g. DigiQuant down), `workflow_end` is logged with `success: false` and the user gets a failure message.
- Otherwise, DigiGraph builds a success message string (strategy name, symbols, return %, trades), logs `workflow_end` with `success: true` and `run_id`, and returns a **WorkflowResult**: `success`, `message`, `backtest_result` (the full backtest JSON).

**API response:** HTTP 200 with JSON body:
- `success`: boolean
- `message`: human-readable summary
- `backtest_result`: object (run_id, strategy_name, symbols, total_return_pct, num_trades, status, etc.)

**Code:** `digigraph/workflow.py` → after `graph.invoke()`, build `WorkflowResult` and return.

---

## Quick run (all-in-one)

With the stack up:

```bash
# 1) Health checks
curl -s http://127.0.0.1:8000/health && echo
curl -s http://127.0.0.1:8001/health && echo

# 2) Full workflow (prompt → research → backtest → response)
curl -s -X POST http://127.0.0.1:8000/workflow \
  -H "Content-Type: application/json" \
  -d '{"prompt":"Pairs trade SPY and QQQ with 2-day lookback","session_id":"walkthrough"}'
```

Then inspect the audit log (if configured):
- `digiquant/results/audit/events.jsonl` should contain `workflow_start`, `run_backtest`, `workflow_end`.

---

## Example run (summary)

| Step | Action | Result |
|------|--------|--------|
| 1 | User prompt: "Pairs trade SPY and QQQ with 2-day lookback" | Request hits DigiGraph `POST /workflow`. |
| 2 | Audit + graph | `workflow_start` logged; graph invoked. |
| 3 | Research node | LLM (or heuristic) extracts `strategy_name`, `symbols` → e.g. `mean_reversion_stat_arb`, `["SPY","QQQ"]`. |
| 4 | Backtest node | DigiGraph → DigiQuant `POST /run_backtest`; DigiQuant returns real Nautilus BacktestResult (`run_id` starts with `nautilus-`). |
| 5 | (Optional) | `POST /run_optimize` or `POST /run_pipeline` on DigiQuant for optimize/export. |
| 6 | Response | HTTP 200 with `success`, `message`, `backtest_result` (strategy, symbols, return %, trades). |
