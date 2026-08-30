# Settings IA + tier matrix (addendum)

> **Date:** 2026-08-30  
> **Status:** Product addendum for Olympus Settings — fills silence in the Kairos
> tenancy spec on pipeline knobs, models, and BYOK entry. **Amended same day** for
> free-teaser + creator/ops + FX Hub product gates (supersedes the earlier
> “baseline may connect broker” tension).  
> **Binds to:** T3 (tabs), T4 (BYOK storage + overlay budget), T5 (entitlement matrix),
> migration `108_entitlement_grants_and_products.sql`, `ProfileConfig`.

## Why this exists

T3 shipped Profile | Brokers | Notifications | Billing | About. T3 out-of-scope
explicitly deferred **BYOK LLM key entry** to “a fifth tab later.” The implementation
spec is silent on a Settings surface for **pipeline knobs** (watchlist / themes /
research budget) and **model choice**. Human feedback asked for all three. This
addendum defines the minimal coherent IA; v0 implements it without Stripe.

## Information architecture (tabs)

| Tab | Purpose | Persistence |
|-----|---------|-------------|
| **Profile** | Investment posture + asset exclusions (versioned overlay) | `olympus_profile_config` tip |
| **Pipeline** | Overlay research knobs: watchlist, themes, `research_budget_usd` | Same tip payload fields |
| **Keys** | BYOK LLM provider keys (fingerprint-only after save) | `workspace_provider_credentials` |
| **Brokers** | Alpaca paper OAuth / API key; IBKR beta key; revoke | `broker_connections` |
| **Notifications** | Digest + holding/execution alerts | `notification_prefs` |
| **Billing** | Checkout / portal links | Stripe EFs when configured |
| **About** | Status, appearance, build | Local / public env only |

House pipeline remains immutable and always-on. Overlay tabs never edit `profile_key=house`.

## Models semantics (v0)

There is **no free-form model-id picker** in Settings v0 (would need a ProfileConfig /
digillm contract bump). “Change models” means:

1. Choose which **LLM provider** to seal (openai / anthropic / groq / openrouter / xai / gemini).
2. Overlay jobs unseal that key and route via digillm for that provider (T4 / D9).
3. House baseline research continues to use operator/house keys — never the user’s BYOK.

A future `preferred_model` field is out of scope until schemas + overlay dispatch agree.

## Tier matrix (Settings actions) — authoritative product rules

Server authority = **effective** tier:
`max(workspaces.plan_tier, entitlement_grants.plan_floor)` via `my_access()` /
settings EF (migration 108). JWT `app_metadata.plan_tier` alone is **not** enough
(creator grants would miss).

| Action | free (Observer teaser) | baseline (paid) | custom / enterprise | creator/ops grant |
|--------|------------------------|-----------------|---------------------|-------------------|
| Digest summary conclusions | ✓ teaser | ✓ | ✓ | ✓ (floor) |
| Portfolio glimpse (names only) | ✓ teaser | full book | full book | per floor |
| House weights / glass-box pipeline | — | ✓ | ✓ | ✓ if floor ≥ baseline |
| Notifications GET/PATCH | ✓ (member) | ✓ | ✓ | ✓ |
| Billing links | ✓ | ✓ | ✓ | ✓ |
| Profile / Pipeline write | omitted (no tab) | omitted (no tab) | ✓ | ✓ if floor ≥ custom |
| Keys (BYOK) seal/revoke | omitted (no tab) | omitted (no tab) | ✓ | ✓ if floor ≥ custom |
| Brokers connect/revoke | omitted (no tab) — **no connections on free** | omitted (no tab) | ✓ | ✓ if floor ≥ custom |
| Automations / overlay runs | — | — | ✓ | ✓ if floor ≥ custom |

**UI rule:** Settings tabs the current *effective* tier cannot use are **omitted**,
not greyed or locked. Observer (free) and Baseline see Notifications | Billing |
About only. Custom / enterprise / creator floor see the full set. Server still
returns `TIER_FORBIDDEN` if a hidden path is called directly.

**Supersedes prior note:** baseline does **not** unlock broker connect. Free is
teaser-only (digest conclusions + light portfolio glimpse — not enough to
reverse-engineer the PM product). Full product for everyone else requires a
subscription. The **creator** email (seeded `chris.stefan@proton.me`) holds
`plan_floor=custom` so baseline pipeline + Kairos Settings writes work **without
Stripe**; paying customers still go through Checkout.

## Client products (FX Hub + future)

| Product key | Visibility |
|-------------|------------|
| `fx_hub` | Creator + rows in `client_product_grants` (12x email allowlist — human supplies list later; empty/configurable now) |
| *(future)* | Same table + `ClientProductGate` / nav filter |

Maintain grants in Supabase (`core`) near auth. Optional later: sync from the
twelve-x repo. Env fallbacks for UI before migration apply:
`NEXT_PUBLIC_OLYMPUS_CREATOR_EMAILS`, `NEXT_PUBLIC_OLYMPUS_PRODUCT_GRANTS`.

## API surface (settings Edge Function)

Existing: `/profile`, `/brokers/*`, `/notifications`, `/keys/*`.

Tier writes use **effective** plan (workspace + `entitlement_grants`).

`PATCH /profile` accepts `research_budget_usd` (number ≥ 0 or null). GET returns
`watchlist`, `themes`, `research_budget_usd` from the tip payload.

## Testing without Stripe

- Creator path: sign in as allowlisted email → effective custom → Settings writes 200.
- Free path: non-allowlisted free workspace → `TIER_FORBIDDEN` on profile/keys/brokers.
- Ops: insert into `entitlement_grants` / `client_product_grants` (service_role).
- No Stripe webhook required for Settings v0 or creator unlock.

## Non-goals

- Live broker env; amending free to include broker connect.
- Stripe product config; Auth cutover migration 900.
- Redefining epic complete (staging E2E still needs vendor captchas/secrets).
