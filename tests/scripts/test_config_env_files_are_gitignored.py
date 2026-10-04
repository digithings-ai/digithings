"""DIG-83: the filled-in credential files under digiquant's research config are gitignored.

The root `.gitignore` carried `.env` and `.env*`, which match basenames that
*begin* with `.env`. `mcp.secrets.env`, `supabase.env` and `local.env` do
not, so all three real files were committable by accident while three places
in the repo asserted the opposite:

- `digiquant/src/digiquant/research/config/MCP-SETUP.md`
- `digiquant/src/digiquant/research/docs/ops/REPOSITORY-INVENTORY.md`
- `digiquant/scripts/research/audit_config_references.py`

One ignore rule makes those three assertions true. These tests are the pin:
the three real files must be ignored, the committed `.example` templates must
stay committable, and the placeholder guard must keep passing.
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import pytest

pytestmark = pytest.mark.unit

_REPO_ROOT = Path(__file__).resolve().parents[2]

_CONFIG_DIR = "digiquant/src/digiquant/research/config"

# Real, filled-in credential files. Referenced by path only: never read, never
# printed, never opened. `git check-ignore --no-index` answers from the
# ignore rules alone, so an absent file is fine.
_REAL_SECRET_FILES = [
    f"{_CONFIG_DIR}/mcp.secrets.env",
    f"{_CONFIG_DIR}/supabase.env",
    f"{_CONFIG_DIR}/local.env",
]

# The committed templates. These must stay committable or onboarding breaks.
_EXAMPLE_TEMPLATES = [
    f"{_CONFIG_DIR}/mcp.secrets.env.example",
    f"{_CONFIG_DIR}/local.env.example",
]

_GUARD = "scripts/check_example_credentials.py"


def _git(*args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["git", *args],
        cwd=_REPO_ROOT,
        capture_output=True,
        text=True,
        check=False,
    )


@pytest.mark.parametrize("path", _REAL_SECRET_FILES)
def test_filled_in_config_env_file_is_gitignored(path: str) -> None:
    result = _git("check-ignore", "-v", "--no-index", path)
    assert result.returncode == 0, (
        f"{path} is not gitignored, so a real credential file is committable. "
        f"stdout={result.stdout!r} stderr={result.stderr!r}"
    )
    source = result.stdout.split(":", 1)[0]
    assert Path(source).name == ".gitignore", (
        f"{path} is ignored by {source!r} rather than by the root .gitignore"
    )


@pytest.mark.parametrize("path", _EXAMPLE_TEMPLATES)
def test_example_template_is_not_gitignored(path: str) -> None:
    result = _git("check-ignore", "-v", "--no-index", path)
    assert result.returncode == 1, (
        f"{path} is gitignored by {result.stdout.strip()!r}; the template "
        "would stop being committable"
    )


@pytest.mark.parametrize("path", _EXAMPLE_TEMPLATES)
def test_example_template_is_tracked(path: str) -> None:
    result = _git("ls-files", "--error-unmatch", path)
    assert result.returncode == 0, f"{path} is not tracked: {result.stderr!r}"


def test_placeholder_guard_still_passes() -> None:
    result = subprocess.run(
        [sys.executable, str(_REPO_ROOT / _GUARD)],
        cwd=_REPO_ROOT,
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 0, f"{_GUARD} failed: {result.stdout}{result.stderr}"
    assert "OK" in result.stdout, f"{_GUARD} did not report OK: {result.stdout!r}"