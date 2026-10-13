# Review — PR #4983 (commit bcd21138e)

- Reviewer: subagent (read-only docs review)
- Subject: digithings-ai/digithings#4983 — docs(occ): update tenant JSON examples to fan-out pair
- Verdict: **Approve** — merge-ready as docs-only change. No blocking findings.

## Severity counts

- Blocking: 0 | Major: 0 | Minor: 0 | Info: 1

## Checks

1. **Changed JSON blobs parse, occ entries carry the pair** — PASS. All 4 blobs
   verified with `json.loads`; every occ entry has
   `"digisearchIndex": "occ_help,occ_tickets"`:
   - `apps/digichat-cloudflare/README.md:77-110` (fenced tenant JSON; occ entry lines 92-109)
   - `docs/projects/online-compliance-center/README.md:60` (`DIGICHAT_EMBED_TENANTS`)
   - `docs/projects/online-compliance-center/README.md:66` (`DIGI_TENANT_CORPUS_MAP`)
   - `infra/digichat-digithings/README.md:193` (`DIGICHAT_EMBED_TENANTS`)
2. **No missed single-`occ_help` tenant references** — PASS. `grep -rn 'occ_help"'`
   over the three files returns zero bare-single matches; every tenant JSON blob
   now carries the pair.
3. **Tool list edit accurate** — PASS. `aggregate_tickets` is a real MCP tool:
   `scripts/zammad_mcp/server.py:309-310` (`@mcp.tool()` + `def aggregate_tickets`),
   alongside `search_tickets` (:64), `list_tickets` (:131), `get_ticket` (:150),
   `ticket_report` (:195). The `infra/digichat-digithings/README.md:110` list
   addition matches the server's tool set exactly.

## Info (non-blocking)

- (Info) Two non-JSON `occ_help` singles remain and were correctly left alone per
  this PR's tenant-JSON scope, but may warrant a follow-up: summary table
  `docs/projects/online-compliance-center/README.md:20`
  (`| digisearch index | occ_help |`) and routing schematic `:52`
  (`→ tenant occ → occ_help`) still describe a single index. The other singles
  (`occ_help.yaml` filename at :45; Chroma seed note at
  `infra/digichat-digithings/README.md:117`) are factually still correct.
