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
