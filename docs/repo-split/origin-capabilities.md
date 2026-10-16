# Cursor Origin capability matrix

Checked 2026-10-14 for DIG-3558 against the repo-split plan in PR #5695 (`docs/repo-split/decisions.md`, `review.md`). This file is evidence. It does not create repos, change mirror state, or deploy.

Confidence labels: **CONFIRMED** (primary doc or a read-only live call), **LIKELY** (docs agree, not executed), **UNKNOWN** (not in the sources below).

## How this was checked

- Cursor docs fetched the same day: [Origin](https://cursor.com/docs/origin), [Mirror a GitHub repository](https://cursor.com/docs/origin/mirror-github), [Clone, Push & Pull](https://cursor.com/docs/origin/git), [Pull requests](https://cursor.com/docs/origin/pull-requests), [Origin code hosting changelog](https://cursor.com/changelog/origin-code-hosting), [Origin API](https://cursor.com/docs/api/origin), [API changelog](https://cursor.com/docs/api/origin/changelog), [Mirrored repositories](https://cursor.com/docs/api/origin/reference/mirrored-repositories), [Current limitations](https://cursor.com/docs/api/origin/reference/current-limitations), [Check runs](https://cursor.com/docs/api/origin/reference/check-runs), [Post Check Run](https://cursor.com/docs/api/origin/reference/post-check-run), [Sync Mirror](https://cursor.com/docs/api/origin/reference/sync-mirror), [Rate limits](https://cursor.com/docs/api/origin/reference/rate-limits), [Origin MCP](https://cursor.com/docs/api/origin/mcp), [MCP tools](https://cursor.com/docs/api/origin/mcp/tools), [CloneKit CI](https://cursor.com/docs/origin/clonekit-ci).
- Origin CLI `2026.09.24-20-34-11-8ed25e0`, already signed in on this Mac. Read-only commands only: `origin repo list`, `origin repo view`, `origin repo mirror status`, `origin ruleset list`, and `--help` for `repo mirror transition`, `repo edit`, `repo access`, `pr checks`. No `create`, `transition`, `detach`, `sync`, or `push`.
- Live read, namespace `chrizefan`:
  - `chrizefan/digithings` — `mirrorStatus: inbound`, `visibility: internal`, `defaultBranch: develop`. Last transition `initial-to-inbound` succeeded (drain time 2026-08-18).
  - `chrizefan/twelve-x` — `mirrorStatus: inbound`, `visibility: private`, `defaultBranch: develop`. Same transition shape, succeeded the same minute.
- At check time, `develop` was `d227b6ed526202aaa095b8e645804ef308dde813` on the Origin remote and on `github.com/digithings-ai/digithings`.
- Origin MCP (`https://api.origin.cursor.com/mcp`) is not connected in this run. The tool list below is from the MCP tool reference, not a live `tools/list`.

## Matrix

| Capability | Verdict | What the evidence says |
|---|---|---|
| Host a repo on Origin | **supported** | Create, clone, push, pull. Origin-hosted repos: Origin is the source of truth and GitHub is not in the path. [changelog](https://cursor.com/changelog/origin-code-hosting) |
| Public repo on Origin | **not supported** | `origin repo edit --visibility` accepts only `internal` or `private`. No public value. |
| `internal` on a personal namespace | **supported** | Live `chrizefan/digithings` is `internal`. The CLI offers `internal` with no team flag. |
| Private repo | **supported** | Live `chrizefan/twelve-x` is `private`. |
| Inbound mirror (GitHub → Origin) | **supported** | Both live repos are inbound. GitHub stays the source of truth. A push to `https://origin.cursor.com/{owner}/{repo}.git` is forwarded to GitHub; Origin updates after GitHub accepts it. [mirror](https://cursor.com/docs/origin/mirror-github), [git](https://cursor.com/docs/origin/git) |
| Outbound mirror (Origin → GitHub) | **not supported** for a new plan | The current API reference dropped outbound. The changelog says `inbound_to_outbound` returns `FailedPrecondition` unless outbound is enabled for that repo; repos already outbound keep working. The CLI still prints `--to outbound`. Both live repos are inbound. This check did not start a transition. |
| Detach (Origin becomes primary, GitHub stops receiving pushes) | **supported**, one-way | Settings → Detach, or `origin repo mirror detach`. The GitHub repo is left as it is. Pushes no longer flow to GitHub. [mirror](https://cursor.com/docs/origin/mirror-github) |
| What an inbound mirror copies | **supported** for git; **not supported** for the rest | Copies history, branches, and tags, and shows GitHub pull requests. Does not copy Issues, Actions workflows, or secrets. Skips GitHub branches named `origin` or `origin/…`. [mirror](https://cursor.com/docs/origin/mirror-github) |
| Sync timing | **supported**, with lag | Changelog: synced repos update in real time. CI doc: wait up to about two minutes for a SHA (`syncMirror` `wait=true`, budget ~2 minutes). No fixed poll interval is published. [CloneKit CI](https://cursor.com/docs/origin/clonekit-ci), [Sync Mirror](https://cursor.com/docs/api/origin/reference/sync-mirror) |
| Force-push and moved tags on an inbound mirror | **workaround** | GitHub is the source of truth, and tags are in the copy set, so a force-push or moved tag that GitHub accepts should show up on Origin. **LIKELY**, not executed here. Origin rulesets on the live inbound repo are `evaluate`, so they do not block it. The block, if any, is GitHub's. |
| Forge-local `origin/…` branches | **supported** | `origin push local` writes only `refs/heads/origin/…` to the `/local` endpoint. Those refs never sync to GitHub and are not GitHub pull-request heads. [git](https://cursor.com/docs/origin/git) |
| Pull requests on an inbound mirror | **workaround** | The Pull Requests tab shows GitHub pull requests. Comments sync both ways. [changelog](https://cursor.com/changelog/origin-code-hosting). The Origin API rejects merge on a mirrored repo. [limitations](https://cursor.com/docs/api/origin/reference/current-limitations). An app token is read-only on a mirror (403 on pull requests, reviews, checks, rulesets, and other writes). [mirrored repositories](https://cursor.com/docs/api/origin/reference/mirrored-repositories) |
| Outside contributors | **workaround** | They use GitHub. Fork pull-request heads are not mirrored. [CloneKit CI](https://cursor.com/docs/origin/clonekit-ci). An Origin external collaborator must already be a Cursor user (`origin repo access set --external`). There is no anonymous GitHub login on Origin. |
| Pull requests on a native Origin repo | **supported** | They stay on Origin and are not copied to GitHub. [pull requests](https://cursor.com/docs/origin/pull-requests) |
| Branch and tag rulesets | **supported** on native repos; **present but not blocking** on the live inbound mirror | Kinds: `merge_branch`, `push_branch`, `push_tag`, `push_repository`. Enforcement: `active`, `evaluate`, `disabled`. Push rules include `deletion`, `non_fast_forward`, `block_direct_updates`, `block_merges`, `ref_name_pattern`, `required_linear_history`. Merge rules include `pull_request`, `require_status_checks`, `require_branch_up_to_date`. [changelog](https://cursor.com/docs/api/origin/changelog). Live `chrizefan/digithings` (inbound) already has six rulesets, all `evaluate`, on `develop`, `main`, and `module/**`. |
| Signed tags or signed commits as a ruleset | **not supported** | The nine rule types include no signature rule. `push_tag` can block deletion and non-fast-forward. A signature check is a local `git verify-tag` in the runner. SSH certificate authorities are for SSH login, not for tag signatures. |
| Native CI runner | **not supported** | Origin does not run jobs. Depot and Buildkite are separate apps. [changelog](https://cursor.com/changelog/origin-code-hosting) |
| A local runner reports an Origin check | **workaround** | `POST /check-runs` needs an **app installation** token with `repository:checks:write`. A user token cannot post it. On an inbound mirror the app gets 403. On a native Origin repo, an Origin App or Buildkite (it requests checks write) can post the run. [Post Check Run](https://cursor.com/docs/api/origin/reference/post-check-run) |
| GitHub Actions on an Origin push | **not supported** | Actions stay on GitHub. They do not run because a commit landed on Origin. |
| Buildkite as the CI app | **supported** for a native Origin repo | Buildkite connects Origin as a repository provider and asks for checks write. [CloneKit CI](https://cursor.com/docs/origin/clonekit-ci). On an inbound mirror, that checks write is in the 403 set. |
| `origin repo clone-fast` (CloneKit) | **not supported** on Ultra | Enterprise only, turned on per repo by Cursor, no self-serve switch. Plain `git clone` is the Ultra path. [CloneKit CI](https://cursor.com/docs/origin/clonekit-ci) |
| REST API for agents | **supported**, with the mirror read-only limit | Base `https://api.cursor.com/v1/origin`. CLI: `origin api`. User budget 600 points/minute; installation token 3,000; app JWT 6,000. [rate limits](https://cursor.com/docs/api/origin/reference/rate-limits) |
| MCP for agents | **supported** in Cursor and Grok Bot only | `https://api.origin.cursor.com/mcp` (and `/mcp/readonly`). Tools include repo browse, commits, pull-request read/write, `checks_read`, `list_rulesets`, `sync_mirror`, `create_repository`. No post-check tool, no ruleset write, no mirror transition. [MCP](https://cursor.com/docs/api/origin/mcp), [tools](https://cursor.com/docs/api/origin/mcp/tools). Not connected in this run. |
| Ultra storage quota | **UNKNOWN** | Origin code storage is on Ultra (and the other paid plans), not on the free plan. [overview](https://cursor.com/docs/origin). No gigabyte cap is published in the pages above. Do not treat that silence as unlimited. |

## Assumptions in the plan that fail

The plan's own correction still stands: **R0 is GitHub-primary with an inbound Origin mirror** (D-O1). The older line in the DIG-3558 brief ("R0 primary on Origin, mirrored to GitHub") does not match the product or the later answer. These claims in PR #5695 do not survive this check.

1. **"No Teams plan, so no `internal` visibility" (D-O2 consequence).** Fails. `chrizefan/digithings` is already `internal` on the personal namespace. `private` and `internal` are both available. R1–R7 can be `private` in `chrizefan` without a Teams plan, and `internal` is not blocked.
2. **"Rulesets exist only on Origin-hosted repos, not on mirrors" (`review.md`).** Fails as a hard claim. The inbound `chrizefan/digithings` mirror already has rulesets. They are `evaluate`, so they record and do not block. Whether `active` would block a push that GitHub accepted was not tested.
3. **"Origin rulesets are advisory" as a product limit (D-O4).** Fails as a product claim. Enforcement can be `active`. Advisory is the live configuration (`evaluate`) and the consequence of agents sharing Chris's user if that user is a bypass actor. An `active` ruleset with no bypass would block that user too.
4. **"Outbound mirroring is absent, therefore impossible."** Too strong. It is absent from the current API reference and gated off unless Cursor enables it for the repo. The installed CLI still offers `--to outbound`. Both live repos are inbound. Do not plan a push mirror. Detach is the documented way to make Origin primary, and it stops the GitHub copy from updating.
5. **Public R0 keeps free GitHub-hosted Actions minutes (D-G4, review "G6 goes away").** Fails as of 2026-10-14 22:09. Minutes are exhausted. A missing Actions check is not a failure. A pull request needs a local test pass written in the pull request. That includes R0 until minutes return or CI has left GitHub Actions.
6. **`origin repo clone-fast` as the Buildkite checkout (if P0 copies the CloneKit recipe).** Fails on Ultra. CloneKit is Enterprise-only. Buildkite itself can still connect a native Origin repo and post checks. Checkout is a normal git clone with a short-lived token.
7. **Fork pull requests arrive on the Origin copy.** Fails. Fork heads are not mirrored. External review and CI for those pulls stay on GitHub (D-O1 already says this; the Origin copy will not contain the fork branch).
8. **A local Mac job can post an Origin check on today's inbound mirrors with the user CLI.** Fails. Check writes need an app installation token, and a mirror rejects them. The working record today is the local test pass in the pull-request body. On a future **native** private repo, an Origin App or Buildkite can post the check.
9. **twelve-x is not on Origin until P4.7.** Fails. `chrizefan/twelve-x` is already a private inbound mirror (since the 2026-08-18 initial sync). A later "move" is a detach or a gated outbound transition, not a first create. Detach stops GitHub from receiving new pushes.

## Assumptions that hold

- No public Origin repo. R0 stays public on GitHub.
- Inbound mirror is the supported GitHub relationship. Both existing repos are already inbound.
- No signed-tag rule. Keeping signed release tags optional (D-G6) matches the product. The runner's `git verify-tag` is the only signature check, and only when a signature is present.
- No package registry on Origin. Git tag pins (D-Q7′) match the docs.
- No native job runner. Private-repo CI is an external app or a local job, not Origin itself.
- App tokens cannot write pull requests, checks, or rulesets on an inbound mirror.
- `develop` on the live Origin mirror matched GitHub at `d227b6ed` when this was checked.

## What this check did not do

No repo was created. No mirror transition, detach, sync, or push was sent. No Cloudflare setting was changed. Origin MCP was not called. CloneKit, Buildkite, and an `active` ruleset were not executed. Storage capacity in gigabytes was not found.
