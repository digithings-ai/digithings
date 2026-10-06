# Dependency Freshness Radar — Design Note

**Date:** 2026-10-06
**Author:** Architect (c3bf0d65-aff4-453b-baac-ce53a9861be3)
**Status:** Proposal
**Issue:** DIG-1515

---

## Problem Statement

Every dependency floor in the digithings monorepo uses `>=` (or `>=X,<Y` for capped tools), never `==` or `~=`. This means the declared floor is **not what we actually run** — uv resolves to the latest compatible version at lock time.

Three unreviewed major version jumps are currently queued behind floors that will never stop them:

| Package | Floor | Locked | Latest | Gap |
|---------|-------|--------|--------|-----|
| `mcp` | `>=1.2,<2` | 1.29.0 | 2.3.0 | **Major** (held only by `<2` cap) |
| `optuna` | `>=4.7.0` | 4.9.0 | 5.0.0 | **Major** |
| `cryptography` | `>=42` | 49.0.0 | 50.0.2 | **Major** |
| `polars` | `>=1.0` | 1.43.1 | 2.0.0rc2 | Major (rc) |
| `sqlalchemy` | `>=2.0` | 2.0.51 | 2.1.3 | Minor |
| `langchain-core` | `>=1.4.7` | 1.5.2 | 1.6.6 | Minor |
| `fastapi` | `>=0.115` | 0.141.1 | 0.142.2 | Minor |
| `playwright` | `>=1.40` | 1.61.0 | 1.63.0 | Minor |
| `ruff` | `>=0.16,<0.17` | 0.16.0 | 0.16.10 | Patch |
| `mypy` | `>=2,<3` | 2.3.0 | 2.4.0 | Minor |
| `pytest` | `>=8,<10` | 9.1.1 | 9.1.1 | Current |
| `redis` | `>=5` | 8.0.1 | — | 3 majors past floor |

**The real issue is invisibility**, not drift. Lock refreshes happen reactively (when installs break), never proactively. The team already has the vocabulary — `pipeline-maintenance.yml` uses "lock freshness" for a runtime monitor — but the dependency side has no equivalent.

---

## Proposal

Add a **monthly dependency freshness radar** as a new job in `.github/workflows/pipeline-maintenance.yml` (or a new dedicated workflow) that:

1. **Exports the full workspace closure** from `uv.lock` (all packages, all extras)
2. **Queries PyPI** for latest stable version of each package
3. **Computes version gaps** (major/minor/patch) using semantic versioning
4. **Posts a formatted GitHub issue** with a comparison table (like the one above)
5. **Deduplicates** by issue body marker so only one tracking issue exists at a time

This is a **standing check**, not a reaction. The goal is to make major version arrivals visible *on purpose* instead of discovering them mid-incident.

---

## Non-Goals

- **No constraint changes** — floors may be deliberate and correct
- **No `mcp` cap changes** — that's DIG-1514 with its own owner
- **No `uv lock --upgrade` dry runs** — that's a separate half-day ask with real branch changes
- **No auto-bumping** — this is visibility only; human decides upgrades

---

## Design Options

### Option A: Extend `pipeline-maintenance.yml` (Recommended)

Add a new job `dependency-freshness` to the existing weekly maintenance workflow, but run it monthly via a cron schedule.

**Pros:**
- Reuses existing GH_TOKEN, project placement, issue creation patterns
- Same deduplication marker pattern as other maintenance jobs
- Single workflow to maintain

**Cons:**
- `pipeline-maintenance.yml` is already 948 lines; adding more increases complexity
- Weekly workflow with one monthly job is slightly awkward

### Option B: New dedicated workflow `pipeline-dependency-freshness.yml`

Standalone workflow with monthly cron schedule.

**Pros:**
- Clean separation of concerns
- Can have its own schedule (monthly) without weekly workflow confusion
- Simpler, focused file

**Cons:**
- Duplicates boilerplate (checkout, uv setup, GH_TOKEN, project placement)
- Another workflow file to maintain

### Option C: Monthly cron in `pipeline-maintenance.yml` with conditional

Keep one workflow, use `if: github.event_name == 'schedule' && github.event.schedule == 'monthly'` (or similar) to gate the job.

**Pros:**
- Single workflow file
- Clear schedule separation

