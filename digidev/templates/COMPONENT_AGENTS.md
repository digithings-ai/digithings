# {{COMPONENT_NAME}} — AGENTS.md

**Component:** {{COMPONENT_NAME}} — {{COMPONENT_DESCRIPTION}}

**Test command:** `{{COMPONENT_TEST_CMD}}`

---

## Pre-flight checklist

Before writing any code in this component, verify:

- [ ] Read this file completely
- [ ] Read `{{COMPONENT_NAME}}/ARCHITECTURE.md` (if it exists) for the relevant section
- [ ] Run the test command above to establish a green baseline
- [ ] Confirm your branch is `task/N-slug` or a named feature branch (not `main`/`{{DEFAULT_BRANCH}}`)

---

## Rules for this component

<!-- Add component-specific rules here. Examples: -->
- Follow the project-wide rules in `AGENTS.md` and `agents.yml`.
- Typed interfaces on all public functions and API boundaries.
- Tests required for all new or changed behavior.
- Update `{{COMPONENT_NAME}}/ARCHITECTURE.md` if you add modules, endpoints, or env vars.

---

## Anti-patterns to avoid

<!-- Document things that have gone wrong before or that agents commonly do wrong. -->
- Don't add circular imports between this component and others.
- Don't hardcode configuration values — use environment variables.
- Don't suppress errors with bare `except: pass`.

---

## Architecture reference

<!-- Point to the relevant ARCHITECTURE.md section. -->
See `{{COMPONENT_NAME}}/ARCHITECTURE.md` for the module map, public API, and configuration.

If `ARCHITECTURE.md` doesn't exist yet, create it when you add the first non-trivial interface.

---

## Test command

```bash
{{COMPONENT_TEST_CMD}}
```

Run this before scoring. Zero failures required.

---

## Common patterns

<!-- Document the key patterns for this component. Add entries as the codebase evolves. -->

### Adding a new endpoint / function

1. Define the typed input/output models.
2. Implement with error handling (structured errors, not raw strings).
3. Add a unit test covering the happy path and at least one error case.
4. Update `{{COMPONENT_NAME}}/ARCHITECTURE.md` → Public API section.

### Adding configuration

1. Add to `.env.example` with a comment explaining the value.
2. Load via the project's config pattern (not `os.getenv` scattered across files).
3. Document in `{{COMPONENT_NAME}}/ARCHITECTURE.md` → Configuration section.

---

## Known gotchas

<!-- Add project-specific quirks and gotchas as you discover them. -->
<!-- Example: "The X dependency requires Y to be initialized first." -->
