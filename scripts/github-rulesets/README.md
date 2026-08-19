# GitHub rulesets (source of truth)

Branch-protection rulesets for `digithings-ai/digithings`. Apply these to
`origin` to enforce the branch taxonomy defined in `BRANCHING.md`.

**Desired state, not live state.** `"enforcement": "active"` in a file says
nothing about `origin` — only `module-branch-protection` is applied there today,
and the taxonomy is enforced client-side by `scripts/hooks/pre-push.sh`. Keep
`01-branch-naming.json`'s regex equal to that hook's `branch_regex`.

**Before applying `01-branch-naming.json`, audit the refs it would reject:**

```
git ls-remote --heads origin | sed 's|.*refs/heads/||'
```

Two known classes fail the taxonomy today — the ~100 `bot/*` refs (#2465, legal
names, just stale) and `release-please--branches--*--components--*`, which
`release-please-digichat.yml` and `release-please-digiskills.yml` push on their
own fixed naming scheme. A server-side rule would block the release PRs; the
client hook never sees them, because Actions push through the API.

## Apply all four

```
for f in scripts/github-rulesets/*.json; do
  gh api -X POST repos/digithings-ai/digithings/rulesets --input "$f"
done
```

## Rulesets

| File | Purpose |
|------|---------|
| `01-branch-naming.json` | Regex enforcement of the BRANCHING.md taxonomy on all branches except `main` and `develop` (those two are excluded since they're exact-match, not pattern-based). |
| `02-protect-main.json` | `main`: block delete, block force-push, require linear history. |
| `03-protect-develop.json` | `develop`: block delete, block force-push. |
| `04-protect-releases.json` | `release/v*`: block delete, block force-push. |

Rulesets do not currently require PR reviews (solo-contributor mode). When a
second contributor joins, add a `pull_request` rule to `02-protect-main.json`
and `03-protect-develop.json`.

## Update a ruleset

List existing rulesets:

```
gh api repos/digithings-ai/digithings/rulesets --jq '.[] | {id, name}'
```

Update by ID:

```
gh api -X PUT repos/digithings-ai/digithings/rulesets/<ID> --input scripts/github-rulesets/<file>.json
```
