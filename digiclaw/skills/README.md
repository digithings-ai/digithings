# DigiClaw Custom Skills

**Phase 0:** One custom skill that calls DigiGraph.

## run_digigraph_workflow

**Contract (ARCHITECTURE.md):** DigiClaw exposes one custom skill: `run_digigraph_workflow`.

**Behavior:** User chat message (e.g. "Build me a mean-reversion stat-arb on tech") is sent to DigiGraph. DigiGraph runs the workflow (Phase 0: backtest via DigiQuant) and returns a structured result. DigiClaw surfaces the result in chat.

**DigiGraph API (Phase 0):**
- **Endpoint:** `POST {DIGIGRAPH_URL}/workflow`
- **Body:** `{ "prompt": "<user message>", "session_id": "<optional>" }`
- **Response:** `{ "success": true|false, "message": "...", "backtest_result": { ... } }`

**Example (curl):**
```bash
curl -X POST http://127.0.0.1:8000/workflow \
  -H "Content-Type: application/json" \
  -d '{"prompt": "Build me a mean-reversion stat-arb on tech"}'
```

**OpenClaw integration:** When DigiClaw (OpenClaw) is added to the stack, implement this skill as an HTTP call to the DigiGraph service. Set `DIGIGRAPH_URL` (e.g. `http://digigraph:8000`) in the gateway environment so the skill can reach DigiGraph from inside Docker.

**Milestone (Phase 0):** "Build me a mean-reversion stat-arb on tech" returns backtest results in < 10s.
