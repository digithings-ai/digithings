# digitrace tracing architecture review (v2.1 — Cloudflare hybrid with MLflow)

**Reviewer:** Claude consultant (seat 42609dd2), DIG-2664
**Date:** 2026-10-09
**Scope:** design doc `free-tracing-options.md` v2.1 (Chris-approved 2026-10-09 21:34 CEST), judged against digithings `develop` @ `203684dcf0`
**Gates:** DIG-2655–DIG-2663 (backlog, unassigned), parked pending this verdict

## Verdict: **APPROVE WITH CHANGES**

Option E (Cloudflare-owned ingest/store, OSS UI on demand) is the right call, and the elimination of ClickHouse/Redis-dependent tools (Langfuse, Opik, SigNoz, Helicone, …) in favor of Postgres-only MLflow is sound reasoning the repo evidence doesn't contradict. But the design was written without reading three pieces of this repo's own history that each change scope or sequencing: an accepted ADR that rejected the exact pattern (separate Postgres schema) this design re-proposes, a still-in-tree Langfuse implementation this design silently supersedes, and digitrace's own architecture doc, which states a zero-dependency philosophy this design discards without updating. None of these are reasons to reject the plan — they're reasons the first ticket (DIG-2655) can't just be "close DIG-2644/DIG-2645" as drafted.

Six **must** items gate DIG-2655–2658 before implementation starts; the rest are sequencing/consistency fixes that don't block starting work.

---

## 1. OTLP span attributes & PII redaction (`digitrace/src/digitrace/trace.py`)

