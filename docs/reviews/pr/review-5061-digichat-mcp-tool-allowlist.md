# Review — PR #5061: digichat operator-only MCP tool allowlist (DIG-284 leaf 284.2)

- Reviewer: Code Reviewer (agent c59332b4-a0ef-4a6a-8027-5c081486f899), reporting to QA Lead
- Subject: PR #5061, head `2e2d1516c`, branch `DIG-102-digichat-write-the-ticket-update-while-the-work-is-done-datatap-ask-of-2026-10-01`, commits `b0649cd33` + `d4f4e0cdd` + `2e2d1516c`, base `develop` (merge-base `0f9d2103b`)
- Scope: 5 files, +280/−4 vs true base; no lockfile change
  - `apps/digichat/src/lib/deploy-config/schema.ts`
  - `apps/digichat/src/lib/deploy-config/mcp-servers.ts`
  - `apps/digichat/src/lib/deploy-config/mcp-servers.test.ts`
  - `apps/digichat/src/lib/deploy-config/schema.test.ts`
  - `apps/digichat/ARCHITECTURE.md` (docs-only, outside leaf allowed files, standalone commit `2e2d1516c`, droppable)
- Verdict: **changes requested**
- Severity counts: blocker 1 (doc-only) / suggestions 3 / code defects 0

## Blocker (must fix before merge)

### B1 — Doc claims "fails loudly in digigraph"; behavior is silently ignored (doc-only, no new hole)
- `apps/digichat/ARCHITECTURE.md:995`: "configuring them today fails loudly in digigraph rather than taking effect" — false.
- Evidence: `digigraph/src/digigraph/orchestration/mcp_client.py:420-455` (`parse_mcp_servers_json`) rebuilds each row as `id`/`url` plus auth/setup only; unknown keys (`allowedTools`, `mutatingTools`) are dropped without error. `digigraph/src/digigraph/http_api/context.py:147-157` then constructs `McpServerRef` field-by-field (`id`, `url`, `auth`, `token`, `auth_header`, `setup`), so `McpServerRef`'s `extra="forbid"` (`digigraph/src/digigraph/models.py:277-282`) never fires on these keys.
- Effect until leaf 284.1: the keys are accepted by the BFF, forwarded on `X-Digi-Mcp-Servers`, then silently unenforced in digigraph — full tool access, i.e. fail-open relative to operator intent. Exposure does not exceed today's default (nothing in-tree configures the field), so no ADR or sequencing fix is required on safety grounds; but the sentence must be corrected to "silently ignored until 284.1", or drop commit `2e2d1516c` wholesale (already flagged as outside the leaf's allowed files).
- Same premature framing in `apps/digichat/src/lib/deploy-config/mcp-servers.ts:244-246` ("digigraph treats an absent allowlist as zero tools" — true only after 284.1 lands).

## Author's three questions (answered)

1. **Value import edge `schema.ts → mcp-servers.ts` is safe.** `schema.ts:9` value-imports the two consts from `mcp-servers.ts`; the reverse edge (`mcp-servers.ts:7`) is `import type` and erased at runtime. `mcp-servers.ts` has no other runtime imports, so nothing from `schema.ts` (including `@digithings/ui/chat/skins` via `schema.ts:14`) leaks into the client-reachable bundle. Direction is correct; no bundle-size finding.
2. **Deny-by-default holds end to end BFF-side.** `boundedToolAllowlist` (`mcp-servers.ts:247-254`) returns `undefined` for absent/empty/over-budget; `operatorMcpServersForUpstream` (`mcp-servers.ts:291-294`) omits the key in all three cases; `mergeMcpSessionOverlay` (`mcp-servers.ts:350-358`) copies operator lists only when present and its overlay loop (`mcp-servers.ts:361-378`) has no path that writes the fields (overlay type `McpSessionOverlayItem`, `mcp-servers.ts:185-196`, deliberately lacks them); `mcpUpstreamHeaderValue` (`mcp-servers.ts:396-397`) forwards only when non-empty. No branch turns an unset allowlist into "all tools".
3. **Digigraph claim judged above (B1).** The author's exposure analysis (no new hole) is correct; the failure-mode framing ("fail-closed to fail-closed" / "422/500") is wrong — it is "fail-closed-silent to accepted-but-unenforced". Worth a doc-line fix, not an ADR or re-sequencing, since in-tree exposure is nil.

## Suggestions (non-blocking, at most 3)

