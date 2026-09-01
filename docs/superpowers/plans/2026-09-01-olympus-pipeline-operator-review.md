# Olympus pipeline operator review — implementation plan

> **For agentic workers:** implement one work package per task PR. Do not land this
> document as a single mega-diff. Each WP is independently reviewable and testable.
> Use test-first-implementer (or equivalent TDD) inside a WP; do not start WP-C/E/H
> until WP-A/B have a hatch on the record if they share files.

**Date:** 2026-09-01
**Source:** Operator walk of the Olympus dashboard pipeline for **2026-08-31**, plus
code investigation of Atlas A0–A4, Hermes H1–H9, and `frontend/dashboard` pipeline
chrome.
**Status:** Plan only. This document authorizes no runtime change until a GitHub
issue exists per WP (`Fixes #<N>` / `task/<N>-slug`).
**Distinct from:** [2026-08-06 architecture review](../../reviews/2026-08-06-olympus-pipeline-review.md)
(learning-loop / evidence ledger). This pass is **operator readability**: produced
documents, research, and whether the pipeline page shows a real run.

**Goal:** Make the pipeline page a transparent reading of one daily run: every visible
node is a real step with inspectable I/O; research and digest read as reports; H6
reads as a conversation; H7 is the PM conclusion (narrative + direction + rank +
confidence); H8 sizes from that confidence; learning updates every day.

**Architecture:** Keep one daily graph (Atlas → Hermes → optional beliefs). Do not
add a second cadence or a second sizer. Change **what is published and how it is
authored/rendered**, not graph topology, except where a node is removed (sector
scorecard) or collapsed (Decision/Commit). Digest subsection agents reuse the
existing sector-swarm fan-out pattern — not a new orchestration framework.

**Tech stack:** LangGraph phases in `digiquant/src/digiquant/olympus/`, Pydantic v2
payloads, Supabase `documents`, Next.js dashboard in `frontend/dashboard/`.

## Global constraints

- Digi names lowercase in prose (`olympus`, `digiquant`, `digithings`).
- Polars only; Pydantic v2; no pandas.
- H7 still emits **no weights**. H8 remains the only sizer. H9 remains the only booker.
- No live-trading / `digiquant/brokers/` changes.
- No `digikey/` changes.
- Task PRs into `develop` for `frontend/dashboard` and `docs/`; into `module/digiquant`
  (after a current-base check) for Olympus Python.
- ruff line length 100; dashboard tests via `cd frontend/dashboard && npm run test`.
- Human-readable artifacts are **markdown reports or dedicated views**, not JSON
  pretty-prints of structured-output slots.

---

## The one interaction rule

Stage cards **expand in place**. The sidebar opens **only when that node has a
document for the selected date**. No “navigational overview” pane. No
description-only nodes.

If a step has no inspectable input or output, it is not a node.

---

## Investigation — what the operator actually hit

### Pipeline chrome is a flowchart of labels

`frontend/dashboard/lib/pipeline-topology.ts` defines six stages. Several
sub-steps are `stateOnly: true` (preflight, consolidate, thesis, screener): the
backend runs them and **never publishes a `documents` row**. Clicking the stage
card or those leaves opens `PipelineNodeDetail` with `pipelineNodeExplanation`
copy (“Stage overview” / “In-memory operation”).

Layout (`pipeline-layout.ts`) expands **to the right**, then fan-out branches
**down**. Research therefore walks sideways into Alt-data / Institutional / …
instead of opening as an outline under the Research card.

`leafDocumentKey` in `pipeline-links.ts` does not even map thesis or screener.
H4 already has `OpportunityScreenerDocumentView` for `opportunity-screener.json`;
the pipeline graph never binds it.

### Research is a JSON schema the UI then dumps

Atlas segments emit `SegmentReport` (`digiquant/src/digiquant/olympus/atlas/segments.py`):
`bias`, `headline`, `material_findings[]`, `sources[]`, `notes`, `data_quality`,
`confidence`, plus per-segment metric fields. Skills already contain markdown
templates **and** “populate the structured fields”; strict structured output wins.

The dashboard reconstructs markdown in `renderSegmentReportMarkdown`
(`frontend/dashboard/lib/render-pipeline-payloads.ts`):

1. Bias + headline
2. Material findings as bullets
3. **Signals** — leftover scalars. `data_quality` and `confidence` are **not** in
   `CORE_KEYS`, so they leak here as “Data Quality: median” and “Confidence: 0.7”
