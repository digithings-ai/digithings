# GitHub rulesets (source of truth)

Branch-protection rulesets for `digithings-ai/digithings`. Apply these to
the GitHub repo to enforce the branch taxonomy defined in `BRANCHING.md`
(`origin` is the cursor mirror, not GitHub — see DIG-3425).

**Desired state, not live state.** `"enforcement": "active"` in a file says
nothing about the live repo. None of these four JSON files is applied.
`module-branch-protection` (id 15270439) was retired with the `module/*`
branches (#6751). The name taxonomy stays client-side
(`scripts/hooks/pre-push.sh`).

A different ruleset **is** live, and it is not one of these files. `Public CI`
(id 26699837, created 2026-11-06) targets `refs/heads/main` and
`refs/heads/develop`: pull request required (0 approving reviews), required
checks `lint`, `secrets`, and `unit` with strict up-to-date, no force-push, no
deletion. See [BRANCHING.md](../../BRANCHING.md).

Classic `GET …/branches/<name>/protection` is a separate API. On 2026-11-06 it
returned HTTP 403 for a token without administration scope, which does not
prove the classic rule is absent. Query both before concluding a branch is
unguarded:

```
gh api repos/digithings-ai/digithings/branches/main/protection
gh api repos/digithings-ai/digithings/rules/branches/main
```

Keep `01-branch-naming.json`'s regex equal to the hook's `branch_regex` **except
for the `main` and `develop` arms**, which the JSON omits on purpose because
`conditions.ref_name.exclude` carves those refs out before the pattern runs.
Those two arms are the only difference; anything else diverging is a bug.

**Before applying `01-branch-naming.json`, audit the refs it would reject:**

```
git ls-remote --heads https://github.com/digithings-ai/digithings.git | sed 's|.*refs/heads/||'
```

`origin` on a digithings clone is the Cursor mirror, not this repo (see the
opening paragraph). Listing that remote audits mirror heads, including
`origin/<slug>` drafts the GitHub ruleset never sees.

`release-please--branches--develop--components--<component>`
is an arm of the pattern (#2557). `release-please-digichat.yml` and
`release-please-digiskills.yml` were removed in #4919, and nothing under
`.github/workflows/` pushes those refs now. The arm stays so an existing
branch of that shape still matches; targets other than `develop`
(e.g. `main`, or the retired `module/*`) stay rejected.

`bot/*` is the same class — `bot/[a-z0-9-]+` is an arm of the pattern, so the
refs `agent-backlog-snapshot.yml` and `pipeline-provider-review.yml` push are
legal on the way in. `project-stub-fields.yml` was removed in #4919. These
names were a cleanup backlog (#2465, now closed), never a rejection risk.

## Apply all four

Read the caveats below before running this — as written it changes `main`'s
merge policy, and posting `02` or `03` stacks a second ruleset on live `Public CI`.

```
for f in scripts/github-rulesets/*.json; do
  gh api -X POST repos/digithings-ai/digithings/rulesets --input "$f"
done
```

- **`02-protect-main.json` carries `required_linear_history`, and `Public CI`
  does not.** `BRANCHING.md` says linear history is not enforced. Promotions
  into `main` are merge commits (`gh pr merge --merge` in the cutting-a-release
  recipe). Applying this file blocks that flow. Decide the policy first; do not
  adopt it as a side effect of a `for` loop.
- **`Public CI` already covers `main` and `develop`.** Posting `02` or `03`
  stacks a second ruleset on those branches. It does not edit 26699837. Leave
  that ruleset's strict checks on; the release-please decision is recorded in
  [BRANCHING.md](../../BRANCHING.md#release-please-and-strict-up-to-date).
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

These four files do not require approving reviews (solo-contributor mode).
`Public CI` already requires a pull request and zero approving reviews. When a
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
