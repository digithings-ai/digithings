QA on develop (DIG-5134): the D8 live preview never talks to the embed, so it can never obtain a plan proof.

apps/dashboard/components/digichat-live-preview.tsx has no iframe ref, no effect and no postMessage. The shipped popup does: apps/dashboard/components/digichat-popup.tsx:238-244 sends buildThemeMessage and, for entitled users, buildPlanTierMessage(tier, accessToken). The embed turns that into an HMAC proof (apps/digichat/src/app/(digichat)/embed/embed-client.tsx:350-399 posts to /api/plan-proof, then sends X-Embed-Plan-Proof on every chat request), and the chat route fails closed without it (apps/digichat/src/app/api/chat/route.ts:344-379 returns 403 plan_tier_required).

Expected: the preview runs the same handshake as the popup, so the two dashboard surfaces embedding host=digiquant.io cannot drift.
Acceptance: a test asserting the preview posts digichat:plan-tier with the session access token for entitled tiers and nothing for baseline tiers.
Evidence and tenant-contract notes are in the first comment.
