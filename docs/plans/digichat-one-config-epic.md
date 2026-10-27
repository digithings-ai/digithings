# One config shape per tenant, and a local stack that proves it

Status: **active** (owner decision, 26 Oct 2026: "Both as one epic").

## Goal

Two chats that are the same app must be configured the same way. Today they
are not:

| | digithings chat | OCC chat |
|---|---|---|
| store | KV `config-yaml` | KV `embed-tenants` |
| schema | `DigichatDeployment` | `EmbedTenantConfig`, converted then merged *over* the document |
| gate | `gate.mode` (config) | host hardcoded in `occ-gate.ts:105` and its Pages twin |

Two schemas means two ways to drop a field, and a field dropped on one path is
invisible on the other. That is the shape of the MCP identity bug fixed in
#6493.

## Target

```
apps/digichat/config/
  digithings.yaml      # full deployment document
  occ.yaml             # same schema, different path
```

Both documents are the same schema, loaded by the same loader. OCC's
differences live inside its own YAML: `gate.mode: invite` plus the invite key
reference, its own backend index/path, its own MCP servers, its own tools.

KV keys become `config/digithings.yaml` and `config/occ.yaml`, chosen by
request host. `embed-tenants` becomes a compatibility shim and then retires.

## Slices (dependency order)

### 1. Schema and documents
- Add `invite` to `GateModeSchema` (`schema.ts:56`) and handle every exhaustive
  switch it touches.
- Add `apps/digichat/config/digithings.yaml` (the house document) and
  `apps/digichat/config/occ.yaml` (a full document, not an overlay).
- **Equivalence test is the acceptance bar:** resolving `digithings.ai` and
  `occ.digithings.ai` from these two documents must produce the *same effective
  deployment* as today's document + KV tenant entry. Fixture the current OCC
  entry from KV so drift fails the test.

### 2. KV per-tenant keys
- Write `config/digithings.yaml` and `config/occ.yaml` to the namespace.
- The Worker selects the key by request host.
- Backward compatible: absent new keys fall back to `config-yaml` +
  `embed-tenants` in that order, so a rollback is a KV write, not a deploy.

### 3. Gate from config
- Derive the invite requirement from the resolved deployment
  (`gate.mode: invite`) instead of `INVITE_ONLY_EMBED_HOSTS` in `occ-gate.ts`
  and the Pages twin.
- A host without the gate must still get the site's own 404, byte-identical.

### 4. Local stack
- `make stack-up`: compose (`infra/digichat-release/compose.profile-a*.yml`)
  plus the chat worker with local KV seeded from the two YAMLs.
- One generated env file, so local and deployed share one list of key names.
- `make stack-smoke`: the same assertions against `localhost` and production —
  `/chat` 200, `/chat/occ` 404 without the invite and 200 with it, MCP
  `initialize` 200, one real tool call, and which config source resolved.
- A drift check that fails when a path or key exists in the deployed config but
  not locally.

## Acceptance

- Adding a gated client is a YAML file plus a KV write, with no TypeScript
  constant to edit in two places.
- `make stack-smoke` passes locally and against production, and the same
  failure appears in both when a key or path is wrong.

---

## Worker-first topology (added 26 Oct 2026)

**Owner direction:** remove the Containers and run Worker-first. The chat, the
MCP tools and the stack are not needed continuously, so pay for execution, not
for a box, and accept a bounded cold-start latency in exchange.

This is a **reversal** of the decision of record and has to be recorded as one,
not filed beside it. `DIG-2914` / PR #6497 currently says *keep the box and
clean it*; #4761 says *migrate pipelines onto containers*. Neither closes
itself, and both are contradicted here.

### The arithmetic, stated honestly

- `DIG-2904` is the only place the bill is quantified: **$77/mo**, with
  containers awake **87–146 h/week**.
- `DIG-5549` measured what emptying the box is worth: **$15–27/mo** against
  roughly **61k LOC** to port.

So the saving is real but small, and the case for Worker-first is **latency and
operability**, not the monthly figure: a Worker wakes in milliseconds where a
container cold start has been measured at **42.9 s**. That is the trade being
accepted, and it should be written down as the reason rather than assumed.