**Cons:**
- GitHub Actions doesn't easily support multiple cron schedules in one workflow with job-level filtering

---

## Decision: Option B — New Dedicated Workflow

**Rationale:** The existing `pipeline-maintenance.yml` is already large and handles multiple distinct concerns (CVE audit, stale branches, doc links, ADR numbering, agents-init drift, architecture drift, stale issues/PRs, label coverage, workflow health, duplicate issues, project backfill). Adding a 12th job with a different schedule increases cognitive load. A focused `pipeline-dependency-freshness.yml` is cleaner and follows the pattern of other dedicated pipelines (`pipeline-digiquant.yml`, `pipeline-digiquant-tearsheets.yml`, etc.).

---

## Implementation Plan

### 1. Create `pipeline-dependency-freshness.yml`

```yaml
name: "Pipeline: dependency freshness radar"

on:
  schedule:
    - cron: "0 6 1 * *"  # Monthly, 1st of month 06:00 UTC
  workflow_dispatch:      # Manual trigger

permissions:
  contents: read
  issues: write

jobs:
  dependency-freshness:
    name: Dependency freshness radar
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: astral-sh/setup-uv@v5
        with:
          enable-cache: true

      - name: Export workspace closure from uv.lock
        run: |
          uv export --frozen --all-packages --all-extras \
            --format requirements-txt \
            --no-emit-project --no-emit-workspace --no-hashes \
            -o freshness-requirements.txt

      - name: Compute freshness report
        id: report
        run: |
          python3 <<'PY'
          import json, re, subprocess, sys, urllib.request
          from packaging.version import parse as parse_version

          # Parse pinned packages from exported requirements
          pinned = {}
          with open("freshness-requirements.txt") as f:
              for line in f:
                  line = line.strip()
                  if not line or line.startswith("#"):
                      continue
                  # Format: package==version
                  m = re.match(r"^([^=]+)==(.+)$", line)
                  if m:
                      pinned[m.group(1).lower()] = m.group(2)

          # Query PyPI for latest versions
          latest = {}
          for pkg in pinned:
              try:
                  url = f"https://pypi.org/pypi/{pkg}/json"
                  with urllib.request.urlopen(url, timeout=10) as resp:
                      data = json.load(resp)
                  # Get latest stable (non-pre-release) version
                  releases = data.get("releases", {})
                  stable_versions = [v for v in releases if not parse_version(v).is_prerelease]
                  if stable_versions:
                      latest[pkg] = max(stable_versions, key=parse_version)
              except Exception as e:
                  print(f"Warning: failed to fetch {pkg}: {e}", file=sys.stderr)

          # Classify gaps
          rows = []
          for pkg, locked_ver in sorted(pinned.items()):
              if pkg not in latest:
                  rows.append((pkg, locked_ver, "unknown", "unknown", "⚠️"))
                  continue
              latest_ver = latest[pkg]
              locked_parsed = parse_version(locked_ver)
              latest_parsed = parse_version(latest_ver)

              if locked_parsed.major != latest_parsed.major:
                  gap = "major"
                  icon = "🔴"
              elif locked_parsed.minor != latest_parsed.minor:
                  gap = "minor"
                  icon = "🟡"
              elif locked_parsed.micro != latest_parsed.micro:
                  gap = "patch"
                  icon = "🟢"
              else:
                  gap = "current"
                  icon = "✅"

              rows.append((pkg, locked_ver, latest_ver, gap, icon))

          # Build markdown table
          lines = ["| package | locked | latest | gap |", "|---|---|---|---|"]
          major_count = sum(1 for r in rows if r[3] == "major")
          minor_count = sum(1 for r in rows if r[3] == "minor")
          patch_count = sum(1 for r in rows if r[3] == "patch")
          current_count = sum(1 for r in rows if r[3] == "current")
          unknown_count = sum(1 for r in rows if r[3] == "unknown")

          for pkg, locked, latest, gap, icon in rows:
              lines.append(f"| {pkg} | {locked} | {latest} | {icon} {gap} |")

          summary = f"**{major_count} major**, {minor_count} minor, {patch_count} patch, {current_count} current, {unknown_count} unknown"

          output = {
              "table": "\n".join(lines),
              "summary": summary,
              "major_count": major_count,
              "minor_count": minor_count,
              "total_packages": len(rows),
          }
          print(json.dumps(output))
          PY

      - name: Create/update tracking issue
        if: steps.report.outputs.major_count != '0' || always()
        env:
          GH_TOKEN: ${{ secrets.DIGITHINGS_PROJECT_TOKEN }}
          REPO: ${{ github.repository }}
          PROJ: ${{ vars.DIGI_MAINTENANCE_PROJECT_NUMBER }}
          TABLE: ${{ steps.report.outputs.table }}
          SUMMARY: ${{ steps.report.outputs.summary }}
        run: |
          TITLE="[radar] Dependency freshness report — $(date +%Y-%m-%d)"
          MARKER="<!-- dependency-freshness-radar -->"

          BODY="${MARKER}
          ## Dependency Freshness Radar

          Monthly comparison of \`uv.lock\` against PyPI latest versions.

          ${SUMMARY}

          ## Comparison Table

          ${TABLE}

          ## Notes
          - Floors are \`>=\` — the locked version is what uv resolved, not the floor
          - Major gaps 🔴 are candidates for review; minors 🟡 for awareness; patches 🟢 for info
          - \`mcp\` cap (\`<2\`) is tracked in DIG-1514 separately
          - This is visibility only — no auto-bumping

          ## Acceptance Criteria
          - [ ] Major gaps reviewed by team
          - [ ] Decision recorded (upgrade / hold / investigate)"

          EXISTING=$(gh issue list --repo "$REPO" --label "radar" --state open \
            --search "Dependency freshness radar in:title" --json number --jq '.[0].number' 2>/dev/null || echo "")

          if [[ -n "$EXISTING" ]]; then
            gh issue edit "$EXISTING" --repo "$REPO" --title "$TITLE" --body "$BODY"
            echo "Updated existing radar issue #$EXISTING"
          else
            URL=$(gh issue create --repo "$REPO" \
              --title "$TITLE" \
              --label "radar,component:root,priority:low" \
              --body "$BODY")
            echo "Created: $URL"
            if [[ -n "${PROJ:-}" ]]; then
              gh project item-add "$PROJ" --owner digithings-ai --url "$URL" >/dev/null 2>&1 || true
            fi
          fi
```

