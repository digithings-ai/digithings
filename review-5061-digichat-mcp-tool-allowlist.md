# Review — PR #5061 (head `2e2d1516c`)

- Reviewer: Code Reviewer (Muse; developers run Space Bunny — model family differs, per AGENTS.md)
- Subject: PR #5061, head `2e2d1516c` (`DIG-284` leaf 284.2 — digichat operator-only MCP tool allowlist), 3 commits `b0649cd33` + `d4f4e0cdd` + `2e2d1516c`, base `develop`
- Verdict: **changes requested** (1 blocker, doc-only; code itself is correct)
- Severity counts: blocker 1 / suggestion 3 / verified-clean 12
- Scope (diff `merge-base(github/develop, 2e2d1516c)` → `2e2d1516c`): 5 files, 280 insertions, 4 deletions; no `package-lock.json` change in range. All `file:line` below refer to the PR-head blobs unless marked `develop`.

## Blocker

### B1 — ARCHITECTURE.md:995: "fails loudly in digigraph" is false; the keys are silently ignored

`apps/digichat/ARCHITECTURE.md:995` (head blob) says configuring `allowedTools`/`mutatingTools` today "fails loudly in digigraph rather than taking effect". Neither half holds:

1. Nothing fails. digigraph `parse_mcp_servers_json` (`digigraph/src/digigraph/orchestration/mcp_client.py:442-455`, develop) rebuilds each row as `{id, url}` + auth fields + `setup` — unknown keys are never consulted. `context.py:147-157` then constructs `McpServerRef(id=…, url=…, auth=…, token=…, auth_header=…, setup=…)` field-by-field, so `extra="forbid"` (`models.py:282`) never fires — the keys are never passed to the model. Silent drop at two layers, no error, no log.
2. The failure mode is not fail-closed. Until leaf 284.1 lands, a configured in-budget allowlist parses in the BFF, forwards on `X-Digi-Mcp-Servers`, is ignored by digigraph, and the server connects with **full tool access**. Relative to the operator's intent ("only these tools") that is fail-open, not "one fail-closed mode shifted to another" as the PR body argues.

Exposure does not exceed today's default (no allowlist configured also means all tools — I confirmed `_resolve_allowed_tools_chat` in `chat_resolve.py:52` is the unrelated catalog-level `X-Allowed-Tools` mechanism), so this is not a new hole and no sequencing ADR is required. But the doc sentence promises a loud failure that does not exist, and an operator reading it could deploy believing a misconfiguration would alert them. Fix the sentence to "silently ignored until leaf 284.1; do not configure expecting enforcement" — or drop commit `2e2d1516c` wholesale (it is already flagged as outside the leaf's allowed-files list). Same premature claim in code comment `mcp-servers.ts:244-246` ("digigraph treats an absent allowlist as zero tools") — true only after 284.1; reword to "will treat … once digigraph 284.1 lands".

## Suggestions (at most 3)

### S1 — `mcp-servers.ts:355-356`: route the merge copy through `boundedToolAllowlist`

`mergeMcpSessionOverlay` copies `s.allowedTools`/`s.mutatingTools` verbatim (`[...s.allowedTools]`), and `mcpUpstreamHeaderValue` (`:396-397`) forwards verbatim. The "bound once, enforced twice" claim therefore holds only for rows built by `operatorMcpServersForUpstream` (`:291-294`); any hand-built `McpServerForward` bypasses count/name bounds with only `MAX_UPSTREAM_JSON` as backstop. In the one real call path (`route.ts`, PR blob `~592-601`: `operatorMcpServersForUpstream` → `mergeMcpSessionOverlay` → `mcpUpstreamHeaderValue`) all rows are pre-bounded, so this is unreachable today — defense in depth, not a bug. (Consistent with the existing `token` precedent, which merge also copies verbatim.)

### S2 — Decide `mutatingTools ⊄ allowedTools` semantics

Comments (`schema.ts:480-482`, `mcp-servers.ts:179-182`) call `mutatingTools` "the subset of `allowedTools`", but nothing enforces subset: `{allowedTools: ["a"], mutatingTools: ["b"]}` parses clean and forwards. Either add a zod `superRefine` or document that 284.1 will intersect/clamp — otherwise an operator typo fails silently into undefined meaning.

### S3 — Pin the overlay absence at the type level, not just via `as` casts

