# Review: PR #4992 — fan-out leg isolation (digisearch `query_index`)

- **Reviewer:** fresh-context subagent (Claude, in-session review; did not author the change)
- **Subject:** PR digithings-ai/digithings#4992 — commit `8bb876321` "fix(digisearch): isolate fan-out legs so one bad index cannot deny the rest", on `fix/4991-fanout-leg-isolation` over `origin/main`
- **Scope reviewed:** `digisearch/src/digisearch/search/_stub.py` (+59/-9), `tests/ds/test_multi_index_query.py` (+132)
- **Verdict:** **approve** (restores service; minimal, tested, negative-controlled) — 2 major findings that are **must-follow, not merge-blocking** for the live outage
- **Severity counts:** critical 0 · major 2 · minor 3 · info 4

Verification performed: `pytest tests/ds/test_multi_index_query.py` → 13 passed; `pytest tests/ds/ -m unit` → 1208 passed, 1 pre-existing environmental failure (`test_chonkie_chunking.py::test_get_chunker_backend_semantic_and_token`, `ImportError: model2vec`; that file has zero references to `query_index`); `ruff check` + `ruff format --check` clean on both files; negative control re-run independently (see i3). **All of the above need `PYTHONPATH=$PWD/digisearch/src`** — see i3.

---

## Major

### M1 — `except Exception` also neutralizes the two deliberately fail-loud error classes

`_query_fanout_leg` catches every `Exception` (`_stub.py:344`), which includes `SearchBackendError` and `VectorizeBackendError` — the classes that exist specifically so that a configured-but-failing index is **not** silently answered from a different corpus:

- `_stub.py:103-108` (`_vectorize_backend` docstring): "must never be answered from a different corpus with no error surfaced to the caller."
- `_stub.py:173-175` / `:93-95`: Chroma and Azure wrap `_BACKEND_ERRORS` into `SearchBackendError`, which is deliberately **not** in `_BACKEND_ERRORS` (`backend_errors.py:19`), so it escapes `_query_single_index` — and now gets swallowed per leg.
- Pinned by existing tests, single-index only: `tests/ds/test_vectorize_selection.py:14`, `:61` (both call `_stub.query_index(query, "occ-help")`). Nothing pins the fan-out case, so the semantic change is invisible to CI.

Verified against the PR code (`PYTHONPATH` set, `_backends` swapped for one leg that raises):

```
SearchBackendError     FANOUT  -> no raise; backend='multi' ids=['live-1']
SearchBackendError     SINGLE  -> raises SearchBackendError (invariant intact)
VectorizeBackendError  FANOUT  -> no raise; backend='multi' ids=['live-1']
VectorizeBackendError  SINGLE  -> raises VectorizeBackendError (invariant intact)
```

This is the honest answer to review question 1: `raise errors[0]` does not mislead *about the surviving corpus*, but the isolation layer now silently absorbs the error types the file documents as must-surface. Not a data leak (a dropped leg can only remove rows), and not a caller-contract break — no production caller catches these types (`grep`: only `scripts/index_occ_tickets.py:305` catches the mismatch class). Fix cost is documentation plus one test, not behavior change:

- state the reversal in the `query_index` docstring next to the new "isolation contains the damage" paragraph, and
- add a test pinning `SearchBackendError` on a fan-out leg → dropped + logged (mirroring `test_failing_leg_is_logged_with_its_index_name`), so the decision is on the record rather than implied.

**Do not** narrow the catch to re-raise the mismatch class — `EmbeddingModelMismatchError` (`chroma_errors.py:11`, deliberately not a `ValueError`) is the incident and must keep degrading.

### M2 — partial degradation is invisible to the caller, in the exact way the docstring rejects for the all-fail case

`_stub.py:364-372` argues that returning nothing from a fan-out would be "a confident wrong answer rather than a visible failure". A 1-of-2 merge has the same character and gets no signal: the response is `SearchResponse(..., backend="multi")` (`:399`) with nothing recording which legs were dropped, and the OCC system prompt tells the model both indexes were searched together (`apps/digithings-stack-cloudflare/src/index.ts:133`). So after this fix, a broken `occ_tickets` yields confident help-doc-only answers that read as complete — a quieter failure than the outage being fixed.

Cheapest mitigations (any one; needs an issue, not a blocker):

- a `degraded_indices` field on `SearchResponse` (or a `multi-1of2`-style `backend` marker) consumed by `digisearch/mcp_server.py:94-96` / `server.py:643` so the tool text can say one index was unavailable;
- or at minimum a single `logger.warning` at the end of `query_index` naming every dropped index (today only the per-leg `logger.exception` at `:345` carries `index_name`, in `extra` only).

Side effect worth noting in the same issue: `backend="multi"` for a 1-of-2 merge makes `effective_query_mode(mode, "multi")` (`embedding/factory.py:52-63`) skip its coercion, so a `keyword` request is reported as keyword-executed even though the survivor was Chroma ANN. Pre-existing (fan-out always reported `multi`), now more reachable.

---

## Minor

