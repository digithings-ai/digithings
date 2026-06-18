# ADR-0019 — Unified mode-morphing Atlas/Hermes workflow

- **Status:** Proposed
- **Date:** 2026-06-17
- **Related issue:** [#814](https://github.com/digithings-ai/digithings/issues/814)
- **Amends:** [ADR-0015](0015-atlas-vs-hermes.md) (two cron workflows implied; this ADR collapses them)

---

## Context

The Atlas/Hermes pipeline is currently driven by two near-identical GitHub Actions
workflow files:

| File | Schedule | `--run-type` | Timeout | Retention |
|------|----------|--------------|---------|-----------|
| `.github/workflows/atlas-baseline.yml` | `0 12 * * SAT` | `baseline` | 240 min | 30 days |
| `.github/workflows/atlas-delta.yml` | `0 12 * * MON-FRI` | `delta` | 120 min | 14 days |

Both files share:

- identical install steps (`scripts/install-workspace.sh digiquant`, `digiquant[atlas]`,
  `langgraph-checkpoint-postgres`)
- identical "Resolve run date" step
- identical "Validate providers (preflight)" step with identical env vars
  (`OPENROUTER_ALLOWED_MODELS`, `OPENROUTER_COST_QUALITY_TRADEOFF`)
- identical outer-retry shell loop (3 attempts, `OUTER_BACKOFF=(0 300 900)`)
- identical "Upload logs" step (differing only in the artifact name prefix)
- near-identical "Open or update failure issue" step (differing only in `TITLE`)
- identical Python entry point (`python -m digiquant.olympus.hermes.chain`)

The only substantive differences are:

1. `--run-type baseline` vs `--run-type delta --auto-baseline`
2. `timeout-minutes: 240` vs `120`
3. Artifact/issue-title prefix (`atlas-baseline-*` vs `atlas-delta-*`)
4. `LANGSMITH_PROJECT: atlas-baseline` vs `atlas-delta`

**Delta reliability gap.** The delta path was introduced after the baseline and has
received significantly less investment. It re-runs the full pipeline with `--run-type
delta`, which triggers the triage phase but still fans out to all analysts (subject to
`ATLAS_MAX_ANALYSTS`). In practice, delta runs have exhibited the same cost profile as
baseline runs without meaningfully reducing token spend, because the pipeline re-generates
all research documents from scratch each weekday rather than patching only the stale
segments identified by triage.

**Duplication cost.** Any env-var, step, or logic change must be applied in two files,
with no tooling to enforce consistency. Past divergences (e.g., missing
`ATLAS_ONCHAIN_POSITIONING` in one file) were discovered only after failed runs.

**Goals:**

1. One workflow file, two modes — eliminate duplicated boilerplate.
2. Delta mode as a genuine incremental updater — triage gates which segments are
   re-run/patched; everything else is carried forward from the last baseline.
3. Minimize token spend on weekday delta runs (target: ≤20 % of a baseline run
   for a typical low-drift day).
4. Preserve the existing `--run-type baseline|delta` CLI surface in
   `digiquant.olympus.hermes.chain` so callers outside CI are unaffected.

---

## Decision

### 1 — Single workflow file: `atlas.yml`

Replace `atlas-baseline.yml` and `atlas-delta.yml` with a single
`.github/workflows/atlas.yml`. The file has two triggers:

```yaml
on:
  schedule:
    # Baseline: Saturday 12:00 UTC (full weekly run)
    - cron: "0 12 * * SAT"
    # Delta: weekday noon UTC (incremental update)
    - cron: "0 12 * * MON-FRI"
  workflow_dispatch:
    inputs:
      mode:
        description: "baseline | delta"
        required: true
        default: "delta"
        type: choice
        options: [baseline, delta]
      run_date:
        description: "Logical run date (YYYY-MM-DD). Defaults to today UTC."
        required: false
        default: ""
      dry_run:
        description: "Compile + validate inputs only (no LLM calls)."
        required: false
        type: boolean
        default: false
      resume_run_id:
        description: "Resume a prior run's checkpoints (its GITHUB_RUN_ID). Empty = fresh run."
        required: false
        default: ""
```

A `resolve-mode` job (runs before the `run` job) maps the cron trigger to the correct
mode by inspecting `github.event.schedule`:

```yaml
jobs:
  resolve-mode:
    runs-on: ubuntu-latest
    outputs:
      mode: ${{ steps.pick.outputs.mode }}
      timeout: ${{ steps.pick.outputs.timeout }}
    steps:
      - id: pick
        run: |
          if [ "${{ github.event_name }}" = "workflow_dispatch" ]; then
            MODE="${{ inputs.mode }}"
          elif [ "${{ github.event.schedule }}" = "0 12 * * SAT" ]; then
            MODE="baseline"
          else
            MODE="delta"
          fi
          echo "mode=$MODE" >> "$GITHUB_OUTPUT"
          echo "timeout=$( [ "$MODE" = "baseline" ] && echo 240 || echo 120 )" \
            >> "$GITHUB_OUTPUT"
```

The `run` job sets `timeout-minutes: ${{ needs.resolve-mode.outputs.timeout }}` and
branches on `needs.resolve-mode.outputs.mode` where the two paths diverge.

### 2 — Shared boilerplate, parameterized divergences

All steps that are identical today become a single definition in the merged file. The
diverging parameters are injected via the `mode` output:

| Parameter | Baseline | Delta |
|-----------|----------|-------|
| `--run-type` | `baseline` | `delta` |
| `--auto-baseline` flag | absent | present |
| `LANGSMITH_PROJECT` | `atlas-baseline` | `atlas-delta` |
| `timeout-minutes` | 240 | 120 |
| Artifact name prefix | `atlas-baseline-` | `atlas-delta-` |
| Issue failure title | `atlas-baseline-failure` | `atlas-delta-failure` |

Everything else (install, preflight, env secrets, retry loop, upload, issue body
format) is unconditional.

### 3 — Delta as a genuine incremental doc-patch

The current delta path re-runs all pipeline phases with `--run-type delta`. The triage
phase (`atlas/phases/triage_phase.py`) runs first: `TriageDeps` supplies the Supabase
client + price-lookback window; the node calls `triage.evaluate()` and writes a
`DeltaTriageResult` (`atlas/state.py`) into `AtlasResearchState.triage`. However, even
gated nodes currently regenerate their full document from scratch when they do run,
giving the same per-document token cost as a baseline.

The proposed delta strategy is **patch, not regen**:

1. **Triage phase** (already exists) — compares today's market signals to the last
   baseline snapshot. The triage node (built by `build_triage_node` in
   `atlas/phases/triage_phase.py`) produces a `DeltaTriageResult`
   (`atlas/state.py:DeltaTriageResult`) that lists per-segment
   `DeltaTriageDecision` entries with a `decision: "regenerate" | "carry"` field and
   a mandatory/high/standard/low tier. The result is stored in
   `AtlasResearchState.triage`.

2. **Selective fan-out** — only segments whose `DeltaTriageDecision.decision ==
   "regenerate"` proceed to their research nodes. All other segments carry the last
   baseline document forward unchanged (shallow copy of the Supabase row,
   `source_run_id` preserved, `updated_at` untouched).

3. **Incremental doc-edit** — for stale segments, the research node receives both the
   prior baseline document and the new signals. The LLM prompt is switched to an
   "edit mode" variant: "Here is the existing document. Update only the sections
   affected by the following new data. Preserve all unchanged sections verbatim." This
   is cheaper than full regeneration and produces semantically coherent patches.

4. **Phase 7 synthesis** — re-runs only if ≥1 segment was patched, using the mixed
   set (patched + carried-forward). If zero segments are stale the pipeline exits
   early after recording a `no-op delta` diagnostics row.

5. **Hermes phases (7c/7cd/7d/9)** — always re-run on delta (they are cheap relative
   to research fan-out, and allocation must reflect today's price/signal state).

**Token-budget expectations:**

| Scenario | Baseline | Delta (typical) | Delta (high-drift) |
|----------|----------|-----------------|--------------------|
| Segments re-run | all | ≤5 of ~30 | ≤15 of ~30 |
| Approx. token cost | ~$0.80 | ~$0.10–$0.20 | ~$0.30–$0.50 |
| Runtime | ~90 min | ~15–25 min | ~40–60 min |

_(Estimates based on current `OPENROUTER_COST_QUALITY_TRADEOFF=10` / DeepSeek-class
routing from #802.)_

### 4 — Cron schedule without runner contention

The Saturday baseline (`0 12 * * SAT`) and the weekday delta (`0 12 * * MON-FRI`)
share the same UTC noon slot but never land on the same day. No runner-level
concurrency control is needed beyond the existing `concurrency` groups:

```yaml
concurrency:
  group: atlas-${{ needs.resolve-mode.outputs.mode }}
  cancel-in-progress: false
```

Baseline and delta runs are in separate concurrency groups, so a slow Saturday run
cannot block Monday's delta, and a stuck delta cannot cancel a baseline.

### 5 — Python CLI backward-compatibility

`digiquant.olympus.hermes.chain` already accepts `--run-type baseline|delta|monthly`
(see `_build_cli_parser` in `chain.py`). The proposed workflow calls it as:

- Baseline: `python -m digiquant.olympus.hermes.chain --run-type baseline --run-date <date>`
- Delta: `python -m digiquant.olympus.hermes.chain --run-type delta --run-date <date> --auto-baseline`

No CLI changes are required for the workflow migration. The incremental doc-edit
behavior (Section 3) is a pipeline-internal change; the CLI surface is unchanged.

---

## Migration plan

### Phase 1 — Workflow consolidation (low-risk, no Python changes)

1. Create `.github/workflows/atlas.yml` implementing Sections 1–2.
2. Disable the cron schedules in `atlas-baseline.yml` and `atlas-delta.yml` (set
   `schedule: []`) but keep the files as no-ops until the new workflow is validated
   over two Saturday + five weekday runs.
3. After validation, delete `atlas-baseline.yml` and `atlas-delta.yml`.

This phase is safe to ship independently. The Python pipeline is untouched; only the
CI wrapper changes.

### Phase 2 — Incremental doc-patch delta (medium-risk, Python changes)

1. Add `delta_mode: Literal["patch", "full"] = "full"` to `AtlasInput`. Delta runs
   from CI pass `delta_mode="patch"`; the existing behavior is preserved as `"full"`.
2. Implement the selective fan-out gate in `triage_phase.py` / `graph.py`: skip-and-carry
   nodes when `delta_mode == "patch"` and the segment's `DeltaTriageDecision.decision ==
   "carry"` (per `AtlasResearchState.triage`).
3. Add "edit mode" prompt variants to the affected research skills (Pillar skills for
   each segment type). The prompt switch is conditional on `delta_mode`.
4. Add an early-exit path in `run_atlas_then_hermes` when triage reports zero stale
   segments (write `no-op delta` diagnostics row and return without invoking Hermes).
5. Update `atlas.yml` to pass `ATLAS_DELTA_MODE=patch` for the delta path; `chain.py`
   reads this env var and sets `AtlasInput.delta_mode`.

Phase 2 gates on Phase 1 being stable. It requires a scoring pass and owner sign-off
before merge (Python changes to the live pipeline path).

### Backward-compatibility for `--run-type`

The `--run-type baseline|delta|monthly` CLI flag in `chain.py` is unchanged throughout.
The `delta_mode` field is an orthogonal axis (how much to re-run, not which shape to run).
Callers that invoke `chain.py` directly (e.g., local developer runs, non-CI scripts) are
unaffected by either phase.

---

## Consequences

**Positive:**

- One file to maintain instead of two — env-var changes, new secrets, and step upgrades
  apply once.
- Delta runs become meaningfully cheaper than baseline runs (goal: ≤20 % token cost on
  low-drift days) rather than just a triage-gated full run.
- Concurrency groups remain independent; no cross-mode blocking.
- The existing `--run-type` CLI surface is fully preserved.

**Negative / tradeoffs:**

- The `resolve-mode` job adds a small fixed overhead (~15 s) to every run for the
  schedule→mode mapping.
- The Phase 2 "edit mode" prompt path introduces a new LLM call pattern that needs
  evaluation: does the model faithfully preserve unchanged sections, or does it silently
  rephrase them? This needs a pilot over 2–3 delta runs before enabling in production.
- Deleting the two old workflow files removes their individual run histories from the
  GitHub Actions UI (histories are tied to the workflow file path). Export run summaries
  before deletion if historical timing data is needed.

---

## Open questions (owner decision required)

1. **Edit-mode prompt fidelity.** The incremental doc-patch strategy assumes the LLM
   preserves unchanged sections verbatim. Should we add a diff-based post-processor that
   rejects a patch where >N % of unchanged sections were modified (and falls back to full
   regen for that segment)?

2. **Staleness thresholds.** The triage phase needs configured thresholds per segment
   type (e.g., macro re-runs if the Fed odds move >2 %; a ticker re-runs if its price
   moves >3 % or a news event fires). Who owns these thresholds, and how are they tuned?
   Are they in `config/` (code-reviewed) or in Supabase (operator-tunable at runtime)?

3. **Phase 1 cutover timing.** Two Saturday + five weekday runs to validate before
   deleting the old files — is that the right bar, or should we require a full month
   of clean delta runs given the prior reliability issues?

4. **LANGSMITH_PROJECT names.** The proposed file preserves `atlas-baseline` and
   `atlas-delta` as the LangSmith project names for continuity. Should they be
   consolidated into a single `atlas` project with a `run_type` tag to simplify the
   LangSmith dashboard?

5. **`atlas-monthly.yml` scope.** This ADR does not cover `atlas-monthly.yml` (it
   exists but is not mentioned in the #814 scope). Should the monthly workflow be
   folded into the same `atlas.yml` as a third mode, or kept separate?

---

## Links

- Issue: [#814](https://github.com/digithings-ai/digithings/issues/814)
- Workflow files: `.github/workflows/atlas-baseline.yml`, `.github/workflows/atlas-delta.yml`
  (both confirmed present on `develop`; `atlas-monthly.yml` also exists — see open question 5)
- Python entry point: `digiquant/src/digiquant/olympus/hermes/chain.py`
  (run as `python -m digiquant.olympus.hermes.chain`; `digiquant/src/digiquant/olympus/` package
  confirmed present — `__init__.py` exists at that path)
- Triage types: `DeltaTriageResult`, `DeltaTriageDecision` in `digiquant/src/digiquant/olympus/atlas/state.py`;
  `TriageDeps` (dependency container) in `digiquant/src/digiquant/olympus/atlas/phases/triage_phase.py`
- Predecessor: [ADR-0015](0015-atlas-vs-hermes.md) (Atlas/Hermes split)
- Related: [ADR-0014](0014-atlas-in-digiquant.md) (Atlas in digiquant)
