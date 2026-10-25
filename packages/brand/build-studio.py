#!/usr/bin/env python3
"""Sync the brand-studio assets to the reference app's public mirror.

The canonical files live in ``packages/brand/studio/``. The reference app
serves them from ``apps/reference/public/brand/studio/`` so the studio page
can fetch the logo, wordmark, fields and preset data as ordinary static files.

Usage::

    python3 packages/brand/build-studio.py           # write the mirror
    python3 packages/brand/build-studio.py --check   # verify, write nothing
"""

from __future__ import annotations

import filecmp
import shutil
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SRC = ROOT / "packages" / "brand" / "studio"
DEST = ROOT / "apps" / "reference" / "public" / "brand" / "studio"
ASSET_SUFFIXES = {".svg", ".json"}


def assets() -> list[Path]:
    return sorted(p for p in SRC.iterdir() if p.is_file() and p.suffix in ASSET_SUFFIXES)


def check() -> int:
    ok = True
    expected = {p.name for p in assets()}
    for source in assets():
        target = DEST / source.name
        if not target.exists():
            print(f"❌  missing {target.relative_to(ROOT)}", file=sys.stderr)
            ok = False
        elif not filecmp.cmp(source, target, shallow=False):
            print(
                f"❌  {target.relative_to(ROOT)} is stale — re-run build-studio.py",
                file=sys.stderr,
            )
            ok = False
    if DEST.exists():
        for target in sorted(DEST.iterdir()):
            if (
                target.is_file()
                and target.suffix in ASSET_SUFFIXES
                and target.name not in expected
            ):
                print(
                    f"❌  {target.relative_to(ROOT)} has no source — remove it",
                    file=sys.stderr,
                )
                ok = False
    if ok:
        print(f"✅  brand studio mirror is current ({len(expected)} files)")
    return 0 if ok else 1


def write() -> int:
    DEST.mkdir(parents=True, exist_ok=True)
    expected = {p.name for p in assets()}
    for source in assets():
        target = DEST / source.name
        shutil.copy2(source, target)
        print(f"wrote {target.relative_to(ROOT)}")
    for target in sorted(DEST.iterdir()):
        if target.is_file() and target.suffix in ASSET_SUFFIXES and target.name not in expected:
            target.unlink()
            print(f"removed stale {target.relative_to(ROOT)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(check() if "--check" in sys.argv[1:] else write())
