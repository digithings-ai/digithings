#!/usr/bin/env python3
"""Unpack the tenant-files bundle the Worker put in the env (src/tenant-files.ts).

Reads DIGI_TENANT_FILES_PARTS and DIGI_TENANT_FILES_<n>, joins and decodes
base64 -> gzip -> JSON ``{path: text}``, and writes each file under the root
(argv[1], default /data/tenant-files). Only ``sites/<id>.md`` and
``pages/<id>/<name>.md`` are accepted; anything else is skipped with a note.
Never raises: a bad bundle writes nothing and exits 0 so the boot goes on (the
readers then see no files, which never widens what a tenant reaches).
"""

from __future__ import annotations

import base64
import gzip
import json
import os
import re
import sys
from pathlib import Path

_ID = r"[a-z0-9][a-z0-9-]{0,63}"
_SITE = re.compile(rf"^sites/{_ID}\.md$")
_PAGE = re.compile(rf"^pages/{_ID}/[a-z0-9][a-z0-9._-]{{0,199}}\.md$")
MAX_JSON_BYTES = 8 * 1024 * 1024


def unpack(env: dict[str, str], root: Path) -> tuple[int, int]:
    """Write the bundle's files under ``root``; return (written, skipped)."""
    try:
        parts = int(env.get("DIGI_TENANT_FILES_PARTS", "0"))
    except ValueError:
        return 0, 0
    if parts <= 0 or parts > 64:
        return 0, 0
    b64 = "".join(env.get(f"DIGI_TENANT_FILES_{i}", "") for i in range(parts))
    try:
        with gzip.GzipFile(
            fileobj=__import__("io").BytesIO(base64.b64decode(b64, validate=True))
        ) as gz:
            raw = gz.read(MAX_JSON_BYTES + 1)
        if len(raw) > MAX_JSON_BYTES:
            raise ValueError("bundle too large")
        files = json.loads(raw.decode("utf-8"))
    except Exception as exc:  # any bad bundle means no files
        print(f"tenant-files: bundle ignored ({type(exc).__name__})", file=sys.stderr)
        return 0, 0
    if not isinstance(files, dict):
        return 0, 0
    written = skipped = 0
    for rel, text in files.items():
        if (
            not isinstance(rel, str)
            or not isinstance(text, str)
            or not (_SITE.match(rel) or _PAGE.match(rel))
        ):
            skipped += 1
            continue
        dest = root / rel
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_text(text, encoding="utf-8")
        written += 1
    return written, skipped


def main() -> int:
    root = Path(sys.argv[1] if len(sys.argv) > 1 else "/data/tenant-files")
    try:
        written, skipped = unpack(dict(os.environ), root)
    except OSError as exc:
        print(f"tenant-files: write failed ({type(exc).__name__})", file=sys.stderr)
        return 0
    if written or skipped:
        print(f"tenant-files: wrote {written}, skipped {skipped}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(main())
