# digifetch post-deploy verification (#4101)

Post-deploy verification checklist for the digifetch × Gloomberb market-data
family. It confirms two things against a live deployment: (1) the 13 phase-0
cohort tools from #4069 are present on the **served** MCP surface, and (2) the
anonymous live smoke against `api.gloom.sh` passes. The family has since grown
to 33 read tools under #4110, so the family count is **reported**, not gated —
the 13-tool cohort is the pass gate.

This is an operator runbook plus a recording procedure; it is not a scheduled
probe. Escalation criteria and the probe shape are documented in
[Drift signals and escalation](#drift-signals-and-escalation); the probe ships
only when a trigger fires.

## Preconditions

- The deploy that carries the digifetch family is live (its `mcp_server.py`
  `READ_SCOPE_TOOLS` includes the cohort below). Note the commit SHA under test.
- The repo virtualenv is installed and the `mcp` extra is available:
  `pip install -e "digiquant[mcp]"` (see `digiquant/ARCHITECTURE.md` § MCP
  hosting, `:1642-1651`).
- A local `.env` is present for the smoke (see Check 2). Never print, echo, or
  commit its values.
- The hosted route is still **reserved**, not enabled: `mcp.digithings.ai`
  (`cloudflare/digithings-stack-cloudflare/src/ports.ts:22`) has its Worker
  route commented out behind a human gate
  (`cloudflare/digithings-stack-cloudflare/wrangler.toml:63-73`). Check 3 stays
  BLOCKED until a later note enables it.

## Check 1 — list the served MCP surface tools

The served path matches the hosted container's scope and port
(`Dockerfile.mcp:31-34`): `--scope read` on `127.0.0.1:8767`, streamable-http at
`/mcp`.

Start the server in a second terminal:

```bash
PATH="$PWD/.venv/bin:$PATH" python -m digiquant.mcp_server --scope read
```

Expected log line:
`Starting digiquant MCP server on 127.0.0.1:8767 (transport=streamable-http scope=read)`
(`digiquant/src/digiquant/mcp_server.py:1996-2010`).

Then list the tools with the repo's own client shape
(`digigraph/src/digigraph/orchestration/mcp_client.py:611-623`):

```bash
PATH="$PWD/.venv/bin:$PATH" python - <<'PY'
import asyncio
import json

from mcp import ClientSession
from mcp.client.streamable_http import streamablehttp_client

COHORT = [
    "digifetch_quote", "digifetch_quotes_batch", "digifetch_price_history",
    "digifetch_ticker_financials", "digifetch_options_chain",
    "digifetch_sec_filings", "digifetch_holders", "digifetch_analyst_research",
    "digifetch_corporate_actions", "digifetch_earnings_calendar",
    "digifetch_exchange_rate", "digifetch_search", "digifetch_news",
]


async def main() -> None:
    async with streamablehttp_client("http://127.0.0.1:8767/mcp") as (read, write, _):
        async with ClientSession(read, write) as session:
            await session.initialize()
            listed = await session.list_tools()
    names = sorted(t.name for t in listed.tools if t.name.startswith("digifetch_"))
    print(json.dumps({
        "digifetch_count": len(names),
        "cohort_missing": [n for n in COHORT if n not in names],
        "names": names,
    }, indent=2))


asyncio.run(main())
PY
```

Expected: `"digifetch_count": 33` (2026-09-16 value) and `"cohort_missing": []`.
**PASS = empty `cohort_missing`**; the count is recorded as-is.

## Check 2 — production smoke against api.gloom.sh

Run the existing live-smoke harness (anonymous — no cookie):

```bash
set -a; . ./.env; set +a
GLOOMBERB_LIVE_SMOKE=1 PATH="$PWD/.venv/bin:$PATH" pytest tests/dq/test_gloomberb_live_smoke.py -v
```

What it asserts: one anonymous quote returns a `QuoteResult` with
`provider_id == "gloomberb-cloud"`
(`tests/dq/test_gloomberb_live_smoke.py:24-33`). Expected: `1 passed`
(`::test_live_anonymous_quote_smoke`).

Notes:

- The smoke is anonymous — it does **not** exercise the session cookie; the
  cookie-gated path is out of scope here and tracked by #4099.
- `set -a; . ./.env; set +a` exports the environment silently; no value is ever
  printed. Never echo, log, or paste a cookie or token.

## Check 3 — hosted-surface row (reserved route)

The reserved hostname `mcp.digithings.ai`
(`cloudflare/digithings-stack-cloudflare/src/ports.ts:22`) has no live route
today — the Worker route block is commented out at
`cloudflare/digithings-stack-cloudflare/wrangler.toml:63-73` behind a human
gate.

When that route is enabled, run the Check 1 listing heredoc against it, with the
Worker-edge digikey JWT in the request headers
(`streamablehttp_client("https://mcp.digithings.ai/mcp", headers=...)`, scope
`digiquant:backtest`; see `digiquant/ARCHITECTURE.md` § MCP hosting).

**Mark this row BLOCKED until then.** Do not invent a token command that is not
documented yet.

## Record results

Post the results as a comment on #4101 with exactly this shape:

```markdown
## Post-deploy verification (#4101) — <YYYY-MM-DD>

Surface: local served path (python -m digiquant.mcp_server --scope read, 127.0.0.1:8767).
Build/commit under test: <sha>.

| Check | Result | Evidence |
|---|---|---|
| 13-tool cohort on the served MCP surface | PASS/FAIL | cohort_missing=[...], digifetch_count=<n> (tools/list) |
| Production smoke vs api.gloom.sh | PASS/FAIL | GLOOMBERB_LIVE_SMOKE=1 pytest tests/dq/test_gloomberb_live_smoke.py -v → <n> passed |
| Hosted row (mcp.digithings.ai) | BLOCKED/PASS | route commented out (wrangler.toml:63-73) / hosted tools/list output |
```

Post it with:

```bash
gh issue comment 4101 -R digithings-ai/digithings --body "$(cat <<'EOF'
...the filled template above...
EOF
)"
```

A failed check is filed as an issue (see below) with the typed envelope and the
request shape — never re-run in a loop until it passes.

## Drift signals and escalation

Treat these as drift signals (not expected conditions):

- **S1** — `not_found` on the pinned request shapes on 2 runs ≥24h apart.
- **S2** — payload field loss (`upstream_error` "unexpected payload") twice.
- **S3** — an anonymous endpoint returns 401/403, or the cookie names no longer
  match `SESSION_COOKIE_NAMES`
  (`digiquant/src/digiquant/data/gloomberb/client.py:180-183`).
- **S4** — the smoke fails 2 consecutive days with non-rate-limit errors.
- **S5** — host/family-wide break.

Escalation: file an issue (`component:digiquant`, `priority:medium` — or
`priority:high` for S5/S3) with the typed envelope, the request shape, and the
dates.

Scheduled-probe trigger: ≥2 distinct drift events in 30 days, or one
family-wide break. The probe itself is one anonymous quote plus one anonymous
history per day (`0 14 * * *` UTC), no cookie.
`api.gloom.sh is an existing runtime dependency of the client (client.py:152), so a scheduled probe is not new network exposure.`
Rate limits (`rate_limited`) and free-tier delays are non-events.

## Related

- [`2026-09-16-gloomberb-post-deploy-verification-design.md`](../superpowers/specs/2026-09-16-gloomberb-post-deploy-verification-design.md)
- [`2026-09-12-digifetch-scoping-design.md`](../superpowers/specs/2026-09-12-digifetch-scoping-design.md)
- Issues: [#4101](https://github.com/digithings-ai/digithings/issues/4101),
  [#4069](https://github.com/digithings-ai/digithings/issues/4069),
  [#4110](https://github.com/digithings-ai/digithings/issues/4110)
