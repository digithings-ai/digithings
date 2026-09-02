<!-- in-session-review -->
# Review hatch — `cursor/olympus-auth-pages-e036` → `main`

**Scope:** Narrow T1 Auth Pages deploy (login + callback routes + build-script AUTH default). **Not** draft #3183. **No** cutover 900.

## Verdict
**Approve for merge to `main`** after human confirms Cloudflare Access still covers `/olympus/*` until intentional Access removal.

## Checked
- [x] Diff limited to `frontend/olympus` Auth surfaces + `scripts/build-digiquant.sh` + AUTH.md — no broker live paths, no migrations/cutover.
- [x] Cutover `900_*` not moved to top-level migrations.
- [x] `NEXT_PUBLIC_OLYMPUS_AUTH` default only when `CF_PAGES=1` and unset; explicit `0` keeps classic shell.
- [x] Build asserts `dist/olympus/login/index.html` and `auth/callback/index.html`.
- [x] Auth Vitest 17/17; local static `/olympus/login/` HTTP 200 with LoginScreen (Google/GitHub).
- [x] Prod currently 404 because routes absent on `main` — this PR is the fix.

## Risks / follow-ups (non-blocking)
- After merge, Pages must rebuild; smoke `https://digiquant.io/olympus/login`.
- Auth UI on without anon-drop: UI gate only; anon RLS still allows API reads if someone bypasses the SPA — Access should stay until cutover §6.
- Staging E2E still blocked on Stripe/Mailgun/Alpaca/Google secrets (separate).

## Do not
- Merge #3183 for this gap.
- Apply cutover 900.
- Touch live-trading.
