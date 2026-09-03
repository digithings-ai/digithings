#!/usr/bin/env python3
"""Seal a gitignored BYOK LLM key onto a core overlay workspace.

Default ``--check`` exits 2 until ``.local/secrets/digithings-byok.env`` exists
with ``BYOK_PROVIDER`` + ``BYOK_API_KEY``. ``--apply`` writes one active
``workspace_provider_credentials`` row (fingerprint-only logs). Never prints
secret values. Refuses house/system and non-entitled workspaces.

Usage (repo root)::

    PATH="$PWD/.venv/bin:$PATH" python scripts/digiquant_seal_byok.py
    PATH="$PWD/.venv/bin:$PATH" python scripts/digiquant_seal_byok.py \\
        --apply --workspace-id <entitled-uuid>
"""

from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path
from uuid import UUID

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "digiquant" / "src"))

try:
    from supabase import create_client as _create_client
except ImportError:
    _create_client = None  # type: ignore[misc,assignment]

from digiquant.dashboard.overlay.byok_seal import (  # noqa: E402
    EXIT_BYOK_SEAL_FAILED,
    run_byok_seal,
)


def _client_from_env() -> object | None:
    url = (os.environ.get("CORE_SUPABASE_URL") or os.environ.get("SUPABASE_URL") or "").strip()
    key = (
        os.environ.get("CORE_SUPABASE_SERVICE_KEY")
        or os.environ.get("SUPABASE_SERVICE_ROLE_KEY")
        or ""
    ).strip()
    if not url or not key or _create_client is None:
        return None
    return _create_client(url, key)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--apply", action="store_true")
    parser.add_argument("--workspace-id", type=UUID, default=None)
    args = parser.parse_args(argv)
    client = _client_from_env() if args.apply else None
    if args.apply and client is None:
        print("BYOK seal blocked — store_not_configured", flush=True)
        return EXIT_BYOK_SEAL_FAILED
    return run_byok_seal(
        repo_root=ROOT,
        apply=args.apply,
        workspace_id=args.workspace_id,
        client=client,
        log=lambda msg: print(msg, flush=True),
    )


if __name__ == "__main__":
    raise SystemExit(main())
