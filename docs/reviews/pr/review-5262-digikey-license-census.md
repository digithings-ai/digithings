# Review — PR #5262: temporary read-only licence census route (DIG-2203)

- **Reviewer:** in-session fresh-context subagent (`<!-- in-session-review -->` pass, not the author session)
- **Subject:** digithings-ai/digithings PR #5262, base `develop`, head `5487eb9ee98a8fd8748b638dbf1bc5d6c3594709`
- **Diff reviewed:** `git diff cddfc6c51f...5487eb9e` — 2 files, +431 / −0, purely additive
  - `digikey/src/digikey/server.py` +101
  - `tests/dk/test_license_census.py` +330
- **Verdict:** **APPROVED** (code under review). No security, correctness, or read-only defect found.
- **Severity counts:** Critical 0 · High 0 · Medium 0 · Low 1 · Informational 4 · Residual risks 1
- **Merge note:** this is a `digikey/` auth-path change — the repo human gate and DIG-2203 step 5 (Security & Risk Lead sign-off) still block agent merge. This review does **not** clear that gate.

> Note on the head: the checked-out worktree is at `0ef58b15ff` (the census commit). The PR head
> `5487eb9e` is that commit plus a `develop` merge whose only delta is `config/contract/*`.
> `git diff 0ef58b15ff 5487eb9e -- digikey/src/digikey/server.py tests/dk/test_license_census.py`
> is empty, so the reviewed census code is byte-identical to the PR head.

## Lenses

### 1. Security (digikey auth path) — PASS
- Reuses the existing gate: `_require_admin(request)` at `server.py:734`, defined at `server.py:134-140`
  (`secrets.compare_digest` at :139, 503 when unset at :137, 401 on mismatch at :140). No new credential,
  token, or config introduced.
- Handler signature takes only `Request` (`server.py:727`); OpenAPI shows zero query parameters for the GET.
- Both SQL statements are module-level `text(...)` literals with **no bind placeholders**; a request body,
  query string, or header cannot reach the SQL text. Pinned by `test_census_sql_has_no_bound_parameters`
  and `test_census_query_and_body_never_reach_sql`.
- Error path logs `type(e).__name__` only (`server.py:743`), never the exception body, so a SQLAlchemy
  error cannot put the DSN in logs. `raise HTTPException(...) from e` does not leak either: the digibase
  handler (`digibase/src/digibase/errors.py:65-75`) returns `detail` only, and the repos 500 handler
  returns a fixed `"Internal server error"`. Pinned by `test_census_store_failure_returns_503_without_leaking_the_dsn`
  (asserts the DSN is absent from both body and `caplog`).
- Response carries only counts and `customer_slug`s; an extra `license_id` in a source row is dropped
  (`server.py:751-757`, `test_census_leaks_no_licence_rows_or_tokens`).

### 2. Correctness — PASS
- `expires_at` is `Integer` (unix `exp`): `db_schema.py:139`; the heartbeat compares it as an int
  (`license_heartbeat.py:104`). The census therefore casts the clock, `extract(epoch FROM now())::bigint`
  (`server.py:705`) — a timestamp compare would be wrong. Pinned by
  `test_census_expired_rows_uses_integer_epoch_not_timestamp`.
- Both statements match the strings the test file labels as "approved" (whitespace-normalised), run exactly
  twice with `params is None`, and name only `digikey_licenses`
  (`test_census_sql_matches_approved_statements`, `test_census_touches_only_the_licenses_table`,
  `test_census_runs_exactly_the_two_approved_statements`).
- Response model exposes exactly the six approved fields — verified against the generated OpenAPI schema
  (`total_rows, revoked_rows, expired_rows, oldest_issued_at, newest_issued_at, per_customer`).
- Empty table → `oldest_issued_at`/`newest_issued_at` null and `per_customer == []`
  (`test_census_empty_table_returns_null_timestamps`).

### 3. Read-only guarantee — PASS
- Both `SELECT`/aggregate; no `INSERT`/`UPDATE`/`DELETE`/`TRUNCATE`/DDL, and no `session.commit()` in the
  new path (`server.py:736-758`). `sessionmaker(... expire_on_commit=False, autoflush=False)` closes the
  session without committing on context exit (`digikey/src/digikey/db.py:57-60`). The fake session's
  `commit()` raises, so any regression commit fails the suite (`tests/dk/test_license_census.py:106-107`).

### 4. Claim accuracy (PR description vs source)
| Claim | Result |
|---|---|
| Route is `GET /v1/admin/licenses/census` | ✔ registered (`test_census_route_is_registered`; OpenAPI) |
| Reuses `_require_admin` (`compare_digest`, 503 unset, 401 mismatch) | ✔ `server.py:134-140, 734` |
| No new credential/token/config | ✔ |
| Handler takes only `Request`, nothing caller-supplied reaches SQL | ✔ `server.py:727`; OpenAPI `parameters: []` |
| No string interpolation / bind params | ✔ literal concatenation; no `:param` |
| Aggregate SELECTs only, no DML/DDL, no `commit()` | ✔ |
| `expires_at` is integer unix exp → epoch cast | ✔ `db_schema.py:139`, `server.py:705` |
| Error path logs `type(e).__name__` only | ✔ `server.py:743` |
| `/v1/admin/...` matches existing admin routes | ✔ (`/v1/admin/keys`, `/v1/admin/licenses/{id}/revoke`) |
| "17 tests" for the census file | ✔ collected 17 |
| `pytest tests/dk/ -q → 163 passed` | ✘ **observed 188 passed** (see Low-1) |
| `ruff check` / `ruff format --check` clean | ✔ "All checks passed!" / "50 files already formatted" |

