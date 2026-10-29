# Agent rules card

Draft for Chris's review (2026-10-29). This is the short form of the agent-facing rules in
[AGENTS.md](../../AGENTS.md) and [MERGE_QUEUE.md](../MERGE_QUEUE.md). Those files stay the full
reference until this card is adopted; where they disagree, they win until then.

## 1. Before you start

- Check the local forge: `curl -s -m 2 -o /dev/null -w "%{http_code}" http://localhost:3000/api/healthz`.
  `200` means use `sctl` and Forgejo for all iterative work (change, forge PR, review,
  `sctl publish`) and open no GitHub PRs for iteration. Anything else means the GitHub flow below.
- Forgejo flow:

  ```bash
  sctl change new --id DIG-1234-fix-thing --owner <platform> --base local/develop
  sctl forge open --change DIG-1234-fix-thing --base develop
  sctl review record --change DIG-1234-fix-thing --from-forge --pr 7
  sctl doctor --base local/develop
  sctl publish --change DIG-1234-fix-thing --remote github --target develop
  ```

  `--owner` takes the platform (new, see [ATTRIBUTION.md](../ops/ATTRIBUTION.md)); AGENTS.md still says `<seat>`.
- Never use the forge's `github-develop` branch as a base, and never push to it.
- Run local CI (Woodpecker) and Docker before publishing.
- Before changing a component, read `{component}/AGENTS.md` and `{component}/ARCHITECTURE.md`.
  Update `ARCHITECTURE.md` after any interface or behaviour change.
- Pick the skills that fit the task; there is no fixed pipeline. A one-line docs fix needs no
  TDD or full review toolkit.

## 2. Hard rules

- Polars only, never pandas. Pydantic v2, strict typing, ruff (line length 100).
- LangGraph supervisor and sub-graphs; LiteLLM with caching; NautilusTrader for every
  backtest, optimize and live path; MCP-first.
- Every change traces to an issue: a `task/<N>-slug` branch, or `Fixes #N` (or `Fixes DIG-1234`)
  in the PR body. This is a convention, not a CI gate.
- Never touch live-trading paths without explicit human approval.
- `projects/` is confidential. Never push it to a public remote. A projects-path-guard denial
  is not a bug to work around.
- digi* names are always lowercase in prose (digithings, digiquant, digichat, …). Code
  identifiers keep their language's casing.
- Never push directly to `develop` or `main`. Never `git stash`.
- `az` exit 78 (`az guard: REFUSED`) and `gh` shim exit 76 are enforced refusals: do not retry,
  bypass, or re-argue them. Exits 69 and 70 are not refusals and are not a reason to fall back
  to the host credential. If a task truly needs the access, say so in the run report.
- No PR outside the `digithings-ai` org.
- Do not route review through the CodeRabbit Cursor plugin.

## 3. Branches and PRs

- `main ← develop ← module/<component> ← task/<N>-slug`. Create task branches with
  `make task ISSUE=N`; it cuts from the current `origin/<base>` and refuses a stale module base.
- `component:root`, `component:digivault`, `component:website` and the default route go straight
  to `develop`. Other backend modules go through `module/<component>`
  (`scripts/project_routing.json`).
- Branch names follow [BRANCHING.md](../../BRANCHING.md): `task/<N>-slug`,
  `{feat,fix,docs,chore,revert}/<slug>`, `{claude,codex,cursor,copilot}/<slug>`, `bot/<slug>`,
  `<handle>/<slug>`. The pre-push hook enforces it.
- Module branches allow no force-push or deletion and need a PR. Sync one with a PR from
  `develop` or from a `chore/sync-*` branch.
- PR titles into `develop` use Conventional Commits with a required scope, e.g. `feat(digillm): …`.
- Hand-run worktrees: `git worktree add --no-track -b <branch> <remote-ref>`. Push with an
  explicit refspec and confirm with `git ls-remote`. Remove task worktrees after merge
  (`scripts/worktree_task.sh remove N`).
- Before committing a lockfile change, check that `git diff origin/develop -- package-lock.json`
  shows only your edit (macOS `npm ci` strips the `libc` fields).
- Never hand-edit `.claude/agents/`, `.claude/skills/` or `.claude/commands/`. Edit
  `agents/sources/` and run `make agents-init`.
