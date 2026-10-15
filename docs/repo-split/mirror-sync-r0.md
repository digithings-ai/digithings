# R0 mirror sync: GitHub (primary) <-> Cursor Origin (inbound mirror)

Slice C of the repo split (DIG-3560, parent epic DIG-3518). Plan only — no repo
creation, migration, or Cloudflare change is part of this slice.

Supersedes the slice title's premise: per D-O1 (answered 2026-10-14, in PR #5695
`docs/repo-split/decisions.md`), R0 stays **GitHub-primary** with an **Origin
inbound mirror** — not Origin-primary. Truth flows GitHub -> Origin. No push
mirror is built.

Sources: PR #5695 (`DIG-3518-repo-split-plan`), decisions.md D-G/D-O, review.md
§ Cursor Origin, migration-plan.md §§ Source-control/P3. Depends on slice A
(DIG-3558, Origin capability verification): assumptions below marked [A].

## 1. Mechanism (no custom code)

- Use Origin native **inbound mirror**: after P3 cutover Chris runs
  `origin repo create-mirrored` for R0 (migration-plan § Source-control).
- What syncs (review.md, VERIFIED from Cursor docs/OpenAPI): **branches, tags, PRs**.
  What does NOT sync: **issues, Actions, secrets**.
- A push to the Origin mirror is **forwarded to GitHub** (GitHub stays source of truth).
- No local push hook, no cron mirror, no deploy-host push job. Rationale: nothing
  custom to operate; the (b) option (Origin-primary + hand-built push mirror) was
  explicitly not chosen in D-O1 because any writer can make GitHub diverge.
- Agents may clone from either remote; canonical fetch/push remote stays GitHub.
  The Origin mirror is a read path + Origin-PR working path.

Assumptions [A] (slice A to confirm against live Origin behaviour):
- [A1] Tag sync cadence covers release tags (`<component>-v*`) promptly; verify one tag round-trip post-P3.
- [A2] Push-forward applies to tags as well as branches.
- [A3] No outbound Origin -> GitHub mirror doc appears before P3 (absence verified 2026-10-14; re-check at build time).

## 2. Tags / releases

- Release tags are cut **by Chris on GitHub**; **signed tags are mandatory (D-G6, mandatory since 23:18)**, enforced by local-ci `git verify-tag` against `allowed_signers`. Origin has no signed-tag rule type, so the check lives in local-ci; unsigned tags are refused.
  The mirror carries them to Origin automatically (§1 sync set).
- Nothing deploys from R0 (migration-plan: "Nothing deploys from R0"), so a tag on R0
  is a **publish marker** (release-please / PyPI / npm / GHCR), never a deploy trigger.
- Per-package release branches (`release/<module>`, D-R3: tags + release-please on
  `main` in R0) sync as ordinary branches. No signed-tag rule exists on Origin,
  so the tag gate is enforced by local-ci, not by Origin.

## 3. External contributions flow back (GitHub -> Origin)

- **PRs:** external PRs live on GitHub natively; they sync to the Origin mirror as
  mirrored PRs. Review + merge happen **on GitHub** (merge queue, required checks).
  No hand-carry needed. Origin-side clones see the same branch refs.
- **Issues:** do NOT sync. GitHub Issues are the only issue tracker for R0.
  Agents working from an Origin clone reference `digithings-ai/digithings#NNN`
  manually; no issue mirror is built (out of scope by design).
- **Direction rule:** nobody merges on the Origin mirror expecting it to stick —
  merges land on GitHub; the mirror follows. Detach (making Origin primary) is
  one-way, needs Chris's user credential (`repository:mirror:delete`), and is
  **never** run for R0.

## 4. Conflict / divergence policy

1. GitHub is source of truth in every dispute, by D-O1.
2. Divergence symptom: `git ls-remote` SHA mismatch on same ref (GitHub vs Origin mirror).
3. Response: stop writing via Origin, finish/merge on GitHub, then either wait for
   mirror catch-up or (Chris only) re-run `create-mirrored`. Never force-push the
   mirror to "fix" it; never detach.
4. Namespace guard: R0 mirror name in Chris's personal namespace is fixed at
   creation (cannot change during beta) — record the exact `<ns>/digithings` path
   in R0's README at P3.

## 5. Failure / lag alerting

- Origin documents no built-in mirror-lag alert (gap recorded for slice A to confirm [A4]).
- Proposed (no build this wave): extend Production run watch with a bounded check —
  once per hour compare `HEAD` + latest `<component>-v*` tag SHAs on both remotes;
  file ONE `[run-watch] r0-mirror-lag` ticket on mismatch persisting >2 polls,
  comment on recurrence. Read-only, no re-kick/re-mirror by the watcher.
- Mirror creation itself (P3) is a Chris action; its receipt is the SHA-equality
  table in the cutover ticket, not an alert.

## 6. What GitHub Actions remain on R0 (publish + CI only)

- Stay on GitHub-hosted runners (D-G4; Free minutes apply to public repos):
  lint/typecheck/test lanes, `doc-links`, release-please, trusted publishing to
  PyPI (`digibase … digiquant`) and npm (`@digithings/*`), GHCR image publish
  (digichat, digillm).
- Removed/moved before or at cutover: every `wrangler deploy`, Cloudflare deploy,
  Supabase prod-migration, and dispatch-secret workflow (they belong to R2/R5 or
  the Mac `deploy` queue). No `environment: production` with human reviewers on R0.
- Never attach a self-hosted runner to R0 (fork-PR code execution rule, review.md).
- The Cloudflare Cursor-Origin app (auto-deploy on push) is **never installed**
  for R0 (O5).

## 7. Open items

- D-G6 decided MANDATORY 23:18 (reflected in §2); D-G5 Worker-fallback detail is slice D (DIG-3561).
- If Origin ever ships outbound mirroring, revisit §1 — until then the decision stands.