### 2. Add `packaging` to dev dependencies (for version parsing)

The script uses `packaging.version.parse` which is already a transitive dependency of `uv`/`pip`, but to be safe, ensure it's available in the workflow environment. The `astral-sh/setup-uv` action provides a full Python environment with `packaging` available.

### 3. Add `radar` label to label set

The issue uses label `radar` — ensure this label exists in the repo (can be created on first run).

---

## Risks & Mitigations

| Risk | Likelihood | Impact | Mitigation |
|------|------------|--------|------------|
| PyPI API rate limits | Low | Medium | 120 packages × 1 request/month = negligible; add retry/backoff if needed |
| Pre-release versions polluting "latest" | Medium | Low | Code filters `is_prerelease`; `polars 2.0.0rc2` correctly excluded from stable |
| Network flakiness | Low | Low | `timeout=10` on requests; `set +e` pattern like other maintenance jobs |
| False confidence from "current" status | Low | Medium | Table shows exact versions; human review still required |
| Workflow runs but issue not created (no majors) | Medium | Low | `if: always()` ensures issue created/updated even with 0 majors |

---

## Rollout

1. Create workflow file
2. Test with `workflow_dispatch`
3. Verify issue created with correct table format
4. First scheduled run: 2026-11-01

---

## Success Criteria

- Monthly issue appears on 1st of each month
- Table accurately reflects uv.lock vs PyPI
- Team reviews major gaps within the month
- No major version jump discovered only at incident time

---

## Alternative Considered: `uv lock --check --upgrade --dry-run`

`uv` has a `--dry-run` flag for `uv lock --upgrade` that shows what would change. This was considered but rejected because:
- Output format is not machine-readable for easy table generation
- Would require parsing human-readable diff output
- Still doesn't give "latest on PyPI" — only what uv *would* resolve to given current constraints
- The goal is visibility into *what exists*, not just what uv *would pick*

---

## Related

- DIG-1514: `mcp` cap decision
- `pipeline-maintenance.yml` — existing maintenance workflow pattern
- AGENTS.md § "Dependency version bounds" — tools capped to current major; runtime deps unbounded