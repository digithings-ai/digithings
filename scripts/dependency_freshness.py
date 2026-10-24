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
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

from packaging.version import InvalidVersion
from packaging.version import parse as parse_version

REQUIREMENTS = Path("freshness-requirements.txt")

# Concurrency for the PyPI read. PyPI serves this fine and asks only that we
# stay gentle; 16 is well inside that and turns an 8-minute scan into ~40s.
DEFAULT_WORKERS = 16

# `name==version ; marker` -> capture name and version only.
PIN_RE = re.compile(r"^([A-Za-z0-9._-]+)==([^;\s]+)")

# Marker for a package we could not compare. Emoji kept as escapes so the
# source stays ASCII and cannot drift on encoding.
UNKNOWN_ICON = "\u26a0\ufe0f"
# No stable release exists: the package has only ever shipped prereleases. This
# is not a failed comparison, so it must not share the `unknown` label.
NO_STABLE_ICON = "\U0001f7e3"
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


def _all_files_yanked(files: list) -> bool:
    """True only when PyPI told us every file in a release is yanked.

    PyPI yanks per file, so a release is only uninstallable when all of its
    files are. A release with no file list in the payload is NOT treated as
    yanked: absence of evidence is not a yank, and guessing here would silently
    drop versions the radar exists to report.
    """
    return bool(files) and all(file.get("yanked") for file in files)


def latest_stable(releases: dict[str, list]) -> str | None:
    """Newest installable, non-prerelease, non-dev release that parses."""
    best = None
    for version in releases:
        try:
            parsed = parse_version(version)
        except InvalidVersion:
            # Legacy non-PEP440 version in the release history. Skip it.
            continue
        if parsed.is_prerelease or parsed.is_devrelease:
            continue
        if _all_files_yanked(releases[version]):
            # Yanked releases cannot be installed, so calling one "latest"
            # points the radar at a version `uv add` would refuse. Verified
            # live: narwhals 2.27.0 has every file yanked while 2.26.0 is the
            # newest installable release.
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


def fetch_all(
    packages: list[str],
    workers: int = DEFAULT_WORKERS,
    timeout: float = 10.0,
) -> dict[str, str | None]:
    """Latest stable version per package, fetched concurrently.

    The return value distinguishes the two ways a comparison can fail, which is
    the whole point of returning ``None`` values rather than dropping the key:

    * present with a ``str`` -> PyPI answered, here is the latest stable release
    * present with ``None`` -> PyPI answered, and it has never shipped a stable
      release for this package (all six opentelemetry-instrumentation packages
      we lock are in this group, having only ever released betas)
    * absent -> we could not read PyPI at all for this package

    Sequential fetching was measured at 8m06s for this repo's 284-package
    closure, and six of its seven `unknown` rows were our own 10s read timeout
    firing under load rather than PyPI being unreachable. `unknown` means "could
    not compare", so the scan must not manufacture it by being slow. Concurrency
    narrows that window to near-nothing (three consecutive runs at 0) but does not
    remove it: the timeout is unchanged, and a review reproduced 6 self-inflicted
    `unknown`s at the same worker count under load. The pool is capped at
    DEFAULT_WORKERS because PyPI is a free public service.
    """
    if not packages:
        return {}

    def one(package: str) -> tuple[str, str | None] | None:
        try:
            return package, fetch_latest(package, timeout=timeout)
        except Exception as exc:  # one bad package must not kill the run
            print(f"Warning: failed to fetch {package}: {exc}", file=sys.stderr)
            return None

    with ThreadPoolExecutor(max_workers=max(1, min(workers, len(packages)))) as pool:
        results = list(pool.map(one, packages))
    return dict(result for result in filter(None, results))


def classify(locked_ver: str, latest_ver: str) -> tuple[str, str]:
    """Return (gap, icon) for a locked/latest pair."""
    try:
        locked = parse_version(locked_ver)
        newest = parse_version(latest_ver)
    except InvalidVersion:
        return "unknown", UNKNOWN_ICON
    if locked > newest:
        # Our locked version is newer than the newest installable release. The
        # only way that happens is a release we locked before it was yanked, so
        # there is nothing to upgrade to. Reporting a negative gap would read as
        # "we are behind", which is the opposite of the truth.
        return "current", CURRENT_ICON
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
        if package not in latest:
            rows.append((package, locked_ver, "unknown", "unknown", UNKNOWN_ICON))
            continue
        latest_ver = latest[package]
        if latest_ver is None:
            # A present-but-None value means PyPI answered and has only ever
            # shipped prereleases. All six opentelemetry-instrumentation packages
            # we lock are in this group, so they get the middle label. An absent
            # key (handled above) is the other failure: unreadable, or a project
            # that does not exist on PyPI at all — the issue body spells that out
            # because `unknown` covers both.
            rows.append((package, locked_ver, "no stable release", "no-stable", NO_STABLE_ICON))
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
        f"{count('no-stable')} no stable release, "
        f"{count('unknown')} unknown (of {len(rows)} packages)"
    )
    return {"table": "\n".join(lines), "summary": summary}


def main() -> int:
    pinned = read_pinned()
    print(f"Parsed {len(pinned)} pinned packages", file=sys.stderr)

    latest = fetch_all(sorted(pinned))

    json.dump(build_report(pinned, latest), sys.stdout)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
