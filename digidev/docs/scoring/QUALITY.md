# Quality rubric

Default minimum: **8/10**

Score one point per criterion satisfied.

---

## Criteria

1. **Typed interfaces** — Public functions, class methods, and API boundaries have explicit type annotations. No untyped `Any` without an inline comment explaining why it's unavoidable.

2. **Linter clean** — `ruff check . && ruff format --check .` (Python) or `eslint` / `tsc --noEmit` (JS/TS) passes with zero errors. No suppressed warnings without justification.

3. **Tests for changed behavior** — Every new function or changed behavior has at least one unit test. Tests cover the happy path and at least one error case. Existing tests are not deleted to make the suite pass.

4. **No orphaned code** — Removed symbols are cleaned from all callers, exports, and import lists. No `_old_` prefixes or `# TODO: remove` comments left behind.

5. **File size discipline** — No file exceeds 400 lines without a comment explaining why. No function exceeds 60 lines without a comment. Large files are a signal that responsibilities need splitting.

6. **Structured errors** — Errors are returned as typed models or structured envelopes, not raw strings or untyped exceptions. Callers can distinguish error categories without string-matching.

7. **ARCHITECTURE.md updated** — If you added a module, changed a public API, added an endpoint, added an env var, or changed a data model, `{component}/ARCHITECTURE.md` reflects it.

8. **No backward-compat hacks** — No `_old_` variable names, no `# removed` comments for removed code, no re-exported symbols kept only for compatibility. If something is unused, delete it.

9. **Focused responsibilities** — Each module, class, and function does one thing. No "kitchen sink" modules. New abstractions are warranted by three or more uses, not anticipated future uses.

10. **Commit history is clean** — Commits have conventional format (`type(component): description`). No "WIP" or "fix fix fix" commits in the final history. Squash or rebase before PR if needed.

---

## Common fixes

| Failure | Fix |
|---|---|
| Missing types | Add annotations; use `mypy --strict` or `pyright` to find gaps |
| Linter errors | Run `ruff check . --fix` for auto-fixable issues |
| No test for new behavior | Write a unit test covering inputs, outputs, and one error case |
| Orphaned imports | Run `make clean-imports` |
| File too long | Split into focused modules |
| Stale ARCHITECTURE.md | Update the relevant section |
