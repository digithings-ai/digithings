#!/usr/bin/env python3
"""Export FastAPI OpenAPI schemas to docs/openapi/<service>.json.

Usage:
  PATH="$PWD/.venv/bin:$PATH" python scripts/export_openapi.py
  PATH="$PWD/.venv/bin:$PATH" python scripts/export_openapi.py --check

--check regenerates in memory and exits non-zero if committed files differ.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
OUT_DIR = REPO_ROOT / "docs" / "openapi"

# Service → import path for FastAPI `app`
SERVICES: dict[str, str] = {
    "digikey": "digikey.server:app",
    "digigraph": "digigraph.server:app",
    "digiquant": "digiquant.server:app",
    "digisearch": "digisearch.server:app",
    "digismith": "digismith.server:app",
    "digivault": "digivault.server:app",
}


def _load_app(spec: str):
    module_path, attr = spec.split(":")
    mod = __import__(module_path, fromlist=[attr])
    return getattr(mod, attr)


def _schema_for(name: str) -> dict:
    # digisearch refuses to start without a backend unless stub is allowed.
    if name == "digisearch":
        os.environ.setdefault("DIGISEARCH_ALLOW_STUB", "1")
    # digikey may refuse startup without blocklist/DB in some envs — openapi()
    # does not run lifespan, but keep ephemeral key allowed for import side effects.
    if name == "digikey":
        os.environ.setdefault("DIGIKEY_ALLOW_EPHEMERAL_KEY", "1")
        os.environ.setdefault(
            "DIGIKEY_DATABASE_URL", "sqlite:////tmp/digikey-openapi-export.sqlite"
        )
    app = _load_app(SERVICES[name])
    return app.openapi()


def _dump(schema: dict) -> str:
    return json.dumps(schema, indent=2, sort_keys=True) + "\n"


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--check",
        action="store_true",
        help="Fail if docs/openapi/*.json differ from live app.openapi()",
    )
    parser.add_argument(
        "--service",
        action="append",
        choices=sorted(SERVICES),
        help="Limit to one or more services (default: all)",
    )
    args = parser.parse_args()
    names = args.service or sorted(SERVICES)
    OUT_DIR.mkdir(parents=True, exist_ok=True)

    drift = False
    for name in names:
        schema = _schema_for(name)
        text = _dump(schema)
        path = OUT_DIR / f"{name}.json"
        if args.check:
            if not path.is_file():
                print(f"MISSING {path}", file=sys.stderr)
                drift = True
                continue
            existing = path.read_text(encoding="utf-8")
            if existing != text:
                print(f"DRIFT {path}", file=sys.stderr)
                drift = True
            else:
                print(f"OK {path}")
        else:
            path.write_text(text, encoding="utf-8")
            print(f"WROTE {path}")

    return 1 if drift else 0


if __name__ == "__main__":
    raise SystemExit(main())
