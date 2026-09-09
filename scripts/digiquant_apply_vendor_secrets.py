#!/usr/bin/env python3
"""Push gitignored vendor env files onto core Edge Function secrets.

Default ``--check`` lists missing file/key *names* and exits 2 if anything
required is absent. ``--apply`` runs ``npx supabase secrets set`` then
redeploys billing/settings functions. Never prints secret values.

Usage (repo root)::

    PATH="$PWD/.venv/bin:$PATH" python scripts/digiquant_apply_vendor_secrets.py
    PATH="$PWD/.venv/bin:$PATH" python scripts/digiquant_apply_vendor_secrets.py --apply
"""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "digiquant" / "src"))

from digiquant.execution.vendor_secret_apply import (  # noqa: E402
    run_vendor_secret_apply,
)


def main() -> int:
    apply = "--apply" in sys.argv[1:]
    return run_vendor_secret_apply(
        repo_root=ROOT,
        apply=apply,
        log=lambda msg: print(msg, flush=True),
    )


if __name__ == "__main__":
    raise SystemExit(main())
