"""Demo users and tenants (plan section 5).

The canonical form of this seed is SQL — `digiquant/supabase/seed.sql` —
because `supabase db reset` loads it after the production migrations
(digiquant/supabase/config.toml `[db.seed]`). This module is the Python
route to the same rows for a stack that is already running, and the single
definition both share is :func:`scripts.seed.portfolio`'s tenant table, so
the SQL and the client path cannot drift apart silently: the ids come from
:func:`stable_uuid` on the same inputs in both.

Idempotency: `workspaces` upserts on its `id` primary key and
`workspace_members` on `(workspace_id, user_id)`, so a re-run updates in
place. The `system` and `house` workspaces are deliberately absent: migration
096 already seeds them with their own deterministic ids and this seed must
not collide with them.
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from typing import Any

from scripts.seed.deterministic import DEFAULT_SEED, demo_email, require_local
from scripts.seed.portfolio import DEMO_USERS, DEMO_WORKSPACES, user_id, workspace_id

SUPABASE_SEED_SQL = os.path.join("digiquant", "supabase", "seed.sql")


@dataclass
class TenantResult:
    workspaces: int = 0
    members: int = 0
    documents: int = 0
    action: str = "skipped"
    detail: str = ""
    tables: dict[str, int] = field(default_factory=dict)


def rows(*, seed: int = DEFAULT_SEED) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    """Return ``(workspace_rows, member_rows)`` — the shared seed definition."""
    workspaces = [
        {
            "id": workspace_id(ws["slug"], seed=seed),
            "slug": ws["slug"],
            "type": ws["type"],
            "name": ws["name"],
        }
        for ws in DEMO_WORKSPACES
    ]
    members = [
        {
            "workspace_id": workspace_id(ws["slug"], seed=seed),
            "user_id": user_id(user["local"], seed=seed),
            "email": demo_email(user["local"]),
            "role": user["role"],
        }
        for ws in DEMO_WORKSPACES
        for user in DEMO_USERS
    ]
    return workspaces, members


def apply(
    *,
    seed: int = DEFAULT_SEED,
    supabase_url: str | None = None,
    service_key: str | None = None,
    documents: list[dict[str, Any]] | None = None,
) -> TenantResult:
    """Apply the tenant seed through the Supabase client, or report `skipped`.

    Refuses a non-loopback `supabase_url` outright: this is the one step that
    writes rows, and it must never be able to reach production.
    """
    workspaces, members = rows(seed=seed)
    if not supabase_url or not service_key:
        return TenantResult(
            action="skipped", detail="SUPABASE_URL / SUPABASE_SERVICE_ROLE_KEY not set"
        )
    require_local(supabase_url, what="tenant rows")

    from supabase import create_client  # deferred: only needed on this path

    client = create_client(supabase_url, service_key)
    ws_rows = client.table("workspaces").upsert(workspaces, on_conflict="id").execute().data
    client.table("workspace_members").upsert(
        [
            {"workspace_id": m["workspace_id"], "user_id": m["user_id"], "role": m["role"]}
            for m in members
        ],
        on_conflict="workspace_id,user_id",
    ).execute()
    doc_count = 0
    if documents:
        client.table("documents").upsert(
            [
                {
                    "workspace_id": d["workspace_id"],
                    "date": d["date"],
                    "document_key": d["document_key"],
                    "doc_type": d["doc_type"],
                    "payload": d["payload"],
                }
                for d in documents
            ],
            on_conflict="workspace_id,date,document_key",
        ).execute()
        doc_count = len(documents)
    return TenantResult(
        workspaces=len(ws_rows or workspaces),
        members=len(members),
        documents=doc_count,
        action="applied",
        detail=supabase_url,
        tables={
            "workspaces": len(ws_rows or workspaces),
            "workspace_members": len(members),
            "documents": doc_count,
        },
    )
