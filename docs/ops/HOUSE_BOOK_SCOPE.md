# House book scope (Group A)

Concise developer guide for **workspace-scoped private books**. Dense inventory
lives in [`digiquant/ARCHITECTURE.md`](../../digiquant/ARCHITECTURE.md)
(overlay / tenancy sections) and the [kairos-tenancy epic](../agent-backlog/kairos-tenancy/EPIC.md).

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

Minted by `digiquant.olympus.tenancy.house_workspace_id()` /
`system_workspace_id()`.

## How to pin (by layer)

### Python house readers / writers

```python
from digiquant.olympus.tenancy import eq_house_workspace, house_workspace_id

# Read — omitted id ⇒ house
q = eq_house_workspace(client.table("positions").select("*").eq("date", day))

# Write — stamp explicitly
row["workspace_id"] = str(house_workspace_id())
```

`resolved_workspace_id(None)` / blank also resolves to house. Overlay paths pass
an explicit workspace UUID and must not fall through to house.

### Research / MCP `query_data`

`HOUSE_BOOK_READ_TABLES` in `digiquant.olympus.atlas.data.queries` stamps house
when `eq` omits `workspace_id`. To read another book:

```python
query_data(client=client, table="positions", eq={"workspace_id": str(overlay_id), "date": day})
```

### Dashboard (TypeScript)

```ts
import { houseBook } from "@/lib/house-workspace";

const { data } = await houseBook(supabase, "positions").eq("date", asOf);
```

Do not `.from("positions").select(...).eq("date", …)` alone on Brief / Holdings /
Performance — migration 109 lets a Custom JWT SELECT house **or** own overlay.

### Atlas ops scripts

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
| Staged cutover **113** (drop legacy `UNIQUE(date)`) | Not auto-applied; do not copy to top-level or apply on `core` while `main` writers still upsert `on_conflict=date`. [#3331](https://github.com/digithings-ai/digithings/pull/3331) stamps house `workspace_id` on those writers but **does not** widen the conflict target. `pipeline-olympus.yml` checks out `ref: main` even when the schedule event is on default `develop`. |
| Main house GHA vs develop tenancy writers | Live cron executes **main**. Develop already stamps via `house_workspace_id()` and upserts `on_conflict=workspace_id,date` — that is not what the scheduled job runs. Do not assume a green develop unit run proves the house publish. |
| Booked positions, missing H9 ledger | Operator recovery: `python digiquant/scripts/atlas/recover_h9_ledger_commit.py --date YYYY-MM-DD` (then `--apply`). Reads house `positions` / `nav_history`; calls `append_commit_chain`. Do not re-run the LLM pipeline. Do not `workflow_dispatch`. |
| `DIGIQUANT_OVERLAY_PERSIST=1` (alias `OLYMPUS_OVERLAY_PERSIST`) before 113 on target | Persist-on still cannot prove a private overlay book while legacy uniques collide |

## Related

- Contracts: `digiquant/src/digiquant/olympus/tenancy.py`
- Dashboard helper: `frontend/dashboard/lib/house-workspace.ts`
- Schema / RLS notes: `digiquant/supabase/SCHEMA.md` (migrations 096–113)
- Settings / APP_URL paths: `digiquant/supabase/functions/_shared/app-url.ts`
  (`APP_URL` = site origin only; paths append `/dashboard/...`)
- Epic status: [`docs/agent-backlog/kairos-tenancy/EPIC.md`](../agent-backlog/kairos-tenancy/EPIC.md)
