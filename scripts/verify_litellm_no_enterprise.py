#!/usr/bin/env python3
"""Assert a LiteLLM install carries none of BerriAI's proprietary tree (DIG-1780).

Chris ratified a red line on DIG-1768: LiteLLM from the Python package repository
only, never the official Docker image. The upstream ``enterprise/LICENSE.md`` grants
production use only to subscribers with an Enterprise seat licence; the upstream
``Dockerfile`` deliberately bakes the tree in:

    # enterprise/ is imported by source path at runtime (proxy_cli puts the working
    # directory on sys.path; litellm/proxy/hooks resolves enterprise.enterprise_hooks from it)
    COPY --from=builder /app/enterprise /app/enterprise

So the compliant image is one built from the MIT-licensed PyPI wheel. This script is
the check that keeps it honest. It runs in two places:

* as a ``RUN`` step in ``Dockerfile.litellm``, so a dirty image cannot be built at all;
* from ``scripts/check_litellm_vendor_boundary.sh`` against a pulled image, so a
  registry tag that was built elsewhere is still verified before we ship it.

What it rejects, and why each one matters:

``litellm-enterprise`` distribution
    The paid package. Its presence means somebody installed the enterprise wheel.

``enterprise`` importable package
    Upstream resolves ``enterprise.enterprise_hooks`` by source path, not by
    installed distribution. A stray ``enterprise/`` directory on ``sys.path`` is
    enough to turn the dev/test carve-out back into production use, even with no
    enterprise wheel anywhere. This is the check that matters most.

``<app>/enterprise`` directory
    The literal thing the upstream Dockerfile copies in. Checked by path, at the
    working directory and at the image root, so it is caught even when it is not
    importable.

``LITELLM_VERSION``
    When set, the installed ``litellm`` must match exactly. The pin is the whole
    point of the image; a drifting base would silently change what we ship.

Exit codes: ``0`` clean, ``1`` at least one finding, ``2`` litellm not importable.
"""

from __future__ import annotations

import json
import os
import sys
from importlib import metadata
from pathlib import Path

# Importing `litellm` is deliberately NOT done here: it is slow, it reads
# environment variables, and a licence check must not inherit that behaviour.
# Importlib.metadata reads the installed dist metadata directly.
LITELLM_DIST = "litellm"
ENTERPRISE_DIST_PREFIXES = ("litellm-enterprise", "litellm_enterprise")

# Paths the upstream Dockerfile copies the proprietary tree into.
APP_DIRS = (Path("/app"), Path(os.environ.get("HOME", "/root")))


def _dist_version(name: str) -> str | None:
    try:
        return metadata.version(name)
    except metadata.PackageNotFoundError:
        return None


def _enterprise_dirs_on_syspath() -> list[str]:
    """Every ``enterprise/`` directory that sits directly on sys.path.

    Direct child only, on purpose: a directory named ``enterprise`` that is not
    itself an import root cannot shadow the upstream import. Over-reporting here
    would train people to ignore the gate.
    """
    found: list[str] = []
    seen: set[Path] = set()
    for entry in sys.path:
        if not entry:
            continue
        root = Path(entry)
        try:
            candidate = root / "enterprise"
            if candidate in seen:
                continue
            seen.add(candidate)
            # resolve() so a symlinked site-packages does not report twice
            if candidate.resolve().is_dir():
                found.append(str(candidate))
        except OSError:
            # Unreadable sys.path entry (permissions, vanished mount) is not a finding.
            continue
    return found


def main() -> int:
    findings: list[dict[str, object]] = []

    version = _dist_version(LITELLM_DIST)
    if version is None:
        print(
            f"FAIL: distribution {LITELLM_DIST!r} is not installed in this image.",
            file=sys.stderr,
        )
        return 2

    expected = os.environ.get("LITELLM_VERSION", "").strip()
    if expected and version != expected:
        findings.append(
            {
                "kind": "pin-mismatch",
                "detail": f"installed {LITELLM_DIST}=={version}, image declares {expected}",
            }
        )

    for dist in metadata.distributions():
        raw = (dist.metadata["Name"] or "").strip().lower()
        if any(raw.startswith(prefix) for prefix in ENTERPRISE_DIST_PREFIXES):
            findings.append({"kind": "enterprise-distribution", "detail": raw})

    for path in _enterprise_dirs_on_syspath():
        findings.append({"kind": "enterprise-importable", "detail": path})

    for app_dir in APP_DIRS:
        candidate = app_dir / "enterprise"
        try:
            if candidate.is_dir():
                findings.append({"kind": "enterprise-directory", "detail": str(candidate)})
        except OSError:
            continue

    if findings:
        print(
            "FAIL: this LiteLLM image carries BerriAI proprietary code. "
            "Chris's red line on DIG-1768 permits the PyPI wheel only.",
            file=sys.stderr,
        )
        for finding in findings:
            print(f"  - {finding['kind']}: {finding['detail']}", file=sys.stderr)
        print(json.dumps(findings, indent=2), file=sys.stderr)
        return 1

    print(f"OK: litellm=={version}, no enterprise distribution, no enterprise/ directory.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
