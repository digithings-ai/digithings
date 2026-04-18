---
name: digithings-doc-pr
description: Prepare a documentation-only pull request and optional automerge-docs labeling for DigiThings.
---

# DigiThings doc PR skill

## When to use

The PR changes only Markdown / agent docs under the **allowlist** in [docs/agent-backlog/AUTOMERGE.md](../../agent-backlog/AUTOMERGE.md).

## Steps

1. Run `python3 scripts/check_doc_links.py` from the repo root; fix broken relative links.
2. Ensure **no** changes to `SECURITY.md`, `.github/workflows/`, source trees, or dependency manifests unless this is **not** a doc-only PR.
3. Open the PR; apply label **`automerge-docs`** only if maintainers want squash auto-merge after CI.
4. If you touched security or workflow files, **do not** use `automerge-docs`.

## Verification

- CI must stay green (same checks as code PRs).
