# ADR-0031 — What the OCC tenant may retrieve, and who may retrieve it

**Status:** Accepted (2026-10-06)
**Date:** 2026-10-06
**Accept:** Chris, on Paperclip board card `ad943a65` for DIG-1210, which he **rejected**
with the instruction: *"no masked default, remove the masking code and logic completely.
then I was to set up the chat/occ page with a private link that can access it"*.
**Accepted risk owner:** Chris. There is no named-approver mechanism and no per-deployment
switch — see Decision 4.
**Related:** Counsel's ruling on DIG-1229, which removed the masking plan on the legal side;
board approval `e4c1d067`, which carries the two acts below; PRs
[#5159](https://github.com/digithings-ai/digithings/pull/5159) and
[#5148](https://github.com/digithings-ai/digithings/pull/5148) (both closed unmerged),
PR [#5172](https://github.com/digithings-ai/digithings/pull/5172), PR
[#5166](https://github.com/digithings-ai/digithings/pull/5166), and the merged Act A
carriers [#5192](https://github.com/digithings-ai/digithings/pull/5192) and
[#5198](https://github.com/digithings-ai/digithings/pull/5198).

This ADR supersedes nothing. It is the decision record for AC #2 of DIG-1210. An earlier
draft of it existed only on the closed PR #5159 and was titled
`0031-mask-occ-tickets-corpus-by-default.md`; that number and title were never merged, and
the decision it recorded was rejected, so this file reuses the number for the decision that
was actually taken.

## Context

`scripts/index_occ_tickets.py` built the `occ_tickets` digisearch index. Per its own
docstring it wrote "full non-anonymized metadata" plus full article bodies. The OCC tenant
queried `digisearchIndex: occ_help,occ_tickets` and is served by an embed that is
`auth: anonymous` and `gateMode: ungated` in production, so corpus content reached anonymous
internet visitors through retrieval on every question. The fan-out has since been retired —
see Decision 1.

Measured against the committed payload
`apps/digithings-stack-cloudflare/container/seed/occ_tickets.jsonl`, counts only, no values:

| | count |
|---|---|
| rows / distinct tickets | 919 / 185 |
| rows quoting an email address (text or metadata) | 791 |
| distinct addresses | 286 (98.4% on organisational domains) |
| distinct customer display names in metadata | 86 |
| `[internal]` staff-only notes | 372, of which 188 also carry an email |
| rows reachable by the OCC tenant | 919 (100%) |

The payload landed in one commit, `86cb1ec5d` (PR #4987, 2026-10-02), and has never been
modified since. The repository is **public**, so it has been retrievable since that date.
`container/seed_chroma.sh` re-ingests it into Chroma on every container cold boot, so the
exposure is live in the deployed surface and not only in git.

The defect is Art. 5(1)(c) data minimisation, the same finding as DIG-1063 for the MCP
surface. It is not the Art. 9 filter, which is tracked separately.

Security's recommendation was a masked-by-default corpus with one named-approver override
(PR #5159). That would have projected 919 rows to 547, 791 rows carrying an address to 0,
and 86 metadata display names to 0. The board rejected it.

## Decision

**1. No masking. The corpus is removed, not filtered.**
PRs #5159 and #5148 are closed unmerged. No masking code exists on `develop` or on `main` and
none ever did, so nothing needs reverting. Instead of redacting the corpus, the `occ_tickets`
fan-out is trimmed to `occ_help`, the seed payload and its `seed_chroma.sh` wiring are
deleted, and the live Chroma index is purged (Act A of board approval `e4c1d067`).

Act A is now **merged**. PR [#5192](https://github.com/digithings-ai/digithings/pull/5192)
removed the committed payload on `main`, and PR
[#5198](https://github.com/digithings-ai/digithings/pull/5198) retired the fan-out on
`develop`: `occ.digisearchIndex` is `occ_help`, the OCC research prompt no longer mentions
`occ_tickets`, the seeder is deleted, `scripts/index_occ_tickets.py` is no longer copied into
the image, and `test_no_layer_fans_out_to_occ_tickets` guards all of it. Because the corpus is
no longer wired on `develop`, the masked default that #5159 and #5148 proposed has nothing left
to protect, and the two halves can no longer be landed separately — see Consequences.

**2. The OCC surface is gated behind a private invite link, not a login.**
digichat already enforces a per-tenant `X-Embed-Token`. OCC was exempt for one reason: the
host `occ.digithings.ai` was added to `FIRST_PARTY_EMBED_HOSTS`, and a first-party host is
authorised with no token at all. The plan that added it says so —
`docs/superpowers/plans/2026-08-10-occ-client-chat.md:131` added the host "so the iframe
works **without `?token=`**". The OCC registry entry already carries the schema-required
`token` field; it was simply never enforced. The link form is
`https://digithings.ai/chat/occ?token=<key>` (PR #5172), and the enforcement switch is
deleting one line from `FIRST_PARTY_EMBED_HOSTS` (Act B2).

**3. The switch is a one-line deletion, and it must not precede the key.**
A fresh high-entropy token goes into `DIGICHAT_EMBED_TENANTS` via `wrangler secret put` and
is verified in production before the allowlist entry is removed. Reversed, OCC loses access
to its own surface. The runbook is `docs/ops/OCC_INVITE_KEY.md`.

**4. There is no named approver and no env-var switch. The risk owner is Chris.**
The earlier design had one switch, `ZAMMAD_MCP_CUSTOMER_DISCLOSURE`, plus
`ZAMMAD_MCP_UNMASK_APPROVER`, so a deployment could opt out of masking by naming the person
accepting the risk. That mechanism is gone with the masking. What remains is a static
configuration with a single accountable owner, the board, and no per-deployment override.

**5. The commit path gets its own gate.**
`scripts/check_pii_seed_payloads.py` (PR #5166) stops a new unmasked payload from being
committed. It redacts nothing and blocks no runtime path; it is diff-scoped, prints counts
and never values, and flags reserved domains only. It is deliberately **not** a required
status check while the committed payload is still present — a check that is red on arrival
teaches suppression rather than fixing.

## Consequences

**Positive.**

- **The 372 `[internal]` staff notes stop being reachable by anonymous callers.** Act A is
  merged; what remains is purging the live Chroma index. Deletion closes that hole; masking
  would only have narrowed it.
- The PII leaves the repository tip, via #5192.
- No second switch is introduced, and no per-deployment override can silently re-open the
  route. There is one configuration and one owner.
- Nothing for an OCC visitor to hold beyond the link itself, which is what the board asked
  for.

**Negative / tradeoffs.**

- **The invite key is the only access control on live customer PII.** With no masking code on
  `main`, there is no second layer. A leaked or shared key re-opens the route, so the key
  must be revocable and staff-scoped. There is no deny-list: rotation is the only revocation.
- **The link is a bearer capability, not authentication.** It can be forwarded, screenshotted
  or pasted. It raises the cost of *finding* the page; it does not identify who holds it and
  cannot audit who used it. digichat treats the embed token as a publishable key by design
  (`apps/digichat/ARCHITECTURE.md`, DIG-619). OCC must be told the key is a password to
  distribute, not a URL to publish.
- **Ticket-grounded answers stop working.** History, "who reported what" and live thread reads
  go away with the corpus. Expect support noise from OCC; the successor is the no-PII-in-git
  path in `scripts/build_occ_tickets_seed.py`, gated behind the key.
- **Masking is forgone for good.** Had it landed, the corpus would have shrunk content. The
  replacement shrinks nothing; it removes the corpus and restricts access to the surface.
- **Neither act un-publishes the payload.** Counsel has ruled a git rewrite is not legally
  required and not technically possible (`forks_count: 2`). This stops future exposure; it
  does not erase the past. The Art. 33 notification duty is unaffected by any of it.
- **A separate live route is not closed by this decision.** `scripts/zammad_mcp/formatting.py`
  on `main` has no masking and reads live Zammad rather than the committed corpus, so the
  corpus trim alone does not close live customer PII on that path. This is why PR #5148's
  closure is a loss of defence-in-depth on a route that is still open, not on the corpus.
- **The masking work can no longer be landed, even if that decision is revisited.** The two
  halves were stacked — the OCC index masking depends on `scripts/zammad_mcp/privacy.py`,
  which only ever existed on #5148's branch — so the OCC half had no independent base on
  `develop`. With #5198 having retired the fan-out, `develop` now actively guards against it
  via `test_no_layer_fans_out_to_occ_tickets`. Restoring masked indexing is therefore a
  deliberate reversal of a merged change, not a re-land.

## Links

- DIG-1210 (this work); DIG-1229 (Counsel: Art. 32/33 notification and the Art. 9/10
  question); DIG-1230 (containment and free-text-name scoping); DIG-1381 (invite-key
  runbook and deny-path tests).
- PR [#5172](https://github.com/digithings-ai/digithings/pull/5172) — invite link
  enablement, and the landing place for `docs/ops/OCC_INVITE_KEY.md` (linked from Decision 3
  by name rather than by relative link, because that runbook lands with #5172 and this ADR
  must merge on its own).
- PR [#5166](https://github.com/digithings-ai/digithings/pull/5166) — seed-payload PII gate.
- PR [#5159](https://github.com/digithings-ai/digithings/pull/5159) — closed unmerged; the
  rejected masked default. Kept open as an unmerged branch because it is the record of the
  alternative that was weighed.
- [`../../SECURITY.md`](../../SECURITY.md) — the commit-time payload gate.
