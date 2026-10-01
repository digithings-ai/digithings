# digitrace / Langfuse swap memo (2026-10-01)

> **Phase 1 implement:** [`docs/ops/digitrace-langfuse.md`](../ops/digitrace-langfuse.md) + [`apps/digitrace-langfuse/`](../../apps/digitrace-langfuse/) (#4930).


**Author:** Lab (for One → Chris Human Gate)  
**Status:** Plan only — **no implement until Human Gate**  
**Locks already in (shared):** digitrace = Langfuse default + pluggable OTEL/Phoenix; wire digigraph; hosting = **all-in Cloudflare** (checkpoint→R2, tolerate SIGTERM; no Fly/Railway product compute); DigiQuant clocks paused; when unpaused baseline = **weekly Monday AM** house-run only.

---

## One-line ask for Chris

**Approve phased swap:** rename `digismith` → `digitrace`, stand up self-hosted Langfuse on Cloudflare (Postgres/R2 + external ClickHouse/Redis), dual-export beside LangSmith, wire digigraph LangGraph spans, then cut LangSmith for digiquant-baseline / OpenWiki / house-run — including digiquant-runner Task 7 secret remap.

---

## Verdict

**Swap, phased via dual-export** — LangSmith SaaS per-trace/seat pricing does not scale for digiquant-baseline / house-run / OpenWiki volume. digismith already documents an OTel-first exit. Destination = **Langfuse (MIT) self-host on Cloudflare**, not a same-day drop-in.

Aligns with all-in CF hosting lock: Langfuse Web+Worker as CF Containers; artifacts on R2; house-runs already must checkpoint→R2 and tolerate SIGTERM.

---

## Product contract (locked)

| Rule | Detail |
|------|--------|
| Name | **digitrace** (not LangSmith-branded) |
| Default backend | **Langfuse** |
| Pluggable | OTEL, Phoenix, … |
| digigraph | Wire LangGraph run/node boundaries + digillm LLM/tool spans |
| Fail-soft | No credentials → no-op; PII redaction preserved |
| Correlation | Propagate `workflow_id` / `request_id` / `session_id` |

Today’s path: `digigraph → digillm → digismith.trace` (LLM/tool only). digigraph hard-deps the package but does **not** call `:8003` (status-only).

---

## Swap vs stay

**Stay:** keep paying LangSmith as volume grows; digismith stays thin LangSmith shim; cost cliff + vendor lock.

**Swap:** MIT self-host, R2 blobs, OTLP ingest, no per-trace SaaS tax. Ops: Langfuse needs **Web + Worker + Postgres + ClickHouse + Redis + R2** — ClickHouse (~2 CPU / 8 GiB min) and Redis are **not** “one lite CF Container”; provision managed/VM alongside CF app containers.

**Hybrid dual-export:** validate house-run / OpenWiki trees in Langfuse before cutting SaaS. **Not in-repo today** (need digibase OTLP auth headers and/or LangSmith Python hybrid OTel).

**Anti-pattern:** pointing `LANGSMITH_ENDPOINT` at Langfuse does **not** work (no LangSmith API shim).

---

## Current state (develop, facts)

- **digismith:** `digismith/` — `traceable` → `langsmith.traceable` when key+SDK present; else no-op. Env: `LANGSMITH_API_KEY`, `LANGSMITH_ENDPOINT`, `LANGSMITH_TRACING`, `LANGSMITH_PROJECT`. Soft extra `digismith[langsmith]`.
- **digibase.otel:** OTLP HTTP/protobuf only (`DIGI_OTEL_ENDPOINT` / `OTEL_EXPORTER_OTLP_ENDPOINT`). **Gap:** no `OTEL_EXPORTER_OTLP_HEADERS` / Basic-auth → not Langfuse-ready.
- **Call sites:** digillm `@traceable`; digigraph hard dep + Docker; `pipeline-digiquant.yml` → project `digiquant-baseline`; `openwiki-update.yml` (#4357); `smoke-langsmith.yml` (#687); digiquant-runner `house-run` + Task 7 (#4761) still LangSmith secrets.
- **No** Langfuse ADR/issue yet — Board files after HG.

---

## Rename surfaces (`digismith` → `digitrace`)

- Package: `digismith/**` → `digitrace/**` (+ tests, ARCHITECTURE, openspec, vision docs).
- pyproject / uv.lock / extras: neutral `[tracing]` / Langfuse; temp `langsmith` alias until cut.
- Imports: digillm.client, smokes, export_openapi; rename SmithStatus / service labels.
- Docker / compose / GHCR / publish-service-images; digigraph Dockerfile.
- Env/HTTP: `DIGISMITH_*` → `DIGITRACE_*`; keep port/routes stable (`:8003`, `/healthz`, `/v1/status`, `/metrics`).
- GHA: `test-digismith.yml` → digitrace; CI path filters; digithings-stack-cloudflare wrangler / entrypoint / digichat health URLs.
- OpenWiki: `openwiki/digismith/**` + index/manifest/slugs regen.
- Keep `LANGSMITH_*` secrets during dual-export (`commands.json` has no digismith string).

---

## Phased CHR plan (Board files after HG; Lab does not implement)

### Phase 0 — Rename + neutral facade — **M**
- AC: package/imports/docs/CI/OpenWiki/CF identifiers → digitrace; backend-neutral API; compat aliases; `LANGSMITH_*` still works.
- Risk: wide mechanical churn; keep extras alias until Phase 3.

### Phase 1 — CF Langfuse + DB/R2 — **L**
- AC: Langfuse Web+Worker on CF Containers; `DATABASE_URL` → existing Postgres; R2 event bucket (`LANGFUSE_S3_EVENT_UPLOAD_*`); **ClickHouse + Redis** provisioned (managed OK); UI login; OTLP `/api/public/otel` accepts smoke span.
- Deps: R2 keys; Postgres schema; CH/Redis decision; instance sizing (do not under-size ClickHouse; do not host CH inside lite CF Container).
- Fits hosting lock: all-in CF app plane + external CH/Redis only where CF cannot.

### Phase 2 — Dual-export + digigraph LangGraph — **M**
- AC: digitrace (and/or digibase.otel) fans out to LangSmith **and** Langfuse; env documented (`LANGSMITH_*` + `LANGFUSE_*` / OTLP headers); digillm call sites unchanged; LangGraph run/node + digillm spans; tests: default / adapter / no-op / dual-export parity.
- Risk: double-ingest cost during window; attribute mapping gaps.

### Phase 3 — Cut LangSmith — **M**
- AC: house-run / OpenWiki / digiquant-baseline traces **only** in Langfuse; stop `LANGSMITH_TRACING` on those paths; smoke dual-gates or replaces `smoke-langsmith.yml`; OpenWiki connector path decided (#4357).
- Deps: Phase 2 green on real house dry-run (still **do not resume clocks** until separate Chris unlock; dry-run ≠ prod cadence).
- Cadence note (when clocks unpause): weekly Monday AM only — lower Langfuse ingest volume than daily; still plan CH retention.

### Phase 4 — Task 7 secrets — **S**
- AC: digiquant-runner secrets map `LANGFUSE_*` (optional dual keys during window); Task 7 checklist not LangSmith-only; `commands.json` / wrangler comments match; allocation-shadow still strips prod tracing secrets; retire legacy `LANGSMITH_*` after cut proven.

---

## Don’ts

- No live-trading claims; paper/research only.
- No implement / PRs until Human Gate.
- Don’t claim digitrace dual-exports today.
- Don’t point `LANGSMITH_ENDPOINT` at Langfuse.
- Don’t host ClickHouse in a lite CF Container.
- Don’t resume DigiQuant product clocks as part of this CHR (separate unlock; weekly when live).
- Don’t open a second CHR if One/Board already filed one after this HG.

---

## Board one-liner

Phase digitrace rename + self-hosted Langfuse on CF (Postgres/R2 + external CH/Redis), dual-export via digitrace/OTel, digigraph LangGraph spans, then cut LangSmith for baseline/OpenWiki/house-run incl. Task 7 secret remap.

---

## Migration / ops note (does not change product contract)

Existing digismith + LangSmith Task 7 stay until Phases 2–4. Hosting all-in CF overrides earlier hybrid Fly compute advice for **product** compute — Langfuse and house-run remain on Cloudflare with checkpoint→R2.

---

## Sources / related

- Prior Lab packets to One (2026-10-01): Langfuse swap memo; digitrace rename amend; digigraph product-contract amend.
- Related issues (context only): #4761 CF migrate / house-run Task 7; #687 LangSmith enable; #4357 OpenWiki secrets; #214 PII.
- Hosting verdict superseded for compute by Chris lock: all-in Cloudflare (`/workspace/hosting-platform-verdict-2026-10-01.md` historical; lock = CF-only product compute).