### 5. Regression / blast radius — PASS
- Additive only (numstat `101 0` / `330 0`); no deletions, no edits to existing routes.
- `healthz` still present and unchanged (`server.py:117`); smoke test confirms both `/healthz` and the new
  route register and the app's OpenAPI still generates.

## Findings

### Low-1 — PR Testing Evidence claim does not reproduce on the head
The PR body states `python3 -m pytest tests/dk/ -q → 163 passed`. On the reviewed head the same command
yields **188 passed**. The census file's own count (17) is exact, so this is a stale aggregate number
(most likely captured before a `develop` merge that added `tests/dk/*` tests), not a code defect.
Same command also passes against the branch tip. Evidence: PR body "Tests" section; observed run below.

### Info-1 — `expired_rows` is a raw past-exp count, not the heartbeat's expired classification
The census counts `expires_at < extract(epoch FROM now())::bigint` (`server.py:705`) with no leeway and no
revoked-exclusion, whereas `resolve_license_state` treats a row as expired only when
`expires_at + CLOCK_SKEW_LEEWAY_SEC <= now` and lets revoked beat expired
(`license_heartbeat.py:99-106`, `CLOCK_SKEW_LEEWAY_SEC = 300` at `license_verify.py:28`). Consequences a
reader of the five DIG-2163 numbers should know: (a) rows expiring within the next 300 s are counted in
`expired_rows` but are still `valid` per heartbeat; (b) a revoked-and-expired row is counted in **both**
`revoked_rows` and `expired_rows`. This matches the approved statement, so no change requested — flagging
for interpretation only.

### Info-2 — `digikey/ARCHITECTURE.md` §3 API Surface not updated
The PR template's "Documentation Updated" checkbox asks for `{component}/ARCHITECTURE.md` when the public
API changes, and §3 enumerates every route (`ARCHITECTURE.md:71-131`) without the census route. Defensible
because the route is explicitly temporary and must be deleted after the one-time read; noting for the
record, not requesting a change (avoiding doc churn for a delete-on-read route).

### Info-3 — test comparison does not prove approval provenance
`test_census_sql_matches_approved_statements` compares the implementation to `APPROVED_*_SQL` defined in the
same test file (`tests/dk/test_license_census.py:27-43, 157-161`). It proves the implementation matches the
author's copy, not that the text equals what DIG-2203 approved; no independent copy of the approved
statements exists in-repo. No basis to refute — recorded as a verification gap.

### Info-4 — merge-queue state carried forward (context, not review)
The merge queue has handed this PR back repeatedly on `check 'All commits signed off' is FAILURE` and
`mergeStateStatus=BEHIND`. Those are merge gates (DCO / base freshness), outside this review's lenses.
The PR body also carries `<!-- in-session-review -->` in the description body; the coverage script reads
that marker from **comments** (`scripts/check_review_coverage.py:289-290`, `comments(last:100)`), so the
body marker never satisfied the gate — this comment is the real hatch.

## Residual risk (carry forward — known, not new)
The two statements use `count(*) FILTER (...)` and `extract(epoch FROM now())::bigint`, which SQLite cannot
execute. The suite therefore pins the SQL string and shapes the response against a fake session
(`tests/dk/test_license_census.py:73-115`), so **the statements have never run against real Postgres**.
- Likelihood the SQL is valid: high (both constructs are standard PostgreSQL; the epoch/int comparison is
  type-correct).
- Mitigation at first production call: sanity-check `expired_rows` against the `issued_at` range and
  `total_rows` — an implausible `expired_rows`/`total_rows` ratio would expose a bad epoch cast,
  and a 500/503 rather than a JSON body would expose a dialect error. If `expired_rows` looks wrong,
  treat it as a failed read, not a licence fact.

## Commands run (observed results)
```
git diff cddfc6c51f...5487eb9e --numstat
  101  0  digikey/src/digikey/server.py
  330  0  tests/dk/test_license_census.py

python -m pytest tests/dk/ -q          →  188 passed in 26.90s
python -m pytest tests/dk/test_license_census.py -q  →  17 passed in 0.94s
python -m ruff check digikey/ tests/dk/   →  All checks passed!
python -m ruff format --check digikey/ tests/dk/  →  50 files already formatted
```
OpenAPI smoke (worktree on `PYTHONPATH`): census route present `True`, `healthz` present `True`,
GET parameters `[]`, response fields exactly the six approved names.
