# ADR 0005: chat.digithings.ai Guest-Tier Rate Limits

**Status:** proposed
**Date:** 2026-04-18

## Context

ADR-0002 commits us to a "metered guest tier" on `chat.digithings.ai` — unauthenticated visitors who click **Try it now** on `digithings.ai` can send a handful of messages to the ecosystem guide before being nudged into bring-your-own-key (BYOK) or a signed-in account. The guest pool is a **marketing expense**, not a revenue line: its purpose is to remove the friction of "sign up to try it" while letting prospects experience DigiGraph answering questions about the stack.

Three concrete risks bound the design:

1. **Scraping / content exfiltration** — a script hitting the endpoint in a loop to pull our component docs through the LLM rather than reading the repo.
2. **Token-exhaustion attacks** — adversarial prompts that maximize output tokens (long regenerations, forced verbose outputs) to burn our LiteLLM spend.
3. **Repeated regeneration** — benign-but-expensive UI behavior where a user spams "regenerate" on the same turn.

At the same time, the **false-positive cost is high**: a prospect who hits a rate-limit wall on their second question and sees a generic `429` error is a lost conversion. Any limit that blocks a legitimate five-minute evaluation defeats the marketing premise.

No guest-tier enforcement exists today. DigiChat (`digichat/`, Next.js + BFF) currently assumes authenticated sessions via Auth.js; the guest path has to be bolted onto the BFF without leaking guest traffic into tenant tables.

## Decision

**Two-axis token-bucket rate limiting at the DigiChat BFF, backed by Upstash Redis, returning HTTP 429 with a sign-in CTA on exhaustion.** Numbers below are starting points — calibrated monthly against actual cost and conversion data.

### Limits (initial values)

| Axis | Limit | Window | Rationale |
| --- | --- | --- | --- |
| Per-IP messages | 10 | rolling 24h | Enough for a real evaluation; caps a scraper at 10 req/day/IP. |
| Per-IP concurrent requests | 3 | instantaneous | Prevents burst regeneration spam. |
| Per-session messages | 5 | session lifetime | Triggers the sign-in nudge mid-conversation while value is peaking. |
| Per-message output tokens | 1,024 | per response | Hard cap on token-exhaustion blast radius. |
| Model tier | cheapest tier only (`DIGI_LLM_MODE=test`) | — | Guest traffic never hits `best`. |
| Monthly cost ceiling | $200 USD | calendar month | Guest pool short-circuits to "sign in to continue" when hit. |

Per-IP and per-session are enforced independently — a user who opens five anonymous tabs still hits the per-IP daily cap.

### Enforcement

- **Layer:** DigiChat BFF middleware, in front of the DigiGraph proxy. Guest requests never reach DigiGraph without a valid bucket debit.
- **Backend:** Upstash Redis (serverless-native, fits Vercel deployment, sliding-window primitives). Token-bucket keyed by `ip_hash` and `session_id`.
- **IP handling:** we store only `sha256(ip || daily_salt)` — never raw IP. Salt rotates daily, so buckets expire naturally and we retain no long-lived IP log. This is the GDPR-defensible posture for a marketing trial tier.
- **Session:** opaque cookie, rotated per-browser. Session counter increments on each successful BFF call; the sign-in nudge is rendered client-side when the counter crosses threshold.
- **429 response:** structured JSON `{error: "guest_limit", remaining: {...}, signin_url: "..."}`. The client renders a friendly in-conversation card ("You've used your free messages — sign in to keep going") rather than an error toast.
- **Cost ceiling:** a separate daily budget counter in Redis, incremented by a post-hoc cost estimate (tokens × tier price). When the monthly sum crosses the ceiling, the BFF flips guest mode off and all anonymous traffic gets the sign-in CTA until the calendar rolls.

### Abuse escalation

- Cloudflare Turnstile is **invoked on 429**, not by default — a guest who hits the per-IP cap sees a challenge before the sign-in nudge, which deters the cheapest scrapers without adding friction to the common path.
- Static blocklist (`/etc/guest-blocklist.txt` in the BFF container) for known-bad IP ranges / ASNs discovered via logs. Updated manually; no automated bans.

## Consequences

**Positive**

- Guest experience stays conversational: the first five messages feel unthrottled, and the wall is a product nudge rather than an error.
- Cost is bounded with a hard ceiling; abuse is bounded by per-IP + per-output-token caps.
- No PII retained — hashed, salted, daily-rotated IPs are consistent with the "marketing expense, not a data grab" framing.
- Reuses DigiChat's existing Redis/Upstash connection if present; otherwise a small add.

**Negative / tradeoffs**

- Hard runtime dependency on Redis/Upstash for the guest path. If Upstash is down, the BFF fails closed (guest requests get 503, authenticated traffic unaffected).
- IP-based limits are bypassable by any motivated attacker with a proxy pool. Accepted: the combination of per-output-token caps and the monthly ceiling bounds the *cost* of abuse even if the *count* is bypassed.
- Starting numbers will be wrong. We commit to reviewing them monthly against conversion rate and spend; the ADR does not lock the values.
- Sign-in nudge UX has to be designed carefully; a 429 rendered as an error is worse than no guest tier at all.

## Alternatives considered

1. **Session-only limits, no IP axis.** Rejected: trivially bypassed by clearing cookies or opening an incognito window. Guest-tier abuse is specifically the "many cheap sessions" shape.
2. **No limits, watch the bill.** Rejected: one motivated actor with a regen-loop script can burn a month of budget in an afternoon. Not a risk we'd take for a marketing line item.
3. **Cloudflare Turnstile only, no token-bucket.** Rejected: Turnstile stops bots but does not bound spend. A human-driven abuse pattern (shared link, many clicks) would still exhaust the budget.
4. **Require sign-in for any chat, drop the guest tier.** Rejected by ADR-0002 — the "try it in one click" flow is the core conversion lever for `digithings.ai`.
5. **Per-IP limits at the edge (Cloudflare) instead of the BFF.** Considered. Rejected for v1: we want per-session logic co-located with the BFF's session state and the cost-ceiling counter. Edge enforcement is a reasonable later addition once the bucket values stabilize.

## Links

- Related: ADR-0002 (Domain Unification)
- Related: issue #29 (this decision), epic #8 (DigiChat ecosystem guide)
- DigiChat app: `digichat/`
- LLM mode plumbing: `DIGI_LLM_MODE` in `config/litellm.yaml`
