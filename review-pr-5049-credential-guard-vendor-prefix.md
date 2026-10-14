# Review: PR #5049 — credential guard, vendor-prefix leading-token match (DIG-50 leaf B)

**Reviewer:** two fresh-context OpenCode review subagents, `space-bunny-free`, run by the author
session (the author session did not review its own diff; see "Author independence" below).
**Subject:** branch `task/50-punctuation-secret-detection-fix`, PR
[#5049](https://github.com/digithings-ai/digithings/pull/5049) → base `feat/50-credential-guard-shape`.
Commits under review, in order:

| sha | subject | pass |
| --- | --- | --- |
| `50e9e5907` | `test(scripts): pin DIG-50 defect 2 -- punctuation-bearing secrets` | cherry-picked pinned contract, not authored here |
| `9a7e16072` | `fix(scripts): score credential shape by character distribution` | pass 1 (reviewed, then reworked) |
| `7de04b75d` | `fix(scripts): match vendor credential prefixes on the leading token` | pass 2 (reviewed) |
| `20f3d6493` | `fix(scripts): match vendor prefixes on the value's leading token` | pass 3 (reviewed, **APPROVE**) |
| `8dcc4367d` | `test(scripts): pin the vendor differential test to a credential verdict` | applied after pass 3; test-only, see "Post-review fix" |

**Final verdict: APPROVE** (pass 3, subject `20f3d6493`), with one MINOR and one NIT dispositioned
afterwards. Severity counts are per pass and are not additive across passes.

| Pass | Subject | Verdict | blocker | major | minor | nit |
| --- | --- | --- | --- | --- | --- | --- |
| 1 | `9a7e16072` | REQUEST CHANGES | 1 | 0 | 3 | 2 |
| 2 | `7de04b75d` | REQUEST CHANGES | 1 | 1 | 0 | 0 |
| 3 | `20f3d6493` | **APPROVE** | 0 | 0 | 1 | 1 (+4 informational) |

## Scope

Two files. `scripts/check_example_credentials.py` (114 lines; 38 added / 6 removed against
`50e9e5907`, inside the leaf's 45-line ceiling) and the new
`tests/scripts/test_check_example_credentials_vendor_prefixes.py` (additive). The pinned contract
`tests/scripts/test_check_example_credentials.py` is **byte-identical** to `50e9e5907`
(blob `c16bf8c3d70680d865bd967642378115a9c51f4f` at `50e9e5907`, `7de04b75d`, `20f3d6493` and
`8dcc4367d`) and was not edited by any commit on this branch.

## The defect under review

`CRED_VALUE_PATTERNS` kept `^sk-[A-Za-z0-9]{20,}$` end-anchored while `^ghp_`, `^gho_` and
`^glpat-` are prefix-only. A prefixed key carrying a trailing inline comment
(`sk-… # rotated 2026-01`) matched three of the four vendor prefixes and was reported clean for
the fourth — `sk-`, the highest-value one.

## Pass 1 — REQUEST CHANGES (subject `9a7e16072`)

### BLOCKER — `CRED_MIN_ENTROPY = 3.5` was fitted to a four-item probe list

`scripts/check_example_credentials.py:44` at that sha. The pinned probe `correct-horse-9-Battery-S7`
scores 3.5654, only +0.0654 over the floor; remove the padding digits and the same passphrase scores
3.4947 and is missed by 0.0053 bits. Removing `^[A-Za-z0-9]{32,}$` also left the floor 0.500 bits
under hex's ceiling (`log2(16) = 4.000`), so the most common secret encoding became the weakest
supported: over 2000 samples a 3.5 floor misses 18.5% of 32-char hex secrets where the old pattern
missed 0%.

The reviewer's refutation of the stated justification: scanning every tracked `.example`/`.template`
line, **zero** values reach the entropy gate at any floor — the structural gate already removes all of
them. So 3.5 bought zero measured precision while costing detections.

**Resolved in `9a7e1607`** — floor is **3.0** (now `scripts/check_example_credentials.py:49`); 3.5 /
3.4 / 3.2 / 3.0 / 2.8 / 2.5 all produce zero hits against the tracked corpus.

### MINOR / NIT — all resolved

- `:83-84` (prefix loop) preceded `:85-87` (structural exclusion), falsifying the file's own claim
  that "a prefix alone is enough". **Fixed** — the loop now runs above the prose exclusion; the
  specified order is still honoured (the exclusion runs before the *score*).
- "above every probe" was false: probes `[4.0588, 4.0, 3.5654, 3.7804]` vs comments
  `[4.0049, 4.3477]` — 4.005 is *below* the top probe. **Corrected** to lowest-probe vs
  lowest-comment. Conclusion survived; the reason did not.
- A dangling "decision log" reference (`git ls-files | grep -iE 'DIG-?(112|43)'` → none). **Reworded.**
- 21 of 34 added lines were comments, half of them git archaeology. **Trimmed.**
- The `+ 0.0` at `:69` cited a caller that does not exist. **Corrected.**

## Pass 2 — REQUEST CHANGES (subject `7de04b75d`)

### BLOCKER — the four prefixes still disagreed; the commit's central claim was false

`scripts/check_example_credentials.py:34` — `r'^sk-[A-Za-z0-9]{20,}'`. Dropping the `$` removed
the *end* anchor but left the character-class constraint: `{20,}` still has to be satisfied by 20
consecutive alphanumerics, so any `sk-` key with a non-alphanumeric inside the first 20 characters
still fell through with a comment while the other three caught it. Measured: a `-` at **any** body
index 0–19 produced `{'sk-': False, others: True}` — 20 of 20 positions broke symmetry.

Not hypothetical: both highest-value `sk-` families put a `-` inside the first 20 characters
(OpenAI `sk-proj-`, Anthropic `sk-ant-api03-`), so the false negative survived the first attempt on
exactly the keys that matter.

### MAJOR — `test_no_vendor_pattern_is_end_anchored` pinned a syntactic property, not behaviour

`tests/scripts/test_check_example_credentials_vendor_prefixes.py:78-81` at that sha. It asserted a
property of the pattern *strings*, so `r'^xoxb-[a-z]+$'` would have passed it while reintroducing
the defect. Combined with the blocker above, it was green while `sk-` still had the blind spot.

**Both resolved in `20f3d6493`** — pattern widened to `r'^sk-[A-Za-z0-9_-]{20,}'`
(`scripts/check_example_credentials.py:40`), and the behavioural tests are now authoritative:
`test_vendor_prefixed_key_with_trailing_comment_is_a_credential` is parametrized over six real key
shapes including `sk-proj-` and `sk-ant-api03-` (`:80`), with `test_every_prefix_agrees_on_every_key_shape`
(`:91`) as the differential backstop.

## Pass 3 — APPROVE (subject `20f3d6493`)

The reviewer re-measured rather than trusting the commit text, and confirmed each item independently.

- Prior blocker reproduced on `7de04b75d` (`sk-proj-…`+comment → `False`) then shown fixed
  (`True` for `sk-proj-`, `sk-ant-api03-`, `sk-ant-admin01-`, `sk-svcacct-`, double-quoted,
  leading-whitespace and tab-separated-comment variants).
- All four pass-1/pass-2 findings re-checked as FIXED, including the comment rewording.
- **Three mutations red** against the new tests, each caught by a distinct test: restoring the `$`
  → 5 failed; reverting the class to `[A-Za-z0-9]` → 3 failed (exactly the `sk-proj-` /
  `sk-ant-api03-` cases plus the differential test); dropping `{20,}` to `r'^sk-'` → 1 failed (the
  length test). Baseline 15 passed.
- **Corpus fence re-derived**: 27 credential-bearing values across 9 tracked `.example`/`.template`
  files; the old class flags 0, the widened class flags 0, symmetric difference empty. No tracked
  value even begins with `sk-`.
- **No new false positives**: nine plausible `sk-` documentation strings
  (`sk-not-a-real-key-here` … `sk-sample-key-abc123`) are already reported **by the old script** —
  `sk-not-a-real-key-here` scores 3.295 and is caught by the entropy gate. Widening the class adds
  no false-positive surface.
- **Every number in the comments reproduces**: over 100 000 random 32-char hex (seed 20261004),
  `<3.5` → 18.768% (comment 18.8%), `<3.2` → 0.361% (0.36%), `<3.0` → 6/100000 = 0.006%, observed
  minimum 2.9357 (comment 2.936).
- Gate order correct on every path; `startswith('#')` load-bearing, not dead.

### Findings raised and dispositioned

| # | Severity | Location (at `20f3d6493`) | Disposition |
| --- | --- | --- | --- |
| 1 | MINOR | `tests/scripts/test_check_example_credentials_vendor_prefixes.py:103` | **Fixed** in `8dcc4367d`, see below |
| 2 | NIT | same file, `test_no_vendor_pattern_is_end_anchored` | Accepted, not changed — the docstring already states it catches only the literal `$` / `\Z` spellings and is a backstop; the behavioural tests carry the real contract. Recorded here rather than renamed. |
| 3 | MINOR (informational, pre-existing, not a regression) | `scripts/check_example_credentials.py:40` | `sk-` + a standard-base64 body (`+`, `/`) is still clean with a comment. Not a regression — the old `[A-Za-z0-9]` class failed identically. Consistent with the commit's stated rule ("the alphabet the vendor really uses"). No repo evidence that any `sk-` family uses `+`/`/`. **Follow-up issue warranted; not on this leaf.** |
| 4 | MINOR (informational, pre-existing) | `scripts/check_example_credentials.py:41` | Unlisted prefixes hide commented keys entirely: `sk_live_`/`sk_test_` (Stripe), `AIzaSy` (Google), `AKIA` (AWS), `hf_` (HuggingFace) all → `False`. This is prefix **coverage**, orthogonal to pattern **shape**. **Belongs in its own issue.** |
| 5 | NIT | prefix matching is case-sensitive | `SK-…` → `False`. Vendor keys are lowercase-prefixed in practice; pre-existing. |
| 6 | NIT | `scripts/check_example_credentials.py:40` | `sk-` + a body under 20 chars + a comment is not caught end to end; the `{20,}` floor is only enforced by the pattern-level test, because a short key still scores high enough for `looks_cred_val` to report it. Documented trade-off, already disclosed in the test docstring. |

### Post-review fix — `8dcc4367d`

Finding 1 was real: `assert len(set(verdicts.values())) == 1` is satisfied by `{False}` as well as
`{True}`, so the differential test passed while **every** prefix in the list was dead. Proven by
mutating all four patterns to `^NOMATCH-*` — that mutation left the differential test green while 7
others went red. The reviewer supplied the one-line remedy; the author applied it, adding the
assertion that the agreed verdict is a credential.

Re-verified at `8dcc4367d`: `^NOMATCH-*` on all four prefixes now gives **8 failed** (the
differential test included), and restoring the end anchor still gives **5 failed**.

`8dcc4367d` is **test-only** — `git diff --stat 20f3d6493 8dcc4367d` is one file, 5 insertions, all
in `tests/scripts/test_check_example_credentials_vendor_prefixes.py`. The production script is
byte-identical to what pass 3 approved, so that approval carries over without a third pass; the
script churn stays 38/6 against the 45-line ceiling.

## Verification at the final head (`8dcc4367d`)

```
$ python3 -m pytest tests/scripts/test_check_example_credentials.py \
      tests/scripts/test_check_example_credentials_vendor_prefixes.py -q
35 passed in 0.09s

$ ruff check scripts/check_example_credentials.py \
      tests/scripts/test_check_example_credentials_vendor_prefixes.py
All checks passed!

$ python3 scripts/check_example_credentials.py
OK          # exit 0

$ git diff --numstat 50e9e5907 HEAD -- scripts/check_example_credentials.py
38  6  scripts/check_example_credentials.py

$ git status --porcelain      # empty
$ git rev-parse HEAD:tests/scripts/test_check_example_credentials.py
c16bf8c3d70680d865bd967642378115a9c51f4f   # identical to 50e9e5907
```

Gate order at `scripts/check_example_credentials.py:75-91`, unchanged by this branch and pinned by the
contract file: strip whitespace/quotes → `len(v) < 16` → `is_placeholder` → vendor prefix loop →
`startswith('#')` or any `c.isspace()` → `shannon_entropy(v) >= CRED_MIN_ENTROPY`. The exclusion
runs **before** the score, which is the point: the two live `.env.example` inline comments score
4.0049 and 4.3477 bits/char and the weakest pinned probe scores 3.5654, so no threshold separates
them.

`tests/scripts/` as a whole: `1 failed, 1167 passed, 67 skipped`. The single failure is
`tests/scripts/test_zammad_mcp.py::test_allowed_host_patterns_append_port_wildcard`,
`ModuleNotFoundError: No module named 'mcp'` — environmental, in a file this branch does not touch.

## Author independence

Passes 1 and 2 were separate fresh-context subagents. Pass 3 was also a fresh-context subagent;
its full verdict is reproduced in the PR comment thread on #5049. The author session compiled this
file from those verdicts and applied finding 1 afterwards, and did not review its own diff.

## What could not be verified

- Whether any real `sk-` vendor family uses standard base64 (`+`/`/`) — no repo evidence, no network
  lookup attempted (finding 3). The repository does document the two families that *are* handled:
  `docs/providers/anthropic.md:17` (`sk-ant-api03-`), `docs/providers/openai.md:17`
  (`sk-proj-` or `sk-`), `config/byok-providers.json:26` (`"keyPrefix": "sk-ant-"`).
- Only `tests/scripts/` was exercised, not the whole repository suite.
- Whether upstream deliberately narrowed the `sk-` body class in `9a7e16072`, and whether that
  decision is recorded anywhere. It was widened here on measured evidence, not on a documented
  intent.
- Pre-existing, **not** attributable to this branch: `ruff format --check` fails on
  `scripts/check_example_credentials.py` identically at `9a7e16072`, `7de04b75d` and `20f3d6493`. CI
  runs `ruff check` on `scripts/` and `tests/`, and no workflow runs `ruff format` over
  `tests/scripts/` or `scripts/`.
- Also pre-existing and untouched: `main()`'s `except Exception:` fallback at
  `scripts/check_example_credentials.py:97-98` rescans the whole filesystem with
  `Path('.').rglob('*')` when `git ls-files` fails, so outside a worktree the guard silently scans
  untracked files instead of erroring.