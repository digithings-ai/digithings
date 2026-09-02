<!-- in-session-review -->
# In-session review — cursor/kairos-settings-surface-3d52

**Verdict:** approve with notes (Settings completeness progress; not epic-complete).

## Scope
Olympus Settings IA + Pipeline/Keys UI + settings EF `/keys*` + profile budget/watchlist round-trip.
Branch: `cursor/kairos-settings-surface-3d52` → `develop`.

## Checks performed
- Deno: `settings/settings.test.ts` + vault vectors — green (incl. BYOK AAD `workspace:provider:llm`, `TIER_FORBIDDEN` on baseline keys).
- Vitest: settings-api + settings components — green; fingerprint-only assertions on Keys tab.
- Confirmed D1 unchanged: broker/keys/overlay writes stay Custom+.
- No secrets committed; no migration 900; #3183 untouched.

## Findings
1. **Product tension (documented):** human “baseline can connect broker” vs locked D1 — SETTINGS-IA keeps Custom+; widen only via deliberate D1/T5 amendment.
2. **Models v0:** provider BYOK only; no free-form model id (needs ProfileConfig/digillm bump) — intentional.
3. **Deploy:** EF `/keys*` needs migration 104 live + vault master key (same as broker seal).

## Residual gaps
Stripe checkout, Alpaca OAuth product connect, preferred_model schema, Auth Pages on `main`.