- Never write review, report, handoff, plan or scratch files to the repo root, and never commit
  review files. Plans go in `docs/plans/`, research in `docs/research/`, scratch outside the repo
  or in `.scratch/`, screenshots in `/tmp/`.

## 4. Attribution (new, decided by Chris on 2026-10-29)

- Ownership is recorded by platform only: `claude`, `cursor`, `grokbot`, `paperclip`. Paperclip
  has no per-seat breakdown.
- Every commit carries `Source-Platform: <platform>`. Keep it through squash.
- `src:<platform>` labels are applied by tooling from the trailer, never by hand.
- The owner of a GitHub PR is the platform that pushes it. A promotion PR lists the platforms it
  carries.
- `reviewed:agent` and `reviewed:owner` are retired. Never add them after merge. Until the
  tooling follow-up lands, the queue and the `main` check still read `reviewed:agent` plus the
  findings comment, so keep posting that pair for an in-session review.
- Details: [ATTRIBUTION.md](../ops/ATTRIBUTION.md).

## 5. Review

- Every review leaves a record on the PR: a comment opening with `<!-- in-session-review -->`,
  with `<!-- digithings-review agent=<seat> run=<run> head=<sha> -->` on a line of its own, the
  verdict, severity counts and file:line evidence. A review that exists only in chat is not
  coverage.
- The marker must name the current head (at least 7 characters of the sha). A verdict applies
  only to the head it names.
- The author session never reviews its own work. A review must come from a reviewer that did not
  write the code.
- A review done in a fresh session on the same platform counts as an independent review
  (new, Chris, 2026-10-29). The queue still enforces seat-level independence until its tooling
  is migrated.
- Post verdicts as `Review verdict: approved` or `Review verdict: changes requested`, outside
  code fences and inline code. Anything inside code is a quote and counts for nothing.
- To clear your own block on the same, unchanged head, your approve must also carry a line
  `Withdraws: changes requested on <sha>`. A fresh approve on a new head needs no such line.
  Another reviewer's approve never clears your block.
- Resolve every review thread (fixed, or refuted on the record) before merge.
- Metered bots are optional. Run Bugbot only once the diff is final, never per push. `neutral` is
  not a review; run `/review` instead.

## 6. Merging

- Merge-ready means required CI is green, the branch is not conflicted (`CLEAN`), review threads
  are triaged, review coverage is on the record, and deslop/simplify ran when the diff warrants it.
- Into a stacked `module/<component>` base, the authoring agent merges its own merge-ready PR.
- Into `develop`, only `scripts/merge_queue.py` merges, run as a roster role (`cto` or `em`, in
  `scripts/merge_queue_policy.json`). QA reviews and does not merge. Anyone else leaves the PR
  merge-ready and says which role the queue should run as. Adding a role is Chris's decision.

  ```bash
  python3 scripts/merge_queue.py list --repo digithings-ai/digithings --acting-role cto
  python3 scripts/merge_queue.py run  --repo digithings-ai/digithings --acting-role em
  # add --dry-run to see the plan without touching anything
  ```

- The queue merges only when the base is `develop`; `local-ci` reported `SUCCESS` and no other
  check failed; the PR is mergeable and `CLEAN` (it updates `BEHIND` branches itself); no
  verdict blocks the head; review coverage from another reviewer names the current head; and no
  review thread is open. It passes `--match-head-commit`, never `--admin`, and leaves an audit
  comment.
- Exit codes: 0 merged or nothing eligible; 1 `gh` failure; 2 role not on the roster; 3 base
  needs a human. Codes 2 and 3 are refusals, not something to retry.
- Stop and ask, do not merge: `digikey/` auth, JWT or crypto; live trading or
  `digiquant/brokers/`; new external network exposure or service dependency; any PR into `main`;
  release-please PRs; anything the user marked draft-only, research-only or do-not-merge.
- "Never merge" lines in harness prompts are overridden by this policy, except for the
  stop-and-ask list above.

## 7. Models

- Use the best model for the job, then the most token-efficient one that clears the bar. Never
  use fast mode (`*-fast`).
- Pin a model on every subagent; never let one inherit silently. Name each model before fanning
  out more than about five subagents.
