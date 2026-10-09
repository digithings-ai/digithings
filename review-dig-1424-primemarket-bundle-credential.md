# Review — DIG-1424 vendor-published browser-bundle credential

Subject: `docs/secrets): record the PrimeMarket browser-bundle credential as never-used (DIG-1424)`
Branch: `DIG-1424-primemarket-bundle-bearer-token-never-use-never-paste`
Base: `origin/develop`
Reviewer: fresh-context subagent (`general`), no prior knowledge of the change
Date: 2026-10-06

## Verdict (as first returned)

**CHANGES REQUESTED** — no blockers, four should-fix and four nits. Two of the
should-fix items were new wrong facts introduced by this PR; the reviewer was
right to refuse them, because the file's own contract is *"every claim above
carries a `file:line`, a commit, or a named command"*, and this PR adds to that
file.

## Disposition

All findings addressed in the same commit, which was then rebuilt on the current
`develop` tip to clear a merge conflict in this file (both sides kept: the `R15
status` block added by #5109 and the new `R16` entry). Re-verified after the
fixes; see "Re-verification" below. Verdict after fixes: **APPROVE**.

## What the reviewer was asked to attack

Five hard constraints, every citation in the new text, and specifically the three
pre-existing citation errors the PR claimed to fix.

## Constraint checks (run by the reviewer)

| # | Constraint | Result | Evidence |
|---|---|---|---|
| 1 | No value, prefix, length, hash or redacted fragment | **PASS** | Extracted every `[A-Za-z0-9_./-]{16,}` token from the 106 added lines: variable names, filenames, one hostname (`frontendapi.primemarket-terminal.com`) and two Markdown anchors only. A second pass for base64/hex blobs (`[A-Za-z0-9+/]{24,}={0,2}\|[0-9a-f]{24,}`) returned nothing. |
| 2 | No recipe for using the credential | **PASS** | `grep -niE 'curl\|requests\.\|fetch(\|axios\|http\.get\|Authorization:\|Bearer \|node -e\|python3? -c\|wget'` over the added lines → exit 1. The only "bearer" is prose classifying the credential type. |
| 3 | The vendor bundle was not fetched | **NO EVIDENCE IT WAS** | One changed file, clean worktree, no `_next`/chunk artifact tracked or untracked, and the section attributes its bundle-specific facts to the DIG-1261 report rather than to inspection. A negative process claim cannot be proved from a one-file diff; the absence of any literal only a fetcher would hold is the strongest available evidence. |
| 4 | Stays inside the ADR-0030 hold | **INSIDE**, one judgment call | No step-by-step method, no request example, no header construction, no endpoint *path* — only the endpoint's *name* and the host. Strictly less PrimeMarket-actionable than rows already in this same file, which publish `desk.prime-terminal.com`, the `localStorage['pmt_auth_token']` key and the `gh secret set` refresh command. The reviewer read naming as inside a hold scoped to *examples*, and flagged it for Chris to ratify. |
| 5 | `python3 scripts/check_doc_links.py` passes | **PASS, exit 0** | `check_doc_links: OK (470 markdown files scanned)`. The reviewer's read of the script is confirmed from source: `_link_ok` returns `True` unconditionally for a target starting with `#` (lines 156-157) and strips the fragment with `path_part = t.split("#", 1)[0].split("?", 1)[0]` (line 161). **The gate validates link paths only — a broken anchor is not caught by it**, so anchor verification was done by hand. |

Unprompted extra gate run by the reviewer, which is recorded here because it is
the only automated check in this repo that parses this file:
`pytest tests/scripts/test_retired_provider_keys.py tests/scripts/test_fred_credential_retired.py tests/scripts/test_secret_staleness_check.py -q` → **90 passed, 1 skipped** (the skip needs an authenticated `gh`). Three of those tests parse or reference `SECRETS_INVENTORY.md`; the new table breaks none.

## The three citation corrections — CONFIRMED

This is the part the reviewer was most prepared to fail, because the PR silently
rewrites other people's documentation.

**(a) `docs/PRIMEMARKET_DESK_API.md:139-152` → `:193-198` — CONFIRMED.**
139-152 is the cookie-derivation paragraph, the `refresh_session_token.sh` runbook
and the "never paste the session value" rule. The string "fall back to
credentials" does not occur in that range; `grep -n` finds it at 195 only. The
old citation could not have been supporting the claim made of it.

**(b) `nodes/scrape.py:692` → `:609` — CONFIRMED.**
692 is inside `_fetch_pdf_bytes` (`PRIMEMARKET_FILE_BY_ID_URL`,
`json={"FileID": str(file_id)}`) and has nothing to do with credential login. 609
is `username, password = get_primemarket_credentials()`. The added sharpening is
independently correct: 605-607 reads the env var, tests it, and returns, so the
credential route runs only when the token name is unset — never "after both
supplied sessions fail", which is what the old text described.

**(c) `PRIMEMARKET_SESSION_COOKIE` reader `nodes/scrape.py:559,662` → "no reader" — CONFIRMED.**
559 is docstring prose about the DIG-745 expiry alarm; 662 is the closing `}` of
a docstring. `git grep -n PRIMEMARKET_SESSION_COOKIE github/develop` returns 12
hits and zero reads.

## Findings and what was done about each

| # | Sev | Finding | Resolution |
|---|---|---|---|
| 1 | should-fix | `:201` credited **DIG-745** with removing the cookie link from the code. DIG-745 *added* the cookie derivation. Reviewer attributed the removal to DIG-249/DIG-266. | **Fixed, with the reviewer's attribution also corrected.** Measured directly: the `scrape.py` hits are 10 at `8368932` (DIG-249), still 10 at `ffbf354^`, and 0 at `ffbf354` (DIG-266). DIG-249 did not touch `scrape.py`; DIG-266 did, with 146 lines changed. So DIG-266 removed the read and renamed the script, matching what twelve-x `docs/PRIMEMARKET_DESK_API.md:180-181` already states. Text now says DIG-266 for the code removal and DIG-249 for CI and docs. |
| 2 | should-fix | `:165` asserted, from `:171-172`, that the desk had moved to a Bearer scheme. The cited doc now **withdraws** that attribution as unsupported (`:220-227`) and states the cause is unmeasured. `:161` → `:211`. | **Fixed.** The row now reports the withdrawal and its two checkable reasons instead of repeating a retracted claim. Verified `:220-227` and `:211` directly. |
| 3 | should-fix | `:163` (g1 token row) — three wrong citations: `nodes/scrape.py:661` is a date-format docstring line; `PRIMEMARKET_DESK_API.md:157-165` is the report-this table, the measurement is at `:213-215`; `twelve-x/scripts/refresh_session_cookie.sh` **does not exist** on `github/develop`, so a reader following the recorded refresh path got a 404. | **Fixed.** → `nodes/scrape.py:605`, `primemarket_session_heartbeat.py:57` (`:59` is the log string), added `scripts/ingest_market_context.py:32`, `:213-215`, and `refresh_session_token.sh:217` without the `--body` flag the old text showed (the real command is `printf '%s' "$VALUE" \| gh secret set PRIMEMARKET_SESSION_TOKEN --repo "$REPO"`). |
| 4 | should-fix | `:332` pointed at a report-this / never-report-this table in `docs/ops/credential-ownership.md`. That table is **not in that file on develop** — its sections are GLOOMBERB_SESSION_COOKIE, DataTap Azure, Other Hand-Held Credentials, Adding a New Credential, Enforcement. | **Fixed.** The table is twelve-x `docs/PRIMEMARKET_DESK_API.md:158-162`, added there after the DIG-1226 incident; the in-repo link now cites the Enforcement section that does exist. The reviewer independently confirmed that dropping the `#never-paste-a-credential-value` anchor was right: `git grep "never-paste-a-credential-value" origin/develop` → exit 1. |
| 5 | nit | `:304` "Copies we hold: none" was evidenced by a grep for the *name*, which cannot prove the *value* is absent under another name. | **Fixed.** Now says the evidence establishes absence of the name, states plainly that no local command can prove the rest, and notes that a credential we never wrote down could only reach us by being read out of the bundle — which this record deliberately did not do. |
| 6 | nit | `:304` "Not in any Worker secret, not in any GitHub secret" is not establishable by any local command (both are write-only), yet is worded identically to the grep-backed half. | **Fixed.** Now attributed to the repo-secret and Worker-secret enumerations recorded earlier in the same file. |
| 7 | nit | `:165` enumerated only some hits, omitting two workflow comments and the superpowers plan/spec. | **Fixed.** All 12 hits accounted for, by count and by category. |
| 8 | nit | `:165` test citation stopped at `:169-174`, before the assertions. | **Fixed.** → `:131,166-184`, assertions at `:180-184`. |
| 9 | nit | The new `##` sat directly under `## Review coverage for this section`, which is scoped to the twelve-x laptop-`.env` section it reviews. | **Fixed by renaming, not moving.** Moving the section above the heading would have separated the `.env` section from its own review-coverage note. The heading is now `## Review coverage for the twelve-x laptop `.env` section`. `grep` across the repo: nothing referenced `#review-coverage-for-this-section`, so the anchor change breaks no link. Placement on the substantive question was already correct — line 294 is a new top-level `##`, well outside the laptop-`.env` section at 142-276, because a vendor-published credential with no local copy must not be filed under "secrets we actually hold". |
| 10 | nit | **Rotation** was the weakest-covered of the four plausible wrong next moves: "write a probe", "wire it in" and "paste it" each had a bullet, but "this is unrotated, so I should rotate it" hit only a table cell. | **Fixed.** Added an explicit "never try to rotate it" prohibition covering both rotating and opening a ticket that asks for it. |
| 11 | **false positive** | The reviewer warned the 7-column table row carries 10 raw `\|` against 8 in the header, which would split it into 9 cells in a GFM-strict renderer. | **No change needed.** The two extra pipes are the `\|` inside the code span `git grep -i "NEXT_PUBLIC_API_TOKEN\|userLogin\|frontendapi"`. GFM requires escaping pipes inside inline spans in tables, and `\|` renders as `|`, so the parser sees 8 delimiters. The count is correct as written. Recorded here because the warning is plausible and the next reviewer will see the same count. |

## Citation audit of the new text — all exact

`docs/PRIMEMARKET_DESK_API.md:193-198` · `nodes/scrape.py:605-607` · `:609` ·
`:568` · `scripts/refresh_session_token.sh:12` · `config.py:27-32` ·
`tests/test_desk_digifetch_transport.py:169-174` (now `:131,166-184`) ·
the absence grep in twelve-x `github/develop` (exit 1) ·
`#the-vendor-published-browser-bundle-credential-dig-1424` ·
`#gaps-and-unknowns` · `../plans/adr-0030/HOLD-Primarket.md` (quotes Section 12
including "APIs (unless officially provided by us)" and "material breach"; DIG-478
card `295f3d75` matches).

The anchor slug was computed character by character: parentheses dropped, the
space before `(DIG-1424)` becoming the single hyphen before `dig-1424`.

Grep sanity check, because a grep that returns nothing because the pattern is
broken is the failure mode to catch: in the same twelve-x tree,
`PRIMEMARKET_SESSION_TOKEN` hits 16 files and `pmt_auth_token` 12.

## Editing quality — the trap-guard on all four wrong moves

| Wrong move | How it is stopped |
|---|---|
| write a liveness probe | three times over: "A liveness probe is a use", "Never write a script that fetches it or tests it", and R16 "Do not write a liveness probe for it — a probe is a use" |
| wire it into `twelve-x` | exhaustively and by name — not `.env`, not `config.py`, not a workflow, and not as a fourth route behind (g1), with the reason a fourth route would break the deliberate no-fallback-chain design on purpose |
| paste it | blocked, with the prefix-plus-length reasoning spelled out, which is exactly the DIG-1226 lesson |
| rotate it | **added in this review pass** — see finding 10 |

Structure is consistent with the file's voice. The bespoke 7-column table
deliberately parallels the (g1)/(g2) tables rather than the canonical
"How to read this table" vocabulary, which is scoped to the §Inventory tables —
and (g1)/(g2) already break from it.

## Could not verify, and why

1. **That the bundle was not fetched.** See constraint 3. The strongest available
   evidence is the absence of any literal only a fetcher would hold, and it
   holds.
2. **The governance layer.** The CTO ruling on DIG-1261, Counsel's DIG-1246
   ruling that automated login is not permitted, the DIG-1226 incident and
   DIG-478 card `295f3d75` are outside both repos. Only the digithings-side
   records were checked, for internal consistency — and
   `HOLD-Primarket.md` does cite DIG-478 / card `295f3d75` / DIG-503 / DIG-461
   exactly as the new text says, while twelve-x
   `docs/PRIMEMARKET_DESK_API.md:170-173` independently corroborates the DIG-1226
   incident and its date.
3. **The factual core of the vendor exposure** — that the bundle really hardcodes
   this fallback, that the desk really is a Next.js app, that the literal really
   reaches every visitor. Taken from DIG-1261 and **deliberately not verified**:
   verifying it would be the use the section prohibits. This is the one
   load-bearing claim in the change that no command in either repo can support,
   and it is a single point of failure for the whole record. Flagged for Chris.
4. **Whether CI tooling could have touched the value.** `gitleaks` is configured
   (`.gitleaks.toml`, with `SECRETS_INVENTORY.md` discussed in its comments) but
   was not run — scanning a diff already tokenised by hand adds nothing.
5. **`credential-ownership.md` on branches other than develop.** Only
   `origin/develop` was checked, for the anchor. Whether some other branch already
   carries a "Never paste a credential value" section that this change should link
   to instead was not checked.

## Re-verification after the fixes

- `python3 scripts/check_doc_links.py` → `check_doc_links: OK (470 markdown files
  scanned)`, exit 0.
- `git -C twelve-x grep -i -n "NEXT_PUBLIC_API_TOKEN\|userLogin\|frontendapi"
  github/develop` → exit 1, no output.
- `git -C twelve-x grep -n PRIMEMARKET_SESSION_COOKIE github/develop` → 12 hits,
  broken down by file and confirmed to be 6 documentation, 3 comments and 3 test
  lines.
- Cookie-read history measured at four revisions: `8368932` 10 hits, `ffbf354^`
  10 hits, `ffbf354` 0 hits, `a15dc35` 0 hits — which is what fixes finding 1 on
  evidence rather than on the reviewer's inference.
- Leak scan of every added line re-run against the full `origin/develop` diff.
  Long tokens found: variable names, filenames, script paths, the one hostname,
  and two Markdown anchors. Base64/hex blob scan: nothing.
