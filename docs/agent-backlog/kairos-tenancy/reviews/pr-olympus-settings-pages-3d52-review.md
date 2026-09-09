<!-- in-session-review -->
# Review hatch — `cursor/olympus-settings-pages-3d52` → `main`

**Scope:** Narrow Olympus Settings UI promote (T3 tabs + Pipeline/Keys + settings-api client + entitlement surfaces) so Cloudflare Pages serves the post-T3 Settings shell on digiquant.io. **Not** draft #3183. **No** cutover 900. Settings EF `/keys*` already on core (v24) — this PR is Pages/frontend only.

## Verdict
**Approve for merge to `main`** so Pages can rebuild Settings with Profile | Pipeline | Keys | Brokers | Notifications | Billing | About.

## Checked
- [x] Diff limited to `frontend/olympus` Settings surfaces + entitlements/locked UI + `settings-api` + SETTINGS-IA + build-script asserts — no migrations, no cutover 900, no live-trading, no EF bulk.
- [x] D1 / T5 tier matrix unchanged: Profile/Pipeline/Keys/Brokers writes stay Custom+; baseline-broker product tension documented in SETTINGS-IA (not silently widened).
- [x] `NEXT_PUBLIC_OLYMPUS_AUTH` CF_PAGES default from Auth Pages #3231 preserved; build still asserts login + auth/callback.
- [x] Build asserts `dist/olympus/settings/index.html` plus Pipeline/Keys tab markers (guards against shipping the old Status/Appearance shell).
- [x] No secrets; fingerprint-only Keys presentation preserved from develop.

## Risks / follow-ups (non-blocking)
- After merge, Pages must rebuild; smoke `https://digiquant.io/olympus/settings` for Pipeline/Keys tabs (auth gate may require login).
- Settings writes still need Custom+ workspace + live EF; Free/baseline see locked UI + `TIER_FORBIDDEN`.
- Draft #3183 remains the wrong vehicle for this gap.

## Do not
- Merge #3183 for this gap.
- Apply cutover 900.
- Amend D1 to let baseline connect brokers without an explicit product decision.
