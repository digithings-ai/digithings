# Snapshot Daily-Contributions Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** `scripts/fetch_repo_activity.py` emits a pre-bucketed `dailyContributions` year-series so `RepoHeatmap` renders repo-level contributions without client-side fetching.

**Architecture:** Paginate the existing GitHub endpoints over a 365-day window in the weekly cron (which already holds a token), bucket per UTC day in pure Python, commit 371 `{date, count}` pairs (~10KB) into `repo-activity.json`. The component consumes it via its existing `data?` prop; live refresh keeps snapshot heat (client-side pagination would burn the 60 req/hr/IP budget).

**Tech Stack:** Python 3.12 script + `gh` CLI (existing), `RepoActivitySnapshot.dailyContributions?: HeatDay[]`, existing `RepoHeatmap data` prop.

**Spec:** Approved in chat 2026-09-08 (user: "plan to extend the snapshot builder" → plan presented → user chose subagent-driven execution). Key finding: everything needed already exists — `_commits_since()` paginates commits, the Search pagination pattern exists, `RepoHeatmap` already accepts pre-bucketed `data`, and `applyLive` preserves snapshot-only keys (like `features`/`modules`) so live refresh won't wipe the heat.

## Global Constraints

- FORBIDDEN snapshot keys (`stars`, `stargazers`, `forks`, `watchers`, `subscribers`) are never collected — `check()` asserts their absence.
- No test touches the network: `collect()` is the only function that calls `gh`; everything under it is pure or reads the working tree.
- Windowed (commits/pullsMerged/issuesClosed, last 30 days on `main`) vs unwindowed (issuesOpen/pullsOpen/latestRelease, current state) distinction stays load-bearing — do not conflate.
- Heat is snapshot-sourced; the client live path (`fetch.ts`) is NOT extended (unauthenticated rate budget).

---

### Task 1: `dailyContributions` type + prop wiring

**Files:**
- Modify: `frontend/digiweb/web/src/components/repo-activity/types.ts`
- Modify: `frontend/digiweb/web/src/components/repo-activity/RepoActivity.tsx`

**Interfaces:**
- Consumes: `HeatDay` (already exported from `./heatmap`)
- Produces: `snapshot.dailyContributions?: HeatDay[]` for Task 4

- [ ] **Step 1: add optional field to `RepoActivitySnapshot`**

```ts
/** Pre-bucketed per-day contributions for the heatmap (oldest → newest).
 *  Emitted by scripts/fetch_repo_activity.py; absent in older snapshots. */
dailyContributions?: HeatDay[];
```

(`HeatDay` import type from `./heatmap`.)

- [ ] **Step 2: Detailed heat block passes it through**

```tsx
<RepoHeatmap
  pulls={data.mergedPulls}
  data={data.dailyContributions}
  weeks={53}
/>
```

(falls back to pulls-bucketing when absent — old snapshots keep working)

- [ ] **Step 3: run component tests**

Run: `npm test -- src/components/repo-activity` (from `frontend/digiweb/web`)
Expected: 5 files / 19+ pass; `demo.ts` without the field still renders (fallback path).

- [ ] **Step 4: Commit**

```bash
git add frontend/digiweb/web/src/components/repo-activity/types.ts frontend/digiweb/web/src/components/repo-activity/RepoActivity.tsx
git commit -m "feat(digiweb): wire snapshot dailyContributions into RepoHeatmap"
```

### Task 2: pure bucketer + Search paginator in the script (TDD)

**Files:**
- Modify: `scripts/fetch_repo_activity.py`
- Test: `tests/scripts/test_fetch_repo_activity.py`

**Interfaces:**
- Consumes: existing `_gh()` helper (stub via monkeypatch in tests — no network)
- Produces: `_search_dates(query) -> list[str]` and `_to_daily(commits, merged, closed, end) -> list[dict]` consumed by Task 3

