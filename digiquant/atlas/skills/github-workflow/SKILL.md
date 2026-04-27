---
name: github-workflow
description: >
  Use GitHub CLI (gh) for issues and pull requests in this repo — list evolution backlog,
  view an issue, create a fix branch, open a PR that closes the issue.
---

# GitHub workflow (CLI)

## Prerequisites

- [`gh`](https://cli.github.com/) installed: `gh auth status`
- Repo root = digiquant-atlas (git remote points at GitHub)

## Common commands

```bash
# Issues labeled evolution (pipeline backlog)
gh issue list --label evolution --state open

gh issue view 123 --web

# Create branch and PR (after making commits)
git checkout -b fix/evolution-123-short-slug
git add -p
git commit -m "fix: describe change (#123)"
git push -u origin HEAD
gh pr create --title "fix: ..." --body "Closes #123

Summary: ...
"
```

## Labels

See [`docs/ops/GITHUB_PIPELINE_LABELS.md`](../../docs/ops/GITHUB_PIPELINE_LABELS.md). Issues from [`scripts/pipeline_review_to_github.py`](../../scripts/pipeline_review_to_github.py) include `evolution`, `source/post-mortem`, `track/research` or `track/portfolio`, type/severity labels.

## Guardrails

- Do not put secrets or `SUPABASE_SERVICE_KEY` in issue or PR bodies.
- Do not enable auto-merge unless the repo owner requests it; default is human review.
