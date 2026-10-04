"""Unit tests for scripts/check_example_credentials.py (follow-up to #5030).

The guard scans tracked .example/.template files for credential-shaped
values that are not obvious placeholders. PR #5030 (DIG-41) replaced the
committed credential values with placeholders; these tests pin the three
bypasses that survived that cleanup and would have let a real key
straight through again:

- CoinGecko-style ``CG-…`` keys — the hyphen escaped every value
  pattern,
- Alpha Vantage-style exactly-16-alphanumeric keys — below the old
  32-char bare-alphanumeric floor,
- product-name values (``PASSWORD=digichat``) — the soft allowlist
  excused them for credential-shaped variables.

Failing fixtures live in ``tmp_path`` only. Putting them in a tracked
.example/.template file is exactly what the guard exists to prevent.
"""

from __future__ import annotations

import importlib.util
import subprocess
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
_SCRIPT = REPO_ROOT / "scripts" / "check_example_credentials.py"

pytestmark = pytest.mark.unit


def _load_module():
    spec = importlib.util.spec_from_file_location("check_example_credentials", _SCRIPT)
    assert spec and spec.loader
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)  # type: ignore[union-attr]
    return mod


@pytest.fixture(scope="module")
def mod():
    return _load_module()


# ── variable-name classification ─────────────────────────────────────────


@pytest.mark.parametrize(
    "var",
    [
        "COINGECKO_API_KEY",
        "ALPHA_VANTAGE_API_KEY",
        "FRED_API_KEY",
        "PASSWORD",
        "AUTH_SECRET",
        "DIGIKEY_BFF_TOKEN",
        "WEBHOOK_SECRET",
    ],
)
def test_cred_var_detected(mod, var):
    assert mod.looks_cred_var(var)


@pytest.mark.parametrize(
    "var",
    [
        "DATABASE_URL",
        "DIGIGRAPH_HOST",
        "SEC_EDGAR_USER_AGENT",
        "NOTIFY_FROM",
        "DIGI_LLM_MODE",
    ],
)
def test_non_cred_var_not_detected(mod, var):
    assert not mod.looks_cred_var(var)


# ── the three closed bypasses ────────────────────────────────────────────


def test_coingecko_style_cg_key_is_detected(mod):
    assert mod.looks_cred_val("COINGECKO_API_KEY", "CG-abcdefghijklmnopqrstuvwx")


@pytest.mark.parametrize(
    "value",
    ["ABCDEFGHIJKLMNOP", "abcdefghijklmnop", "ABCDEF1234567890"],
)
def test_sixteen_char_alphanumeric_key_is_detected(mod, value):
    # Alpha Vantage keys are exactly 16 alphanumeric characters.
    assert mod.looks_cred_val("ALPHA_VANTAGE_API_KEY", value)


@pytest.mark.parametrize("value", ["digichat", "digiquant", "digithings"])
def test_product_name_password_is_detected(mod, value):
    # The product-name soft allowlist must not exempt
    # PASSWORD/SECRET-like variables.
    assert mod.looks_cred_val("PASSWORD", value)
    assert mod.looks_cred_val("SECRET", value)


@pytest.mark.parametrize("value", ['"digichat"', "'digichat'"])
def test_quoted_product_name_password_is_detected(mod, value):
    assert mod.looks_cred_val("PASSWORD", value)


# ── placeholders that must stay silent (no false positives) ─────────────


@pytest.mark.parametrize(
    "value",
    [
        "replace-with-your-fred-api-key",
        "your-litellm-key-here",
        "replace-me",
        "dev",
        "test",
        "local",
        "",
    ],
)
def test_placeholder_values_are_not_detected(mod, value):
    assert not mod.looks_cred_val("FRED_API_KEY", value)


@pytest.mark.parametrize("value", ["dev", "test"])
def test_generic_placeholder_password_is_not_detected(mod, value):
    # Documented dev defaults (DIGICHAT_DEV_PASSWORD=dev in the
    # repo's own .env.example) are still placeholders, not leaks.
    assert not mod.looks_cred_val("DIGICHAT_DEV_PASSWORD", value)


def test_short_values_are_not_detected(mod):
    assert not mod.looks_cred_val("PASSWORD", "short")
    assert not mod.looks_cred_val("API_KEY", "abc123")


def test_product_name_is_no_longer_a_placeholder(mod):
    # Mechanism behind the fix: a product name is not a placeholder;
    # the guard reports it for credential-shaped variables instead.
    assert not mod.is_placeholder("digichat")
    assert mod.is_placeholder("dev")
    assert mod.is_placeholder("replace-with-your-key")
    assert mod.is_placeholder("<your-key>")


# ── end-to-end main() ───────────────────────────────────────────────────


def _run_guard(mod, monkeypatch, files):
    """Run main() against synthetic tracked files instead of `git ls-files`."""

    def fake_git_ls_files(*args, **kwargs):
        return subprocess.CompletedProcess(
            args=[],
            returncode=0,
            stdout="\n".join(str(f) for f in files),
            stderr="",
        )

    monkeypatch.setattr(mod.subprocess, "run", fake_git_ls_files)
    return mod.main()


def test_main_fails_on_the_three_bypasses(mod, monkeypatch, tmp_path, capsys):
    fixture = tmp_path / "secrets.env.example"
    fixture.write_text(
        "# synthetic failing fixture — tests only, never a tracked file\n"
        "COINGECKO_API_KEY=CG-abcdefghijklmnopqrstuvwx\n"
        "ALPHA_VANTAGE_API_KEY=ABCDEFGHIJKLMNOP\n"
        "PASSWORD=digichat\n",
        encoding="utf-8",
    )
    assert _run_guard(mod, monkeypatch, [fixture]) == 1
    err = capsys.readouterr().err
    assert "COINGECKO_API_KEY" in err
    assert "ALPHA_VANTAGE_API_KEY" in err
    assert "PASSWORD" in err


def test_main_passes_on_placeholder_only_examples(mod, monkeypatch, tmp_path, capsys):
    fixture = tmp_path / "clean.env.example"
    fixture.write_text(
        "FRED_API_KEY=replace-with-your-fred-api-key\n"
        "COINGECKO_API_KEY=\n"
        "DIGICHAT_DEV_PASSWORD=dev\n"
        "# PASSWORD=digichat on a comment line is not a value\n",
        encoding="utf-8",
    )
    assert _run_guard(mod, monkeypatch, [fixture]) == 0
    assert capsys.readouterr().out.strip() == "OK"


@pytest.mark.skipif(
    not (REPO_ROOT / ".git").exists(),
    reason="needs a git checkout of the repo",
)
def test_guard_passes_on_the_repos_own_tracked_examples(mod, monkeypatch):
    # The hardened rules must not false-positive on the repo's own
    # tracked .example/.template files.
    monkeypatch.chdir(REPO_ROOT)
    assert mod.main() == 0
