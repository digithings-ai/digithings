Follow-up: the fork's pull request CI never starts, so PR #51 carries no checks and the merge path is Chris's review.

Evidence (21 Oct 2026):

- `gh pr checks 51` reports "no checks reported". The check list of the PR is empty. The PR itself is MERGEABLE and CLEAN.
- The fork has 0 registered runners (`GET /repos/digithings-ai/paperclip/actions/runners` returns `total_count: 0`). `.github/workflows/pr.yml` calls upstream's `paperclipai/paperclip/.github/workflows/pr-trusted.yml@master`, and that workflow routes the jobs to an AWS RunsOn fleet label the fork does not have.
- Two runs sit queued since 14 and 17 Oct (PR run 38648471494 on `fix/dig-3344-reject-secret-comment`, CodeQL 38989733751 on master). No new run started for PR #51, and no run has started for any fork PR since 14 Oct.
- The fork's agentic review workflow (`commitperclip PR Review`) failed on the 14 Oct PRs.

This is a known and separate defect, so I did not open a new ticket for it: DIG-4446 ("fork PR CI never starts: no runner for the upstream AWS fleet label"), in_review with PR #44 open (fork-owned PR gates on ubuntu-latest). DIG-4446 also blocks the weekly upstream sync, so it is worth landing before more platform PRs stack up.

How the fork's PRs have been landing: PR #48 merged on 20 Oct by Chris, with an empty check list and no reviews. Six other fork PRs are open (#40, #41, #46, #47, #49, #50). The merge path is Chris's review, not a CI gate.

What I changed because of it:

- The PR body now states why the check list is empty and lists the gates a reviewer can repeat on the branch: the new test file (11/11), the two workspace suites (199/199), `cd server && pnpm exec tsc --noEmit` (clean).
- The full server suite (`pnpm test:run`) is still running on the branch. I replaced the line "the full suite passes" in the PR body with the exact state and the command to repeat. I do not leave an unverified claim in a PR that a human will merge. The result goes into the PR body when the run ends.

Unblock path, in order and with one actor named:

1. Chris reviews and merges digithings-ai/paperclip#51. Until the fork's CI runs again, the local verification receipt in the PR body is the gate.
2. Chris restarts Paperclip. I do not restart it.
3. After the restart the write-back keeps the isolated preference. The 117 bound issues then heal on their next run, without a field write on them.
4. The remaining 37 DROP issues are the last repair batch for the sweep. They are field writes, 9 issues per run at the write cap of 20.

Nothing else on this issue moves until step 2. The trap is dormant today: no issue in the last 40 is bound to another issue's worktree.
