# Digi Heartbeat Checklist (Phase 3)

**Purpose:** Read by the heartbeat agent every 30–60 minutes. Enables the agent to run checklist-driven tasks without human intervention (see root [SECURITY.md](../../SECURITY.md)).

## 1. Service health

- [ ] Ping DigiGraph `/health` (DIGIGRAPH_URL)
- [ ] Ping DigiQuant `/health` (DIGIQUANT_URL)
- [ ] If any unhealthy: log to audit and optionally alert (Phase 3: log only)

## 2. Portfolio / strategy (when live)

- [ ] Check ADDM drift (digiquant.addm.check_drift) for active strategies
- [ ] If drift detected: trigger re-optimization workflow (Phase 3: stub)
- **v0.1:** ADDM is a stub; drift is never reported. Re-optimization is not triggered.

## 3. Security checklist (every run)

- [ ] Confirm services bound to loopback only (config review)
- [ ] No unapproved MCP skills loaded (when OpenClaw integrated)

## 4. Macro / data (optional)

- [ ] Evaluate macro events or data freshness (Phase 3: placeholder)

---

**How to run (Phase 3):** From repo root with stack up:
```bash
export DIGIGRAPH_URL=http://127.0.0.1:8000
export DIGIQUANT_URL=http://127.0.0.1:8001
export AUDIT_LOG_PATH=./digiquant/results/audit/events.jsonl
python -m digiclaw
```
Or schedule via cron (e.g. every 30 min). With Docker: `docker compose --profile heartbeat up -d` or `make up-heartbeat`.

## 7-day unattended run (Phase 3 milestone)

To run the stack for 7 days without manual intervention:

1. Start with heartbeat: `docker compose --profile heartbeat up -d` (or `make up-heartbeat`).
2. Ensure `digiquant/results/audit` is persisted (default compose volume).
3. Set `REOPTIMIZE_STRATEGY` in the heartbeat service if you use ADDM drift → re-optimize (stub returns no drift by default).
4. No live trading without human gates (SECURITY.md). Monitor audit log and health as needed.
