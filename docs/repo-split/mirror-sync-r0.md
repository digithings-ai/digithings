# R0 mirror sync: GitHub (primary) -> Forgejo (local loop copy)

Slice C of the repo split (DIG-3560, parent epic DIG-3518). **Rewritten 2026-10-31** for the
Forgejo home (D-C1, 2026-10-29). Until 2026-10-29 this file described a Cursor Origin inbound
mirror; that is history now (see [§7](#7-history-cursor-origin-inbound-mirror-until-2026-10-29)).
Plan only — no repo creation, migration, or Cloudflare change is part of this slice.

R0 stays **GitHub-primary** (D-O1, unchanged): the public org is GitHub `digithings-ai`, and
`digithings-ai/digithings` on GitHub is the source of truth. The Forgejo copy
`digithings-ai/digithings` on the local forge is the **working surface** of the local review loop,
not a second home. Truth flows GitHub -> Forgejo, and changes go back only by `sctl publish`.

Sources: decisions.md D-O1, D-C1 … D-C13 and the 2026-10-31 re-home record; migration-plan.md
§ Source control on Forgejo; the root `AGENTS.md` ("Source control: local forge first");
[docs/plans/forgejo-full-setup.md](../plans/forgejo-full-setup.md).

## 1. Mechanism

- **GitHub -> Forgejo:** the forge's `github-develop` branch mirrors GitHub `develop`. It reaches
  the forge's `develop` only through a `chore/sync-develop` PR; nobody uses it as a change base or
  pushes to it.
- **Forgejo -> GitHub:** the only path is `sctl publish --remote github --target develop` after a
  recorded review verdict at the exact head (root `AGENTS.md`). No push hook, no cron push mirror.
- Agents clone from the forge for iteration and keep a `github` remote for publish. Release tags,
  issues, external PRs and Actions live on GitHub only.
- Assumptions to verify when the sync job is repaired:
  - [F1] the `github-develop` refresh runs on a schedule and its last run is visible (`sctl doctor`);
  - [F2] release tags `<component>-v*` are fetched with it, so the forge copy can build a tag;
  - [F3] a failed refresh is reported, not silent (see §5).

## 2. Tags / releases

- Release tags are cut **by Chris on GitHub**; **signed tags are mandatory (D-G6)**, verified with
  `git verify-tag` against `allowed_signers`. Unsigned tags are refused.
- Nothing deploys from R0, so a tag on R0 is a **publish marker** (release-please, PyPI
  `digithings-<module>`, npm `@digithings-ai/*`, images), never a deploy trigger.
- Per-package release branches (D-R3: tags + release-please on `main` in R0) are ordinary GitHub
  branches; the forge copy follows them.

## 3. External contributions (GitHub only)

- **PRs:** external PRs live on GitHub. Review + merge happen **on GitHub** (merge queue, required
  checks). Fork heads are never fetched into the forge, and local CI never runs fork code.
- **Issues:** GitHub Issues are the only issue tracker for R0. Forge work references
  `digithings-ai/digithings#NNN` by hand; no issue mirror is built.
- **Direction rule:** nobody merges on the forge expecting it to reach GitHub by itself — work
  reaches GitHub only through `sctl publish`, and the forge follows GitHub `develop`.

## 4. Conflict / divergence policy

1. GitHub is source of truth in every dispute (D-O1).
2. Divergence symptom: the forge `develop` is behind GitHub `develop`, or holds commits GitHub
   does not have (`git rev-list --left-right --count`).
3. Response: for each forge-only commit, check by patch-id whether it is already on GitHub
   `develop` (for example as a squash). Unmatched commits are kept as branches on the forge, and
   published through the normal loop if still wanted. Only then is the forge `develop` moved to
   GitHub `develop`, by fast-forward.
4. **Never force-push** to fix divergence. If moving a ref would need a rewrite, stop and ask Chris.

## 5. Failure / lag alerting

- Proposed: a bounded check once per hour compares GitHub `develop` HEAD and the latest
  `<component>-v*` tag with the forge copy; file ONE `[run-watch] r0-mirror-lag` ticket on a
  mismatch that persists for >2 polls, comment on recurrence. Read-only; the watcher never
  re-syncs or pushes.
- At the P3 cutover Chris re-points the forge copy at the new public R0; its receipt is the
  SHA-equality table in the cutover ticket.

## 6. What GitHub Actions remain on R0 (publish + CI only)

- Stay on GitHub-hosted runners (D-G4; Free minutes apply to public repos):
  lint/typecheck/test lanes, `doc-links`, release-please, trusted publishing to
  PyPI (`digithings-<module>`, D-C5) and npm (`@digithings-ai/*`), GHCR image publish
  (digichat, digillm).
- Removed/moved before or at cutover: every `wrangler deploy`, Cloudflare deploy,
  Supabase prod-migration, and dispatch-secret workflow (they belong to R2/R5 or
  the Mac `deploy` queue). No `environment: production` with human reviewers on R0.
- Never attach a self-hosted runner to R0 (fork-PR code execution rule, review.md).
- No Cloudflare project is connected to R0 for auto-deploy on push (O5, D-X2); this held for
  the Cursor Origin app and holds for any forge.

## 7. History: Cursor Origin inbound mirror (until 2026-10-29)

From 2026-10-14 the plan gave R0 a Cursor Origin **inbound** mirror in Chris's personal namespace
(GitHub -> Origin; branches, tags and PRs synced; a push to the mirror forwarded to GitHub; "detach"
forbidden for R0), created with `origin repo create-mirrored` after P3, plus a mirror-lag watch.
D-C1 (2026-10-29) replaced Origin as the private home, and the 2026-10-31 re-home replaced the R0
Origin mirror with the Forgejo copy above. No Origin mirror is created for the new R0. Evidence of
the 14 Oct check: [origin-capabilities.md](origin-capabilities.md) (historical).

Open items carried over: D-G5 Worker-fallback detail is slice D (DIG-3561); the sync-job repair
and the drift reconcile (§4) are platform work, tracked outside this file.

## 8. R0 client-literal gate (local-ci, required)

- `scripts/check_r0_no_client_literals.py` (DIG-3689, wired as required by
  DIG-4043) scans every tracked path that stays public (R0) for client/tenant
  literals and fails on any hit outside the explicit grandfather list. It runs
  in the local-ci static gates, so a non-zero exit fails the required
  `local-ci` status and the PR cannot merge.
- Run it locally as `python3 scripts/check_r0_no_client_literals.py` (add
  `--census` for per-path counts). The census reads the git index, so `git add`
  new files before trusting a local green.
- Grandfather list: `scripts/r0_client_literals_baseline.json` — every entry
  names the owning ticket. Baseline refresh and literal removal belong to
  DIG-3689 / the repo-split scrub, not to passing PRs.
- Findings carry path + line + pattern name, never the matched value: CI logs
  on this repo are public. Never print a matched literal in a log, comment,
  or ticket.
