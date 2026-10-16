"""Worker-side equivalents of the non-guard Postgres functions.

The ``reject_*_mutation`` guards live in ``d1_reject_guards.sql`` and the RLS
tenant-scoping surface in ``d1_authz_policies.py``. This module ports every
remaining Postgres function (census: 33 distinct functions in
``digiquant/supabase/migrations``) as either SQLite trigger SQL
(``d1_function_triggers.sql``) or plain Python operating on a DB-API
connection, so the D1/Worker path needs no Postgres.

Supersession note: ``plan_tier_rank``/``max_plan_tier`` were defined twice
(108 ``baseline/custom`` then 115 ``brief/desk/studio``). The 115 spelling is
the live one; the 108 tiers are NOT accepted here.

``search_architecture_notes`` is a deliberate approximation: Postgres ranks
with ``ts_rank`` over a ``tsvector`` column, which D1 has no equivalent of.
This port tokenises on non-alphanumerics and ranks by field-hit count, which
preserves ordering intent (more matches first, clamped 1..20 rows) without
claiming FTS parity.
"""

from __future__ import annotations

import re
import sqlite3
import uuid
from datetime import datetime, timedelta, timezone

# Workspaces this path must never attach a new user to (107).
_SYSTEM_WORKSPACE_IDS = frozenset(
    {
        "1105372f-4109-5815-be5a-21091ccfc8ad",
        "6b753576-ced9-5319-9bfa-c5d0aacd9319",
    }
)

# Live tier ladder (115). 108 spelled baseline/custom; superseded, not merged.
_PLAN_TIER_RANK = {
    "free": 0,
    "brief": 1,
    "desk": 2,
    "studio": 3,
    "enterprise": 4,
}


def plan_tier_rank(tier: str | None) -> int:
    """Rank a plan tier. Unknown/NULL tiers are ``free`` (rank 0)."""
    return _PLAN_TIER_RANK.get((tier or "free").lower(), 0)


def max_plan_tier(a: str | None, b: str | None) -> str:
    """Return the higher of two tiers, canonicalising unknown spellings."""
    winner = a if plan_tier_rank(a) >= plan_tier_rank(b) else b
    w = (winner or "free").lower()
    return w if w in _PLAN_TIER_RANK else "free"


def resolve_position_instrument(ticker: str) -> dict[str, str | None]:
    """Row values ``ensure_position_instrument()`` would insert for a ticker."""
    t = (ticker or "").strip().upper()
    if t == "CASH":
        return {
            "ticker": "CASH",
            "official_name": "Cash",
            "instrument_type": "CASH",
            "asset_class": "CASH",
            "category": "cash",
            "provider": "position-trigger",
            "provider_metadata": '{"resolution":"unresolved"}',
        }
    return {
        "ticker": t,
        "official_name": t,
        "instrument_type": None,
        "asset_class": "UNKNOWN",
        "category": "unknown",
        "provider": "position-trigger",
        "provider_metadata": '{"resolution":"unresolved"}',
    }


def ensure_personal_workspace(conn: sqlite3.Connection, user_id: str) -> str:
    """Return the user's workspace id, creating a personal one if needed."""
    if not user_id:
        raise ValueError("ensure_personal_workspace: user_id required")
    row = conn.execute(
        "SELECT workspace_id FROM workspace_members WHERE user_id = ?"
        " ORDER BY CASE WHEN role = 'owner' THEN 0 ELSE 1 END, created_at ASC"
        " LIMIT 1",
        (user_id,),
    ).fetchone()
    if row is not None:
        return row[0]

    slug = "u-" + user_id.replace("-", "")
    ws_id = "ws-" + uuid.uuid4().hex[:12]
    conn.execute(
        "INSERT OR IGNORE INTO workspaces (id, slug, type, name, plan_tier,"
        " subscription_status) VALUES (?, ?, 'user', 'Personal', 'free', 'none')",
        (ws_id, slug),
    )
    found = conn.execute("SELECT id FROM workspaces WHERE slug = ?", (slug,)).fetchone()
    if found is None:
        raise RuntimeError("ensure_personal_workspace: failed to resolve workspace")
    ws_id = found[0]
    if ws_id in _SYSTEM_WORKSPACE_IDS:
        raise ValueError("ensure_personal_workspace: refused system/house workspace")
    conn.execute(
        "INSERT OR IGNORE INTO workspace_members (workspace_id, user_id, role)"
        " VALUES (?, ?, 'owner')",
        (ws_id, user_id),
    )
    return ws_id


def ensure_my_workspace(conn: sqlite3.Connection, user_id: str | None) -> str:
    """Authenticated entry point: a NULL caller is refused, never defaulted."""
    if not user_id:
        raise ValueError("ensure_my_workspace: not authenticated")
    return ensure_personal_workspace(conn, user_id)


def handle_new_auth_user_workspace(conn: sqlite3.Connection, new_user_id: str) -> str:
    """Signup hook: provision the personal workspace for a new auth user."""
    return ensure_personal_workspace(conn, new_user_id)


