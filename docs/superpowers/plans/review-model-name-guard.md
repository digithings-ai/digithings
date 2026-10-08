# Review — `check_model_name_literals.py` (#5090)

- **Subject:** PR #5090, `ci(root): guard production code against hardcoded model names (#5089)`
- **Reviewer:** in-session review, three fresh-context subagents (`general`)
- **Author session:** implemented, then did not review its own work
- **Date:** 2026-10-05
- **Verdicts:** R1 `request-changes` · R2 `request-changes` · R3 `request-changes`
- **Outcome:** 12 findings, 11 fixed, 1 recorded as an inherent gap. Plus 2 further bugs found by the author's own regression tests during the fix pass.

---

## Why three subagents and not one

On #5046 this session gave one subagent a single large multi-area review
prompt and it **returned no output at all** — no verdict, no findings, nothing.
The review therefore did not happen, and since AGENTS.md forbids the author
reviewing its own work, there was no substitute.

So the review was split into three narrow, single-question passes, each told
to reply in a fixed markdown format **even when the answer was clean**, and
each capped at ~70 lines. All three answered. That split is what surfaced
both the major and the critical; a single combined pass would most likely
have hit the same empty return.

| pass | question | found |
|---|---|---|
| R1 | *can this guard be made to PASS while a literal is still present?* | D1 CRITICAL, D2/D3 MAJOR, D4/D5 minor, D6 nit |
| R2 | *is the guard's picture of the tree correct — right files skipped, wrong files allowed, honest exemption reasons?* | F1 MAJOR (same defect, found independently), F2–F4 |
| R3 | *does the wiring gate, are the tests load-bearing, do the docs match?* | F1 MAJOR (same defect, found independently), F2–F5 |

R2 and R3 found the F1 defect **independently of each other**. That is worth
recording: it was not a subtle read, it was a documented behaviour with no
implementation.

---

## Disposition of every finding

| # | finding | severity | disposition |
|---|---|---|---|
| R1-D1 | the `test` **directory** rule hid a shipping Next.js route handler carrying 5 literals | CRITICAL | **fixed** |
| R2-F1 / R3-F1 | the configured-marker detection mode was documented but never consulted — 8 of 16 markers enforceable by neither path | MAJOR | **fixed** |
| R2-F4 | `MODEL_ID_PATTERN` missed id shapes this repo's own config routes on (`o1`, `o3`, `o4-mini`, `r1`, `GLM-5.3-Flash`, `Kimi-K3`) | MAJOR | **fixed** |
| R1-D3 | a `//` inside a regex literal blanked the rest of the line, taking a real literal with it | MAJOR | **fixed** |
| R1-D4 | `KNOWN_REMAINING` pinned a bare count, so swapping an allowlisted literal for a different unconfigured one kept the count matching | minor | **fixed in part** — see *D4, and what I chose not to do* |
| R1-D5 | `GENERATED_MARKERS` waived 405 literals on a self-declared filename; a planted `b_handwritten.generated.ts` went unreported | minor | **fixed** |
| R2-F2 | the `packages/ui` exemption reason was factually wrong (`"private": true`, `scripts: {test, typecheck}`, no build step at all) | minor | **fixed** in both the script and `config/MODELS.md` |
| R3-F2 | `test_repo_passes_clean` duplicated the CI step byte-for-byte and stayed green when `main()` was stubbed to `return 0` | minor | **fixed** |
| R1-D6 | split-literal construction (`"gpt-" + "4o-mini"`) defeats the matcher | nit | **recorded as inherent** |
| R3-F3 / R2-F3 | the cited provenance file did not exist at the path given (`reference/SOURCE.md`) | nit | **fixed** in both files |
| R3-F4 | the `config/MODELS.md` exemption table omitted the guard's own self-exemption | nit | **fixed** — table now 6 rows |
| R3-F5 | the ci-docs comment overstated the end state ("live in config/" with 79 literals present by design) | nit | **fixed** |

---

## The two that mattered

### F1 (MAJOR, found independently by R2 and R3) — the documented detection mode did not exist

`configured_markers()` read `config/model-policy.json`, fed a vacuity check,
and printed its size in the success message. Nothing else used the set:
`scan`, `_python_hits` and `_script_hits` all took no markers argument at
all. The module docstring, `config/MODELS.md` and a test docstring all
described a "configured id" detection mode.

Author verification, before accepting the finding:

```
printf 'export const A = "claude-3-5-sonnet";\n' > scripts/_probe_cfg.ts
python3 scripts/check_model_name_literals.py
  → OK (... 16 configured markers, 59 known literal(s) ...)   EXIT=0
```

