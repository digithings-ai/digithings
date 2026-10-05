# Review: DIG-526 — the twelve-x laptop `.env` inventory section

- Reviewer: `general` subagent, fresh context, read-only, against `digithings-ai/twelve-x` `github/develop` (`4f308ef`). Requested by `b14d7a18` (Security), who wrote the section and therefore did not review it.
- Subject: two commits pushed straight to `develop`, no source PR — `d0a69714` ("docs(secrets): give the twelve-x laptop .env an owner per key (DIG-526)") and `b6f7d75d` ("docs(secrets): correct five errors the DIG-526 review found in the twelve-x .env section").
- File under review: `docs/ops/SECRETS_INVENTORY.md`, new section `## The twelve-x developer laptop .env — every key has an owner (DIG-526)` (`:140`–`:278`), subsections (g1) `:158`, (g2) `:178`, (g3) `:218`, (g4) `:240`, `## Review coverage for this section` `:264`.
- Verdict: **CHANGES REQUESTED** on `d0a69714` — 2 high, 4 medium, 3 low/nit, all factual errors in a document whose stated value is that every claim is checkable. **APPROVE** on `b6f7d75d`, which fixes all 10.
- Severity counts: 2 high · 4 medium · 3 low · 1 nit (10 findings, all refuted in the original; 5 substantive).

## Scope

`d0a69714` adds 99 lines to one file. No code, no workflow, no secret value. The claim under test is narrow and perishable: *each of the 17 key names in `/Users/chrisstefan/Code/twelve-x/.env` gets an owner, a reader, and an action.* Every cell in that claim is a citation into another repository, which is exactly the kind of content that rots the moment a line moves.

## Checks performed

1. `git show github/develop:<file>` + `sed -n` for every cited line, in **twelve-x**, not in the twelve-x working tree — the working tree sits at `10d4d82`, which is not `4f308ef`, so several citations would have "verified" against code nobody ships.
2. `git grep -n '<NAME>' github/develop -- <path>` for every reader claim, to distinguish "read by code" from "mentioned in a comment, docstring, or error string".
3. Cross-repo grep in `digithings` for any name the section calls dead, because the same names are live repo variables here.
4. `python3 scripts/check_doc_links.py` → `check_doc_links: OK (462 markdown files scanned)`, exit 0. New heading anchor `#the-twelve-x-developer-laptop-env--every-key-has-an-owner-dig-526` collides with nothing.
5. Secret-safety sweep of the added text: no values, only names. `/Users/chrisstefan/Code/twelve-x/.env` is mode `-rw-------` and gitignored (`.gitignore:1`). `config.py:21` `load_dotenv(_PROJECT_DIR / ".env", override=False)` is what makes that file live at runtime — the central premise of the section, and correct.
6. Consistency against the rows the section must not contradict: §(b) `:62` `:65`, §(c) `:90` `:91` `:97`, §(f) `:135`. No contradiction.

## Findings on `d0a69714`

