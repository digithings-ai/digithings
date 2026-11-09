"""Unit tests for scripts/write-build-info.sh and its build wiring (#1759).

Neither static export carried a build identity, so `smoke-site.yml` could not
tell a frozen Cloudflare Pages project from a healthy one. This writer emits the
stamp the freshness probe reads, for digiquant.io and digithings.ai alike. It
runs inside the Pages build image, so it is bash-only (python3 is not guaranteed
there) and it must never abort the build: every field degrades to "unknown"
rather than failing.

#6848 split this file by subject: it now tests only the R0 writer. The two
deploy-wiring halves live with the build scripts they read —
`test_write_build_info_digiquant.py` (R2 `scripts/build-digiquant.sh`) and
`test_write_build_info_digithings.py` (R4 `scripts/build-digithings.sh`).
"""

from __future__ import annotations

import json
import subprocess
from datetime import UTC, datetime
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
_WRITER = REPO_ROOT / "scripts" / "write-build-info.sh"

pytestmark = pytest.mark.unit


def _write(
    out: Path, site: str = "digiquant.io", env: dict[str, str] | None = None
) -> dict[str, str]:
    """Run the writer with a controlled environment and return the parsed stamp."""
    # Empty PATH-independent env plus PATH, so a stray CF_PAGES_* or GITHUB_* in
    # the developer's shell cannot silently change what the assertions see.
    child_env = {"PATH": "/usr/bin:/bin:/usr/local/bin", "HOME": str(out.parent)}
    child_env.update(env or {})
    result = subprocess.run(
        ["bash", str(_WRITER), str(out), site],
        capture_output=True,
        text=True,
        env=child_env,
        cwd=REPO_ROOT,
        check=True,
    )
    assert "build stamp:" in result.stdout
    return json.loads(out.read_text(encoding="utf-8"))


class TestWriter:
    def test_emits_a_parseable_stamp_with_every_field(self, tmp_path: Path) -> None:
        stamp = _write(tmp_path / "build-info.json")
        assert set(stamp) == {"site", "commit", "branch", "builder", "built_at"}
        assert stamp["site"] == "digiquant.io"
        built_at = datetime.strptime(stamp["built_at"], "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=UTC)
        # Freshly written, so it must read as fresh to check_deploy_freshness.
        assert abs((datetime.now(tz=UTC) - built_at).total_seconds()) < 300

    def test_cloudflare_pages_env_wins_over_github_and_git(self, tmp_path: Path) -> None:
        stamp = _write(
            tmp_path / "build-info.json",
            env={
                "CF_PAGES": "1",
                "CF_PAGES_COMMIT_SHA": "cf00ffee",
                "CF_PAGES_BRANCH": "main",
                "GITHUB_SHA": "ghaaaaaa",
                "GITHUB_REF_NAME": "develop",
            },
        )
        assert (stamp["commit"], stamp["branch"], stamp["builder"]) == (
            "cf00ffee",
            "main",
            "cloudflare-pages",
        )

    def test_github_actions_env_is_the_second_choice(self, tmp_path: Path) -> None:
        stamp = _write(
            tmp_path / "build-info.json",
            env={"GITHUB_ACTIONS": "true", "GITHUB_SHA": "ghaaaaaa", "GITHUB_REF_NAME": "develop"},
        )
        assert (stamp["commit"], stamp["branch"], stamp["builder"]) == (
            "ghaaaaaa",
            "develop",
            "github-actions",
        )

    def test_falls_back_to_git_and_reports_a_local_build(self, tmp_path: Path) -> None:
        stamp = _write(tmp_path / "build-info.json")
        assert stamp["builder"] == "local"
        # The repo checkout resolves; a tarball build would yield "unknown".
        assert stamp["commit"] != ""

    def test_hostile_env_values_cannot_break_the_json(self, tmp_path: Path) -> None:
        # An unescaped quote or backslash out of the build environment would emit
        # invalid JSON, which the probe would then report as a malformed stamp on
        # a perfectly healthy deploy. Values are allowlist-filtered instead.
        stamp = _write(
            tmp_path / "build-info.json",
            env={
                "CF_PAGES": "1",
                "CF_PAGES_BRANCH": 'ta"sk/x\\',
                "CF_PAGES_COMMIT_SHA": 'dead"beef',
            },
        )
        assert stamp["branch"] == "task/x"
        assert stamp["commit"] == "deadbeef"

    def test_substitution_syntax_is_stripped_not_evaluated(self, tmp_path: Path) -> None:
        # `$(...)` survives as its letters only — proof the value is filtered as
        # text and never re-evaluated by the shell. An evaluated value would read
        # "pwned"; an unfiltered one would break the JSON.
        stamp = _write(
            tmp_path / "build-info.json",
            env={"CF_PAGES": "1", "CF_PAGES_COMMIT_SHA": "$(echo pwned)"},
        )
        assert stamp["commit"] == "echopwned"

    def test_long_values_are_capped(self, tmp_path: Path) -> None:
        stamp = _write(
            tmp_path / "build-info.json",
            env={"CF_PAGES": "1", "CF_PAGES_BRANCH": "b" * 500},
        )
        assert len(stamp["branch"]) == 200

    def test_creates_missing_parent_directories(self, tmp_path: Path) -> None:
        out = tmp_path / "dist" / "nested" / "build-info.json"
        _write(out)
        assert out.is_file()

    def test_requires_both_arguments(self, tmp_path: Path) -> None:
        result = subprocess.run(
            ["bash", str(_WRITER), str(tmp_path / "build-info.json")],
            capture_output=True,
            text=True,
            cwd=REPO_ROOT,
            check=False,
        )
        assert result.returncode != 0
