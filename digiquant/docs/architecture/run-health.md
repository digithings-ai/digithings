## Run health telemetry — `run_diagnostics` (#1736)

> Split out of [digiquant/ARCHITECTURE.md](../../ARCHITECTURE.md) (DIG-3399). Prose is unchanged. Relative links were adjusted for this directory.

`digiquant/src/digiquant/research/diagnostics.py` derives **two** verdicts from a
finished run's state, and they are deliberately not the same signal:

Call-level transparency is a separate relation from this aggregate health row. Migration 066
adds the ordered `olympus_run_events` base table and curated `olympus_run_event_trace` view;
historical diagnostics rows are not backfilled because aggregate counters cannot reconstruct
individual calls, ordering, retries, or timing without fabrication.

| Field | Question | Consumers |
|---|---|---|
| `RunSummary.status` | Was the run healthy? | `run_diagnostics.status`, `apps/dashboard` (`run-episodes.ts` `classify()`, `freshness-banner.tsx` `isOk()`) |
| `RunSummary.retry_signal` | Is re-running worth the money? | `chain._retry_worthy` → the process exit code → CI's outer-retry loop |

`status` stays inside `ok | degraded | failed | cancelled` — there is no CHECK constraint on
the column, but both frontend readers string-match, so a new value would silently fall
through to "unknown". `retry_signal` is frozen at the pre-#1736 rules; `is_degraded()`
returns it, which is why that function's name no longer matches the health verdict.

### One row per retry ATTEMPT, not per workflow run (#1762)

`pipeline-digiquant.yml` retries the chain up to `MAX_OUTER_ATTEMPTS=2` times **inside one job**,
so every attempt sees the same `GITHUB_RUN_ID`. That was the entire upsert key, so the last
attempt — usually the cheap checkpoint-resumed one — replaced the expensive attempt's tokens,
cost, `status` and `error_summary`. 28 of 54 production rows were affected.

The forensic tell is `created_at`: `_row()` omits it, so `ON CONFLICT DO UPDATE` preserved the
*first* insert's value while replacing everything else, leaving rows whose creation predates
their own `started_at`. **Keep omitting it** — that asymmetry is what made the corruption
detectable and is the only way a future collision would be visible.

- The attempt number reaches Python through exactly one channel: `DIGIQUANT_ATTEMPT`, exported
  per attempt by the workflow's retry loop and read by `chain._outer_attempt()` (defaults to 1,
  tolerant of a malformed value — telemetry must never kill a run). Guarded by
  `tests/scripts/test_pipeline_dashboard_attempt.py`, because dropping the export restores the
  defect with no error anywhere and no symptom but a cost figure that is quietly a floor.
- `run_id` is **unchanged** and still the resume handle — `chain._thread_base = resume_run_id or
  run_id` builds the LangGraph checkpoint thread from it, and `--resume-run-id` takes a bare
  `GITHUB_RUN_ID`. The attempt is a separate column precisely so the telemetry key and the
  resume key cannot drift apart.
- Migration `065` swaps the primary key to `(run_id, attempt)` and appends `attempt` to the
  `run_health` view — appended **last**, since `CREATE OR REPLACE VIEW` can only add
  columns. Pre-existing rows carry the sentinel `0`, never `1`: backfilling 1 would assert 28
  provably-collapsed rows are first attempts, which is the fabrication the change exists to end.
- `apps/dashboard/lib/run-episodes.ts` gets fixed for free — `attempts = rows.length` and the
  `recovered` outcome were built on the assumption that attempts are distinct rows. It orders by
  `attempt` where usable and falls back to `created_at` for `0`-sentinel rows.
  `RUN_DIAGNOSTICS_LIMIT` rose 30 → 90 because a retried date now consumes several slots.

**Escalation rules on `status`** (each records itself in `breakdown.degraded_reasons`):
any failed research segment (STRICT — supersedes the `DIGIQUANT_DEGRADED_RUN_PCT` share rule for
health purposes), more than `_PORTFOLIO_DEGRADED_PCT_DEFAULT` of the run's portfolio deliberations
failed, and `research_produced and not book_committed` (the no-book gate — closes the
residual detection hole behind #1766, which the #1555 commit gate misses because it only
fires once a book has *materialized*).

### Spend alert — the one breakdown key that is NOT a contributor (#1764)

`RESEARCH_SPEND_ALERT_USD` (default $10) is a warning threshold on one chain invocation. Over it,
`breakdown.spend_alert` is written, a warning is logged, and `_emit_ci_warning` raises a GitHub
Actions `::warning::` annotation — the annotation is the part that makes this an alert rather
than a record, since a jsonb key and a log line are both passive.