`claude-3-5-sonnet` is an explicit `flagship_model_id_markers` entry. Eight
of the sixteen configured markers — `o1-`, `o1/`, `o3-`, `o3/`, `o4-`,
`claude-3-opus`, `claude-3-5-sonnet`, `claude-4` — were not matched by the
shape pattern either, so nothing caught them.

Fixed by threading the set from `main()` into `scan()` and having both
matchers consult it. The same probe now reports
`FAIL scripts/_probe_cfg.ts: 1 model name literal(s) — 1: 'claude-3-5-sonnet'`.

### D1 (CRITICAL, R1) — a directory rule reopened a hole the stem rule closed

`apps/digichat/src/app/api/byok/test/route.ts` carries five literals and is
340 lines of live Next.js code. The same BYOK probe ships **twice**: as a
Cloudflare Pages Function at `functions/api/byok/test.ts` (a bare `test`
**stem**) and as a Next.js route at `src/app/api/byok/test/route.ts` (a
`test` **directory**).

`TEST_FILE_STEMS` had been written specifically to refuse the bare stem
`test`, because that stem is how a route segment names itself. The
`TEST_DIR_PARTS` rule then exempted any directory named `test`, reopening
exactly the same hole one level up. The fix: a directory holding a route
file is a route, not a fixture.

R1's caveat, honoured: it did not trace whether `/api/byok/test` is still
mounted in `digichat-release`. A stale-but-present route handler is not an
exemption argument, so it is scanned.

---

## Two bugs the author's own regression tests found

Neither came from a reviewer. Both are recorded because they say something
about the guard that a reviewer could not see from the outside.

**A latent crash that the guard was green over.** `_script_hits` called
`match.start()`, but the shape branch produces a `re.Match` (whose
`.start()`/`.end()` are *methods*) while the configured-marker fallback
produces a `_Span` (a `NamedTuple` whose `start`/`end` are *fields*).
Calling the field as a method raised `TypeError: 'int' object is not
callable`.

It never fired on the real tree, because every marker in the shipped policy
is *also* shape-matched, so the configured branch was dead code. The guard's
own green run could not reach its own bug. Fixed by normalising to a `_Span`
at the branch.

**And that crash explains what the F1 fix is actually worth.** Once the
widening (R2-F4) landed, I computed that **zero** configured markers are
unmatched by shape. So the configured and shape paths fully overlap on
today's data: F1 is forward defence for the *next* marker added, not a live
gap. The overlap is precisely why the crash stayed latent — which is
second-order confirmation that the wiring mattered.

My first F1 test asserted `claude-3-5-sonnet` was *not* shape-matched. It
is, because the widening added `claude-[34]`. My own assertion caught my
stale premise, so the test now proves the **wiring** — inject a
shape-blind marker through `configured_markers`, assert shape alone returns
`[]`, then assert `main() == 1` — rather than the data.

---

## D4, and what I chose not to do

R1's attack: in an allowlisted path, swap a model literal for a different
unconfigured one; the count still matches, the guard still passes. The
obvious fix is to pin the literal *names*.

I measured what that costs. There are **73 distinct literal strings** across
the 9 allowlisted files, and pinning them is wrong twice over:

1. **Several are not names.** `_enclosing_literal` reports span artifacts on
   multi-key object literals — `'o3: "OpenAI API",'`,
   `'o3: { inPerM: RAG_PRICING.reasoningInPerM, ... },'`. Four of
   `stackCatalog.ts`'s seven "names" are `o3:`-prefixed fragments.
   Pinning artifacts is plainly wrong.
2. **It makes the guard brittle.** Rewording a refusal message —
   `'Model is required for ${provider} (e.g. grok-4.3).'` — would fail CI
   for a change that has nothing to do with the guard's purpose. A guard
   that cries wolf gets switched off, which is worse than the gap it guards.

So I pinned `(occurrences, distinct)` instead of a name set, which closes
the *repeated*-name case (`stackCatalog.ts` has 8 occurrences of 7 distinct
names, so a bare occurrence count would not notice a swap between two
repeats) and leaves the substitution case open. **The residual gap is named
in the `_Allowance` docstring rather than hidden**, and is recorded here as
accepted-with-reason rather than silently dropped.

## D6 — recorded, not fixed

