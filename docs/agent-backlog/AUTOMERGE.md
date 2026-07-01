# Doc-only auto-merge policy

Pull requests that change **only** allowlisted paths may enable **squash auto-merge** after CI passes, when the label **`automerge-docs`** is applied.

## GitHub settings (maintainers)

1. **Settings → General → Pull Requests:** enable **Allow auto-merge**.
2. **Settings → Branches:** branch protection on `main` / `develop` — require status checks including **CI** and **Doc paths gate** (from `.github/workflows/agent-docs-automerge.yml`).
3. Default merge: **squash** (recommended).

## Label

- **`automerge-docs`** — maintainer (or bot) applies when the PR is documentation-only and safe to merge without human click.

## Path rules (enforced in CI)

The job `Doc paths gate` runs `scripts/verify_doc_only_pr.py` for PRs labeled `automerge-docs`. It **fails** if any changed file is outside the allowlist.

**Allowed:**

- `docs/**`
- `website/**/*.md` (static site copy only)
- Selected root Markdown files: `README.md`, `AGENTS.md`, `CLAUDE.md`, `ARCHITECTURE.md`, `CONTRIBUTING.md`, `RELEASES.md`, `ROADMAP.md`
- Root config: `agents.yml`
- Any `**/AGENTS.md`, `**/CLAUDE.md`, or `**/ARCHITECTURE.md`

**Never auto-merge (job fails):**

- **`.github/workflows/**`** — workflow changes require human review
- **`SECURITY.md`** anywhere — security narrative must not merge without explicit review

The workflow **enable automerge** step also requires the `automerge-docs` label and only runs when the gate succeeds.

## SECURITY.md exclusion

Changes under `SECURITY.md` are **rejected** by `verify_doc_only_pr.py`. To update security docs, merge via a normal PR **without** `automerge-docs`.

## Manual override

Remove `automerge-docs` or push a non-doc commit to cancel auto-merge eligibility.