Confirmed as stated in the design: the OTel leg (`_maybe_wrap_otel`, Phase 2 / #4931, already shipped) opens one span `digitrace.<name>` carrying only `digi.workflow_id` / `digi.request_id` / `digi.session_id` (≤128 chars, dropped not truncated if longer) — zero `gen_ai.*`/OpenInference attributes, no I/O, no tokens, no model, no cost. `PiiRedactor` (`digitrace/src/digitrace/redaction.py`) is wired today **only** into the LangSmith leg via `langsmith.traceable`'s `process_inputs`/`process_outputs` hooks; the OTel leg is redaction-exempt only because it currently carries no payload. `digitrace/ARCHITECTURE.md` §11 already self-documents the gap this design needs to close: redaction is value-pattern only (email/API-key-prefix/phone + env-supplied regexes), with **no key-name allowlist and no document-body summarization** — both flagged as "Placeholder / stub" in the repo's own component table.

That gap matters more once this ships, because the destination changes: today a redaction miss leaks into LangSmith (a single SaaS vendor with its own deletion tooling); after DIG-2656/2657 land, a miss lands in R2 + the Supabase `digitrace` index, which DIG-2661's dashboard then serves to **whichever tenant's dashboard session queries it** — a durable, multi-tenant-readable store, not a single-vendor sink. Value-pattern regex redaction (no key-name denylist) is not strong enough to be the only control for content that becomes both durable and multi-tenant-visible.

- **Must (DIG-2656):** Don't put raw prompt/completion text on the OTel span at all, even redacted. Emit length + hash (or a short truncated preview behind a sampling/opt-in flag), matching the "document bodies (summarize or hash instead)" line already in `trace.py`'s own forbidden-attribute contract (`ARCHITECTURE.md` §4). Raw I/O capture, if wanted later, is a separate decision with its own retention/access story, not a default of the enrichment ticket.
- **Must (DIG-2656):** Define an explicit attribute-key allowlist for what the enrichment layer will set (`gen_ai.request.model`, `gen_ai.usage.*`, `digi.tenant_id`, etc.). Don't let callers pass arbitrary `**kwargs` straight onto span attributes — that reopens exactly the key-name-leak gap `ARCHITECTURE.md` already flags, just on a new, more exposed leg.
- **Should (DIG-2656):** Reuse `PiiRedactor.process_inputs`/`process_outputs` directly on the OTel attribute payload (they're already dict-in/dict-out, not LangSmith-SDK-specific) rather than writing a second redaction call path.

## 2. Ingest Worker + Queue (auth, tenant stamping, sampling, backpressure, retries)

Cloudflare Queues are **not used anywhere in this repo today** (`grep` across all `wrangler.toml` for `[[queues` returns nothing) — this is a new primitive for the monorepo, so there's no in-repo retry/DLQ/backpressure convention to inherit; DIG-2657's AC ("vitest, `wrangler dev` local mode, per-tenant tokens in KV, backlog test") should explicitly add `max_retries` + `dead_letter_queue` config, since CF Queues support both natively and nothing here will catch their absence by accident.

Tenant stamping is the bigger issue. digikey already owns a tenant-verification convention: `TokenClaims`/`DigiAuthContext` carry `tenant_slug` **plus a `tenant_slug_verified: bool`** flag that is `True` only when the slug came from a signed JWT claim, `False` when it fell back to an unsigned `X-Digi-Tenant` header (`digikey/src/digikey/integrations/service_middleware.py`, explicitly referencing a past issue, #2303, about not trusting the unverified path). The design's "stamp tenant.id from the per-tenant ingest token (never trust client attribute)" is the right instinct but invents a parallel, bespoke auth scheme instead of reusing or extending this existing verified/unverified distinction.

- **Should (DIG-2657):** Either route ingest auth through digikey's existing API-key→JWT exchange (the pattern `digichat-cloudflare` and `digithings-stack-cloudflare` already use via `DIGIKEY_URL`/`DIGIKEY_BFF_TOKEN`), or, if a lighter static per-tenant token is chosen for latency/cost reasons on a high-volume ingest path, carry the equivalent of `tenant_slug_verified` through to the stored span/trace row and document the deviation from the digikey convention explicitly in the ADR (DIG-2655) rather than leaving it implicit.
- **Could (DIG-2657):** Confirm CF Queues' per-batch max (100 messages) against expected burst volume from Workers-native-traces fan-in (DIG-2659) before sizing the consumer.

## 3. R2 archive layout & lifecycle

Greenfield — no existing R2 usage in the repo has a date/tenant-partitioned key convention to inherit (the three existing bindings are flat/ticker-keyed or a reserved-but-unused binding for `digitrace-langfuse`'s S3-style uploads), so there's nothing to conform to here. One internal inconsistency in the design itself, though: §3 and §4 state R2 lifecycle = 180 days while the Supabase index retention (DIG-2658) is 90 days.

- **Should (DIG-2658/2662):** State explicitly whether replay beyond 90 days is supported. If the Supabase index (which DIG-2662's `digitrace replay` presumably uses to find R2 objects) is pruned at 90 days but R2 objects live to 180, replaying day 91–180 means enumerating R2 by prefix with no index — decide now whether that's an intentional "cold, slow, rare" tier or just an unreviewed mismatch between two tickets' AC.

## 4. Supabase `digitrace` schema & tenant isolation (RLS, connection limits)

This is the finding most likely to change scope, not just detail. **ADR-0021** (accepted 2026-06-25, same `core` project this design targets) explicitly considered and rejected a separate Postgres schema for tenant isolation: *"A separate Postgres schema inside `core`... Rejected as needless: `public` + per-table RLS already gives the isolation... and a second schema complicates PostgREST exposure... for no gain at this scale."* The established, working pattern in this exact project is `public` schema + a `workspace_id` column + RLS policies keyed on `auth.uid()` via a membership table (`digiquant/supabase/migrations/098_workspaces_rls_policies.sql`). The v2.1 design proposes a new `digitrace` schema now and an `mlflow` schema later, with no acknowledgment of ADR-0021.

It may well be that digitrace's case is genuinely different — ADR-0021's objection was specifically about PostgREST exposure, and the current design has the Worker/dashboard-api reading `digitrace` tables via **service-role** credentials (bypassing PostgREST's anon/authenticated surface entirely), which may sidestep the exact concern ADR-0021 raised. But that argument needs to be made, not skipped.

A second, related point: if the consumer Worker and dashboard-api read/write via **service-role**, then "RLS by tenant" on the `digitrace` tables is largely decorative — service-role bypasses RLS by definition in Postgres/Supabase. The real tenant-isolation boundary is the application-layer filter in the consumer Worker and dashboard-api (i.e., "does this query include `WHERE tenant_id = :caller's_verified_tenant`"), not Postgres RLS. The design should say that plainly rather than implying RLS is doing isolation work it structurally cannot do under a service-role access pattern.

Connection limits: no Worker in this repo opens a direct Postgres connection today — every existing Worker (`dashboard-api`, `digithings-stack-cloudflare`) talks to Supabase exclusively via PostgREST/REST with a service-role key. The one direct-Postgres precedent in the repo, `digichat`'s Node/Drizzle pool (`max: 10` per replica), is a **long-lived container process**, not a stateless edge Worker, and even that pattern already earned an explicit warning in `digichat/ARCHITECTURE.md` about connection multiplication across replicas ("use PgBouncer... or reduce `max` per replica"). A stateless Worker opening direct Postgres connections per queue-batch invocation, with no Hyperdrive/Supavisor pooling in front of it, is a materially bigger multiplication risk than the thing that already drew a warning — Workers scale out per-isolate far more elastically than a fixed container replica count. "≤5 connections" doesn't mean much without saying per-what.

- **Must (DIG-2655, DIG-2658):** The ADR ticket must explicitly address ADR-0021 — either justify the schema-per-feature deviation (service-role access bypasses the PostgREST-exposure objection ADR-0021 raised) or conform to the established `public` + prefixed-table + RLS pattern. Don't let two contradictory, un-cross-referenced Postgres-topology decisions sit in the same project.
- **Must (DIG-2658):** Write down what "≤5 connections" actually bounds (per-isolate? global steady-state? burst ceiling against Supabase Pro's connection limit for `core`?), and prefer the repo's only precedented Worker→Supabase pattern — PostgREST/REST upserts from the consumer Worker — over a raw direct-Postgres driver, unless Hyperdrive is explicitly adopted to solve exactly this pooling problem. This also removes the need to introduce a genuinely novel connection pattern for a cost-sensitive edge Worker.
- **Should (DIG-2658/2661):** State plainly that RLS is not the tenant-isolation boundary when access is service-role-only, and that the real boundary is the application-layer tenant filter in the consumer Worker and dashboard-api — then make sure DIG-2661's AC includes a test for that filter, since that's where an isolation bug would actually live.

## 5. Workers Analytics Engine

Confirmed fully unused anywhere in this repo today (`grep` for `analytics_engine`/`AnalyticsEngineDataset` returns nothing) — this is a new binding type with zero in-house operating experience behind it. WAE write-path is fire-and-forget from the Worker binding with no read-after-write guarantee, and Cloudflare samples WAE data under high write volume, which the design's "tokens/cost/latency per tenant/model" dashboard treats as an exact source of truth.

- **Should (DIG-2657/2661):** Timebox a small spike against WAE's SQL API (query latency, cardinality limits, sampling behavior at expected write volume) before the dashboard (DIG-2661) is built to depend on WAE as its metrics source of record. If sampling turns out to matter at this volume, the AI Gateway logs cross-check the design already proposes becomes load-bearing rather than optional.

## 6. Dashboard Traces tab (dashboard-api)

Structurally this fits cleanly: `dashboard-api` already uses one-TS-file-per-feature (`ledger.ts`, `tables.ts`, `performance.ts`, …) registered centrally in `src/index.ts`, and the Next.js `dashboard` app already uses one-folder-per-page with sub-tab components (`components/settings/*-tab.tsx`) — a `traces.ts` + a traces tab component is a straight fit, no new structural pattern needed.

- **Could (DIG-2661):** `app/observability/page.tsx` already exists today as a legacy-SPA redirect (→ `/system` → `/pipeline`). Decide up front whether "Traces tab" reuses/replaces that route or is a wholly new nav item, to avoid a second observability-shaped route confusing future readers.

## 7. MLflow 3.6+ replay over OTLP/HTTP

No existing MLflow usage anywhere in the repo (confirmed greenfield) — no conflicts to flag. The OTLP/HTTP-only (no gRPC) choice actually matches the repo's existing exporter choice in `digibase/otel.py` (`OTLPSpanExporter` from the HTTP/protobuf module, chosen specifically to avoid the gRPC dependency) — a real, if coincidental, point of alignment worth keeping in the ADR as a positive argument for MLflow over gRPC-only alternatives.

- **Could (DIG-2662):** The CF Containers precedent in this repo (`digiquant-runner`, `digichat-cloudflare`, `digitrace-langfuse`) is all always-on-ish service containers behind a Durable Object, not scale-to-zero on-demand UI containers. `sleepAfter`-based wake latency for a debugging session is a real but minor UX cost worth a line in the ticket, not a blocker.

## 8. Local vs cloud parity

The `wrangler dev` + Miniflare-backed local Queue/R2 approach is the standard, correct way to get parity here — no issue. One omission: local mode also requires Docker (for MLflow) even though Docker wasn't listed among the task's stated constraints.

- **Could (DIG-2662):** Note Docker Desktop (or equivalent) as an explicit local-mode prerequisite in the replay CLI's README, since it's otherwise an implicit new dependency for anyone running "local mode."

## 9. Module boundaries, scaling limits, $0 cost claims, alternatives

The alternatives analysis (§2–3 of the design doc) holds up against the repo: no OSS tracing UI runs on workerd itself, and of the Postgres-only options, MLflow (Apache-2.0) over Phoenix (Elastic 2.0, not OSI) is a reasonable, defensible call given the "repo is open source" constraint. No pushback on the scoring/elimination logic itself.

Where this item does need work: digitrace's own `ARCHITECTURE.md` states the design philosophy this v2.1 plan overturns — *"digitrace should be invisible when working and loud when something breaks,"* *"zero dependencies beyond FastAPI and Pydantic,"* *"no database, no background worker, no queue."* `docs/vision/digitrace.md` (status: "reviewed," last touched 2026-04-19) describes the same minimal-footprint intent. The v2.1 design is roughly a 10x expansion of digitrace's footprint (Worker, Queue, R2, a Postgres schema, Analytics Engine, an on-demand container) and the current draft ticket 1 ("ADR... Closes DIG-2644, DIG-2645") doesn't mention either document.

- **Must (DIG-2655):** The ADR must explicitly supersede `digitrace/ARCHITECTURE.md`'s "Current scope vs. intended platform" framing and `docs/vision/digitrace.md`'s roadmap, not just close the two old tickets. Leaving both in place as-is means the repo carries two canonical, contradictory descriptions of what digitrace is — exactly the kind of drift a future contributor (or agent) will trip on.
- **Should:** Pre-existing, not introduced by this design, but adjacent: `digitrace/config.py`'s `_OTLP_ENDPOINT_ENVS` already partially duplicates `digibase.otel`'s endpoint/header resolution. DIG-2656/2662 should resolve OTLP endpoint/headers through `digibase`'s resolver rather than adding a third independent copy of that fallback chain.

## 10. Monorepo fit

- **digibase:** canonical owner of `DIGI_OTEL_ENDPOINT`/`DIGI_OTEL_HEADERS` resolution (`digibase/src/digibase/otel.py`), already used by digigraph, digiquant, digitrace, digivault, digisearch. DIG-2656 should extend through this, not around it (see §1/§9).
- **digikey:** owns the only existing verified-tenant convention (`tenant_slug_verified`). DIG-2657 should align with it (see §2) rather than inventing a parallel scheme.
- **digiquant / digiquant-runner / digichat (Workers):** neither Worker emits OTel spans today — not via digitrace, not via Workers' native tracing. Turning on `observability.traces.destinations` (DIG-2659) is a pure config addition with no existing behavior to conflict with; low risk. The design's own `persist:false` note (Cloudflare bills persisted trace storage starting 1 Dec 2026) is worth a recheck right before DIG-2659 ships, since that's a live pricing-policy date, not a fixed fact.
- **dashboard / dashboard-api:** fits existing structural conventions cleanly (§6).
- **digitrace packaging/extras:** no `[genai]` extra exists on digitrace today (the design doc's "`[genai]` extra" reference is MLflow's own pip extra, `mlflow[genai]`, not a new digitrace extra — worth making that unambiguous in DIG-2662's ticket body since it currently reads as if digitrace itself needs a new extra).
- **Versioning/release:** digitrace is **not** release-please-tracked (only `apps/digichat` and `digiskills` are); Python packages here ship via manual git tags (`digitrace-vX.Y.Z` per `RELEASES.md`), while Workers under `apps/` ship via dedicated per-app CI workflows (`deploy-digiquant-cloudflare.yml` etc.), not the tag-triggered flow. DIG-2657's AC should explicitly include authoring a new `deploy-digitrace-ingest.yml` alongside the vitest/wrangler-dev items already listed — it's a new deploy surface, not covered by any existing workflow.
- **Name collision / in-flight work to retire:** `apps/digitrace-langfuse` already exists in-tree (code/config landed, never deployed — no secrets, DNS, or live Containers yet, per `docs/ops/digitrace-langfuse.md`'s own status line), built 8 days before this design under a *different*, earlier-approved plan (`docs/plans/digitrace-langfuse-swap-2026-10-01.md`, "digitrace = Langfuse default"). The v2.1 migration path (step 7) already says "retire apps/digitrace-langfuse" — good, this isn't a surprise to the design's author — but it's currently a prose aside inside a *different* ticket's migration section, not a named AC anywhere.
  - **Must (DIG-2655):** Make the Langfuse retirement an explicit, named AC on the ADR ticket: archive/delete `apps/digitrace-langfuse/`, its Dockerfiles, `docs/ops/digitrace-langfuse.md`, and add a one-line "superseded by DIG-2664/v2.1, 2026-10-09" banner at the top of `docs/plans/digitrace-langfuse-swap-2026-10-01.md` (the same courtesy the v2.1 design doc gave its own v1). Low cost (nothing live to tear down) but necessary — a half-retired competing implementation sitting next to the new Postgres schema named `digitrace` is a second, avoidable source of exactly the contradictory-canonical-doc problem flagged in §9.

---

## Ranked changes

### Must (block DIG-2655/2656/2658 as currently scoped)
1. **DIG-2656:** No raw prompt/completion text on OTel spans, even redacted — hash/length/preview only; define an explicit attribute-key allowlist instead of accepting arbitrary attrs. (§1)
2. **DIG-2655 + DIG-2658:** ADR must explicitly address ADR-0021 (accepted rejection of a separate Postgres schema in this project) — justify the deviation or conform to the `public` + RLS pattern.(§4)
3. **DIG-2658:** Define what "≤5 connections" bounds, and default to the repo's only precedented Worker→Supabase pattern (PostgREST/REST) over a raw direct-Postgres driver unless Hyperdrive is explicitly adopted. (§4)
4. **DIG-2655:** ADR must explicitly supersede `digitrace/ARCHITECTURE.md`'s stated zero-dependency philosophy and `docs/vision/digitrace.md`'s roadmap, not just close DIG-2644/DIG-2645. (§9)
5. **DIG-2655:** Make `apps/digitrace-langfuse` retirement (code, Dockerfiles, ops doc, superseding banner on the 2026-10-01 plan memo) a named AC on the ADR ticket, not a prose aside in DIG-2663's migration step. (§10)
6. **DIG-2658:** State plainly that RLS is not the real tenant-isolation boundary under service-role access — the application-layer tenant filter in the consumer Worker/dashboard-api is — and make sure that filter is what DIG-2661 actually tests. (§4)

### Should (fix during implementation, don't need to gate kickoff)
1. **DIG-2657:** Align ingest auth with digikey's verified/unverified tenant convention (`tenant_slug_verified`) rather than a bespoke scheme; add explicit `max_retries`/`dead_letter_queue` to the Queue config. (§2)
2. **DIG-2658/2662:** Reconcile the 90-day Supabase retention vs. 180-day R2 lifecycle mismatch — decide and document whether post-90-day replay is supported. (§3)
3. **DIG-2657/2661:** Timebox a WAE spike (query latency, cardinality, sampling at volume) before the dashboard depends on it as metrics source of record. (§5)
4. **DIG-2656/2662:** Route OTLP endpoint/header resolution through `digibase.otel` rather than adding a third independent copy of the fallback chain. (§9)

### Could (polish, non-blocking)
1. **DIG-2661:** Decide whether the Traces tab reuses or replaces the existing `/observability` redirect route. (§6)
2. **DIG-2662:** Document Docker as an explicit local-mode prerequisite. (§8)
3. **DIG-2662:** Clarify that "`[genai]` extra" refers to MLflow's own pip extra, not a new digitrace extra. (§10)
4. **DIG-2659:** Recheck the Workers trace-persistence billing date (1 Dec 2026) immediately before this ticket ships rather than relying on the date captured today. (§10)

---

## What's already right (no changes needed)
- Elimination of ClickHouse/Redis-dependent tools and the MIT/Apache-2.0-over-Elastic-2.0 licensing argument for MLflow over Phoenix.
- OTLP/HTTP (not gRPC) as the replay protocol — matches `digibase.otel`'s existing exporter choice.
- `wrangler dev` + Miniflare for local/cloud code parity.
- Dashboard structural fit (one-file-per-feature in dashboard-api, one-folder-per-page in dashboard).
- Treating Workers-native-trace billing change (persist:false, Dec 2026) as a live constraint to track rather than ignoring it.
