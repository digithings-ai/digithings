"""DIG-83: config/mcp.secrets.env.example must survive the documented load sequence.

`digiquant/src/digiquant/research/config/MCP-SETUP.md` tells a developer to
copy the template to `mcp.secrets.env` and then run

    set -a && source config/mcp.secrets.env && set +a && cursor .

The template's `SEC_EDGAR_USER_AGENT` line was unquoted and carried spaces
and parentheses, so bash read it as an assignment followed by two command
words: it reported a syntax error and the variable came back empty. A
developer who followed the documented setup silently lost the SEC user-agent.

These tests pin the behaviour, not the placeholder text. They assert on
variable *lengths* and on the presence of a syntax error, never on values.
"""

from __future__ import annotations

import shutil
import subprocess
from pathlib import Path

import pytest

pytestmark = pytest.mark.unit

_REPO_ROOT = Path(__file__).resolve().parents[2]
_TEMPLATE = (
    _REPO_ROOT
    / "digiquant"
    / "src"
    / "digiquant"
    / "research"
    / "config"
    / "mcp.secrets.env.example"
)

# Every assignment the template is expected to export.
_TEMPLATE_KEYS = [
    "FRED_API_KEY",
    "COINGECKO_API_KEY",
    "ALPHA_VANTAGE_API_KEY",
    "SEC_EDGAR_USER_AGENT",
]


def _run_load_sequence(env_file: Path) -> subprocess.CompletedProcess[str]:
    """Run the MCP-SETUP.md load sequence and report each key's length.

    `$0` is the script name, `$1` the env file, the rest the key names.
    Printing lengths instead of values keeps placeholder text out of CI logs.
    """
    script = (
        'set -a; . "$1"; set +a; shift; '
        'for k in "$@"; do v="${!k-}"; printf "%s\\t%d\\n" "$k" "${#v}"; done'
    )
    return subprocess.run(
        ["bash", "-c", script, "bash", str(env_file), *_TEMPLATE_KEYS],
        capture_output=True,
        text=True,
        check=False,
    )


@pytest.fixture()
def filled_copy(tmp_path: Path) -> Path:
    """The template copied the way MCP-SETUP.md tells a developer to copy it."""
    copy = tmp_path / "mcp.secrets.env"
    shutil.copyfile(_TEMPLATE, copy)
    return copy


def test_template_is_valid_bash() -> None:
    result = subprocess.run(
        ["bash", "-n", str(_TEMPLATE)],
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 0, (
        f"{_TEMPLATE.name} is not valid bash: {result.stderr.strip()!r}"
    )


def test_template_load_sequence_raises_no_syntax_error(filled_copy: Path) -> None:
    result = _run_load_sequence(filled_copy)
    assert "syntax error" not in result.stderr, (
        f"sourcing {filled_copy.name} reported a syntax error: "
        f"{result.stderr.strip()!r}"
    )


def test_template_exports_every_key(filled_copy: Path) -> None:
    result = _run_load_sequence(filled_copy)
    assert result.returncode == 0, result.stderr
    lengths = dict(
        line.split("\t", 1) for line in result.stdout.splitlines() if "\t" in line
    )
    missing = [key for key in _TEMPLATE_KEYS if key not in lengths]
    assert not missing, f"template assigns nothing for {missing}: {result.stdout!r}"
    empty = [key for key in _TEMPLATE_KEYS if int(lengths[key]) == 0]
    assert not empty, (
        f"{empty} came back empty after sourcing; "
        f"lengths={ {k: lengths[k] for k in empty} }"
    )