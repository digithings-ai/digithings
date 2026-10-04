"""DIG-337 guard: the retired provider key names stay out of the tree.

Chris asked on 2026-10-04 to remove the CoinGecko and Alpha Vantage keys and the tools
around them. Security verified on both branches that no code path reads either name, so
the remaining work was a set of *names* in configuration and documentation -- not a
pipeline read to be replaced.

This test is the acceptance criterion, made rerunnable: every remaining mention of either
vendor must fall in one of a small set of paths, and each of those paths must keep saying
*why* it is allowed. That second half matters most -- without it the allowlist silently
becomes a dumping ground and the next agent re-adds a server block "just for docs".

The five allowed paths are:

1. ``.gitleaks.toml``                     -- allowlist rules for history-only paths.
2. ``research/config/mcp.secrets.env.example`` -- the placeholder rows themselves. The
   credential guard (``scripts/check_example_credentials.py``) scans this file, so the
   rows stay; only the placeholder *values* are placeholders.
3. ``research/skills/crypto/SKILL.md``     -- asserts the loop has no such tool.
4. ``docs/ops/SECRETS_INVENTORY.md``       -- human lock; DIG-124 owns it.
5. ``embed-mcp-catalog.ts``                -- the keyless public CoinGecko endpoint in
   digichat. It is a chat feature, not a key, and is an EM decision (DIG-337).

The guard file itself is skipped: it has to spell the patterns out to search for them.
"""

from __future__ import annotations

import json
import re
import subprocess
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
GUARD_PATH = "tests/scripts/test_retired_provider_keys.py"

#: Matches every spelling of either vendor: coingecko, CoinGecko, COINGECKO_API_KEY,
#: ``alpha vantage``, ``alpha_vantage``, ``alpha-vantage``, ``alphavantage``.
PATTERN = re.compile(r"coingecko|alpha[\s_-]*vantage", re.IGNORECASE)

FRAGMENT = "digiquant/src/digiquant/research/config/mcp.claude-desktop.fragment.json"
EXAMPLE = "digiquant/src/digiquant/research/config/mcp.secrets.env.example"
SKILL_MD = "digiquant/src/digiquant/research/skills/crypto/SKILL.md"

#: path -> why a mention is allowed to survive. Every entry needs a reason.
ALLOWED: dict[str, str] = {
    ".gitleaks.toml": "allowlist rule for a history-only path",
    EXAMPLE: "placeholder rows kept so the credential guard keeps scanning the file",
    SKILL_MD: "states the loop has no such tool",
    "docs/ops/SECRETS_INVENTORY.md": "human lock; DIG-124 owns this file",
    "apps/digichat/src/components/stock/embed-mcp-catalog.ts": (
        "keyless public endpoint; digichat chat feature, EM-gated"
    ),
}

#: Servers removed from the fragment in DIG-337.
RETIRED_SERVERS = ("coingecko", "alpha-vantage")

#: Rows that must survive in the example file.
RETIRED_ROWS = ("COINGECKO_API_KEY", "ALPHA_VANTAGE_API_KEY")

pytestmark = pytest.mark.unit


def _hits() -> list[tuple[str, int, str]]:
    """(path, line number, line) for every vendor mention in a tracked file."""
    out = subprocess.run(
        ["git", "grep", "-n", "-i", "-E", r"coingecko|alpha[ _-]?vantage", "--", "."],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
        check=True,
    )
    found = []
    for raw in out.stdout.splitlines():
        path, lineno, line = raw.split(":", 2)
        if path == GUARD_PATH:
            continue  # this file names the patterns in order to search for them
        if PATTERN.search(line):
            found.append((path, int(lineno), line))
    return found


# ── the acceptance criterion ────────────────────────────────────────────────────


def test_no_vendor_mentions_outside_the_allowlist():
    """Every remaining mention lives in one of the five allowed paths."""
    offenders = [
        f"{p}:{n}: {line.strip()}"
        for p, n, line in _hits()
        if p not in ALLOWED
    ]
    assert not offenders, (
        "vendor names found outside the DIG-337 allowlist:\n  " + "\n  ".join(offenders)
    )


def test_every_allowed_path_is_still_allowed():
    """The allowlist is not padded with paths that no longer mention either vendor."""
    mentioned = {p for p, _, _ in _hits()}
    stale = set(ALLOWED) - mentioned
    assert not stale, (
        "allowlist entries with no remaining mention; drop them or restore the line:\n  "
        + "\n  ".join(f"{p} ({why})" for p, why in ALLOWED.items() if p in stale)
    )


def test_allowlist_entries_all_carry_a_reason():
    """Every exemption is documented, so a reviewer can audit it from the test alone."""
    assert all(why.strip() for why in ALLOWED.values())


# ── the allowlisted paths still say what they are supposed to say ───────────────


def test_fragment_is_valid_json_and_has_no_retired_servers():
    """The two server blocks are gone and the file still parses as JSON."""
    data = json.loads((REPO_ROOT / FRAGMENT).read_text())
    servers = data["mcpServers"]
    for name in RETIRED_SERVERS:
        assert name not in servers, f"{name} is still wired in {FRAGMENT}"
    # Sanity: the edit did not empty the file. DIG-335 also removed `fred`, so it
    # is no longer a valid witness here; pick servers that stay.
    assert "world-bank" in servers and "frankfurter-fx" in servers


def test_fragment_env_block_carries_no_vendor_variable():
    """No server block passes a vendor variable through to the IDE."""
    text = (REPO_ROOT / FRAGMENT).read_text()
    assert not PATTERN.search(text), f"{FRAGMENT} still references a vendor"


def test_example_keeps_its_placeholder_rows():
    """The rows stay (the credential guard scans this file) and stay placeholders."""
    lines = (REPO_ROOT / EXAMPLE).read_text().splitlines()
    assignments = dict(
        ln.split("=", 1)
        for ln in lines
        if ln.strip() and not ln.lstrip().startswith("#") and "=" in ln
    )
    for row in RETIRED_ROWS:
        assert row in assignments, f"{row} was dropped from {EXAMPLE}"
        value = assignments[row].strip()
        assert value.startswith("replace-with-"), (
            f"{row} must stay an obvious placeholder; found {value!r}"
        )


def test_example_no_longer_claims_a_server_exists():
    """The comments beside the retired rows must not promise an MCP server."""
    for raw in (REPO_ROOT / EXAMPLE).read_text().splitlines():
        if not raw.lstrip().startswith("#"):
            continue
        low = raw.lower()
        assert "required only if you use" not in low, raw
        assert "works with empty key" not in low, raw


def test_crypto_skill_still_states_there_is_no_tool():
    """SKILL.md must keep telling the agent the tool is absent."""
    text = (REPO_ROOT / SKILL_MD).read_text()
    assert "no CoinGecko tool" in text, "SKILL.md stopped stating there is no tool"


# ── negative controls: prove the scan actually detects the names ────────────────


@pytest.mark.parametrize(
    "line",
    [
        "COINGECKO_API_KEY=abc",
        "the Alpha Vantage key",
        "| `alpha-vantage` | `mcp_alpha-vantage_*` |",
        "@coingecko/coingecko-mcp",
    ],
)
def test_scan_detects_every_spelling(line):
    """Guards against a pattern that silently stops matching."""
    assert PATTERN.search(line), f"PATTERN failed to detect {line!r}"


def test_scan_ignores_unrelated_text():
    assert not PATTERN.search("| `fred` | `mcp_fred_*` | FRED series |")