- [ ] **Step 1: Write the failing tests** (no network — stub `_gh` via monkeypatch, following the file's existing patterns)

```python
def test_to_daily_sums_three_sources_per_utc_day() -> None:
    end = datetime(2026, 8, 24, tzinfo=UTC)
    days = fra._to_daily(
        commits=[{"commit": {"committer": {"date": "2026-08-21T10:00:00Z"}}}],
        merged=["2026-08-21T17:35:10Z", "2026-08-21T09:00:00Z"],
        closed=["2026-08-20T08:00:00Z"],
        end=end, total=14,
    )
    by_date = {d["date"]: d["count"] for d in days}
    assert by_date["2026-08-21"] == 3
    assert by_date["2026-08-20"] == 1
    assert by_date["2026-08-19"] == 0
    assert len(days) == 14
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/scripts/test_fetch_repo_activity.py -m unit`
Expected: FAIL (`_to_daily` missing).

- [ ] **Step 3: Write minimal implementation**

```python
YEAR_DAYS = 371  # 53 weeks, matches RepoHeatmap's default

def _day_key(stamp: str | None) -> str | None:
    return stamp[:10] if stamp else None

def _to_daily(commits, merged, closed, end, total=YEAR_DAYS) -> list[dict]:
    counts: dict[str, int] = {}
    def add(stamp):
        day = _day_key(stamp)
        if day: counts[day] = counts.get(day, 0) + 1
    for c in commits:
        add((c.get("commit") or {}).get("committer", {}).get("date"))
    for s in (*merged, *closed):
        add(s)
    start = (end - timedelta(days=total - 1)).date()
    return [
        {"date": (start + timedelta(days=i)).isoformat(),
         "count": counts.get((start + timedelta(days=i)).isoformat(), 0)}
        for i in range(total)
    ]

def _search_dates(query: str) -> list[str]:
    """All closed_at dates for a Search issues query, paginated at 100/page.

    Authenticated Search allows 30 req/min — ~65 pages per query sleeps its
    way through ~3 min. Weekly cron only; never call this client-side.
    """
    out: list[str] = []
    page = 1
    while True:
        payload = _gh("api", f"search/issues?q={query}&per_page=100&page={page}")
        items = payload.get("items", []) if isinstance(payload, dict) else []
        if not items: return out
        out.extend(it["closed_at"] for it in items
                   if isinstance(it, dict) and it.get("closed_at"))
        if len(items) < 100: return out
        page += 1
        time.sleep(2.5)
```

(Requires `import time` at top of script if not present.)

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/scripts/test_fetch_repo_activity.py -m unit`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add scripts/fetch_repo_activity.py tests/scripts/test_fetch_repo_activity.py
git commit -m "feat(website): bucket daily contributions in the activity snapshot script"
```

### Task 3: wire `collect()` to a 365-day window

**Files:**
- Modify: `scripts/fetch_repo_activity.py` (`collect()` only)

**Interfaces:**
- Consumes: `_search_dates`, `_to_daily` from Task 2
- Produces: `dailyContributions` key in snapshot dict consumed by Task 4

- [ ] **Step 1: extend commit fetch + add two date queries** (existing 30-day velocity queries untouched — the windowed/unwindowed distinction in the docstring stays load-bearing)

```python
year_since = (datetime.now(UTC) - timedelta(days=365)).strftime("%Y-%m-%dT%H:%M:%SZ")
year_commits = _commits_since(year_since)          # same sha=main semantics, ~90 pages
year_merged = _search_dates(f"repo:{SLUG}+is:pr+is:merged+merged:>={year_since[:10]}")
year_closed = _search_dates(f"repo:{SLUG}+is:issue+is:closed+closed:>={year_since[:10]}")
# in the returned dict:
"dailyContributions": _to_daily(year_commits, year_merged, year_closed, datetime.now(UTC)),
```

- [ ] **Step 2: extend the module docstring** — one paragraph: heat is snapshot-sourced because client-side pagination would exhaust the unauthenticated budget; weekly refresh keeps it fresh.

- [ ] **Step 3: run tests**

Run: `pytest tests/scripts/test_fetch_repo_activity.py -m unit`
Expected: PASS (no network in tests).

- [ ] **Step 4: Commit**

```bash
git add scripts/fetch_repo_activity.py
git commit -m "feat(website): collect year-long daily contributions for the heatmap"
```

### Task 4: validate + regenerate + specimens

**Files:**
- Modify: `scripts/fetch_repo_activity.py` (`check()` + `REQUIRED`)
- Regenerate: `frontend/digithings-web/lib/repo-activity.json`
- Modify: `frontend/digiweb/web/src/components/repo-activity/demo.ts`

**Interfaces:**
- Consumes: `dailyContributions` from Task 3, optional field from Task 1

- [ ] **Step 1: add `"dailyContributions"` to `REQUIRED` + shape validation**

```python
dc = data["dailyContributions"]
assert isinstance(dc, list) and len(dc) == 371
assert all(set(d) == {"date", "count"} and d["count"] >= 0 for d in dc)
assert [d["date"] for d in dc] == sorted(d["date"] for d in dc)
```

(Follow the file's existing `check()` style — print `❌` to stderr and return 1 rather than bare assert if that matches surrounding code.)

- [ ] **Step 2: regenerate + check**

Run: `scripts/fetch_repo_activity.py` (needs `GH_TOKEN`/`gh auth`), then `scripts/fetch_repo_activity.py --check --max-age-days 1`
Expected: exit 0.

- [ ] **Step 3: synthetic series for `demo.ts`** — a tiny `dailyContributions` (e.g. last 14 days nonzero) so the reference specimen shows graded cells without bloating the fixture; then `npm test -- src/components/repo-activity` (from `frontend/digiweb/web`) green.

- [ ] **Step 4: Commit** (JSON + script + demo together — the bare `--check` in `test-web.yml` must see the key in the same PR that requires it)

```bash
git add scripts/fetch_repo_activity.py tests/scripts/test_fetch_repo_activity.py frontend/digithings-web/lib/repo-activity.json frontend/digiweb/web/src/components/repo-activity/demo.ts
git commit -m "feat(website): validate and ship daily contributions snapshot"
```

### Task 5: verify + review

- [ ] **Step 1: run python tests**

Run: `pytest tests/scripts/test_fetch_repo_activity.py -m unit`
Expected: PASS; `make test-unit` unaffected otherwise.

- [ ] **Step 2: confirm scope** — `FORBIDDEN` untouched (no stars/forks/watchers crept in), `git diff --stat` shows only intended files.

- [ ] **Step 3: run `/review`** on the changes (fresh-context subagent per repo policy) before merge.