4. Other arrays as tables
5. Narrative / memo notes
6. Sources appendix

That is why every alt-data / sector / macro memo looks like the same forced form,
with hallucinated-looking grades, and why length jumps around: the model fills
slots, it does not write a memo.

### Sector scorecard is a no-LLM rollup the operator does not want

`phase5_equities.py` `_scorecard_node` is deterministic: copy bias/headline/quality
off the 11 sector JSON bodies into `sector-scorecard`. Hermes/PM were told to
weight this artifact. The operator would rather analysts pick sectors and names
from the sector memos. Extra step, technicals-flavoured, no independent judgment.

### Consolidate bias is not an LLM call — but it does have output

`phase6_consolidate.py` is deterministic. It writes `phase6_bias_row` (macro
regime, per-asset biases, VIX, flows, Fed odds, on-chain). Hermes H1/H7/H8 read
it. It is `stateOnly` in the UI, so the operator sees a blank sidebar and
assumes a hidden LLM. Show the row. Do not invent an LLM here.

### Daily digest is one structured-output call

`phase7_synthesis.py`: single `run_research_agent` into `DigestSnapshot`
(extends `SegmentReport` plus `us_equities_summary`, `asset_classes_summary`,
…). Continuity today is a **slimmed prior digest** in `shared_context` (headline /
bias / regime only — `#1559`), not a two-day read of full reports. The operator
wants a long analyst-entry report, subsection agents (same pattern as the 11
sector swarm), a markdown template, and yesterday + the day before as grounding.

### Deliberation loop is right; authoring + chrome are not

H6 (`h6_deliberation.py`) already does: analyst report exists → PM challenge →
analyst response → PM may challenge again or converge (min rounds default 2, max
10). Transcript is `[{role, round_number, message}]`.

Two bugs relative to the operator’s ask:

1. **Analyst turn reuses the H5 `asset-analyst` skill**, which says “Emit a
   unified `AnalystPayload`” and “write the full case.” That is why replies look
   like “Response to PM challenges” with titles. There is no H6-only
   conversational skill.
2. **UI is stacked report cards**, not chat. `DeliberationDocumentView` has a
   `deliberation-chat` list of bordered blocks labeled `PM · Round N`. Pipeline
   markdown fallback (`renderDebateSummaryMarkdown`) is `### PM · Round 1`
   headings. Neither is bubbles. Opening the analyst report as the first message
   is not implemented.

PM skill (`deliberation-full.md`) is already a short challenger prompt. Keep
that; stop forcing structured “challenge” headings in the visible message.
`converged=true` already allows agree or disagree — do not add a new machine
state for that. Put the PM’s last message in the transcript as a bubble, not
only in `conclusion`.

### PM direction is the right artifact, rendered as a schema dump

`PMDirectionMemo`: `date`, `memo`, `roster[{ticker, direction: long|flat,
conviction_rank, narrative, forecast_reference}]`. No confidence. No buy/hold/sell.
`forecast_reference` / `degradation_reason` are **post-LLM audit links** (WP4.5).
Empty degradation is normal when lineage exists; empty IDs force
`forecast_unavailable`. The operator should not see those fields.

`LibraryDocumentBody` has **no PM-direction view**. The memo falls through to
markdown or `PayloadKeyValueView` — hence “hard to see,” nested
forecast_reference objects, empty degradation.

### Rank #1 ≠ largest weight (gold ~10% on 2026-08-31)

H8 default is `h8_sizing_input_mode=calibrated` (`phase7e_risk_sizing.py`). On
that path, raw weights are `reliability × max(0, μ) / σ_ε` from the forecast
bundle. **Ordinal rank is not used for size.** Rank→conviction exists only on
the incumbent fallback.

Even on the rank path, `_rank_to_conviction` maps 1..N into [floor, 5], then
inverse-vol + 12% portfolio vol budget + 5% weight grid + sector/name caps. A
wide long book plus a vol budget will pin a #1 name near 10% without any bug.

The operator wants: display rank **and** a confidence; confidence scales risk;
low confidence → less gross. That is a real H8 policy change, not a UI fix.
Inspect 2026-08-31 `pm-rebalance` `applied_scales` / per-name notes in the
implementation WP before changing the formula, so gold is explained in the
sizing event log rather than guessed.

