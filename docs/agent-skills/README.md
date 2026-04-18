# Agent skills (DigiThings)

Small **task recipes** for coding agents. Cursor stores skills under the user skill directory or project rules; Codex uses `$CODEX_HOME/skills`. This folder is the **canonical copy in git**.

## Install (Cursor)

Copy or symlink each `SKILL.md` into a Cursor skill folder your build recognizes (e.g. project `.cursor/skills/<name>/SKILL.md` if your Cursor version supports project skills), **or** paste the body into a project rule under `.cursor/rules/`.

## Bundled skills

| File | Purpose |
|------|---------|
| [digithings-backlog/SKILL.md](digithings-backlog/SKILL.md) | Update INDEX, align with GitHub Issues |
| [digithings-doc-pr/SKILL.md](digithings-doc-pr/SKILL.md) | Doc-only PR checklist and auto-merge allowlist |
| [digithings-component-touch/SKILL.md](digithings-component-touch/SKILL.md) | Before editing code: doc + test commands |

## Conventions

- Keep skills **short**; link to `docs/` and root `AGENTS.md` instead of duplicating policy.
