# Runbook: Agent Fault State Clearing (DIG-116)

## Problem

`errorReason` and fault-derived `status` are written on failure and **never reset** when the cause is removed. This causes:

1. **Stale faults read as live** — health reads, escalation metrics, and board views report faults that no longer exist
2. **Wrong model attribution** — faults attach to whatever model is currently in `metadata.slot`, even if that model didn't cause the fault
3. **Inflated fault counts** — metrics are directionally wrong (over-counting) and not symmetric noise

### Live Proof (from DIG-116)

| agent | `metadata.slot` | `status` | `errorReason` | `lastHeartbeatAt` |
| --- | --- | --- | --- | --- |
| **Code reviewer** | `opencode/nemotron-3-ultra-free` | **`running`** | `Error from provider (Console): This model is not available in your country` | **08:27:55Z — minutes ago, and it succeeded** |
| `Impl-3` | `opencode/big-pickle` | `running` | Postgres: `update "heartbeat_runs" set "status"...` | — |
| `Release and ops` | `opencode/space-bunny-free` | `idle` | `continuation_source_context_missing` | — |
| `Keymaster` | `opencode/space-bunny-free` | `error` | `continuation_task_ownership_changed` | — |
| `Impl-1` | `opencode/big-pickle` | `error` | `Rate limit exceeded. Please try again later.` | — |

The Code reviewer row is the proof case: a green heartbeat that leaves a stale geo error in place while the agent is actively working on a different model entirely.

---

## CTO Decision

**Decision 1 — yes, a successful run clears `errorReason`, and it must clear it when the pin changes.**

- `errorReason` and the fault-derived part of `status` are cleared on the **first successful run after a pin change**
- While a pin is being validated, the watchdog compares the `errorReason` slot against `metadata.slot` before it surfaces anything as live
- A fault belonging to a model no longer on the slot is **not a live fault**

**Decision 2 — no heartbeat to prove the review slot is alive.**

- The review slot is on-demand; waking it to demonstrate liveness costs runs and produces a verdict nobody asked for
- The measure of this slot is a real review with real findings (DIG-614 already gave us one — three reproduced blockers on PR #5080)

**Note:** `adapterConfig` comes back `{}` for every agent the CTO does not hold `agents:configure` on. That is **redaction, not an empty pin** — only the CEO holds the grant. Do not read `{}` as "unset".

---

## Fix Specification

### Clear on Successful Run
When a run completes with `status: success` (or equivalent terminal success state):
1. Clear `errorReason` → `null`
2. Clear fault-derived portion of `status` (reset to `idle` or `running` as appropriate)

### Clear on Pin Change (`metadata.slot`)
When `metadata.slot` changes (detected via webhook or periodic poll):
1. If `errorReason` references a model no longer in `metadata.slot`, clear `errorReason` → `null`
2. Clear fault-derived portion of `status`

### Watchdog Pre-Flight Check
Before surfacing any agent fault as "live" in metrics, dashboards, or escalation:
1. Read `errorReason` and extract the model/slot it references (if any)
2. Read current `metadata.slot`
3. If they differ → treat as **stale**, do not surface as live fault
4. Log the stale fault for audit trail

---

## Implementation Checklist (Paperclip Control Plane)

The fix must be implemented in the Paperclip control plane (separate service, not in this repo):

- [ ] **Run completion handler**: On run success, PATCH agent with `errorReason: null` and reset fault-derived `status`
- [ ] **Pin change detector**: On `metadata.slot` change, compare against `errorReason`; if mismatched, clear both fields
- [ ] **Watchdog pre-flight**: Add slot comparison check before emitting fault metrics/alerts
- [ ] **Audit log**: Record every clear operation with timestamp, trigger (success/pin-change), and previous `errorReason` value
- [ ] **Backfill**: One-time script to clear stale `errorReason` on all agents where `errorReason` slot ≠ `metadata.slot`
- [ ] **Tests**: Unit tests for each clear path; integration test simulating pin change + stale fault
- [ ] **Deploy**: Roll out behind feature flag; verify on the five affected agents from the live proof table

---

## Verification

After deployment, verify on the five affected agents:

| agent | expected `errorReason` | expected `status` | pass criteria |
| --- | --- | --- | --- |
| Code reviewer | `null` | `running` / `idle` | No geo error while slot is `nemotron-3-ultra-free` |
| Impl-3 | `null` | `running` / `idle` | No Postgres error on healthy run |
| Release and ops | `null` | `idle` | No continuation fault on idle agent |
| Keymaster | `null` | `idle` / `error` (only if *current* run failed) | No ownership fault on current slot |
| Impl-1 | `null` | `idle` / `error` (only if *current* run failed) | No rate-limit error on current slot |

**Metric check**: Escalation rate must drop to reflect only *current* model faults, not historical ones.

---

## IT Support Runbook

### Diagnose
1. Read agent state: `GET /api/agents/{id}` → check `errorReason`, `status`, `metadata.slot`
2. Compare `errorReason` referenced slot vs `metadata.slot`
3. If mismatched → **stale fault confirmed**

### Remediate (Manual Override)
If control plane fix not yet deployed:
```bash
# Clear stale errorReason via control plane API
PATCH /api/agents/{id} \
  -H "Authorization: Bearer <token>" \
  -d '{"errorReason": null, "status": "idle"}'
```
**Only do this when** `errorReason` references a model not in `metadata.slot` and the agent is demonstrably healthy (recent successful heartbeat).

### Escalate
If stale faults persist after control plane deploy:
1. File incident with `IT:` prefix
2. Tag Paperclip control plane team
3. Include agent IDs, stale `errorReason` values, and `metadata.slot` values

---

## Related

- **DIG-116** — Original issue with live proof and CTO decisions
- **DIG-65** — Slot audit that found "escalation rate is unusable"
- **DIG-49** — Previous attempt (incorrectly targeted `adapterConfig.model`)
- **DIG-614** — Code reviewer produced three reproduced blockers on PR #5080
- **DIG-345** — Pre-flight detector work (todo)

---

*Created: 2026-10-05 | Owner: IT Support | Decision: CTO*