Direction today is `long | flat` only. Buy / hold / sell for the reader should
be **derived** from prior weight vs H8 target (increase / keep / exit). Do not
give H7 weights. Optional: H7 `intent: add | hold | exit` as a label only.

### Decision / Commit

Decision has a single child, `commit`, bound to `commit-run/{run_id}` — an
internal H9 manifest (run id, seq, booking metadata). The operator is right:
that is not a user document. Clicking Decision should not open a guide card.
Either collapse the stage into the booked book (`pm-rebalance` / positions) or
drop the stage and hang commit internals off a ledger, not the graph.

### Learning is not daily

`beliefs_distillation.py`: runs only if `refresh_scope=beliefs` **or** unfolded
resolved `decision_log` rows **> `OLYMPUS_BELIEFS_BACKLOG` (default 20)**. Not
weekly. Not daily. Aug 25 with a document and silent days after is the expected
backlog trigger. The operator wants a daily fold: today’s lessons pass to
tomorrow. That is a product/cost change (one more LLM on every house run).

### 31 analyst calls

`.github/olympus-pipeline.yml` sets `ATLAS_MAX_ANALYSTS: "30"`. Cap invariant
(`roster_cap.py`): held book may overshoot the cap, never the other way.
30 + one extra held (or rounding) → 31. Operator called this extensive; they
stopped mid-comment. **Do not change the cap in this program until they finish
that note.** Default: leave H5 width as-is.

---

## Locked product decisions (from commentary)

1. Visible nodes = real I/O. Description-only nodes go away.
2. Expand-in-place outline, not a rightward flowchart.
3. Research memos are markdown reports: title, topical prose, inline hyperlinks.
   Suggested template in the prompt, not a required JSON skeleton.
4. Drop user-facing `bias` chip, `confidence` float, `data_quality` grade, Signals
   dump, Sources appendix. Keep a thin envelope for the graph (`segment`, `date`,
   markdown body, real URLs).
5. Remove the sector scorecard step.
6. Digest is a long stitched report; subsection agents; prior two digests for
   continuity.
7. H6 is a chat: analyst report, then PM/analyst bubbles, conversational
   professional tone, PM may keep challenging or converge at the bottom.
8. H7 is the conclusion surface: per ticker, PM narrative, directional bet,
   buy/hold/sell vs prior book, conviction rank, confidence. Hide forecast
   audit fields.
9. H8 must use that confidence (rank alone is not size).
10. Hide commit-run from the graph. Learning runs daily.

---

## File map (who owns what)

| Area | Paths |
|---|---|
| Pipeline graph / expand / sidebar | `frontend/dashboard/lib/pipeline-topology.ts`, `pipeline-layout.ts`, `pipeline-links.ts`, `pipeline-topology-status.ts`, `components/pipeline/PipelineCanvas.tsx`, `PipelineNodeDetail.tsx`, `PipelineNode.tsx` |
| Research/digest markdown dump | `frontend/dashboard/lib/render-pipeline-payloads.ts`, `components/library/LibraryDocumentBody.tsx` |
| Segment schema + skills | `digiquant/src/digiquant/olympus/atlas/segments.py`, `atlas/skills/**`, `atlas/phases/phase7_synthesis.py` |
| Scorecard | `atlas/phases/phase5_equities.py`, topology `scorecard` leaf, digest/PM consumers of `sector-scorecard` |
| Inputs / bias row persist | `atlas/phases/preflight.py`, `phase6_consolidate.py`, `publish_phase.py` |
| H1 / H4 documents | `hermes/phases/h1_thesis_review.py`, `h4_opportunity_screener.py`, `pipeline-links.ts` |
| H6 chat | `hermes/skills/deliberation/*`, **new** `hermes/skills/deliberation/analyst-response-*.md`, `h6_deliberation.py`, `components/library/DeliberationDocumentView.tsx` |
| H7 view + confidence | `hermes/models/pm_direction.py`, `hermes/skills/pm-direction/*`, **new** `components/library/PmDirectionDocumentView.tsx` |
| H8 confidence | `hermes/phases/phase7e_risk_sizing.py`, `hermes/sizing.py` |
| Beliefs cadence | `olympus/learning/beliefs_distillation.py` |
| Tests | `frontend/dashboard/lib/*.test.ts`, `components/**/*.test.tsx`, `tests/dq/olympus/`, `tests/dq/atlas/`, `tests/dq/hermes/` |

---

## Work packages