- **S1** — Route the `mergeMcpSessionOverlay` copy (`mcp-servers.ts:355-356`) through `boundedToolAllowlist` so "enforced twice" holds on every construction path, not just `operatorMcpServersForUpstream`. Currently safe (inputs are already bounded, overlay cannot inject), but the invariant is stated generally and the copy is the one path that trusts its input.
- **S2** — Decide and document `mutatingTools` subset semantics: nothing today enforces `mutatingTools ⊆ allowedTools`. If intentional (advisory flag for a future leaf), say so; otherwise add the check.
- **S3** — Pin overlay absence at the type level in tests rather than via `as` casts, so a future field addition to `McpSessionOverlayItem` fails the test instead of slipping past a cast.

## Spot-checks

- Bounds agree at the 64/65 boundary in both layers (`MAX_MCP_TOOL_ENTRIES = 64`, `MAX_MCP_TOOL_NAME_LENGTH = 64`, `mcp-servers.ts:236-237`, imported at `schema.ts:9`); zod arrays capped at `schema.ts:478,484`, header guard at `mcp-servers.ts:249-250`.
- `prefixed_tool_name` 64-width confirmed (`digigraph/src/digigraph/orchestration/mcp_client.py:492-493`: `re.sub(...)[:64]`), matching the bound rationale.
- TDD framing in `b0649cd33` honest: commit body names 3 red + 3 green-by-design (overlay-override, header-forwarding, config-parse red; already-correct behavior pinned green).
- `isAllowedMcpServerUrl` and `tests/dg/test_mcp_client.py` untouched per diff; DataTap example assertions intact per diff.
- Full vitest suite could not run in this checkout (pre-existing env gap); compensated with targeted reads and grep-verified digigraph paths above. Confirm CI green before merge.
- `.strict()` preserved on `McpServerSchema` (`schema.ts:486`); `McpSessionOverlayItem` correctly gains no fields.

## Required follow-up

- Author (DIG-409) owns fixes. This review posts as `<!-- in-session-review -->` with sha `2e2d1516c` on DIG-422; a review with adverse findings is `done`, not `blocked`. Do not merge; do not push to `develop`.

---

# Second round — entry bound 64 → 256 (DIG-436)

- Reviewer: Code Reviewer (agent c59332b4-a0ef-4a6a-8027-5c081486f899), reporting to QA Lead
- Subject: PR #5061, head `7f050336c`, same branch, three commits on top of the first pass (`fd4fdbc7a` test, `ad217292c` fix, `7f050336c` docs), base `develop`
- Scope this round: `apps/digichat/src/lib/deploy-config/schema.test.ts` (+31), `apps/digichat/src/lib/deploy-config/mcp-servers.ts` (comment + constant), `apps/digichat/ARCHITECTURE.md` (bound text). Earlier commits re-checked only where this round alters their reasoning (S1/S2 below).
- Verdict: **approve** — no blockers. Three non-blocking suggestions below.
- Severity counts: blockers 0 / suggestions 3 / code defects 0

## Author's four questions (answered with evidence)

1. **256 is corpus-anchored, not another guess — approve.** 113 confirmed by parse (`digiquant/src/digiquant/mcp_server.py:499`, `READ_SCOPE_TOOLS` frozenset, 113 members), so the bound clears the widest shipped read-scope surface with ~2.3x headroom. 113 synthetic names serialise to 2,563 bytes (measured), matching the commit's "~3 KB" claim, well inside `MAX_UPSTREAM_JSON = 16_384` (`mcp-servers.ts:220`). Caveat (S2): at the new worst case the header cap becomes the operative bound — a single row with 256×64-char names in both lists is ~35 KB (measured 34,904), and even 256×30-char names in both lists is ~17.5 KB (measured 17,496), both over 16,384. At 64 the worst case fit (64×64 both lists measured 8,792). Failure stays fail-closed (whole header dropped, `mcpUpstreamHeaderValue`, `mcp-servers.ts:419`), so this is a doc-precision point, not a behavior defect.
2. **Synthetic 113-name test is the right shape — approve.** The bound under test is entry *count*, and `digifetch_read_NNN` names exercise exactly that; importing digiquant's real Python list into a digichat unit test would couple the suites across languages for no additional count coverage. The author's observed red is credible (verbatim zod error at 64) and the assertion (`toHaveLength(113)`) cannot pass under the old bound. Gap: nothing pins the *upper* side at the new bound (S1).
3. **Raising the bound weakens nothing — confirmed by read.** `boundedToolAllowlist` (`mcp-servers.ts:258-265`) returns `undefined` for over-budget (dropped whole, callers omit the key — never truncated). All three production construction paths re-bound: `operatorMcpServersForUpstream` (`mcp-servers.ts:302-305`), `mergeMcpSessionOverlay` (`mcp-servers.ts:371-374`, the first-round S1 fix, comment cites "review #5061 S1"), and the header gate (`mcp-servers.ts:419`). `route.ts:592-599` chains projection → merge → header with no bypass; `mcp/oauth/start/route.ts:97` uses the bounded projection. Direct `mcpUpstreamHeaderValue` calls with hand-built objects exist only in tests.
4. **Name-length 64 confirmed against both claims.** Longest real name is 36 (`dashboard_get_policy_gate_evaluation`), verified by parsing `READ_SCOPE_TOOLS` (max length 36 over 113 members). `prefixed_tool_name` truncates the tool part to `[:64]` (`digigraph/src/digigraph/orchestration/mcp_client.py:492-493`: `re.sub(r"[^a-zA-Z0-9_-]", "_", tool_name)[:64]`), so the doc comment's "same width as truncation" claim holds: any name that passes the 64-char schema bound survives digigraph's truncation intact.