`"gpt-" + "4o-mini"` and `` `gpt-${x}-mini` `` are not literals any shape
matcher can see. The alternatives are a constant-folding build step or a
data-flow analysis, and both cost more than the hole is worth in a guard
whose job is catching a copy-pasted real id. Python's *implicit*
concatenation (`"gpt-" "4o-mini"`) **is** caught — the parser folds it into
one constant before the matcher runs. Recorded in the module docstring.

---

## `KNOWN_REMAINING` — re-derived, never copied

Run the guard, read the counts off, write them in. Copying the counts from
the issue body is exactly how an allowlist rots into unfalsifiable, and R1
independently made the same point about the original 5 entries.

| file | occurrences | distinct | why it is here |
|---|---|---|---|
| `digillm/src/digillm/client.py` | 17 | 17 | must be **generated**, not read at runtime — `digillm/AGENTS.md` forbids runtime file reads in an installable library |
| `apps/digichat/src/hooks/use-byok-key.ts` | 17 | 12 | byok key validation |
| `apps/digithings-web/lib/providerSettings.ts` | 15 | 15 | provider settings UI |
| `apps/digithings-web/functions/api/byok/test.ts` | 10 | 10 | a Cloudflare Pages Function serving `POST /api/byok/test`; production code whose name comes from its route |
| `apps/digithings-web/lib/stackCatalog.ts` | 8 | **7** | stack catalogue defaults |
| `apps/digichat/src/app/api/byok/test/route.ts` | 5 | 5 | the D1 Next.js route, same probe as the row above |
| `apps/digithings-web/lib/ragCost.ts` | 4 | 4 | surfaced by the pattern widening — previously invisible |
| `apps/digithings-web/lib/appPresets.ts` | 2 | 2 | one is `providerDefaults`, one is **marketing copy** naming `o3` |
| `scripts/validate_model_routing.py` | 1 | 1 | one refusal message naming the fallback model |

79 literals in 9 files, up from 59 in 5. Four of the entries are new, and
three of those exist only because the pattern was widened.

Entries are meant to be **deleted**, not added. A mismatch in either count,
or an entry whose file has vanished, is reported as stale.

---

## Post-fix verification

```
python3 scripts/check_model_name_literals.py
  OK (2143 production sources, 16 configured markers,
      79 known literal(s) in 9 allowlisted file(s))          EXIT=0

pytest tests/scripts/test_check_model_name_literals.py -q    40 passed
ruff check + ruff format --check    both files clean
make doc-check                       OK (462 markdown files scanned)
yaml.safe_load(ci-docs.yml)          OK
git diff --stat <develop> -- package-lock.json   (empty)
```

Falsifiability, re-probed after every fix. Each probe was written, run and
deleted in one shell call:

```
CAUGHT  scripts/_f1.ts                                  'export const A = "claude-3-5-sonnet";'          F1
CAUGHT  apps/digichat/src/app/api/byok/test/_d1probe.ts  'export const A = "grok-4.3";'                    D1
CAUGHT  scripts/_d3.ts                                  'const u = /^https?:\/\//, m = "gpt-4o-mini";'   D3
CAUGHT  scripts/_d5.generated.ts                        'export const X = "gpt-4o-mini";'                 D5
MISSED  scripts/_o1.py                                  'CODES = {"O1": "Operations halt", "H9": "x"}'   correct
```

The last one is the desired result. Uppercase `O1` is a SEC
suspension-reasoning code in `digiquant/src/digiquant/data/gloomberb/client.py`,
not a model id — which is why `REASONING_ID_PATTERN` is deliberately
case-*sensitive* while `MODEL_ID_PATTERN` is not. Widening the pattern with
`IGNORECASE` everywhere made that a false positive; the reviewer's F4
pushed me to narrow one pattern rather than the other.

---

## What the review verified rather than accepted

- `apps/digichat/reference/` is genuinely not shipping: excluded from
  `tsconfig.json`, no importers, and the `Dockerfile` copies it only into
  the builder stage — never the standalone runtime.
- `packages/ui` skins carry 7 literals across 4 files, all under the
  exempt prefix, and nothing outside `skins/` is silently exempt.
- No unscanned-extension blind spot exists today: the only code files
  outside `SOURCE_SUFFIXES` are two `.d.mts` declaration files with no
  literals.
- The CI step gates correctly: it is inside the existing
  `docs-and-agents-init` job in `ci-docs.yml`, whose `pull_request:` trigger
  has **no path filter** — deliberately, because a filtered check never
  posts a status on the PRs it would have failed, and GitHub then blocks
  the merge forever. No new required status check name is created, so no
  existing PR can be left waiting on a check that never runs.
- Exit code propagates: a planted literal gives `EXIT=1`, removal `EXIT=0`.
