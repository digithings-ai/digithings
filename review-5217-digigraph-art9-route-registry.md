# Review — PR #5217 (commit dc2f157d3)

- Reviewer: EM (agent 6f361355-e086-4a53-a913-b5811e099ab0), execution-review stage participant for [DIG-1076](/DIG/issues/DIG-1076)
- Subject: PR #5217, commit `dc2f157d302ae1745d0c85f857ba5f2dd48d9a20` (`test(digigraph): pin the art9 ingestion routes to the running app (DIG-1076)`)
- Verdict: **approve-with-nits**
- Severity counts: high 0 / medium 0 / low 1 / info 2

Scope: 1 file — `tests/digigraph/test_art9_route_registry.py` (new, +269/-0). No
implementation change. Base is the stacked leaf-0 branch `task/1074-art9-route-registry-ds`;
this leaf adds a digigraph-side registry pin on top of leaf 0's `digibase.art9`.

The review request asked two specific questions: can the two-way diff pass vacuously, and
does the mutation assertion genuinely fail. Both are answered below with runs, not reasoning.

## Review question 1 — can the diff pass vacuously?

No. The digigraph trap is real and the test is structurally immune to it.

Measured against the live app:

- `art9.INGEST_PREFIXES["digigraph"] == ("/v1/chat",)`
- `art9.INGEST_ROUTES["digigraph"] == ["/v1/chat/completions"]`
- `art9.iter_ingest_routes(app.routes, "digigraph")` yields exactly `["/v1/chat/completions"]`
- Top-level `app.routes` has 14 entries (types `APIRoute`, `Route`, `_IncludedRouter`) and
  **zero** paths matching `v1/chat`. `/v1` is mounted lazily through an `_IncludedRouter`,
  so a naive top-level `.path.startswith("/v1/chat")` walk finds nothing.

A diff built on a top-level walk would compare an empty served set against a one-entry
registry and fail loudly, which is the safe direction — but it would also mean the leaf
never tested the real mount path. `_served_templates()` reads
`art9.iter_ingest_routes(app.routes, APP)` (leaf 0's helper, imported, never re-implemented),
which descends the include and finds the real route.

`test_the_comparison_is_not_vacuous` asserts both sides are non-empty, which pins the
enumeration itself.

Confirmed by mutation: replacing `_served_templates` with a flat top-level
`.path.startswith(_PREFIX)` walk made **5 of 5** tests fail.

There is also no F2 tautology. Nothing in the file re-declares a real production route
path — `_PREFIX` comes from `art9.INGEST_PREFIXES[APP][0]` and every probe path is an
f-string off it, so there is no second copy of the prefix that could drift from the source
of truth. The registry side is read from `art9.INGEST_ROUTES`, the served side from the live
router. Two independent sources.

## Review question 2 — does the mutation assertion genuinely fail?

Yes. Five faults injected one at a time, each reverted from a pristine copy:

| # | Injected fault | Result |
|---|---|---|
| A | `return set(), registered - served` — drop the app→registry direction | 1 failed — `test_unlisted_route_is_reported_then_clears`, "Extra items in the right set: `/v1/chat/__art9_registry_probe__`" |
| B | `return served - registered, set()` — drop the registry→app direction | 1 failed — `test_registry_entry_with_no_route_is_reported`, names `/v1/chat/__art9_registry_phantom__` |
| C | `_served_templates` replaced by a flat top-level prefix walk (blinds include traversal) | 5 of 5 failed |
| D | `_template` normalisation removed (`return path` instead of `path.rstrip("/") or "/"`) | 1 failed — `test_a_trailing_slash_route_matches_its_registry_entry`, names `/v1/chat/completions/` |
| E | diff filters the probe out (`if "__art9" not in x`) | 1 failed — `test_unlisted_route_is_reported_then_clears`, names the probe path |

Every fault is caught by exactly the test that owns it, and the failure message names the
offending path — so a future regression reports the route, not just a red test.

## Design points accepted

- `_diff()` returns `(served - registered, registered - served)`; both directions are
  asserted in `test_registry_and_running_app_agree_in_both_directions`.
- `_attached` installs probes through `app.include_router` — the same mechanism digigraph
  uses for `/v1` — and removes them by identity in a `finally`.
- An autouse `_app_routes_restored` fixture snapshots and restores `app.routes`, so a probe
  cannot leak into the other digigraph tests that share the module-level `app` singleton.
  Verified: `tests/digigraph` passes clean with and without this file present.
- `test_registry_entry_with_no_route_is_reported` monkeypatches `art9.INGEST_ROUTES` only and
  deliberately leaves `INGEST_PREFIXES` unpatched, so enumeration still filters on the real
  declared scope.
- The failure message points at leaf **L9** as owner of `digigraph/src/digigraph/server.py`
  (verified against the DIG-959 plan lines 78/87/198). L9 is blocked by L1 and L4c, so this
  leaf unblocks it.

## Verification runs

Re-run by the reviewer against the branch worktree, not copied from the PR body:

```
pytest tests/digigraph/test_art9_route_registry.py -v --tb=short   -> 5 passed
pytest tests/digigraph tests/db -q                                  -> 141 passed
ruff check tests/digigraph                                           -> All checks passed!
ruff format --check digigraph/ tests/digigraph/                     -> 144 files already formatted
```

CI on PR #5217: `Required checks passed`, gitleaks, sign-off, ruff-and-scripts, mypy
(digibase + digikey), Frontend canon guard, changes/path-filter all SUCCESS. `doc-links +
agents-init` CANCELLED (not a gate); component jobs SKIPPED by the path filter.

## Findings

- nit-1 (low) — No `review-*.md` artifact was produced inside the leaf branch. The leaf's
  allowed-file list is the test file only and the path-filter check enforces that, so the
  in-session review lives on the PR (label `reviewed:agent` plus the
  `<!-- in-session-review -->` comment) and this file, landed separately, rather than inside
  the leaf diff. Nothing to fix in the leaf.
- info-1 — PR #5217 is stacked on `task/1074-art9-route-registry-ds` and must not be merged
  independently of leaf 0 (PR #5212). Merging is a separate decision from this review.
- info-2 — Leaf 0's PR #5212 currently carries no labels and shows unknown mergeability.
  Worth resolving before the stack lands, since this leaf cannot reach `develop` until leaf 0
  does.

## Recommendation

Approve. Land after leaf 0, in stack order. No changes requested.