1. **HIGH — `docs/ops/SECRETS_INVENTORY.md` (g3 row, "Read by" column): `SUPABASE_SERVICE_KEY` cannot satisfy the local reader, so a laptop run is broken today.** False. `config.py:38` is an `or` chain — `TWELVEX_SUPABASE_SERVICE_KEY` first, `SUPABASE_SERVICE_KEY` second — and the raise at `:42` fires only when **both** are empty. The twelve-x comment on `:36-37`, `.env.example:17`, `docs/ARCHITECTURE.md:501` and `README.md` all describe the legacy name as a transition fallback, and they are right. The row contradicts itself three lines apart ("kept so existing local envs keep working" → "cannot satisfy the local reader"), and the commit message repeats it. What *is* true and much smaller: the error text at `:42` names only the canonical variable, so an operator who did supply a key under the old name is told the wrong variable is missing. Action changed from "delete" to "rename to canonical".
2. **HIGH — the section claimed both alert bodies in twelve-x now say which copy they cover and both name this file as the uncovered one.** False as of `github/develop` `4f308ef`: there is exactly **one** alert body, `.github/workflows/primemarket_session_heartbeat.yml:62-75`, body text `'The interim desk session (PRIMEMARKET_SESSION_TOKEN) is no longer valid.'` plus refresh steps. It names neither copy. `git grep -n 'pmt_auth_token' github/develop -- .github` → one hit (`:66`); `git grep -l 'session expired' github/develop -- .github` → only that file. This was the section's most operationally load-bearing sentence and it was the false one: a reader would have believed acceptance criterion 2 (an alert that names its copy) was already satisfied in the shipping repo. It is not — it is satisfied on twelve-x PR **#258**, still open.
3. **MEDIUM — wrong line: the `2026-09-14T10:33Z` last-write timestamp cited at `docs/PRIMEMARKET_DESK_API.md:151`.** `:151` reads `pushed exactly 24h forward (confirmed twice against the live desk).` The timestamp is at **`:161`**.
4. **MEDIUM — wrong line: the Bearer-scheme correction cited at `:160-162`.** Those lines open the correction; the Bearer statement is at **`:171-172`**.
5. **MEDIUM — wrong reader: the (g1) row said `PRIMEMARKET_SESSION_TOKEN` is read by `config.py` and `nodes/scrape.py:662,686`.** `git grep -n PRIMEMARKET_SESSION_TOKEN github/develop -- config.py` → no hits. `:662` reads the *cookie*, `:686` is an error-message string mentioning both. The only real readers are `nodes/scrape.py:661` and `scripts/primemarket_session_heartbeat.py:59`. Every other row in this table carries a resolvable `file:line`; this one did not.
6. **MEDIUM — wrong scope: the (g2) row said `PRIMEMARKET_USERNAME`/`PASSWORD` live in "this `.env` only".** `market_context_ingest.yml:72-73` passes both from repo secrets, labelled a dormant credential-login route (DIG-249), and `daily_run_reusable.yml:115-116` does the same. DIG-249 stopped the preflight *requiring* the pair (`daily_run_reusable.yml:55-58`); it did not stop CI passing it. The section's headline for this pair — "the most damaging pair on the laptop", "the only ones that are a human's account" — rested on "only here". Whether the repo-secret copies are populated is unverifiable (secrets are write-only), which is now recorded as a gap rather than guessed.
7. **MEDIUM — wrong reader: `CHEAPERINFERENCE_API_KEY` described as "refuses without it" at `nodes/llm.py:114`.** `:114` is a fragment of an error *message*. `validate_llm_credentials` reads `OPENAI_API_KEY` / `LITELLM_PROXY_API_KEY` at `:102-104` and raises `MissingLLMCredentialsError` at `:113-116`. No `os.environ.get("CHEAPERINFERENCE_API_KEY")` exists anywhere in twelve-x; its own plan doc says the name "alone is a no-op in twelve-x". CI maps it into `OPENAI_API_KEY` (`daily_run_reusable.yml:61,109`). It is a fourth dead name, not a dev convenience.
8. **LOW — arithmetic: "fourteen pairs" / "the other twelve pairs" against a 17-name file.** 2 session + 2 desk-login + 13 others. (g3) now says "the remaining thirteen names", and its intro no longer claims all of them are read (two have no reader).
9. **LOW — repo qualifier missing: `CHEAPERINFERENCE_API_BASE` "no reader".** True in twelve-x (`git grep` → exit 1) but false in **this** repo, where it is a live repo variable with two workflow reads (§Storage surfaces `:27` `:29`, row (f) `:135`). Cross-repo name collision is this document's classic failure mode; the row now names the repo.
10. **NIT — unevidenced instruction: "rotate at Notion, then delete here" for `NOTION_API_TOKEN`.** No reader exists, so no `file:line` is possible and no twelve-x doc mentions Notion. Downgraded to "delete here; only Notion can tell you if it is live".

## Verified correct on `d0a69714` (no change)

`config.py:21`; `.gitignore:1`; `config.py:27` `:28` `:29` `:67` `:107` `:193` `:386-388` `:391`; `nodes/scrape.py:559` `:662` `:692`; `nodes/llm.py:73` `:86` `:102-104` `:113-116`; the token → cookie → credentials ordering (`:661` → `:662` → `:692`, docstring `:641-648`); `docs/PRIMEMARKET_DESK_API.md:139-152` and the deliberate-not-a-fallback-chain passage at `:144-147`; `scripts/refresh_session_cookie.sh:81` is the only `gh secret set` on develop and writes the token only, so "the cookie has no writer" holds; the cookie is deliberately not passed in CI (`primemarket_session_heartbeat.yml:45`, `market_context_ingest.yml:75`); `8368932` is DIG-249, dated 2026-10-05, an ancestor of develop; `7658a22` = 2026-06-25 `(#57)`; no secret values anywhere; `.env` mode `-rw-------`.

## The two habits behind the errors

1. **Cite `github/develop`, never the working tree.** The twelve-x checkout was at `10d4d82`. Three of the five substantive errors were line citations that "verified" against a tree nobody ships.
2. **Grep the other repo before calling a shared name dead.** `CHEAPERINFERENCE_API_KEY` and `CHEAPERINFERENCE_API_BASE` are dead *in twelve-x* and live *in digithings*. A claim scoped to one repo, worded as if universal, is false in this document's terms.

Both are now written into the section itself under `## Review coverage for this section` (`docs/ops/SECRETS_INVENTORY.md:264`), so the next author inherits the trap rather than the fix.

## Remediation

`b6f7d75d` corrects all ten, adds the review-coverage subsection, and re-verifies `check_doc_links.py`. Post-review verification on the final tree: `python3 scripts/check_doc_links.py` → OK (462 files); `gitleaks detect --no-git --source docs/ops --config .gitleaks.toml --redact` → no leaks found.
