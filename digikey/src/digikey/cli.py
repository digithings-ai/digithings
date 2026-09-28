"""CLI for bootstrapping digikey keys and customer licenses (requires DB and env)."""

from __future__ import annotations

import argparse
import json
import os
import sys


def _build_parser() -> argparse.ArgumentParser:
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

    mint = sub.add_parser(
        "license-mint",
        help="Mint a customer license JWT and record it on the allowlist",
    )
    mint.add_argument("--customer", required=True, help="Customer slug, e.g. datatap")
    mint.add_argument(
        "--hosts",
        required=True,
        help="Comma-separated embed-parent hostnames",
    )
    mint.add_argument(
        "--term-days",
        type=int,
        default=90,
        dest="term_days",
        help="Commercial term length in days (1..180, default: 90)",
    )
    mint.add_argument(
        "--services",
        default=None,
        help="Comma-separated hosted-service scopes (omit when entitled)",
    )
    mint.add_argument("--label", default="", help="Owner note, stored on the row only")
    mint.add_argument(
        "--dry-run",
        action="store_true",
        dest="dry_run",
        help="Validate and print claims as JSON without signing or writing",
    )

    revoke = sub.add_parser(
        "license-revoke",
        help="Revoke a customer license by id (sets revoked_at)",
    )
    revoke.add_argument("--license-id", required=True, dest="license_id")
    return parser


def _cmd_issue_key(parser: argparse.ArgumentParser, args: argparse.Namespace) -> None:
    if not args.tenant.strip():
        parser.error("--tenant must not be empty")

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


def _cmd_license_mint(parser: argparse.ArgumentParser, args: argparse.Namespace) -> None:
    from digikey.jwt_issue import LICENSE_MAX_TERM_DAYS
    from digikey.licenses import parse_hosts, parse_services

    customer = args.customer.strip()
    if not customer:
        parser.error("--customer must not be empty")
    try:
        hosts = parse_hosts(args.hosts)
    except ValueError as exc:
        parser.error(str(exc))
    term_days: int = args.term_days
    if term_days < 1 or term_days > LICENSE_MAX_TERM_DAYS:
        parser.error(f"--term-days must be 1..{LICENSE_MAX_TERM_DAYS}")
    try:
        services = parse_services(args.services)
    except ValueError as exc:
        parser.error(str(exc))

    if not os.environ.get("DIGIKEY_DATABASE_URL"):
        print("DIGIKEY_DATABASE_URL required", file=sys.stderr)
        sys.exit(1)
    if not (os.environ.get("DIGIKEY_PRIVATE_KEY_PEM") or "").strip():
        print(
            "refusing to mint: DIGIKEY_PRIVATE_KEY_PEM is not set "
            "(a license signed by an ephemeral key can never verify)",
            file=sys.stderr,
        )
        sys.exit(1)

    from digikey.crypto_keys import load_or_create_signing_key
    from digikey.jwt_issue import build_license_claims, issue_license_token

    private_key, kid = load_or_create_signing_key()

    if args.dry_run:
        claims, _ = build_license_claims(
            customer_slug=customer,
            hosts=hosts,
            services=services,
            term_days=term_days,
        )
        print(json.dumps(claims, indent=2, sort_keys=True))
        return

    from digikey.db import init_db, session_factory
    from digikey.licenses import insert_license_row

    init_db()
    token, license_id, exp = issue_license_token(
        private_key,
        kid=kid,
        customer_slug=customer,
        hosts=hosts,
        services=services,
        term_days=term_days,
    )
    sf = session_factory()
    with sf() as session:
        insert_license_row(
            session,
            license_id=license_id,
            customer_slug=customer,
            hosts=hosts,
            services=services,
            expires_at=exp,
            label=args.label,
        )

    print(f"license_id={license_id}")
    print(f"customer={customer}")
    print(f"exp={exp}")
    print(f"license_jwt={token}")


def _cmd_license_revoke(parser: argparse.ArgumentParser, args: argparse.Namespace) -> None:
    license_id = (args.license_id or "").strip()
    if not license_id:
        parser.error("--license-id must not be empty")

    if not os.environ.get("DIGIKEY_DATABASE_URL"):
        print("DIGIKEY_DATABASE_URL required", file=sys.stderr)
        sys.exit(1)

    from digikey.db import init_db, session_factory
    from digikey.licenses import LicenseNotFoundError, revoke_license

    init_db()
    sf = session_factory()
    with sf() as session:
        try:
            already_revoked = revoke_license(session, license_id)
        except LicenseNotFoundError as exc:
            print(str(exc), file=sys.stderr)
            sys.exit(1)

    print(f"license_id={license_id}")
    print("revoked=true")
    print(f"already_revoked={'true' if already_revoked else 'false'}")


def main() -> None:
    parser = _build_parser()
    args = parser.parse_args()
    if args.cmd == "issue-key":
        _cmd_issue_key(parser, args)
    elif args.cmd == "license-mint":
        _cmd_license_mint(parser, args)
    elif args.cmd == "license-revoke":
        _cmd_license_revoke(parser, args)
    else:
        parser.error("unknown command")


if __name__ == "__main__":
    main()