Ship in this order. Each WP is its own issue + `task/<N>-slug` PR. Do not combine
chrome with H8 policy.

### WP-A — Pipeline chrome (frontend)

**Issue title:** Pipeline nodes expand in place; sidebar only for documents

**Files:**
- Modify: `frontend/dashboard/lib/pipeline-layout.ts` (stack expanded sub-steps
  under the stage at `x = stage.x`, `y` increasing; fan-out branches under the
  parent sub-step, not `cursorX += NODE_W`)
- Modify: `frontend/dashboard/components/pipeline/PipelineCanvas.tsx` (stage click
  toggles `expandedStages`; do not call `onNodeActivate` for `kind === 'stage'`
  unless that stage has exactly one document child — see WP-D Decision collapse)
- Modify: `frontend/dashboard/components/pipeline/PipelineNodeDetail.tsx` (if
  `!documentKey`, render nothing / close; delete the “Pipeline guide” empty state)
- Modify: `frontend/dashboard/lib/pipeline-topology.ts` (drop `behavior: 'Stage
  overview'` as a user-facing path)
- Test: `frontend/dashboard/lib/pipeline-layout.test.ts`,
  `components/pipeline/PipelineCanvas.test.tsx`,
  `components/pipeline/PipelineNodeDetail.test.tsx`

**Done when:**
- Click Research → rows for Alt-data, Institutional, Macro, … appear under the
  card. Click Alt-data → CTA / sentiment / … rows under that row.
- Click Research / Synthesis / Selection / Inputs with no document → no sidebar.
- Click Daily digest / a named research doc → sidebar with the document.

**Out of scope:** prompt/schema changes (WP-C), persist new docs (WP-B).

---

### WP-B — Publish inspectable I/O for today’s silent steps

**Issue title:** Persist Inputs, bias row, thesis review, and screener as documents

**Backend**
- Preflight: publish `document_key=inputs` (watchlist, profile/preferences hash,
  market-data freshness, prior-context dates, attention-plan pointer). Reuse
  existing publish helpers; do not invent a second store.
- Phase 6: publish `document_key=bias-row` from `phase6_bias_row` (the
  deterministic dict, formatted as a short markdown table + notes). Still no LLM.
- H1: publish the thesis-review artifact the phase already builds in state
  (`ARTIFACT_KEY = ("thesis", "thesis-review")`) instead of `stateOnly`.
- H4: bind the existing screener payload to a stable key the graph already has a
  view for (`opportunity-screener.json` or a flat `opportunity-screener` — pick
  one and stop leaving the view unwired).

**Frontend**
- `pipeline-links.ts` `leafDocumentKey`: `preflight → inputs`, `consolidate →
  bias-row`, `thesis →` H1 key, `screener →` H4 key.
- Clear `stateOnly` on those sub-steps once the document exists.
- Dedicated small views beat `PayloadKeyValueView` for Inputs and bias-row.

**Done when:** 2026-08-31-style click on Inputs / Consolidate / Thesis / Screener
opens a real artifact, not a guide card.

**Tests:** `tests/dq/atlas/` publish shape for inputs + bias-row;
`tests/dq/hermes/` H1/H4 document_key; dashboard `pipeline-links.test.ts`,
`pipeline-layout.test.ts`.

---

### WP-C — Research memos (schema + prompt + renderer)

**Issue title:** Atlas research is a markdown report, not a JSON dump

**Contract (thin envelope, user body is markdown):**

```python
class ResearchMemo(BaseModel):
    segment: str
    date: date
    body: str  # markdown; inline [title](url) citations
    sources: list[Source] = []  # optional, for digest grounding only — not rendered as an appendix
```

Keep `body` as the operator artifact. If digest/triage still need a directional
token, derive it in code from the memo or a **non-rendered** optional
`internal_bias` — never print “Bias: mixed” at the top.

**Prompt:** per-segment skill keeps the *job* (what to research) and a **suggested**
markdown skeleton (title, as-of date, 2–5 topical `##` sections, inline links).
Explicitly: variable depth is allowed; do not invent data-quality or confidence
scores; do not emit a Signals section.

**Renderer:** `renderSegmentReportMarkdown` becomes “title + body”. Delete the
Signals leftover-scalar path for research docs. Do not render `data_quality` /
`confidence` even if old rows still have them.

**Compatibility:** old `SegmentReport` rows must still render (findings+notes
fallback) so the library does not blank historical days.