def my_access(conn: sqlite3.Connection, user_id: str, email: str | None = None) -> dict:
    """Compose the ``my_access()`` payload for a user.

    ``email`` stands in for ``auth.users`` (absent from D1 by design); the
    caller passes the verified session email.
    """
    if not user_id:
        raise ValueError("my_access: authentication required")
    mail = (email or "").strip().lower()
    row = conn.execute(
        "SELECT wm.workspace_id, w.plan_tier FROM workspace_members wm"
        " JOIN workspaces w ON w.id = wm.workspace_id"
        " WHERE wm.user_id = ? AND w.type = 'user'"
        " ORDER BY wm.created_at ASC LIMIT 1",
        (user_id,),
    ).fetchone()
    ws_id = row[0] if row else None
    ws_tier = (row[1] if row and row[1] else "free") or "free"
    floor = None
    products: list[str] = []
    if mail:
        hit = conn.execute(
            "SELECT plan_floor FROM entitlement_grants WHERE email = ?", (mail,)
        ).fetchone()
        floor = hit[0] if hit else None
        products = sorted(
            r[0]
            for r in conn.execute(
                "SELECT product_key FROM client_product_grants WHERE email = ?",
                (mail,),
            )
        )
    if floor is not None and "fx_hub" not in products:
        products = sorted(products + ["fx_hub"])
    return {
        "email": mail or None,
        "workspace_id": ws_id,
        "workspace_plan_tier": ws_tier,
        "plan_floor": floor,
        "effective_plan_tier": max_plan_tier(ws_tier, floor),
        "products": products,
    }


def claim_prices_live_refresh(
    conn: sqlite3.Connection,
    min_age_seconds: int,
    now: datetime | None = None,
) -> bool:
    """Atomically claim the prices-live refresh lease.

    One conditional UPDATE decides the winner; returns True iff this caller
    owns the window. A bad ``min_age_seconds`` raises (fail closed) rather
    than silently opening or killing the feed.
    """
    if min_age_seconds is None or min_age_seconds < 1:
        raise ValueError(
            f"claim_prices_live_refresh: min_age_seconds must be >= 1, got {min_age_seconds}"
        )
    at = now or datetime.now(timezone.utc)
    if at.tzinfo is None:
        at = at.replace(tzinfo=timezone.utc)
    cutoff = (at - timedelta(seconds=min_age_seconds)).isoformat()
    cur = conn.execute(
        "UPDATE prices_live_lease SET claimed_at = ? WHERE id = 1 AND claimed_at < ?",
        (at.isoformat(), cutoff),
    )
    return cur.rowcount > 0


def prune_langgraph_checkpoints(
    conn: sqlite3.Connection,
    retain_days: int = 14,
    now: datetime | None = None,
) -> dict[str, int]:
    """Delete checkpointer rows for threads whose newest checkpoint is stale.

    A thread is stale iff its NEWEST parsable ``checkpoint -> 'ts'`` predates
    the window; threads with no parsable timestamp are retained.
    """
    if retain_days is None or retain_days < 1:
        raise ValueError(
            f"prune_langgraph_checkpoints: retain_days must be >= 1, got {retain_days}"
        )
    at = now or datetime.now(timezone.utc)
    if at.tzinfo is None:
        at = at.replace(tzinfo=timezone.utc)
    cutoff = at - timedelta(days=retain_days)
    newest: dict[str, datetime | None] = {}
    for thread_id, blob in conn.execute("SELECT thread_id, checkpoint FROM checkpoints"):
        ts = _parse_ts(blob)
        prev = newest.get(thread_id)
        if ts is not None and (prev is None or ts > prev):
            newest[thread_id] = ts
    stale = [t for t, ts in newest.items() if ts is not None and ts < cutoff]
    if not stale:
        return {
            "threads_pruned": 0,
            "checkpoints_deleted": 0,
            "writes_deleted": 0,
            "blobs_deleted": 0,
        }
    marks = ",".join("?" for _ in stale)
    writes = conn.execute(
        f"DELETE FROM checkpoint_writes WHERE thread_id IN ({marks})", stale
    ).rowcount
    blobs = conn.execute(
        f"DELETE FROM checkpoint_blobs WHERE thread_id IN ({marks})", stale
    ).rowcount
    checkpoints = conn.execute(
        f"DELETE FROM checkpoints WHERE thread_id IN ({marks})", stale
    ).rowcount
    return {
        "threads_pruned": len(stale),
        "checkpoints_deleted": checkpoints,
        "writes_deleted": writes,
        "blobs_deleted": blobs,
    }


def _parse_ts(blob: str | None) -> datetime | None:
    if not blob:
        return None
    m = re.search(r'"ts"\s*:\s*"([^"]+)"', blob)
    if not m:
        return None
    try:
        ts = datetime.fromisoformat(m.group(1).replace("Z", "+00:00"))
    except ValueError:
        return None
    if ts.tzinfo is None:
        ts = ts.replace(tzinfo=timezone.utc)
    return ts


_TOKEN_RE = re.compile(r"[a-z0-9]+")


def search_architecture_notes(
    conn: sqlite3.Connection,
    query: str,
    match_limit: int = 7,
    path_prefix: str | None = None,
) -> list[dict]:
    """Keyword search over architecture notes (FTS approximation, see module)."""
    tokens = _TOKEN_RE.findall((query or "").lower())
    if not tokens:
        return []
    limit = max(1, min(match_limit or 7, 20))
    prefix = (path_prefix or "").strip().strip("/")
    rows = conn.execute(
        "SELECT vault_path, title, note_type, summary, body_markdown,"
        " tags, wikilinks FROM architecture_notes"
    ).fetchall()
    scored = []
    for vault_path, title, note_type, summary, body, tags, wikilinks in rows:
        if prefix and not (vault_path == prefix or vault_path.startswith(prefix + "/")):
            continue
        hay = " ".join(
            str(v or "") for v in (vault_path, title, summary, body, tags, wikilinks)
        ).lower()
        hits = sum(1 for t in tokens if t in hay)
        if hits:
            scored.append(
                (
                    hits,
                    {
                        "vault_path": vault_path,
                        "title": title,
                        "note_type": note_type,
                        "summary": summary,
                        "body_markdown": body,
                        "tags": tags,
                        "wikilinks": wikilinks,
                        "rank": float(hits),
                    },
                )
            )
    scored.sort(key=lambda pair: pair[0], reverse=True)
    return [entry for _, entry in scored[:limit]]