**Alert only, by the owner's explicit decision.** Nothing in this path touches `status`,
`retry_signal`, or the exit code. A mid-run abort would leave a partially-published run, and
#1749/#1751 established that partial states are where the silent-staleness defects live. There
are tests pinning the negative property; do not relax them into a ceiling without a new decision.

**Token-derived fallback (#4596).** The house upstream reports no per-call cost, so the raw
`cost_usd` in the usage snapshot is `0.0` on every run and this alert could never fire. `_row`
therefore resolves `est_cost_usd` once — the reported cost when it is positive, otherwise
`pricing.estimate_cost_usd(usage["by_model"])` against the committed per-model table in
`config/digiquant-model-prices.json` (loaded by `research/pricing.py`) — and feeds the SAME
value to both `spend_alert` and the `est_cost_usd` column. The estimator returns `None` when no
tokens were priced (no priced model, or a priced model whose tokens are all zero/junk), so
behaviour is unchanged when no price is known (never fabricate `$0`).

Each price is taken verbatim from the repo's own committed snapshot,
`docs/providers/snapshots/<provider>.yaml` (`paid_tier.models[].cost_per_1m_input` /
`cost_per_1m_output`); `deepseek/deepseek-v4-pro` deliberately uses the snapshot's **peak**
rate. A price no snapshot corroborates fails
`tests/dq/research/test_pricing.py::TestThePriceTable::test_every_committed_price_is_corroborated_by_a_committed_snapshot`.
`google/gemini-3.7-flash` is a house slug with no price: it is absent from the committed
`gemini.yaml` (the snapshot predates the model), so it is listed in the config file's
`unpriced_slugs` until that snapshot is refreshed.

**The table is config, not code (#5029).** The slugs and their prices live in
`config/digiquant-model-prices.json`, read by `load_price_table()` (mtime-cached on
`(path, mtime)`, so an edited file takes effect without a restart). `DIGI_CONFIG_PATH`
overrides the directory exactly as it does for `digigraph.model_config`; unset, the repo root
is tried before the CWD-relative `config/`. Two consequences worth knowing before editing:

- **Provenance is required, not decorative.** Every price entry carries the `source` snapshot it
  came from and its `last_checked` date, and a rate that is not the obvious one carries
  `rate` + `note`. `ModelPrice` carries these onto the parsed row, so the audit trail is
  readable without opening the JSON. The loader **drops** an entry whose `source` is missing or
  does not point under `docs/providers/snapshots/` — an uncitable price is not a price. A bad
  entry is dropped by name with a warning and the rest of the table still loads, because one
  bad row must not under-report every other model's spend.
- **Failing soft is loud.** A missing/unreadable/corrupt config yields an empty table plus a
  `warning`, never an exception — telemetry must not break a chain run. An empty table means
  `estimate_cost_usd` returns `None` and the caller falls back to the provider's own `0.0`,
  i.e. the pre-#4596 behaviour, so the warning is the only signal that spend went unmeasured.
  Production runs the chain in CI (`python -m digiquant.portfolio.chain`) with the repo checked
  out, so `config/` is present there; the `digiquant` **container** mounts no `config/` and sets
  no `DIGI_CONFIG_PATH`, so in that deployment the table resolves empty and only the warning
  fires.

It is computed in `_row` rather than through `register_breakdown_contributor` because **that seam
is `state -> dict` and spend does not live in state** — it arrives in the `digigraph.usage`
snapshot, which is only in scope at that call site. `models`, `by_kind` and `cached_tokens` set
the precedent for a usage-derived breakdown key. Widening `summarize_run` to carry usage was
considered and rejected: two of its three callers want only `retry_signal` and have no usage to
pass. `diagnostics` imports `telemetry` lazily inside `_row` because `telemetry` imports
`register_breakdown_contributor` from `diagnostics` — a module-level import is a cycle.

Scope limit to state honestly when reading the key: the threshold is **per invocation, not per
day**. `digigraph.usage` is process-global and `chain` calls `start()` once per process, so three
outer-retry attempts at $6 each do not trip a $10 threshold on an $18 day. Since #1762 the day's
true total *is* recoverable (`sum(est_cost_usd) … GROUP BY run_date` now sums across attempts),
but that needs a query, so a daily aggregate belongs in a separate check.

### Extending `breakdown` — use the seam, not a new edit site

`breakdown` is schema-free jsonb, so a new telemetry key needs no migration. Register a
contributor rather than editing `summarize_run`:

```python
from digiquant.research.diagnostics import register_breakdown_contributor

register_breakdown_contributor(lambda state: {"roster": _roster_tally(state)})
```

Contributors are pure, fail-soft (an exception is logged and swallowed), may not overwrite an
existing key, and run **once per run** inside `_segment_counts`. Note the split:
`_segment_totals` is the pure counter used by `research_produced`, which the chain calls
*mid-run* to gate portfolio — contributors must never see that half-populated state.