- **m1 — test helper annotation contradicts its own check.** `_patch_legs(monkeypatch, **behaviour: str | Exception)` (`tests/ds/test_multi_index_query.py:117`) is annotated `str | Exception`, but the body checks `isinstance(outcome, BaseException)` (`:125`) and `test_base_exceptions_are_not_swallowed` (`:221-226`) passes `KeyboardInterrupt()`, which is **not** an `Exception`. Annotate `str | BaseException`. Not a CI break today: `.github/workflows/ci-type-check.yml:49` runs mypy over `digibase/` + `digikey/` only, never `tests/`. Two cosmetic cleanups in the same helper: `_fake.SearchResponse = SearchResponse` (`:127`, assigned at `:133`) is an unnecessary function-attribute hop — `SearchResponse` is already imported at module scope (`:8`) and is the only thing that indirection buys; and `_single_failure(index_name, error)` (`:137-138`) ignores its `error` argument entirely (ruff `ARG` is not selected, so lint stays quiet).
- **m2 — `raise errors[0]` is honest but thin.** `_stub.py:395-397` keeps a real traceback (`logger.exception` already logged each dropped index with `index_name`, so diagnosis is not lost) and `errors` cannot be empty there because `names` is non-empty by `:374-375`, so there is no `IndexError` risk. What it does lose: the other failures are invisible at the raise site, and the chosen error is whichever index happens to be first in the configured string. A one-line `logger.error("fan-out: all %d legs failed", len(names), extra={"index_names": names})` before the raise — or `ExceptionGroup` on 3.11+, which the repo's 3.12 pin allows — makes the case self-describing. Cosmetic type nit: `_query_fanout_leg` is annotated `-> tuple[SearchResponse | None, BaseException | None]` (`:328`) but only `Exception` instances can ever be returned.
- **m3 — the honest-failure guarantee still has a hole this PR does not close (pre-existing).** A leg whose backend is unconfigured returns `SearchResponse(results=[], backend=None)` (`:280-292`) instead of raising, so a fan-out where *no* leg is backend-served still answers HTTP 200 with zero hits and the model says "nothing found" — the confident-wrong-answer shape the new docstring rejects. `EmbeddingConfigError` is a `RuntimeError` (`embedding/factory.py:33`), so it is absorbed by the inner `except _BACKEND_ERRORS` at `:246` and never reaches the new all-fail guard. Worth a follow-up (e.g. raise when a fan-out had zero backend-handled legs).

---

## Info

- **i1 — RRF merge is correct with a dropped leg (question 3: no defect found).** `_rrf_merge_results` derives each leg's rank inside its own `enumerate` (`:224-231`), so removing a leg does not renumber the survivors; dedup is keyed on `chunk.id`; the truncated list is the merged one; and the emitted `rank` is re-derived `1..N` by `enumerate` at `:233-236`. `top_k` truncation (`:237`) applies after the sort, so a dropped leg cannot leak an off-by-one or over-length page. Deduplicated chunks legitimately lose one RRF contribution when their partner leg dies — that is the intended isolation effect, not a bug. `tests/ds/test_multi_index_query.py:208-218` pins the surviving-leg ordering; the per-leg `top_k` fetch (so a 1-of-2 merge can return fewer than `top_k` rows) is a recall-quality note, not correctness.
- **i2 — `except Exception` scope is right (question 2: no silent-empty path introduced).** `asyncio.CancelledError`, `KeyboardInterrupt` and `SystemExit` are `BaseException` and still propagate, so shutdown and request cancellation are unaffected — pinned by `test_base_exceptions_are_not_swallowed`. `logger.exception` keeps the full traceback plus `index_name`, so a dropped leg is never invisible. Two operational notes: a persistently broken leg emits one full ERROR traceback **per user query** (consider a first-failure WARN plus debug tracebacks), and the `extra` dict omits `duration_ms`, unlike the sibling log lines at `:251-257` (cosmetic; `outcome="degraded"` is a new value but `outcome` is free-form across the codebase — `vectorize.py:298` already uses `"clamped"`).
- **i3 — verification caveat, and it affects any evidence the PR cites.** The repo `.venv`'s editable install points at the **primary** checkout (`digisearch.__file__` → `/Users/chrisstefan/Code/digithings/digisearch/src`, currently on `task/4761-phase3-image-bake`, whose `_stub.py` has **no fan-out at all**). A bare `pytest tests/ds/test_multi_index_query.py` inside this worktree therefore imports the other tree's `digisearch`, and its 13 passes would not be evidence for this diff. Re-run with `PYTHONPATH=$PWD/digisearch/src` (that is what I used). Under it: 13/13 pass. Negative control reproduced independently by exec'ing `origin/main`'s `_stub.py` into `sys.modules` — exactly the three isolation tests fail (`test_failing_leg_does_not_take_down_the_others`, `test_failing_leg_is_logged_with_its_index_name`, `test_one_surviving_leg_keeps_its_results_ordered_by_rrf`); the other three new tests pass both before and after, which is correct — they are regression guards for behavior that must *not* change (all-fail raises, single-index still raises, `BaseException` not swallowed), not new-behavior proofs.
- **i4 — branch base.** `origin/develop` carries the same pre-fix comprehension (`git show origin/develop:.../_stub.py` → line 347, no isolation), so this is not duplicated work — but the fix lands on `main` only. The same commit should reach `develop` (or be cherry-picked there) so the next promotion doesn't leave the integration branch outage-prone and the eventual `develop`→`main` merge isn't a textual conflict on the same lines. `apps/digichat/config/examples/occ-embed.yaml:38` and the MCP default at `mcp_server.py:75` still use single-index `occ_help`, which is consistent with the untouched single-index path.

## Callers audited (question 5)

`server.py:643` (`POST /query` + orchestrator invoke), `client.py:69`, `mcp_server.py:94` (stub branch only — the client branch at `:83` catches `(RuntimeError, ValueError, ImportError, OSError, TypeError)`, which never matched the mismatch class anyway), `research_search.py:73`, `agent/pipeline.py:71`, `cli.py:117`, `demos/audit_rag_demo.py:99`. None treats a fan-out raise as a contract: all either propagate to a 500 / MCP tool error (identical to pre-fix on all-fail) or take `.results`. **No caller regresses from a leg degrading.** The single-index fast path (`:376-377`) is untouched, so `test_azure_workspace_scope.py:160` and `test_vectorize_selection.py:14,61` keep passing.