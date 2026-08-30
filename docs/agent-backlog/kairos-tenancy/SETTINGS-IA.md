# Settings IA + tier matrix (addendum)

> **Date:** 2026-08-30  
> **Status:** Product addendum for Olympus Settings — fills silence in the Kairos
> tenancy spec on pipeline knobs, models, and BYOK entry. Does **not** amend locked
> D1–D10.  
> **Binds to:** T3 (tabs), T4 (BYOK storage + overlay budget), T5 (entitlement matrix),
> `ProfileConfig` (`digiquant.olympus.profile_config`).

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

## Tier matrix (Settings actions)

Matches locked D1 / T5. Server authority = `workspaces.plan_tier` (not JWT claim alone).

| Action | free (Observer) | baseline | custom / enterprise |
|--------|-----------------|----------|---------------------|
| View house research / narrative | ✓ | ✓ | ✓ |
| View house weights / glass-box | — | ✓ | ✓ |
| Notifications GET/PATCH | ✓ (member) | ✓ | ✓ |
| Billing links | ✓ | ✓ | ✓ |
| Profile / Pipeline write | locked UI + `TIER_FORBIDDEN` | locked + `TIER_FORBIDDEN` | ✓ |
| Keys (BYOK) seal/revoke | locked + `TIER_FORBIDDEN` | locked + `TIER_FORBIDDEN` | ✓ |
| Brokers connect/revoke | locked + `TIER_FORBIDDEN` | locked + `TIER_FORBIDDEN` | ✓ |
| Profile/Pipeline/Keys/Brokers GET hydrate | member (empty/locked presentation) | same | full |

**Product tension (documented, not amended):** human feedback suggested baseline may
“connect their broker.” Locked D1 keeps broker connect on Custom+. Widening requires
an explicit D1/T5 change + EF gate update in a dedicated PR.

## API surface (settings Edge Function)

Existing: `/profile`, `/brokers/*`, `/notifications`.

Added by v0:

| Method | Path | Behavior |
|--------|------|----------|
| `GET` | `/keys` | Fingerprint projection only |
| `POST` | `/keys/connect` | Custom+; seal `api_key` with AAD `workspace:provider:llm` |
| `POST` | `/keys/revoke` | Fail closed on unknown row |

`PATCH /profile` accepts `research_budget_usd` (number ≥ 0 or null). GET returns
`watchlist`, `themes`, `research_budget_usd` from the tip payload.

## Testing without Stripe

Ops/Custom tier for agent tests: set `workspaces.plan_tier` to `custom` (or
`enterprise`) directly. Free tier proves `TIER_FORBIDDEN` on profile/keys/brokers
writes. No Stripe webhook required for Settings v0.

## Non-goals

- Live broker env; amending D1 for baseline brokers.
- Stripe product config; Auth cutover migration 900.
- Redefining epic complete (progress toward T3/T5 completeness only).
