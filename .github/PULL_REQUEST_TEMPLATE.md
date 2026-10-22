## Linked issue

<!--
Every PR must trace to a backlog issue on the Project board.
Either use a branch named  task/<N>-<slug>  (created by `make task ISSUE=N`),
or add a line below like:  Fixes #123   (also accepts Closes / Resolves).
A PR that traces to a Paperclip issue and has no GitHub issue writes
Fixes DIG-1234 instead: the pr-template gate accepts that form, and the bare
`Fixes #` this template starts with fails it ("names no issue number").
CI check: .github/workflows/ci-pr-hygiene.yml
-->

Fixes #

---

## Component

<!-- Check all that apply -->
- [ ] digigraph
- [ ] digiquant
- [ ] digisearch
- [ ] digitrace
- [ ] digibot
- [ ] digibase
- [ ] digikey
- [ ] digichat
- [ ] website / root docs
- [ ] config / infra

## Change Type

- [ ] feat — new capability
- [ ] fix — bug fix
- [ ] refactor — restructure without behavior change
- [ ] docs — documentation only
- [ ] test — tests only
- [ ] chore — build, CI, deps

## Summary

<!-- 2–4 sentences: what changed and why -->

---

## Modules / files / folders touched

<!-- Required by the develop merge rule (Chris, 15 Oct 2026, DIG-3845).
List every module, file and folder this PR touches, e.g.
`digibase/src/digibase/art9.py`, `tests/db/`, `.github/workflows/ci-docs.yml`. -->

---

## What this PR delivers

<!-- Required: what the PR delivers, in concrete terms. -->

---

## Feature or epic it belongs to

<!-- Required: the feature or epic this PR belongs to (issue link, e.g. Fixes #123). -->

---

## How it fits the project vision

<!-- Required: how this change fits the project vision. -->

---

## Review

Quality bar is **review**, not a self-score — see [CODE_REVIEW_POLICY.md](docs/agents/CODE_REVIEW_POLICY.md).
Run `/review` (or an in-session review) when that policy needs a hatch, and link the findings.
The self-score rubric (`docs/scoring/`, `make score`) was removed in #4868.

---

## Testing Evidence

```
# Paste output of: make test-unit (and ruff check if code change)

```

---

## Documentation Updated

- [ ] `{component}/ARCHITECTURE.md` updated (Module Map, Public API, or Configuration changed)
- [ ] `{component}/AGENTS.md` updated (new patterns or anti-patterns discovered)
- [ ] Root `AGENTS.md` updated (if a cross-cutting rule changed). Keep `CLAUDE.md` as a pointer at AGENTS.md.

---

## Human Gate

> If any box below is checked, this PR **requires human review** before merge — do not label `automerge-docs`.

- [ ] Live-trading path modified (broker adapters, order submission, execution gates)
- [ ] Auth or crypto modified (digikey signing, JWT generation, scope enforcement)
- [ ] New JWT scope added to a protected route
- [ ] `DIGI_ALLOW_CODE_EXEC` gate modified
- [ ] New network exposure (`0.0.0.0` bind or new published port)
- [ ] New external service dependency introduced
- [ ] `SECURITY.md` changed
- [ ] Novel architecture pattern introduced (not described in any existing ARCHITECTURE.md)

**Is human review required?** Yes / No
