"""Connectivity smoke for the LangGraph Postgres checkpointer (#665/#667).

Validates DIGI_CHECKPOINTER_POSTGRES_URI exactly as the chain uses it:
PostgresSaver.from_conn_string(uri) -> setup() (DDL: catches transaction-pooler / no
prepared statements / missing perms) -> get_tuple() (a read). Reachability is implicitly
tested (GitHub Actions is IPv4 — the session pooler must be used, not the direct host).

NEVER prints the URI (it embeds the password) — only an ok/fail verdict + error class.
Dispatch-only; not imported by runtime code.
"""

from __future__ import annotations

import os


def main() -> int:
    uri = os.environ.get("DIGI_CHECKPOINTER_POSTGRES_URI", "").strip()
    if not uri:
        print("FAIL: DIGI_CHECKPOINTER_POSTGRES_URI not set (add the secret first)")
        return 1
    # Surface only the host:port/user shape (no password) for a sanity hint.
    try:
        after_at = uri.split("@", 1)[1]
        print(f"target: …@{after_at}")  # host:port/db — no credentials
    except IndexError:
        print("target: <unparseable uri shape>")

    try:
        from langgraph.checkpoint.postgres import PostgresSaver
    except ImportError as exc:
        print(f"FAIL: langgraph-checkpoint-postgres not installed: {exc}")
        return 1

    try:
        cm = PostgresSaver.from_conn_string(uri)
        saver = cm.__enter__()
        try:
            saver.setup()  # DDL — fails on transaction pooler / no prepared stmts / no perms
            saver.get_tuple({"configurable": {"thread_id": "__conn_smoke__", "checkpoint_ns": ""}})
        finally:
            cm.__exit__(None, None, None)
    except Exception as exc:  # noqa: BLE001 — report the verdict, never leak the URI
        print(f"FAIL: {type(exc).__name__}: {str(exc)[:400]}")
        print(
            "Hints: use the SESSION pooler (port 5432, host …pooler.supabase.com), NOT the "
            "transaction pooler (6543) or the IPv6 direct host; URL-encode special chars in "
            "the password."
        )
        return 1

    print("OK: PostgresSaver connected, setup() + get_tuple() succeeded — checkpointer ready.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
