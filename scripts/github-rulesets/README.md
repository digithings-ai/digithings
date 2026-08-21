# GitHub rulesets (source of truth)

Branch-protection rulesets for `digithings-ai/digithings`. Apply these to
`origin` to enforce the branch taxonomy defined in `BRANCHING.md`.

**Desired state, not live state.** `"enforcement": "active"` in a file says
nothing about `origin`. None of these four is applied there: the only *ruleset*
on the repo is `module-branch-protection`, and the name taxonomy is enforced
client-side by `scripts/hooks/pre-push.sh`.

That is a statement about rulesets, not about protection. `main` and `develop`
also carry **classic branch protection**, which the rulesets API cannot see —
`main` requires the status check `Every commit reaching main was reviewed`,
`develop` requires three checks with `strict: true`. Before concluding a branch
is unprotected, query the classic endpoint too:

```
gh api repos/digithings-ai/digithings/branches/main/protection
```

Keep `01-branch-naming.json`'s regex equal to the hook's `branch_regex` **except
for the `main` and `develop` arms**, which the JSON omits on purpose because
`conditions.ref_name.exclude` carves those refs out before the pattern runs.
Those two arms are the only difference; anything else diverging is a bug.

**Before applying `01-branch-naming.json`, audit the refs it would reject:**

```
git ls-remote --heads origin | sed 's|.*refs/heads/||'
```

`release-please--branches--(develop|module/<component>)--components--<component>`
is an arm of the pattern (#2557) — the same refs `release-please-digichat.yml`
and `release-please-digiskills.yml` already push. Admitting them lets a
maintainer push a follow-up fix onto the bot's branch without `--no-verify`.
Targets other than `develop` / `module/*` (e.g. `main`) stay rejected.

`bot/*` is the same class — `bot/[a-z0-9-]+` is an arm of the pattern, so the
refs `project-stub-fields.yml`, `agent-backlog-snapshot.yml` and
`pipeline-provider-review.yml` push are legal on the way in. They were only ever
a cleanup backlog (#2465, now closed; 5 heads remain), never a rejection risk.

## Apply all four

Read the two caveats below before running this — as written it changes `main`'s
merge policy.

```
for f in scripts/github-rulesets/*.json; do
  gh api -X POST repos/digithings-ai/digithings/rulesets --input "$f"
done
```

- **`02-protect-main.json` carries `required_linear_history`, and `main` does not
  have one.** Live protection has `required_linear_history: false`, `BRANCHING.md`
  says linear history is not enforced, and `origin/main` is full of merge commits
  from the module-branch promotions. Applying this file blocks the promotion flow.
  Decide the policy first; do not adopt it as a side effect of a `for` loop.
- These are `POST`s, so re-running the loop against a ruleset that already exists
  creates a second one rather than updating it. Use the `PUT` form under
  **Update a ruleset**.

## Rulesets

| File | Purpose |
|------|---------|
| `01-branch-naming.json` | Regex enforcement of the BRANCHING.md taxonomy on all branches except `main` and `develop` (those two are excluded since they're exact-match, not pattern-based). |
| `02-protect-main.json` | `main`: block delete, block force-push, require linear history — the last of which contradicts the live merge-based history; see the caveat above. |
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
