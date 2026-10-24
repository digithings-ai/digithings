## Thinking Path

> - Paperclip is the control plane that runs agent issues.
> - Each issue runs in an execution workspace. The issue records the workspace and the way to use it.
> - The issue has two fields for this. `executionWorkspacePreference` and `executionWorkspaceSettings.mode`.
> - The runtime wrote the preference `reuse_existing` when it bound an issue to a workspace.
> - The runtime did not change the mode. The mode stayed `isolated_workspace`.
> - The two fields then said different things. The preference said "reuse a workspace". The mode said "the work is isolated".
> - A reader cannot tell from the fields whether the bound workspace is the worktree of this issue or the worktree of another issue.
> - This pull request makes the two fields agree. The runtime behaviour stays the same.

## Linked Issues or Issue Description

**What happened?**

The runtime wrote `reuse_existing` on the preference of every issue that it bound to its own isolated workspace. The mode in the settings stayed `isolated_workspace`. The issue then carried the pair `reuse_existing` and `isolated_workspace`.

A tool that reads this pair cannot tell an issue that owns its worktree from an issue that shares the worktree of another issue. The pair is the only signal that such a share is possible.

The runtime also wrote no preference at all when it resolved an isolation mode for a new issue. The issue then carried a mode and an empty preference.

**Expected behavior**

The preference and the mode must state the same thing.

- An issue that owns its isolated worktree keeps the preference `isolated_workspace`.
- An issue that is bound to the worktree of another issue keeps the preference `reuse_existing`. The pair stays visible, so the share can be repaired.
- A new issue that receives an isolation mode from the project policy keeps that mode as its preference.

**Steps to reproduce**

1. Create a project with the workspace policy `defaultMode: isolated_workspace`.
2. Create an issue in this project. Send the fields `executionWorkspacePreference: isolated_workspace` and `executionWorkspaceSettings: { mode: isolated_workspace }`.
3. Run the issue. The runtime creates the isolated worktree of the issue and binds it to the issue.
4. Read the issue. The preference is `reuse_existing`. The mode is `isolated_workspace`.
5. Create a second issue in this project. Send no workspace fields.
6. Read the second issue. The preference is empty. The mode is `isolated_workspace`.

**Paperclip version or commit**

`master` at commit `95aba525d`.

## What Changed

- The write-back keeps the preference `isolated_workspace` when the bound workspace is the workspace that the issue owns. The mode stays `isolated_workspace`. The two fields agree.
- The write-back keeps the preference `reuse_existing` when the bound workspace belongs to another issue. The cross-issue share stays visible.
- The reuse request counts a workspace that the issue owns as a reuse request. This happens whatever the stored preference says. The runtime restores that workspace. The runtime does not realize it a second time. A second realization mints a second workspace row for the same worktree path.
- The create path writes the resolved mode as the preference. This happens when the request names no preference and the issue has no workspace of its own.
- A new test file covers the write-back, the reuse request and the create path.

## Verification

- `pnpm vitest run server/src/__tests__/workspace-preference-write-back.test.ts` — 11 tests pass.
- `pnpm vitest run server/src/__tests__/heartbeat-workspace-session.test.ts server/src/__tests__/execution-workspace-policy.test.ts` — 199 tests pass.
- `cd server && pnpm exec tsc --noEmit` — no error.
- `pnpm test:run` — the full server suite runs on this branch. It is a serial run. It was still running when this text was written. The result is added here when the run ends.

## Pull request CI

This repository has no working pull request CI. The workflow of the repository calls the reusable workflow of the upstream repository. That workflow routes the jobs to a runner fleet label that this repository does not have. The repository has 0 registered runners. Two runs sit in the queue since 14 and 17 Oct 2026. No run starts for this pull request. The check list of this pull request is empty.

The gates of this pull request were run on the branch instead. A reviewer can repeat them on the branch:

- `pnpm vitest run server/src/__tests__/workspace-preference-write-back.test.ts`
- `pnpm vitest run server/src/__tests__/heartbeat-workspace-session.test.ts server/src/__tests__/execution-workspace-policy.test.ts`
- `cd server && pnpm exec tsc --noEmit`

## Risks

- A workspace that the issue owns is now restored in every run. Before, some runs realized it again. A realization mints a second workspace row for the same worktree path. The new behaviour removes that second row. The data of older runs is not changed.
- A projectless issue that is bound to a workspace of its own is no longer refused by the unrunnable worktree guard. The guard still refuses an issue that has no workspace.
- The preference of a new issue is no longer empty when the project policy resolves an isolation mode. A tool that reads the preference must accept the values `isolated_workspace`, `operator_branch` and `shared_workspace`. All three values are in the list of valid preferences today.

## Model Used

MiniMax M3.1 Flash Free, provider `opencode-go`. Context window 200000 tokens. No extended thinking mode. The model used the tool gateway for the file edits, the test runs and the git commands.

## Checklist

- [x] I have included a thinking path that traces from project context to this change
- [x] I have specified the model used (with version and capability details)
- [x] I have checked ROADMAP.md and confirmed this PR does not duplicate planned core work
- [x] I have searched GitHub for duplicate or related PRs and linked them above
- [x] I have described the issue in this pull request with the fields of the bug report template
- [x] I have not referenced internal/instance-local Paperclip issues or links
- [x] My branch name describes the change and contains no internal Paperclip ticket id or instance-derived details
- [x] I have run tests locally and they pass
- [x] I have added or updated tests where applicable
- [ ] I have updated relevant documentation to reflect my changes
- [x] I have considered and documented any risks above
- [ ] All Paperclip CI gates are green
- [ ] Greptile is 5/5 with no open P2s, recommendations, or follow-ups
- [ ] I will address all Greptile and reviewer comments before requesting merge