Containers are already scale-to-zero (`sleepAfter` 1 m for chat, 5 m for the
stack) — the bill is wake time, not idle time. "Remove the containers" therefore
means *remove the cold start and the runtime*, not *stop paying for idle*.

### Inventory of the work that already exists

| area | item | state | what it covers |
|---|---|---|---|
| container→Worker | `DIG-2912` | in review | digichat container → plain Worker (largest single saving) |
| | `DIG-5548` | done, parked | digikey FastAPI → Worker on D1+KV, 9 routes ported |
| | `DIG-2913` / PR #6466 | merged | Worker-native digiquant MCP, reads R2 |
| | `DIG-5558` | todo | delete the legacy `DigiQuantMcpContainer` |
| | `DIG-2915` | in review | digiquant runner → Mac launchd |
| | `DIG-2916` | blocked (needs owner) | delete the dead `digitrace-langfuse` app and images |
| | `DIG-2914` / PR #6497 | in review | **decision of record: keep the box — must be superseded** |
| | `DIG-5549` / PR #6462 | done | "can the box ever be emptied?" — answer: no/not worth it |
| cost | `DIG-2904` | blocked | the cost epic; must be re-opened, not cited |
| | `DIG-2905/6/7` (#5410–12) | done | right-size, dedupe, `sleepAfter` — already landed |
| | #3851 | closed | scale stack+chat to zero; superseded in execution by 2905/6/7 |
| | #4761 | open | **inverse direction** — pipelines onto containers |
| cold start | #4323 | closed | warm-up "Connecting…", first turn after sleep fails then retries |
| | #4753 | closed | 503 retry budget 15 s vs 240 s boot |
| | #4546 | closed | digikey cold-wake 401/503 race |
| | #4333 (supersedes #4327) | closed | all sleep windows → 15 m |
| | `DIG-2910` | todo | container health check from the Mac |
| MCP edge | `DIG-5629` | todo | digisearch+digivault unavailable in prod (26 Oct) |
| | `DIG-2913` / #4654 | merged/closed | Worker-native MCP discovery routes |
| config | this epic, #6410 | active | one shape per tenant |
| other | #3854 | open | dev duplicates of prod containers |

Superseded/duplicate relations: #4333 ⊃ #4327; PR #6497 ⊃ PR #6462; `DIG-5558`
is the unfinished remainder of `DIG-2913`; #4689 (fold chat Worker into the
stack Worker) is reversed by `DIG-2912`; #4506 superseded by this epic.

### Load-bearing three

1. **`DIG-2904`** — the only quantified budget. Re-open it; a Worker-first case
   that cites a blocked epic is not a case.
2. **`DIG-2914` / PR #6497`** — must be explicitly superseded, or the repo will
   hold two contradictory decisions.
3. **`DIG-2912`** — the only live line that actually deletes a container, and
   the largest saving.

### Sequencing (proposed, to confirm)

1. **Finish the outage class first.** The tenant-config TTL (#6502) and the
   identity key (#6493) are prerequisites: a Worker-first chat that still
   freezes config at boot just gets faster at being wrong.
2. **Slice 2 of this epic** (KV per-tenant keys, gate from config) — the schema
   unification is what makes a port mechanical rather than bespoke.
3. **`DIG-2912`** chat container → Worker, behind a cold-start budget.
4. **MCP edge** — `DIG-5629` and the Worker-native discovery routes; tools must
   not depend on a container hop.
5. **`DIG-5548`** digikey (already ported) → un-park and cut over.
6. **Runners and dead weight** — `DIG-2915`, `DIG-2916`, `DIG-5558`, `#3854`.
7. **Retire `DigiStackContainer` last**, after the three above have run
   Worker-only for a week. `DIG-2914` then gets rewritten as "removed", not
   "cleaned".

### Acceptance for this section

- A stated cold-start budget per surface (p95), with the current container
  number (**42.9 s** measured) recorded beside it.
- No surface depends on a container being warm to answer its first turn.
- The cost epic `DIG-2904` carries the new expected bill, not the old one.