**Done when:** a new alt-data/macro/sector doc reads as a memo; 2026-08-31 JSON
rows still display something readable.

**Risk:** A4 digest and H1 currently read `bias` / `headline` / `material_findings`.
Retarget those readers in the same PR or they go blind. Do not ship envelope
change without digest/H1 compile+unit tests.

---

### WP-D — Remove sector scorecard

**Issue title:** Drop the deterministic sector-scorecard node

- Delete `build_phase5_scorecard` from the daily graph (keep the function behind
  a test-only import only if something still needs it for a sunset window — prefer
  delete).
- Remove topology leaf `research:scorecard` and `leafDocumentKey('scorecard')`.
- Strip digest/PM skill references to the scorecard as an authority.
- Sector memos remain.

**Done when:** no `sector-scorecard` document on new runs; graph has no Scorecard
node; tests that required the node are rewritten around sector memos.

---

### WP-E — Daily digest as stitched subsection reports

**Issue title:** Digest orchestrator + topical sub-agents, markdown, two-day continuity

Reuse Phase 5 sector swarm: one parent node fans out subsection writers (US
equities, asset classes, institutional, alt-data, macro, …), then a stitcher
assembles one markdown document.

- Skill for the stitcher: template for a long briefing (not `DigestSnapshot`
  JSON slots). Instruct: this is the analyst entry point; length is allowed.
