# GitHub rulesets (source of truth)

Branch-protection rulesets for `digithings-ai/digithings`. Apply these to
`origin` to enforce the branch taxonomy defined in `BRANCHING.md`.

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
