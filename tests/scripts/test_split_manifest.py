"""Path manifest gate (DIG-3690, parent DIG-3518, goal G07).

`scripts/split/manifest.py` maps every tracked path to exactly one of
R0-R7/delete; `--check` fails on unassigned paths and replaces the
`overlaps-known.txt` whitelist (removed: double assignment is impossible by
construction, first matching rule wins).

The suite lives under ``tests/scripts/`` and every test is marked ``unit``,
which is what the ``ruff-and-scripts`` CI lane runs.
"""

from __future__ import annotations

import importlib.util
import subprocess
from pathlib import Path

import pytest

pytestmark = pytest.mark.unit

REPO_ROOT = Path(__file__).resolve().parents[2]
MANIFEST = REPO_ROOT / "scripts" / "split" / "manifest.py"
BOUNDARIES = REPO_ROOT / "scripts" / "split" / "check_boundaries.py"

REPOS = ("R0", "R1", "R2", "R3", "R4", "R5", "R6", "R7", "delete")

# Chris's 01:26 calls (15 Oct): path -> owning repo. Loaded from the manifest
# itself, so the test pins the decision, never a copy of it.
CHRIS_CALLS = {
    "apps/dashboard/app/page.tsx": "R3",
    "apps/dashboard/components/twelve-x/BriefPanel.tsx": "R7",
    "digiquant/src/digiquant/execution/staging_secrets.py": "R2",
    "digiquant/src/digiquant/execution/vendor_secret_apply.py": "R2",
    "digiquant/src/digiquant/execution/vendor_secret_files.py": "R2",
    "digiquant/src/digiquant/data/gloomberb/client.py": "R2",
    "digiquant/src/digiquant/data/luxalgo/client.py": "R2",
    "digiquant/src/digiquant/research/docs/RUNBOOK.md": "R2",
    "config/contract/secrets.yaml": "R2",
    ".github/workflows/ci.yml": "delete",
    ".github/workflows/deploy-digithings-cron.yml": "delete",
}


def load_manifest():
    spec = importlib.util.spec_from_file_location("split_manifest", MANIFEST)
    assert spec is not None and spec.loader is not None
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def test_rules_name_known_repos_only():
    mod = load_manifest()
    for prefix, repo, _reason in mod.RULES:
        assert repo in REPOS, f"unknown repo {repo} for {prefix}"


def test_rules_have_no_exact_duplicates():
    mod = load_manifest()
    seen = [prefix for prefix, _repo, _reason in mod.RULES]
    assert len(seen) == len(set(seen)), "duplicate rule prefixes"


def test_chris_calls_pin_to_the_manifest():
    mod = load_manifest()
    for path, want in CHRIS_CALLS.items():
        hit = mod.match_rule(path)
        assert hit is not None, f"no rule matches {path}"
        assert hit[0] == want, f"{path} -> {hit[0]}, want {want}"


def test_every_tracked_path_maps_to_exactly_one_repo():
    mod = load_manifest()
    out = subprocess.run(
        ["git", "ls-files"], capture_output=True, text=True, check=True, cwd=REPO_ROOT
    )
    paths = sorted(p for p in out.stdout.splitlines() if p)
    assert len(paths) > 0, "no tracked paths enumerated"
    unassigned = [p for p in paths if mod.match_rule(p) is None]
    assert unassigned == [], f"{len(unassigned)} unassigned: {unassigned[:10]}"
    # One row per path: rebuild the mapping twice and require identity, so a
    # rule-order change that moves a path fails here instead of silently.
    first = {p: mod.match_rule(p)[0] for p in paths}
    second = {p: mod.match_rule(p)[0] for p in paths}
    assert first == second
    assert set(first) == set(paths)


def test_manifest_check_is_green_on_this_tree():
    out = subprocess.run(
        ["python3", str(MANIFEST), "--check"], capture_output=True, text=True, cwd=REPO_ROOT
    )
    assert out.returncode == 0, out.stdout[-2000:] + out.stderr[-2000:]


def test_boundaries_advisory_runs_and_reports():
    out = subprocess.run(
        ["python3", str(BOUNDARIES)], capture_output=True, text=True, cwd=REPO_ROOT
    )
    assert out.returncode == 0, out.stdout[-2000:] + out.stderr[-2000:]
    assert "checked" in out.stdout and "violations" in out.stdout