Both `mergeMcpSessionOverlay` overlay tests (`mcp-servers.test.ts`, PR diff `+205-259`) inject `allowedTools` through `as {…}` casts. The tests prove runtime behavior, but a future field addition to `McpSessionOverlayItem` would not fail them. Add a compile-time negative assertion (e.g. `Expect<Equal<keyof McpSessionOverlayItem, …>>` or an exhaustiveness check) so the operator-only invariant breaks the build if the type ever widens.

## Verified clean (evidence, not trust)

- **Q1 import edge — safe, direction correct.** `schema.ts:9` value-imports two consts from `./mcp-servers`; `mcp-servers.ts:7` is `import type … from "./schema"` (erased, no runtime cycle). I bundled PR-head `mcp-servers.ts` with esbuild: zero runtime imports — the client-reachable module gains no dependencies. The reverse direction would have dragged `@digithings/ui/chat/skins` (`schema.ts:13`) into the browser bundle; the author chose correctly. Bundle-size finding: none.
- **Q2 deny-by-default end-to-end (BFF side) — holds.** 10 behavioral checks executed against the real bundled PR module, all pass: absent/empty → key omitted (`operatorMcpServersForUpstream` → `boundedToolAllowlist` → `undefined`); overlay-only rows never gain lists; overlay entries on existing rows change only `auth`/`token`; `parseMcpSessionOverlay` reads only `id/auth/token/url` (unknown keys dropped); forwarded arrays are copies (no aliasing).
- **Bounds agree at the boundary.** 11 schema checks against the real PR `schema.ts` (zod 3.25, repo pin; heavy imports stubbed with faithful values): 64 entries/64 chars accepted at parse, 65 rejected; whitespace/empty/non-string rejected; absent stays absent; `.strict()` typo (`allowdTools`) throws with exact key set `{allowedTools, id, url}`. Zod bound and projection bound coincide — cannot drift (single import).
- **Exact match, no globs** — no pattern/glob code anywhere on the path; names forwarded verbatim (pinned by test + check 3).
- **Drop-whole-never-truncate** — 65-entry and 65-char inputs yield key-absent rows, not truncated ones (checks 4-5).
- **`prefixed_tool_name` 64-width rationale** — confirmed `mcp_client.py:493` truncates `[:64]`.
- **TDD framing honest, not spin.** `b0649cd33` message claims `3 failed | 43 passed` and names the 3 red + 3 green-by-design tests. Red causes are self-evident and I proved the mechanism for the schema leg (strict rejects the new keys). No implication of six reds.
- **Untouched sides confirmed by diff** (not by prose): `isAllowedMcpServerUrl` and `tests/dg/test_mcp_client.py` absent from the range diff — no drift either side; DataTap assertions (`schema.test.ts:339/350`) untouched — diff appends only at 435+; all 7 pre-existing `mergeMcpSessionOverlay` tests untouched.
- **Scope hygiene** — 5 files vs true base; the `occ_help` line-noise seen in one intermediate diff was stale-local-`develop` drift, not part of this PR. `route.ts` swallow (`catch {}` → no MCP header) unchanged — still the backstop, still silent, but this PR narrows one trigger for it.

## Coverage gaps (stated, not hidden)

- Full `vitest` suite + `lint` could not run in this checkout: pre-existing env gap (`@testing-library/jest-dom` unresolvable in `vitest.setup.ts`, no `zod` installed — `npm run test --workspace digichat` fails identically on baseline files). Compensated with the 21 targeted checks above against the actual PR blobs. Recommend the author/EM confirm CI is green before merge; do not take this review as a substitute for the suite.
- digigraph behavior verified by reading `mcp_client.py:420-456`, `context.py:120-175`, `models.py:277-310`, `chat_resolve.py:52-64` on develop — no runtime probe.

## Answers to the author's three hardest questions

1. Import edge: **safe, ship as-is** (evidence above).
2. Deny-by-default: **holds end-to-end on the BFF side** (evidence above). The remaining deny-by-default leg is digigraph 284.1, which does not exist yet — see B1.
3. Digigraph interaction: the author's exposure claim is correct (no new tool access beyond today's default), but the "fail-closed to fail-closed" framing is wrong — until 284.1 it is **accepted-but-silently-unenforced (fail-open relative to intent)**, and the doc's "fails loudly" promise is factually false. Fix the sentence (B1); no ADR or sequencing change needed.
