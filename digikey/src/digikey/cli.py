"""CLI for bootstrapping DigiKey keys (requires running DB and env)."""

from __future__ import annotations

import argparse
import os
import sys


def main() -> None:
    parser = argparse.ArgumentParser(prog="digikey")
    sub = parser.add_subparsers(dest="cmd", required=True)

    issue = sub.add_parser("issue-key", help="Create a new API key and print it once")
    issue.add_argument("--tenant", required=True, help="Tenant slug")
    issue.add_argument("--label", default="", help="Human-readable label")
    issue.add_argument(
        "--scopes",
        default="*",
        help="Comma-separated scopes or * (default: *)",
    )
    issue.add_argument(
        "--kind",
        choices=("standard", "dev_global"),
        default="standard",
    )
    issue.add_argument("--project-id", default="", dest="project_id")
    issue.add_argument("--project-config-ref", default="", dest="project_config_ref")

    args = parser.parse_args()
    if args.cmd != "issue-key":
        parser.error("unknown command")

    os.environ.setdefault("DIGIKEY_DATABASE_URL", "")
    if not os.environ.get("DIGIKEY_DATABASE_URL"):
        print("DIGIKEY_DATABASE_URL required", file=sys.stderr)
        sys.exit(1)

    from digikey.db import init_db, session_factory
    from digikey.db_schema import ApiKeyRow
    from digikey.key_crypto import generate_raw_key, hash_secret
    from digikey.settings import allow_dev_global_keys

    if args.kind == "dev_global" and not allow_dev_global_keys():
        print("dev_global keys require DIGIKEY_ALLOW_DEV_GLOBAL=1", file=sys.stderr)
        sys.exit(1)

    init_db()
    raw, prefix = generate_raw_key()
    scopes_str: str = args.scopes.strip()
    scopes = ["*"] if scopes_str == "*" else [s.strip() for s in scopes_str.split(",") if s.strip()]
    if args.kind == "dev_global" and (not scopes or scopes == ["*"]):
        scopes = ["*"]

    row = ApiKeyRow(
        key_hash=hash_secret(raw),
        key_prefix=prefix,
        tenant_slug=args.tenant.strip(),
        project_id=(args.project_id or "").strip() or None,
        project_config_ref=(args.project_config_ref or "").strip() or None,
        scopes=scopes,
        kind=args.kind,
        label=(args.label or "").strip() or None,
    )
    sf = session_factory()
    with sf() as session:
        session.add(row)
        session.commit()
        session.refresh(row)

    print(f"id={row.id}")
    print(f"key_prefix={prefix}")
    print(f"api_key={raw}")


if __name__ == "__main__":
    main()
