# Review — `aab08ebaf` "feat(ui): Geist Mono everywhere, one font config per surface"

| Field | Value |
|---|---|
| **Subject** | commit `aab08ebafc9f5cb86ddbd0c231ed324d8a66de73` (parent `d34e09038c`) |
| **Range** | 43 files, +589 / −199 |
| **Reviewer** | fresh-context subagent `ses_edf1d9ce5ffekTQcBVnKWuXeSj` ("Review test efficacy"), free model |
| **Verification** | every finding reproduced or refuted by the author session with its own command |
| **Reviewer policy** | `AGENTS.md` → "Every review run produces a review file" / "Author session must not review its own work" |
| **Reviewed** | 2026-10-09 |
| **Verdict** | **APPROVE** — no blocking defects. 1 medium guard gap (non-blocking), 2 informational, 2 reviewer claims refuted. |

## Severity counts

| Severity | Count |
|---|---|
| Critical | 0 |
| High | 0 |
| Medium | 1 |
| Low / informational | 2 |
| Refuted reviewer claims | 2 |

## Verdict

The commit does what the ticket asked: five per-surface `fonts.ts` configs each calling `next/font` once, `packages/design/tokens.css` owning the stacks, and a 143-line contract guard that pins the arrangement. The guard is **not decorative** — I broke it five ways and it caught every break except one (evidence below). Two suspicions I started with (`tokens.css:378`, the digiquant-web `--font-sans` override) are both **refuted by measurement**; both are deliberate and documented in-source.

**The shipped CSS is correct.** Every finding below is about the *guard* not fully covering the code, not about a font being wrong on any surface.

## Findings

### [medium] `font-tokens.contract.test.ts:123-132` (test 5) checks the fallback chain per FILE, not per stack

Test 5 asserts each `FALLBACK_CHAIN` entry is **present somewhere in** `tokens.css` and in `digichat-app-theme.css`. It does not check that each entry is present on **every** mono stack in the file.

`packages/design/tokens.css` uses the identical fallback chain on **two** declarations — `:62` `--font-stack-mono` and `:63` `--font-stack-display`:

```css
--font-stack-mono:    var(--font-mono-face, "Geist Mono"), ui-monospace, "SF Mono", Menlo, Consolas, "DejaVu Sans Mono", "Segoe UI Symbol", monospace;
--font-stack-display: var(--font-mono-face, "Geist Mono"), ui-monospace, "SF Mono", Menlo, Consolas, "DejaVu Sans Mono", "Segoe UI Symbol", monospace;
```

So deleting `, "Segoe UI Symbol"` from the **mono** stack alone leaves `--font-stack-display` satisfying the assertion. Measured:

| Mutation | Result |
|---|---|
| **M-C** drop `, "Segoe UI Symbol"` from the **first** occurrence only (`:63`, display — not the mono stack) | `Tests 6 passed (6)` — correct, nothing required it |
| **M-C1** drop it from the **second** occurrence only (`:62`, the **mono** stack) | **`Tests 6 passed (6)` — FALSE PASS** |
| **M-C2** drop it from **both** | `1 failed \| 5 passed (6)` — fails test 5 |
| **M-C3** drop it from `packages/ui/src/styles/digichat-app-theme.css` (the only mono stack in that file) | `1 failed \| 5 passed (6)` — fails test 5 |

**Impact.** A regression that removes the glyph fallback — the one carrying U+25B8 ▸, U+25BE ▼ and U+2318 ⌘, which Geist Mono lacks — from the mono face on every shipped surface **passes the whole suite green**. That is precisely what acceptance criterion #3 exists to prevent, and the test reads as if it covers it. `digichat-app-theme.css` has a single mono stack, so it is covered; only `tokens.css` has the aliasing.

**Not blocking.** It is a gap in a *guard*, not in the shipped CSS — `:62` currently carries the full chain, and the by-eye glyph screenshots on the issue thread show ▸ ▼ ⌘ rendering. Fix by asserting the chain on the `--font-stack-mono` declaration specifically (slice the `--font-stack-mono:` line and test that string) rather than on the whole file.

### [informational] `font-tokens.contract.test.ts` L102-106 — test 2 is narrower than it reads

`packages/ui/src/styles/font-tokens.contract.test.ts:102-106` asserts only that no file *outside* the five configs imports `next/font`. Read alone, `callers.filter(…)` being empty cannot distinguish "correctly centralised" from "no loader anywhere".

This is **not reachable as a defect**. `:93-97` (test 1) independently asserts each of the five configs matches `/from ["']next\/font/`, `/Geist_Mono\(\{/` and `variable: "--font-mono-face"`. Proved by mutation:

- **M-B** — stripped `next/font` from all five configs. Full suite: `1 failed \| 5 passed (6)`; the failure is test 1, `gives every surface one config file that loads Geist Mono as the mono face`. Test 2 alone under M-B (`-t "keeps next/font out"`): `1 passed | 5 skipped`.

Suggestion if it is ever worth a line: assert `expect(callers.length).toBeGreaterThan(0)`. Not required for approval.

### [informational] `digiquant-web/app/globals.css:82-86` re-declares the canon tokens

`apps/digiquant-web/app/globals.css:83` sets `--font-sans: var(--font-stack-sans)` and `:85` `--font-display: var(--font-sans)`, overriding `packages/design/tokens.css:378-381` at **equal specificity** (`:root[data-theme]`). This looked like a cascade bug; it is not. Each app that overrides does so on purpose, after `tokens.css` is imported, and says so:

