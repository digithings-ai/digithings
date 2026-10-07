# Agent skills (digithings)

Small **task recipes** for coding agents. Cursor stores skills under the user skill directory or project rules; Codex uses `$CODEX_HOME/skills`. This folder is the **canonical copy in git**.

## Install (Cursor)

Copy or symlink each `SKILL.md` into a Cursor skill folder your build recognizes (e.g. project `.cursor/skills/<name>/SKILL.md` if your Cursor version supports project skills), **or** paste the body into a project rule under `.cursor/rules/`.

## Bundled skills

| File | Purpose |
|------|---------|
| [digithings-backlog/SKILL.md](digithings-backlog/SKILL.md) | Update INDEX, align with GitHub Issues |
| [digithings-doc-pr/SKILL.md](digithings-doc-pr/SKILL.md) | Doc-only PR checklist and auto-merge allowlist |
| [digithings-component-touch/SKILL.md](digithings-component-touch/SKILL.md) | Before editing code: doc + test commands |

## Check that skill links resolve

Seats load a skill through `slug` → `slug--<10-hex>` → a materialised source directory. When
the source is garbage-collected the two links survive and the skill silently stops loading,
with no error and no run failure (DIG-2284 left 8 dangling aliases on a 59-seat org).

`scripts/check_agent_skills_links.py` is the read-only check. It never repairs anything —
deleting a broken symlink hides the symptom and loses the skill permanently, so the repair
is to re-materialise the hashed target or re-sync the seat.

```bash
make skills-links-check SKILLS_HOME=~/.claude/skills   # operator run, warnings fail too
python3 scripts/check_agent_skills_links.py --expect product-management --json
```

Exit `0` clean, `1` findings, `2` bad usage. `--expect` is the seat-level signal: it fails
when a named skill a seat is supposed to load does not resolve. The same script runs in the
`CI: docs` job against `.claude/skills`; a CI checkout has none until `make agents-init`
runs, so an absent home is reported rather than failed.

## Conventions

- Keep skills **short**; link to `docs/` and root `AGENTS.md` instead of duplicating policy.
