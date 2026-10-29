# Platform attribution

Status: decided by Chris on 2026-10-29 (platform-only attribution; reviewed:* labels retired; a fresh-session review on the same platform counts as independent). Tooling, template and label changes are follow-up work; nothing in this doc is enforced yet.

## The rule

Ownership of agent work is recorded by **platform**, not by seat. The four platforms are exactly:

```
claude
cursor
grokbot
paperclip
```

Paperclip is recorded as `paperclip`, with no per-seat breakdown. Seat routing inside Paperclip is unchanged — seats still take work, open changes, review and run — but every report and every record collapses it to `paperclip`.

On GitHub, the owner of a pull request is the platform of the agent that pushes the work there. The GitHub PR author stays Chris's login; the platform comes from the commit trailer and the `src:*` label, never from the account that opened the PR.

## Commit trailer

Every commit carries:

```
Source-Platform: <platform>
```

The value is one of the four names above. Each harness adds the trailer at commit time, and it is kept through squash — the squash commit message must keep it. Reviewers and tooling read the trailer from the commit, not from the PR body.

Today, commits carry `Paperclip-Agent-Id:` and `Paperclip-Run-Id:` per seat. Those stay, and stay readable by the merge queue's authorship checks until that queue is migrated. They are not the attribution record.

Example block:

```
docs(ops): fix a link

Signed-off-by: ...
Source-Platform: grokbot
```

## Labels

Four labels, one per platform:

```
src:claude
src:cursor
src:grokbot
src:paperclip
```

They are applied by tooling from the trailer, never by hand. A PR whose commits carry more than one platform — a promotion, for example — gets one label per platform it carries.

Today `exec:cursor` and `exec:claude` exist; the dev-flow plan found them unused since 13 Oct. The plan renames them to `src:cursor` / `src:claude` and adds `src:grokbot` / `src:paperclip`. No `src:*` label exists yet.

## PR template

Proposed, not yet in `.github/PULL_REQUEST_TEMPLATE.md`: one auto-filled line near the top of the body,

```
Source: <platform>
```

The template currently has no owner field, so this is an addition rather than a rename. Until the line exists, the trailer is the only record on a PR.

## sctl --owner

`sctl change new --id <ID> --owner <seat> --base local/develop` is documented in [AGENTS.md § Source control](../../AGENTS.md#source-control-local-forge-first-when-available). In the digiforge repo, `cmd/sctl/changes.go` defines `--owner` as a free-form required string ("owner (required for new)") and copies it into each review record next to `--reviewer`.

Change: pass the platform — one of the four names — not a seat. sctl does not validate the value today; validating it against the four names is follow-up work in digiforge.

## Review records and independence

The `reviewed:agent` and `reviewed:owner` labels are retired (Chris, 2026-10-29). They are often added after merge (the dev-flow plan counts 20 of 38 `develop` merges since 27 Oct carrying `reviewed:owner`), so they carry no information about who reviewed what.

The review record names the reviewer's platform and the head SHA it approved. A review done in a fresh session — new context, not the authoring session or its subagent — on the same platform counts as independent.

This changes the unit of independence from seat to session. Today the merge queue still judges independence by seat: it drops a review marker from the seat named in the commits' `Paperclip-Agent-Id:` / `Paperclip-Run-Id:` trailers (see [MERGE_QUEUE.md § Reviewer independence](../MERGE_QUEUE.md#reviewer-independence)). Until the queue is migrated, a same-platform review still has to satisfy that seat rule to count there. The migration to platform-level review checks is **in progress, owned by Platform**, in Platform's own draft PR (none open as of 2026-10-29 14:45 CET; link it here once it exists).

This doc does not delete the labels. `scripts/check_review_coverage.py`, `scripts/merge_queue.py` and `scripts/readiness.py` still read them, and the main-promotion check "Every commit reaching main was reviewed" still accepts them. Moving the tooling off them is part of Platform's in-progress merge-queue migration (above); deleting the labels from the repo is follow-up work.

## Promotion PRs

The owner of a promotion PR is the platform that pushes it. Its manifest lists the source platforms of the changes it carries.

In the target flow, agents commit and review on the local Forgejo (digiforge), changes accumulate there, and one batch promotion PR goes to GitHub `develop`. Attribution therefore has two layers on a promotion: the platform that pushes it (its own trailer and `src:*` label) and the platforms inside the batch (the manifest, and the trailers on the commits it carries).

## Human Gate

Hard rule (Chris, 2026-10-29): no agent ever submits an approving GitHub review on a promotion PR, whether into `develop` or `main`. Chris's Human Gate is his own approving review on the promotion PR's head commit. Agents push and comment through his `chrizefan` login, so an agent's approving review would be indistinguishable from his and would fake the gate. Agents record their reviews as PR comments with the review markers instead (see [MERGE_QUEUE.md § The verdict rule](../MERGE_QUEUE.md#the-verdict-rule)). The promotion gate that reads the Human Gate is specified in QA's draft [#6659](https://github.com/digithings-ai/digithings/pull/6659).

## Follow-up work

- Harness trailer injection: each platform adds `Source-Platform:` at commit time, including on squash.
- Label automation: apply `src:*` from the trailer, never by hand.
- Label rename/create: `exec:cursor` → `src:cursor`, `exec:claude` → `src:claude`, plus new `src:grokbot` and `src:paperclip`.
- PR template: add the auto-filled `Source: <platform>` line.
- sctl: validate `--owner` against the four platform names in digiforge.
- Merge queue and `check_review_coverage.py`: migrate off the `reviewed:*` labels and the per-seat `Paperclip-Agent-Id:` / `Paperclip-Run-Id:` independence check onto the platform and the `Source-Platform:` trailer. **In progress, owned by Platform**, in Platform's own draft PR (none open as of 2026-10-29 14:45 CET; link it here once it exists).
- `.github/required-contexts.txt`: bring it in line with live branch protection (it still lists the Actions-era contexts; see [BRANCH_PROTECTION.md § Known drift](../BRANCH_PROTECTION.md#known-drift-in-the-tooling)). **In progress, owned by Platform**, in the same draft PR.
- QA gate: check that 100% of merged commits carry the trailer.
