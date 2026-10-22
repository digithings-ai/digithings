#!/usr/bin/env python3
"""The local-ci digiquant build gate must be the check, not a copy of a comment.

GitHub Actions is off. The workflow "Deploy: digiquant.io build check" was disabled
on 2026-10-14, so PRs touching the digiquant build inputs ran no build at all: the
check that proved the deploy path was alive only ran after the deploy had already
broken. `scripts/local-ci/local_ci.py` now carries that check (DIG-4871).

Two things have to hold for it to be the check:

1. the gate fires on every workspace the build compiles, and
2. the gate runs the build script and the assertions the disabled job ran.

(1) is asserted by the repo's own derived guard,
`tests/scripts/test_deploy_build_inputs.py`, which walks the build script's
workspace closure and now holds the live lane - this gate - to it. That file is
where a new build input fails until the gate learns about it, so this file does
not restate it.

(2) is behavioural and lives here: the gate function is called with a recording
`step`, so the steps it runs and the order it runs them in are asserted without
running a build.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]

pytestmark = pytest.mark.unit


def test_gate_watches_the_build_script_and_its_callees(local_ci_module: Any) -> None:
    """Watching the caller alone leaves the gap the check exists to close."""
    for path in (
        "scripts/build-digiquant.sh",
        "scripts/write-build-info.sh",
        "scripts/check_deploy_freshness.py",
    ):
        assert path in local_ci_module.DIGIQUANT_BUILD_PATTERNS, (
            f"{path} is not watched by the gate"
        )


def test_gate_watches_the_root_manifests(local_ci_module: Any) -> None:
    """The root install resolves every workspace before the site compiles.

    #1714 edited only the root pyproject.toml and froze digiquant.io for three
    days without any check running; #1949 changed only package-lock.json.
    """
    for path in ("package.json", "package-lock.json", "pyproject.toml"):
        assert path in local_ci_module.DIGIQUANT_BUILD_PATTERNS, (
            f"{path} is not watched by the gate"
        )


def test_gate_fires_on_a_digiquant_path_and_stays_quiet_elsewhere(
    local_ci_module: Any,
) -> None:
    patterns = local_ci_module.DIGIQUANT_BUILD_PATTERNS
    hit = local_ci_module.path_gate_hit(["apps/digiquant-web/app/page.tsx"], patterns)
    assert hit is not None
    assert hit[1] == "apps/digiquant-web/app/page.tsx"
    assert local_ci_module.path_gate_hit(["docs/ops/digithings-cron.md"], patterns) is None


def test_gate_runs_the_build_script_and_the_assertions(local_ci_module: Any) -> None:
    """The steps the disabled job ran, in the same order, on this lane."""
    calls: list[tuple[str, object]] = []

    def rec(name, cmd, timeout=1800, cwd=None):
        calls.append((name, cmd))
        return True

    assert local_ci_module.digiquant_build("/wt-4010", rec) == []
    names = [c[0] for c in calls]
    assert names == [
        "digiquant-build:pip-installable",
        "digiquant-build:build",
        "digiquant-build:dist-layout",
        "digiquant-build:build-stamp",
    ]
    build_cmd = calls[1][1]
    assert build_cmd == ["bash", "scripts/build-digiquant.sh"]
    layout = str(calls[2][1])
    for assertion in ("dist/index.html", "dist/CNAME", "dist/dashboard", "dist/build-info.json"):
        assert assertion in layout, f"the dist layout check lost {assertion}"
    assert "digiquant.io" in layout
    stamp = calls[3][1]
    assert stamp[0:2] == ["python3", "scripts/check_deploy_freshness.py"]
    assert "--body-file" in stamp and "dist/build-info.json" in stamp


def test_a_failed_build_stops_the_gate_before_the_layout_checks(local_ci_module: Any) -> None:
    """A build that failed proves nothing about the layout; the next steps must not run."""
    calls: list[str] = []

    def rec(name, cmd, timeout=1800, cwd=None):
        calls.append(name)
        return name != "digiquant-build:build"

    assert local_ci_module.digiquant_build("/wt-4010", rec) == ["digiquant-build:build"]
    assert calls == ["digiquant-build:pip-installable", "digiquant-build:build"]


def test_the_gate_does_not_depend_on_the_disabled_workflow_file() -> None:
    """Deleting the disabled workflow must not change the gate.

    The workflow stays disabled by decision. A gate that read its `paths:`
    filter from that file would lose its patterns the day the file is removed,
    and the build check would vanish silently - the same failure the disabled
    workflow itself caused.
    """
    source = (REPO_ROOT / "scripts" / "local-ci" / "local_ci.py").read_text(encoding="utf-8")
    assert "deploy-digiquant-cloudflare.yml" not in source
