#!/usr/bin/env python3
"""Compare the locked dependency closure against PyPI latest.

Reads `freshness-requirements.txt` (produced by `uv export`) and writes a
JSON report on stdout: {"table": <markdown>, "summary": <one line>}.

Visibility only. Nothing here changes a bound or bumps a version.

Two parsing hazards this script exists to handle:

1. `uv export` emits `name==version ; <PEP 508 marker>` for any package with
   a platform or python constraint. The marker must be split off before the
   version is parsed, or `packaging.version.parse` raises InvalidVersion and
   the whole run dies.
2. Some PyPI release histories contain legacy non-PEP440 versions (joblib
   '0.3.2d', pytz '2004d', regex '2013-02-16'). Those are skipped rather than
   aborting the scan.

Used by .github/workflows/pipeline-dependency-freshness.yml.
"""

from __future__ import annotations

import json
import re
import sys
import urllib.request
from pathlib import Path

from packaging.version import InvalidVersion
from packaging.version import parse as parse_version

REQUIREMENTS = Path("freshness-requirements.txt")

# `name==version ; marker` -> capture name and version only.
PIN_RE = re.compile(r"^([A-Za-z0-9._-]+)==([^;\s]+)")

# Marker for a package we could not compare. Emoji kept as escapes so the
# source stays ASCII and cannot drift on encoding.
UNKNOWN_ICON = "\u26a0\ufe0f"
MAJOR_ICON = "\U0001f534"
MINOR_ICON = "\U0001f7e1"
PATCH_ICON = "\U0001f7e2"
CURRENT_ICON = "\u2705"


def read_pinned(path: Path = REQUIREMENTS) -> dict[str, str]:
    """Map normalised package name -> locked version string."""
    pinned: dict[str, str] = {}
    with path.open(encoding="utf-8") as handle:
        for line in handle:
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            match = PIN_RE.match(line)
            if match:
                pinned[match.group(1).lower()] = match.group(2)
    return pinned


def latest_stable(releases: dict[str, list]) -> str | None:
    """Newest non-prerelease, non-dev release that parses as a version."""
    best = None
    for version in releases:
        try:
            parsed = parse_version(version)
        except InvalidVersion:
            # Legacy non-PEP440 version in the release history. Skip it.
            continue
        if parsed.is_prerelease or parsed.is_devrelease:
            continue
        if best is None or parsed > best:
            best = parsed
    return str(best) if best is not None else None


def fetch_latest(package: str, timeout: float = 10.0) -> str | None:
    """Latest stable version on PyPI, or None if it cannot be determined."""
    url = f"https://pypi.org/pypi/{package}/json"
    with urllib.request.urlopen(url, timeout=timeout) as response:
        data = json.load(response)
    return latest_stable(data.get("releases", {}))


def classify(locked_ver: str, latest_ver: str) -> tuple[str, str]:
    """Return (gap, icon) for a locked/latest pair."""
    try:
        locked = parse_version(locked_ver)
        newest = parse_version(latest_ver)
    except InvalidVersion:
        return "unknown", UNKNOWN_ICON
    if locked.major != newest.major:
        return "major", MAJOR_ICON
    if locked.minor != newest.minor:
        return "minor", MINOR_ICON
    if locked.micro != newest.micro:
        return "patch", PATCH_ICON
    return "current", CURRENT_ICON


def build_report(pinned: dict[str, str], latest: dict[str, str]) -> dict:
    """Assemble the markdown table and the one-line summary."""
    rows = []
    for package, locked_ver in sorted(pinned.items()):
        latest_ver = latest.get(package)
        if latest_ver is None:
            rows.append((package, locked_ver, "unknown", "unknown", UNKNOWN_ICON))
            continue
        gap, icon = classify(locked_ver, latest_ver)
        rows.append((package, locked_ver, latest_ver, gap, icon))

    lines = ["| package | locked | latest | gap |", "|---|---|---|---|"]
    for package, locked, newest, gap, icon in rows:
        lines.append(f"| {package} | {locked} | {newest} | {icon} {gap} |")

    def count(kind: str) -> int:
        return sum(1 for row in rows if row[3] == kind)

    summary = (
        f"**{count('major')} major**, {count('minor')} minor, "
        f"{count('patch')} patch, {count('current')} current, "
        f"{count('unknown')} unknown (of {len(rows)} packages)"
    )
    return {"table": "\n".join(lines), "summary": summary}


def main() -> int:
    pinned = read_pinned()
    print(f"Parsed {len(pinned)} pinned packages", file=sys.stderr)

    latest: dict[str, str] = {}
    for package in pinned:
        try:
            version = fetch_latest(package)
        except Exception as exc:  # noqa: BLE001 - one bad package must not kill the run
            print(f"Warning: failed to fetch {package}: {exc}", file=sys.stderr)
            continue
        if version:
            latest[package] = version

    json.dump(build_report(pinned, latest), sys.stdout)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())