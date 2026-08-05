# digichat unification — handoff

**Written:** 2026-08-02, to continue this work in a fresh session (different subscription/machine).
Point a new Claude Code session at this file: `docs/superpowers/2026-08-02-digichat-unification-handoff.md`
in `digithings`, on branch `develop`. Everything below is committed and pushed — nothing lives only in
a prior session's memory.

## Where this came from

Owner noticed DataTap's embedded digichat looks nothing like digithings.ai's native chat — flat trace
rows instead of the layered "thinking chain" — despite both supposedly using the same code. Investigation
found the UI package (`@digithings/digichat-ui`) really is shared, but the backend and controller are two
independently-written stacks that happened to feed the same component. Owner wants genuine sharing:
"if I modify it in one place, the changes could be reflected in the other provided I redeploy."

Full origin story, the audit of what's shared vs. duplicated, and all locked-in architecture decisions are
in **`docs/superpowers/specs/2026-08-01-digichat-activity-protocol-design.md`** (read this first) — it has
a "Program context" section with the 3-phase plan and decisions phases 2–3 must inherit rather than
relitigate.

## Status

**Phase 1 — SHIPPED.** [PR #1817](https://github.com/digithings-ai/digithings/pull/1817), squash-merged to
`develop` at `32f8e926`. All CI green, `digichat` suite 263/263.

- Spec: `docs/superpowers/specs/2026-08-01-digichat-activity-protocol-design.md`
- Plan: `docs/superpowers/plans/2026-08-01-digichat-activity-protocol.md`

What it delivered: an OpenTelemetry GenAI-named `ActivitySpan` vocabulary
(`frontend/digichat/src/lib/chat-activity.ts`) that IS the disclosure allowlist for the public embed;
Foundry now emits structured `tool_result` rows with real citations instead of flattened `Sources: a, b`
strings; per-tenant `activityDetail: "off"|"labels"|"full"` gated server-side; two upstream-error-body
disclosure leaks fixed (digigraph, relay) plus two more found by an automated Copilot PR review after
merge-readiness (a failed search rendering as a false "no hits", and Foundry's own span writes bypassing
the length caps + streaming raw exceptions).

**One deliberate loose end from Phase 1, now Phase 2's problem:** `stream-digigraph-trace.ts` *dual-emits*
— the new gated `data-digichatActivity` span, plus the legacy ungated `data-digigraphTrace` part, but the
legacy part is now scoped to **authenticated requests only** (`emitLegacyTracePart` flag in
`route.ts` ≈ line 256, required not defaulted). It exists because `chat-panel.tsx` (the authenticated
in-app chat, NOT the embed) still renders `DigigraphTraceBlock` off the legacy part, and that block shows
richer data (`RagSourcesTrace`: source id, evidence tier, year, snippet; `ResearchBriefTrace`) than the
flat `chat`-operation span can currently express. Converting `chat-panel.tsx` needs the digigraph mapping
extended first — see Phase 2 below.

**Phase 2 — DESIGN WRITTEN (awaiting user review of the spec).** Spec:
`docs/superpowers/specs/2026-08-05-digichat-phase2-unification-design.md`. Next: user review →
`superpowers:writing-plans` → implement. Do not skip to code.
**Phase 3 — NOT STARTED** (still needs brainstorming → design → plan).

The Phase 2 scope below is the pre-brainstorm brief; the written spec above is authoritative.

### Phase 2 scope (draft)

1. Port the digivault RAG + OpenRouter free-tier agentic loop out of
   `frontend/digithings-web/functions/api/chat.ts` (a 983-line Cloudflare Pages Function — Workers runtime,
   no Node APIs) into `frontend/digichat` as a new `EmbedBackendConfig` variant (today's union is
   `digigraph | external-relay | foundry`, in `frontend/digichat/src/lib/embed-tenants.ts`). Prove parity
   against the live CF Function before cutting over.
2. Extend the digigraph→`ActivitySpan` mapping in `stream-digigraph-trace.ts` so `rag_sources` projects
   into `retrieve` + `documents` (title/tier/year/snippet — may need a documents-shape extension) and
   `graph_update` gets its own representable shape, then repoint `chat-panel.tsx` at
   `data-digichatActivity` and delete the legacy dual-emit path (`emitLegacyTracePart`, the
   `data-digigraphTrace` writer, `DigigraphTraceBlock`/`isDigigraphTracePart` in `chat-panel.tsx`).
3. The ported digivault loop already speaks the five-kind activity vocabulary natively (status/tool_call/
   tool_result/reasoning) over its own NDJSON format — Task 1's `ActivitySpan` projector
   (`toDigiChatActivity`) was deliberately built to make this step mechanical.

### Phase 3 scope (draft, decisions already locked in the Phase 1 spec)

- `digithings.ai/chat` becomes an iframe into `/embed` with its own tenant config — not a native page.
- Landing-page quick-ask handoff (`frontend/digithings-web/lib/chatHandoff.ts`, localStorage-based, feeds
  `/chat`) survives via **parent postMessage**: `/chat` reads its own localStorage and posts a `seed`
  message into the iframe once it signals ready, reusing the channel the DataTap trial-gate work
  (`datatap-web`, merged) already established for `datatap:gated`/`datatap:unlocked`.
- Four things become tenant/URL config on the embed: `showByok` (today derived as `!ungated` in
  `frontend/digichat/src/app/embed/page.tsx`), `showStatusBar` (today hardcoded `false`), `layout="page"`
  (today always `"embed"`), and mermaid rendering (already in the shared package — confirm the embed path
  renders it).
- Once this lands: retire `frontend/digithings-web/functions/api/chat.ts`, `lib/useStackChat.ts`,
  `lib/chatStream.ts`.

## Other open items, unrelated to phases 2/3

**Terracotta accent bug — unresolved, root cause NOT found.** DataTap's embed should show `#b5562b`
accents; it renders `#1f1f1f` (the `digichat` default) instead. Confirmed live on both v0.4.1 and v0.5.0
(240+ commits apart), on dev and prod — not caused by this branch. `datatap-web` sends the correct
`?accent=%23b5562b` param, `location.search` is intact in the live page, manually re-running the exact
parse (`frontend/digichat/src/lib/embed-ui-params.ts`, `HEX_COLOR` regex) in devtools on the live page
returns `#b5562b` and passes. The tenant registry (`DIGICHAT_EMBED_TENANTS` env, parsed by
`frontend/digichat/src/lib/embed-tenants.ts`) independently has the correct accent configured. Yet in
`frontend/digichat/src/app/embed/page.tsx`, the wrapper div's `style` attribute is `null` at runtime and
`--accent` computes to the default. Black-box browser testing couldn't get further — needs someone to
inspect the actual running container's build output or add server-side logging around `resolveAccent`/
`accentStyle` in `embed/page.tsx`, since the bug is real but not explained by anything in the source as
read. `welcome`/`suggestions` URL params work fine through the identical param-parsing path, which is the
confusing part.

**Storage Task 5 — DataTap backend hand-off, not a code task.** From the earlier chat-trial-storage work
(`datatap-web`, spec at `datatap-web/docs/superpowers/specs/2026-07-24-chat-trial-storage-design.md`,
already merged as PR #35): send the spec's "Backend contract" section — `source: "web"|"chat"`,
`chatSessionId` (≤200 chars), `chatQuestions` (≤3 items, ≤2000 chars each) — to whoever owns the DataTap
trial-registration API, and confirm the endpoint ignores unknown fields rather than rejecting the request.
This gates *activation* only: the merged PR sends no `chatContext` from the trial page itself, so nothing
breaks either way until this is confirmed and the chat-side wiring is turned on.

**GHCR → ACR mirror — manual, unautomated.** `publish-digichat-image` (`.github/workflows/
publish-digichat-image.yml`) pushes to `ghcr.io/digithings-ai/digichat`, but the DataTap dev/prod
container apps only have an ACR pull credential. After *every* digichat image release, someone must run
`az acr import` by hand to mirror the new tag into ACR before the container app can pick it up. This has
bitten a rollout once already (see git history around the digichat v0.5.0 release chain, commits/PRs
#1728–#1731 in this repo). Worth automating as a follow-up step in the publish workflow, or at minimum
turning into a checklist item in `engineering:deploy-checklist`.

**Prod status.** Prod digichat (Azure Container App `jollygrass`, resource group `datatap-rg`) is still on
image `v0.4.1` with `gateMode: "turn_limited"`. Nothing from any of this session's work — the trial-form
gate, the chat-trial-storage fields, or this activity-protocol phase — has touched prod. Dev only so far.

## How to resume

In a new session, in the `digithings` repo on `develop`:

```
git log --oneline -1        # should show 32f8e926 or later
```

Then invoke `superpowers:brainstorming` for whichever of Phase 2, Phase 3, or the accent bug you want to
tackle next — each is independent and can go in either order. The accent bug is a `systematic-debugging`
task, not a brainstorm, since the design isn't in question, the cause is unknown.
