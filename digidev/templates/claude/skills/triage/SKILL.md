---
name: triage
description: Triage CI failures on a PR — bucket by type (lint/doc-links/test/compose/other) and propose a minimal fix command for each bucket. Triggers on "triage", "why is CI failing", "fix PR checks", "/triage".
---

# Triage

Quick-scan a PR's CI failures and produce the minimum set of commands to fix each one.

## Usage

```
/triage           # triage the current branch's open PR
/triage <N>       # triage PR #N
```

## Procedure

1. Identify the PR (current branch or provided number).
2. Fetch the list of failing checks.
3. For each failing check, read just enough of the log to categorise it.
4. Output a bucketed fix list (see format below).
5. Ask the user: "Should I apply these fixes now?"

## Output format

```
## CI triage — PR #<N> (<branch>)

### Failing checks
| Check | Status | Bucket |
|---|---|---|
| lint | ❌ | Lint |
| test-unit | ❌ | Unit tests |
| score | ❌ | Scoring gate |

### Fix plan

**Lint**
```bash
ruff check --fix . && ruff format .
```

**Unit tests**
<paste the first failing assertion + file:line>
Fix: <targeted code change — one sentence description>

**Scoring gate**
Run the `score-and-fix` skill.

---
Apply all? (y/n)
```

## After applying

Re-push to re-trigger CI:
```bash
git add <files>
git commit -m "fix(ci): address triage findings"
git push
```

Monitor with `gh run watch` or wait for the next `<github-webhook-activity>` event.