- Each sub-agent reads only its upstream segment memos + the last **two** full
  digest bodies (not the #1559 slim headline-only trim).
- Persist one `digest` / `digest-delta` document whose `body` is the stitched
  markdown. Keep a minimal envelope if snapshot consumers need `date` /
  `regime_label`.
- `DigestDocumentView` should render that markdown, not reconstruct from
  `us_equities_summary` fields. Keep a fallback for old snapshots.

**Cost:** more LLM calls per morning. Cap subsection count to the current digest
sections; do not fan out per sector again.

**Done when:** a new digest is a single long report with topical headings and
inline links; continuity sentences can cite yesterday’s call.

This is **not** a new architecture (fan-out already exists). Update
`digiquant/src/digiquant/olympus/atlas/docs/ARCHITECTURE.md` (and Hermes
boundary note) in the same PR.

---

### WP-F — Deliberation as a conversation

**Issue title:** H6 is a professional chat, not a report stack

**Prompts**
- Keep PM skill short. Add: write `challenge` as a chat message (no “Challenge:”
  heading); you may keep pushing or converge; last message is the visible close.
- **New** skill `hermes/skills/deliberation/analyst-response-full.md` loaded as
  `deliberation-analyst-response`. Do not load H5 `asset-analyst` for the reply
  turn. Instruction: you are in a meeting; answer the PM in conversational
  professional prose; no title blocks; cite facts inline.
- `h6_deliberation.py`: `load_skill_full("deliberation-analyst-response")` on the
  analyst turn. Always append the PM convergence message to `transcript` so the
  last bubble is the PM.

**UI** (`DeliberationDocumentView.tsx`)
- First block: the H5 analyst report (link or embedded summary), not a second
  research dump.
- Then chat bubbles: analyst left/PM right (or equivalent), role label, no
  “Round N” as the headline.
- Conclusion is the last PM bubble if the transcript already has it — do not
  repeat a “## Conclusion” report under the chat unless the transcript is empty
  (carry).

**Tests:** `DeliberationDocumentView.test.tsx` (bubble roles, no round heading as
title); hermes unit that analyst H6 path does not load the H5 skill.

---

### WP-G — PM direction as the conclusion surface

**Issue title:** Dedicated H7 view: narrative, action, rank, confidence; hide audit fields

**Schema:** add `confidence: float` in `[0, 1]` on `TickerDirection` (display as
percent; same scale as thesis confidence). Prompt: rank is ordering; confidence
is how sure you are of that name. Unique ranks remain. Do not emit
`forecast_reference`.

**View:** `PmDirectionDocumentView` — date + memo at top; table or cards sorted
by rank among `long`, then flats. Per row: ticker, narrative, derived action
(buy/add vs hold vs sell/exit from prior weight vs current target if the
rebalance payload is at hand; else show `long`/`flat` only), rank, confidence.
Never show `forecast_reference`, UUIDs, or `degradation_reason`.

Wire `resolveLibraryDocumentView` for `pm-direction-memo`.

**Done when:** the 2026-08-31 memo is scannable as “what I believe, in order,
how sure, whether we are adding/holding/exiting.”

---

### WP-H — Confidence-aware sizing (explain gold first)

**Issue title:** H8 scales risk by PM confidence; rank is order not size

**Before coding:** load 2026-08-31 `pm-rebalance` and H8 sizing events. Record why
gold (IAU/GLD) is ~10% while rank 1 (calibrated score vs vol budget vs grid).
Put that explanation in the PR body.

**Policy (after the measurement):**
- Calibrated μ/σ may remain a vol/reliability input.
- Multiply (or otherwise scale) each long’s raw score by H7 `confidence`.
- Rank is **not** a size input on the default path (document this in
  `hermes/docs/ARCHITECTURE.md` so the UI never implies #1 = largest weight).
- Low-confidence book → lower gross (do not renormalize away the haircut into
  other names; cash-first, matching existing cap style).

**Tests:** unit: two names, same forecast slice, confidence 0.9 vs 0.5 → 0.9
gets more weight; both low confidence → cash rises. Do not touch live brokers.

**Human gate:** this changes paper-book risk. Not live-trading, but treat as
high-scrutiny review (`/review`). Do not merge on a Friday house run without
that hatch.

---

### WP-I — Daily learning

**Issue title:** Beliefs / daily lessons fold every house run

Change `should_distill_beliefs` so the house daily path always runs a **short**
fold (today’s resolved lessons + pointer to yesterday’s beliefs body), not only
backlog > 20.

Keep `refresh_scope=beliefs` as the full rewrite. Cap the daily call (small
model / tight token budget) so this is not a second digest.

Publish `beliefs` every run date so Learning is never “no output” on a day the
pipeline ran. If there is nothing new, the document says so in one paragraph and
carries prior beliefs.

**Done when:** Aug 31-style Learning opens a same-date document.

**Cost:** one extra LLM per morning. Say so in the issue.

---

### WP-J — Analyst roster width (parked)

Operator: “31 analyst calls… I find that’s extensive.” Cap is 30 + held
overshoot. **No code until they specify the desired roster** (held-only,
thesis-linked only, lower `ATLAS_MAX_ANALYSTS`, etc.).

---

## Sequence

```text
WP-A chrome
  → WP-B persist silent steps
  → WP-D drop scorecard          (can parallel A/B)
  → WP-F H6 chat                 (can parallel A/B)
  → WP-C research memos          (after A so you can read the new body in the new chrome)
  → WP-E digest stitcher         (after C; digest must consume memos not SegmentReport slots)
  → WP-G H7 view + confidence field
  → WP-H H8 uses confidence      (after G; needs the field)
  → WP-I daily beliefs           (independent; do after A so Learning isn’t a dead node)
```

Do not start WP-C and WP-E in the same PR. Do not start WP-H before WP-G.

---

## Explicitly not in this program

- Live trading, brokers, Kairos.
- Replacing H8 with an LLM sizer.
- Weekly-only beliefs (the operator rejected “maybe it’s weekly”).
- Keeping structured-output research because downstream code likes it — downstream
  must follow the memo.
- Expanding H4/H5 roster in the planner (`AttentionPlan` still cannot widen H4).

---

## First slice when execution starts

WP-A only: failing layout tests for “expanded research sub-steps share the stage
x and stack in y”; implement; `npm run test` in `frontend/dashboard`; no Python.
Then WP-B on a `module/digiquant` current-base branch.

---

## Spec coverage checklist

| Operator note | WP |
|---|---|
| Inputs / every step is real I/O; no guide sidebar | A, B |
| Research expands as rows under the card | A |
| Research is a report; inline links; no Signals / bias metric / sources dump | C |
| Inconsistent depth / forced JSON | C |
| Remove sector scorecard | D |
| Synthesis/Selection must not open a nav sidebar | A |
| Consolidate bias should show its output | B |
| Digest: long, subsection agents, template, 2-day continuity | E |
| Thesis + screener should show output | B |
| 31 analysts | J (parked) |
| H6 chat bubbles, conversational tone, PM may keep challenging | F |
| H7 clear: narrative, direction, rank + confidence | G |
| Empty degradation / forecast reference | G (hide) |
| Gold rank 1 but ~10% | H |
| Decision/Commit collapse; commit is internal | A (+ hide `commit-run` leaf) |
| Learning should run daily; Aug 22/25 gap | I |