- `apps/digiquant-web/app/globals.css:79-81` — "Same pairing as digithings.ai: Inter for sans/display, Geist Mono for chrome. Both stacks come from tokens.css … no font family is named here."
- `apps/digithings-web/app/globals.css:157-161` — same rationale.
- `apps/dashboard/app/globals.css:119-120` — "Re-declare the canon font tokens (equal specificity, later source) so utilities resolve to the CSP-safe shipped face." Its dashboard block sits at `:121-124`, after the `tokens.css` import at `globals.css:16`, so the later-source claim is correct.

This is exactly the "no CSS outside `tokens.css` names a font family" rule being honoured — the overrides reference `--font-stack-*` vars, never a family name.

## Verification performed

### Guard suite runs, and is not vacuous
```
cd packages/ui && node ../../node_modules/.bin/vitest run src/styles/font-tokens.contract.test.ts --reporter=verbose
→ Test Files 1 passed (1); Tests 6 passed (6); Duration 345ms
```
All six `it` blocks printed with differing durations (2ms / 170ms / 58ms / 1ms / 0ms / 0ms), so each executed. `vitest --collect-only` does not exist on vitest 4.1.10 (`CACError: Unknown option --collectOnly`) — the per-test durations are the substitute evidence.

### Mutation testing (detached worktree; main tree never touched)

| Mutation | Result |
|---|---|
| **M-A** add `import { Geist_Mono } from "next/font/google"` in a NEW file `packages/ui/src/__probe_font_loader.ts` | `1 failed \| 5 passed (6)` — fails test 2, `keeps next/font out of every file but the surface configs` |
| **M-B** strip `next/font` imports from the five configs | `1 failed \| 5 passed (6)` — fails test 1 |
| **M-C1** drop `, "Segoe UI Symbol"` from `tokens.css` **mono** stack only (`:62`) | **`6 passed (6)` — NOT CAUGHT.** See the medium finding |
| **M-C2** drop it from **both** `tokens.css` stacks (2 → 0 occurrences) | `1 failed \| 5 passed (6)` — fails test 5 |
| **M-C3** drop it from `digichat-app-theme.css` (its only mono stack) | `1 failed \| 5 passed (6)` — fails test 5 |
| **M-D** delete `--font-geist-mono: var(--font-mono-face, "Geist Mono");` from `chat-aui.css` | `1 failed \| 5 passed (6)` — fails test 6 |
| **M-E** gut the mono stack to `var(--font-mono-face, "Geist Mono");` (no fallbacks) | `1 failed \| 5 passed (6)` — fails test 4 |

M-A proves test 2 is not vacuous in the direction it is written for (a loader escaping to a non-config file). M-B proves the "no loader anywhere" case is caught by test 1. **M-C1 is the one break the suite missed**, and it is the medium finding above.

Mutation runs used a `git worktree add --detach` at `HEAD` (not `git archive`), so the guard's recursive walker had a real working tree and index. Both trees verified clean afterwards (`git status --porcelain` empty in scratch and main).

### CI covers every path in the diff
`.github/workflows/ci.yml` — `packages/ui/**` appears in three lanes (`digichat` L104-112, `dashboard` L115-125, `web` L130+); `digiquant/**` at L80/L144/L181 gates `.github/workflows/test-digiquant.yml` (dispatch ~L285-287), so the Python tearsheet trio is covered. No CI gap.

### Suspicions refuted by measurement
- `packages/design/tokens.css:378` `--font-sans: var(--font-stack-mono)` is **deliberate**, documented at `:374-377`: "mono is the default voice for claim, body, and chrome. Serif/sans escape hatches set `--font-display` / `--font-sans` locally."
- Acceptance criterion #1 (`git grep -n -i -E "jetbrains|plex.?mono|…"` over `apps packages digiquant`, minus galleries) returns exactly 2 lines, both inside the guard itself — `:108` test name, `:110` the regex literal. **The criterion cannot pass literally**, because a guard test must name the retired fonts. `:58` excludes the guard from its own scan. This is a defect in the acceptance wording, not in the code. (Correction on the record: an earlier comment on DIG-2375, `31e62915`, claimed this grep "now returns nothing" — it does not.)

## Refuted reviewer claims

The subagent raised two; both are wrong on their own terms. Recorded because a review file that only lists survivors hides that its reviewer was partly wrong.

**1. [claimed high] "Test 2 does not catch a full reversion with all `next/font` removed."**
True of test 2 *in isolation*, false as a finding: `font-tokens.contract.test.ts:93-97` (test 1) asserts the same property per config, and M-B shows the suite goes red. Downgraded to informational.

**2. [claimed medium] "Test 4's regex does not match live `tokens.css` (`regex.test === false`) yet the test passes."**
False. Two independent measurements: python `re.search` returns a match spanning `--font-stack-mono: var(--font-mono-face, "Geist Mono"), ui-monospace, …`; node, with the regex lifted character-for-character from the test file, returns `regex.test === true` with matched text `--font-stack-mono: var(--font-mono-face, "Geist Mono"), ui-monospace`. `packages/design/tokens.css:62` verbatim:

```css
--font-stack-mono: var(--font-mono-face, "Geist Mono"), ui-monospace, "SF Mono", Menlo, Consolas, "DejaVu Sans Mono", "Segoe UI Symbol", monospace;
```

## Scope note

This review covers the font-token contract, the guard, and CI reach. It does **not** cover the by-eye glyph verification (▸ ▼ ⌘ render, tabular numerals) recorded on the issue thread by screenshot, nor `next build` for each of the five apps. Those were exercised in the implementation run, not re-run here.