## Re-confirmed from round one (still hold after the bound change)

- **Value import cycle-free and leak-free.** `schema.ts:9` value-imports the two consts from `mcp-servers.ts`; the reverse edge (`mcp-servers.ts:7`) is `import type`, erased at runtime. `mcp-servers.ts` has no other runtime imports, so nothing from `schema.ts` leaks into client-reachable bundles.
- **Deny-by-default holds end to end.** Absent/empty/over-budget → `undefined` → key omitted (`mcp-servers.ts:302-305, 371-374`); overlay type still lacks both fields (`mcp-servers.ts:185-196`); header forwards only non-empty lists (`mcp-servers.ts:414-415`). No branch turns unset into "all tools".

## Suggestions (non-blocking, at most 3)

- **S1** — Pin the upper side at the new bound: a 257-entry list must fail zod parse (schema layer) and must be omitted whole — not truncated — by `operatorMcpServersForUpstream` (projection layer). The 113 test pins "must parse"; nothing pins "must reject", so a future bound bump that accidentally truncates instead of dropping would pass the suite. Two assertions, one per layer.
- **S2** — One sentence in the `mcp-servers.ts:234-243` comment (and/or `ARCHITECTURE.md`): the "well inside `MAX_UPSTREAM_JSON`" claim covers the motivating 113-name case, but a maximal row (256 long names in both lists) trips the 16 KB header cap instead — still fail-closed (whole header dropped), but the header cap, not the entry bound, is then the operative limit. Also note the operator `servers` array itself is uncapped (`schema.ts:501`, no `.max()`), so multi-row enumeration compounds toward the same cap.
- **S3** — Assert the real longest name (`dashboard_get_policy_gate_evaluation`, 36 chars) parses, tying the 64-char name-length bound to the corpus the same way the 113-count test ties the entry bound. Today only the comment (and this review) connects the two; a digiquant rename past 64 chars would otherwise fail first in production config rather than in this suite.

## Spot-checks

- Targeted suites green in this worktree: `schema.test.ts` 26 passed, `mcp-servers.test.ts` 21 passed (47 total).
- `npm run lint --workspace digichat`: 0 errors, 27 warnings (matches author's gate table; none in `deploy-config`).
- `git diff --stat origin/develop -- package-lock.json`: empty (no macOS `libc` collateral).
- First-round fixes verified in-tree: merge-path re-bound carries the "review #5061 S1" comment (`mcp-servers.ts:366-370`); `mutatingTools` non-subset rationale documented (`schema.ts` comment cites "review #5061 S2"); B1 doc correction intact (`034877f7a`).
- `dashboard-modal.yaml:64-65` confirms the motivating row (`id: digiquant`, `url: https://mcp.digithings.ai/mcp`); the example declares no `allowedTools` itself, so the 113 figure refers to the catalog an operator *would* enumerate for that row, consistent with the test comment.
- `ARCHITECTURE.md` (`7f050336c`): numbers match code (256/64), rationale sentence is accurate, semantics paragraph untouched. Outside the leaf's allowed files but a standalone commit — recommend **keeping** (accurate as written); dropping whole remains a one-command fallback if the EM prefers code-only.

## Required follow-up

- Author (me) owns any follow-up fixes. This review posts its verdict on DIG-436; a completed review with adverse findings is `done`, not `blocked`. Do not merge; do not push to `develop`.
