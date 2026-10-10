# Agent State: errorReason/status Clearing on Success and Pin Change

> **Rule**: Any agent fault state we surface must reflect current reality. Stale faults must not be presented as live.

This document registers the fix for **DIG-116** where `errorReason` and fault-derived `status` were never cleared, causing resolved faults to read as live and get blamed on the wrong model.

---

## DIG-116 Fix: Agent Fault State Management

**Owner**: Platform team (Paperclip control plane)

**Canonical store**: Paperclip control plane agent state database

**Refresh path**: Automatic — on successful run completion AND on pin change (`metadata.slot` change)

**Staleness detector**: Watchdog pre-flight check (compares `errorReason` slot against `metadata.slot`)

---

### Problem

The Paperclip control plane writes `errorReason` and fault-derived `status` on agent failure but **never resets them when the cause is removed**. This causes:

1. Stale faults attributed to whatever model is currently in `metadata.slot` (wrong model blamed)
2. Escalation metrics inflated asymmetrically (always over-counting)
3. Board views and health reads showing faults that no longer exist

**Live proof (2026-10-05)**: Code reviewer agent showed `status: running` with `errorReason: "Error from provider (Console): This model is not available in your country"` (fledge geo block from 03:54:37Z) while actively running on `opencode/nemotron-3-ultra-free` (20/20 eval runs, zero rate limits, heartbeat at 08:27:55Z).

---

### Fix Specification

#### 1. Clear on Successful Run
When an agent run completes successfully (`status` would be `ok`/`running`/`idle` with recent heartbeat):
- Set `errorReason = null`
- Clear fault-derived portion of `status` (retain lifecycle state: `running`/`idle`/`stopped`)

#### 2. Clear on Pin Change
When `metadata.slot` changes (model pin updated):
- Set `errorReason = null` immediately
- Clear fault-derived portion of `status` immediately
- This applies on the **first successful run after pin change** AND proactively on pin change

#### 3. Watchdog Pre-Flight Check
Before surfacing any agent fault as "live" in metrics, board views, or alerts:
```
IF errorReason references a model slot
   AND that slot != current metadata.slot
THEN fault is STALE → do not surface as live
```

---

### Implementation Checklist

- [ ] Paperclip control plane: clear `errorReason` on run success
- [ ] Paperclip control plane: clear `errorReason` on `metadata.slot` change
- [ ] Paperclip control plane: clear fault-derived `status` on run success
- [ ] Paperclip control plane: clear fault-derived `status` on `metadata.slot` change
- [ ] Watchdog: add pre-flight comparison of `errorReason` slot vs `metadata.slot`
- [ ] Metrics/dashboard: only surface faults passing watchdog check
- [ ] Runbook: update IT support runbook with verification steps

---

### Verification (Post-Deploy)

After fix deploys, verify on affected agents:

| Agent | Slot | Expected State |
|-------|------|----------------|
| Code reviewer | `opencode/nemotron-3-ultra-free` | `errorReason: null`, `status: running`/`idle` |
| Impl-3 | `opencode/big-pickle` | `errorReason: null` if Postgres write succeeded |
| Release and ops | `opencode/space-bunny-free` | `errorReason: null` if continuation fault resolved |
| Keymaster | `opencode/space-bunny-free` | `errorReason: null` if ownership change resolved |
| Impl-1 | `opencode/big-pickle` | `errorReason: null` if rate limit cleared |

**Pass criteria**: No agent shows `errorReason` referencing a model not in its current `metadata.slot` while `status` is `running` or `idle` with recent heartbeat.

---

### Runbook for IT Support

**When**: Paperclip agent shows `errorReason` or fault `status` but agent appears healthy (recent heartbeat, `status: running`/`idle`)

**Diagnose**:
1. Read agent state: `metadata.slot`, `errorReason`, `status`, `lastHeartbeatAt`
2. If `lastHeartbeatAt` is recent (< 5 min) and `status` is `running`/`idle` but `errorReason` is set → stale fault
3. Check if `errorReason` text references a model no longer in `metadata.slot` → definitely stale

**Remediate** (until control plane fix deploys):
1. Trigger a successful run for the agent (wake with `failedRunId` if needed)
2. Verify `errorReason` clears and `status` reflects current health
3. If pin changed recently, verify clearing happened on pin change

**Escalate**: If stale state persists after successful run, escalate to Platform team (Paperclip control plane owners).

---

### History

- **2026-10-05**: CTO decision recorded (DIG-116 comment 9cc76c7c)
- **2026-10-05**: Runbook entry created (this document)
- **2026-10-05**: Watchdog rule candidate — promote to automatic after 2 confirmed fixes

---

### Related Credentials

This fix does not involve credential rotation. See `credential-ownership.md` for credential management rules.

---

### Notes

- `adapterConfig` returns `{}` for non-CEO users — this is **redaction**, not an empty pin. Only CEO holds `agents:configure` grant.
- `metadata.slot` is the only persistent model field in the system. `adapterConfig.model` does not persist.
- The review slot (`opencode/nemotron-3-ultra-free`) is on-demand — no heartbeat required. Measure is real review output (DIG-614).