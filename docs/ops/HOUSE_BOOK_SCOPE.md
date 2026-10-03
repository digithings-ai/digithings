# House book scope (Group A)

Concise developer guide for **workspace-scoped private books**. Dense inventory
lives in [`digiquant/ARCHITECTURE.md`](../../digiquant/ARCHITECTURE.md)
(overlay / tenancy sections) and the [execution-tenancy epic](../agent-backlog/execution-tenancy/EPIC.md).

## Intent

After tenancy (migration 097+), private portfolio tables carry `workspace_id`.
The digithings operator book is the **house** workspace. Overlay (Custom-tier)
workspaces write the **same date keys** into the same tables. An unfiltered
date scan therefore mixes overlay weights into house research, ops scripts, and
the public dashboard.

**Rule:** omitted `workspace_id` means the **house book**, never “every row”.

## Group A tables

| Table | Why it is Group A |
|-------|-------------------|
| `positions` | Daily book weights |
| `nav_history` | NAV / returns |
| `position_events` | OPEN / ADD / EXIT / TRIM |
| `portfolio_metrics` | Tearsheet / metrics script rows |

Shared teasers without private weights (`daily_snapshots`, `theses`,
`instruments`) stay date-scoped. System corpus research lives under the
**system** workspace, not house.

Well-known ids (deterministic `uuid5`; public book selectors, not secrets):

| Slug | UUID |
|------|------|
| `house` | `6b753576-ced9-5319-9bfa-c5d0aacd9319` |
| `system` | `1105372f-4109-5815-be5a-21091ccfc8ad` |

Minted by `digiquant.dashboard.tenancy.house_workspace_id()` /
`system_workspace_id()`.

## How to pin (by layer)

### Python house readers / writers

```python
from digiquant.dashboard.tenancy import eq_house_workspace, house_workspace_id

# Read — omitted id ⇒ house
q = eq_house_workspace(client.table("positions").select("*").eq("date", day))

# Write — stamp explicitly
row["workspace_id"] = str(house_workspace_id())
```

`resolved_workspace_id(None)` / blank also resolves to house. Overlay paths pass
an explicit workspace UUID and must not fall through to house.

### Research / MCP `query_research`

`search_research` in `digiquant.dashboard.research_retrieval.queries` reads **house
only** — it stamps `_eq_house` and has no `workspace_id` override. There is no
overlay-book read path through this tool; read another book with a direct
Supabase query that pins its `workspace_id`.

### Dashboard (TypeScript)

```ts
import { houseBook } from "@/lib/house-workspace";

const { data } = await houseBook(supabase, "positions").eq("date", asOf);
```

Do not `.from("positions").select(...).eq("date", …)` alone on Brief / Holdings /
Performance — migration 109 lets a Custom JWT SELECT house **or** own overlay.

### research ops scripts

Prefer `eq_house_workspace()` on every Group A PostgREST chain. Document readers
that filter `documents` by workspace use the same helpers (house stamp when the
script is house-owned).

## Constraints & pitfalls

| Pitfall | Correct behavior |
|---------|------------------|
| Date-only `.eq("date", …)` on Group A | Always add workspace pin |
| Relying on RLS alone for the dashboard | RLS may allow overlay; UI must still `houseBook()` |
| Test `_FakeQuery` treating missing column as house | **Test-only**; production PostgREST `eq` matches only equal rows |
| Overlay `--execute` with persist off | Refuses / finishes `persist_disabled` — not a remaining-hop proof |
| Staged cutover **113** (drop legacy `UNIQUE(date)`) | Not auto-applied; do not copy to top-level or apply on `core` from this row. On `origin/main` and `origin/develop` the writers for the keys 113 drops already upsert `nav_history` and `portfolio_metrics` `on_conflict=workspace_id,date` and `positions` / `position_events` `on_conflict=workspace_id,date,ticker`. `daily_snapshots` still uses `on_conflict=date`, and 113 must not drop that unique. The SQL header still says the date-only story. The ledger one-root index rewrite in that file was not checked. This sentence is not approval to apply 113. There is no `pipeline-dashboard.yml`. On `origin/develop`, the enabled house clock is container command `house-run` (`house-run-09`). `pipeline-digiquant.yml` is only the `GITHUB_OVERRIDE_JOBS` workflow string (default empty). `cj().codeRef: "main"` is an image-pin gate, not a checkout. An override can still `workflow_dispatch` that file with `ref: develop`, and the workflow then checks out `ref: main`. |
| Main house GHA vs develop tenancy writers | The runner image workflow deploys on push to `main`; a manual `workflow_dispatch` builds whatever ref was dispatched. `origin/main` already upserts those Group A books on `workspace_id,date` / `workspace_id,date,ticker`, the same targets as `origin/develop`. That widened key is what those files contain; it is not a develop-only upsert the scheduled job skips. Do not assume a green develop unit run proves the house publish. |
| Booked positions, missing commit ledger | Operator recovery: `python digiquant/scripts/research/recover_commit_ledger.py --date YYYY-MM-DD` (then `--apply`). Reads house `positions` / `nav_history`; calls `append_commit_chain`. Do not re-run the LLM pipeline. Do not `workflow_dispatch`. |
| `DIGIQUANT_OVERLAY_PERSIST=1` (a retired alias is also read) before 113 on target | Persist-on still cannot prove a private overlay book while legacy uniques collide |

## nav_history write order (provisional window)

`nav_history` is written by two jobs, not twice on one house run:

1. **commit `commit_io.book_portfolio`** may upsert a **provisional** arithmetic-chain
   NAV for the date. (Legacy `portfolio_materialize.py` has the same shape but is
   not on the daily path — do not reintroduce it.)
2. **`verify_nav_replay.py --write`**: the separate `research-metrics` job (`verify_nav_replay.py --write`) overwrites it with the Nautilus engine
   NAV — the sole source of truth (SSOT) for NAV.

Between those steps a dashboard reader that queries `nav_history` can see the
provisional value (the only enabled house job is `house-run-09` at 09:17 UTC
Monday; research-metrics / the engine NAV writer is 22:05 UTC daily). Treat a
date's `nav_history` row as provisional until the engine writer for that date
has completed; after the overwrite the engine NAV is authoritative. Do not
publish or quote the arithmetic-chain value as a settled NAV.

## Related

- Contracts: `digiquant/src/digiquant/dashboard/tenancy.py`
- Dashboard helper: `apps/dashboard/lib/house-workspace.ts`
- Schema / RLS notes: `digiquant/supabase/SCHEMA.md` (migrations 096–113)
- Settings / APP_URL paths: `digiquant/supabase/functions/_shared/app-url.ts`
  (`APP_URL` = site origin only; paths append `/dashboard/...`)
- Epic status: [`docs/agent-backlog/execution-tenancy/EPIC.md`](../agent-backlog/execution-tenancy/EPIC.md)
