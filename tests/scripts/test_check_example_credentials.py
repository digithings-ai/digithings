"""Unit tests for scripts/check_example_credentials.py (DIG-31).

This guard is the durable half of DIG-31: the credential *values* were scrubbed
from the tracked `.example` files in #5030 (DIG-41), but nothing stopped the
next person from pasting a real secret back into one. On develop the script
existed and no workflow ever ran it, so it could not fail a build.

These tests pin the three properties that make it worth wiring into CI:

* a clean tree passes,
* a planted non-placeholder credential value fails and is *named*,
* a value that is long enough but made of punctuation alongside letters — the
  shape a generated password actually has — is caught. Every original
  ``CRED_VALUE_PATTERNS`` entry matched alphanumerics only, so the class of
  secret this guard exists to catch slipped through it.

Fixtures live under ``tmp_path`` and the module's ``git ls-files`` call is
monkeypatched, so the real tree is never mutated and never scanned.
"""

from __future__ import annotations

import importlib.util
import subprocess
import types
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
_SCRIPT = REPO_ROOT / "scripts" / "check_example_credentials.py"

pytestmark = pytest.mark.unit

# Shapes match the length and alphabet of the credential values that were actually
# committed, rewritten here so nothing secret is reproduced in the test file.
# (Named generically on purpose: DIG-337 keeps the retired vendors' names out of
# the tree outside a five-path allowlist, and this file is not on it.)
ALNUM_SECRET = "k9Xq2mTv7LpZ4wRbNc8Jd3Fh6Sy1Au0Ge5"  # 32 alnum
SHORT_ALNUM_SECRET = "k9Xq2mTv7LpZ4wRb"  # 16 alnum — the original floor, reached
MIXED_SECRET = "kR7v!Qm2@XpL9#Td4$Wn8b"  # 20 alnum + punctuation


def _load_module():
    spec = importlib.util.spec_from_file_location("check_example_credentials", _SCRIPT)
    assert spec and spec.loader
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)  # type: ignore[union-attr]
    return mod


@pytest.fixture(scope="module")
def mod():
    return _load_module()


def _write(root: Path, rel: str, body: str) -> Path:
    p = root / rel
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(body)
    return p


# ── value classification ────────────────────────────────────────────────────


@pytest.mark.parametrize(
    "value",
    [
        ALNUM_SECRET,
        SHORT_ALNUM_SECRET,
        MIXED_SECRET,
        "ghp_0123456789abcdefghijklmnopqrstuvwxyz",
        "sk-0123456789abcdefghijklmnopqrstuvwx",
    ],
)
def test_real_secret_shapes_are_flagged(mod, value):
    assert mod.looks_cred_val(value) is True


@pytest.mark.parametrize(
    "value",
    [
        "replace-with-a-strong-password",
        "replace-with-openssl-rand-base64-32",
        "CHANGE_ME",
        "your-litellm-key-here",
        "your_litellm_key_here",
        "example-value-not-a-key",
        "test-value-not-a-key",
        "dummy-value-not-a-key",
        "<paste-key-here>",
        "TODO",
        "",
        # Below the 16-char floor, and not credential-shaped anyway.
        "digichat",
        "postgres",
        "short",
    ],
)
def test_placeholders_and_short_values_pass(mod, value):
    assert mod.looks_cred_val(value) is False


def test_punctuation_value_is_caught_not_just_alnum(mod):
    """The specific regression: MIXED_SECRET matches no original pattern."""
    assert not any(mod.re.match(p, MIXED_SECRET) for p in mod.CRED_VALUE_PATTERNS)
    assert mod.looks_cred_val(MIXED_SECRET) is True


def test_quoted_values_are_unwrapped_before_classification(mod):
    assert mod.looks_cred_val(f'"{MIXED_SECRET}"') is True
    assert mod.looks_cred_val(f"'{ALNUM_SECRET}'") is True


@pytest.mark.parametrize(
    "var",
    [
        "FRED_API_KEY",
        "EXAMPLE_VENDOR_API_KEY",
        "DIGICHAT_POSTGRES_PASSWORD",
        "AUTH_SECRET",
        "DIGIKEY_BFF_TOKEN",
        "CLIENT_SECRET",
        "REFRESH_TOKEN",
        "WEBHOOK_SECRET",
        "SIGNING_KEY",
    ],
)
def test_credential_variable_names_are_recognised(mod, var):
    assert mod.looks_cred_var(var) is True


@pytest.mark.parametrize(
    "var", ["DATABASE_URL", "DGI_URL", "DGI_ISSUER", "PORT", "HOST", "LLM_MODEL"]
)
def test_non_credential_variable_names_are_ignored(mod, var):
    assert mod.looks_cred_var(var) is False


# ── whole-script behaviour over a synthetic tracked tree ─────────────────────


def _run_main(mod, monkeypatch, tmp_path, files: dict[str, str], tracked=None):
    """Run ``main()`` against a fake tracked tree; return (exit_code, out, err)."""
    import io
    from contextlib import redirect_stderr, redirect_stdout

    for rel, body in files.items():
        _write(tmp_path, rel, body)
    listing = tracked if tracked is not None else list(files)
    # `subprocess.PIPE` is read as a call argument, so the stand-in needs it —
    # omitting it sends main() down its bare-rglob fallback and every test would
    # pass for the wrong reason.
    monkeypatch.setattr(
        mod,
        "subprocess",
        types.SimpleNamespace(PIPE=-1, run=lambda *a, **k: _Result(listing)),
    )
    monkeypatch.chdir(tmp_path)
    out, err = io.StringIO(), io.StringIO()
    with redirect_stdout(out), redirect_stderr(err):
        rc = mod.main()
    return rc, out.getvalue(), err.getvalue()


class _Result:
    def __init__(self, files):
        self.stdout = "\n".join(files)
        self.returncode = 0


def test_clean_tree_passes(mod, monkeypatch, tmp_path):
    rc, out, err = _run_main(
        mod,
        monkeypatch,
        tmp_path,
        {
            "infra/digichat-release/.env.profile-b.example": (
                "# template\n"
                "DIGICHAT_POSTGRES_PASSWORD=replace-with-a-strong-password\n"
                "DIGICHAT_AUTH_SECRET=replace-with-openssl-rand-base64-32\n"
            )
        },
    )
    assert rc == 0
    assert out.strip() == "OK"
    assert err == ""


def test_planted_secret_fails_and_names_file_and_var(mod, monkeypatch, tmp_path):
    rc, out, err = _run_main(
        mod,
        monkeypatch,
        tmp_path,
        {
            "infra/digichat-release/.env.profile-b.example": (
                f"PLANTED_SECRET_TOKEN={MIXED_SECRET}\n"
            )
        },
    )
    assert rc == 1
    assert "PLANTED_SECRET_TOKEN" in err
    assert ".env.profile-b.example" in err


def test_template_files_are_scanned_too(mod, monkeypatch, tmp_path):
    rc, _out, err = _run_main(
        mod, monkeypatch, tmp_path, {"infra/app.yaml.template": f"AUTH_SECRET={ALNUM_SECRET}\n"}
    )
    assert rc == 1
    assert "AUTH_SECRET" in err


def test_comments_and_blank_lines_are_ignored(mod, monkeypatch, tmp_path):
    rc, _out, _err = _run_main(
        mod,
        monkeypatch,
        tmp_path,
        {
            "a.env.example": (
                "# DIGICHAT_POSTGRES_PASSWORD=" + ALNUM_SECRET + "\n"
                "\n"
                "   # TOKEN=" + ALNUM_SECRET + "\n"
            )
        },
    )
    assert rc == 0


def test_untracked_files_are_not_scanned(mod, monkeypatch, tmp_path):
    rc, _out, _err = _run_main(
        mod,
        monkeypatch,
        tmp_path,
        {"a.env.example": f"API_KEY={ALNUM_SECRET}\n"},
        tracked=[],
    )
    assert rc == 0


def test_non_credential_vars_with_long_values_pass(mod, monkeypatch, tmp_path):
    rc, _out, _err = _run_main(
        mod,
        monkeypatch,
        tmp_path,
        {
            "a.env.example": (
                "DATABASE_URL=postgresql://digichat:digichat@127.0.0.1:5433/digichat\n"
                "DGI_URL=https://digikey.example.com\n"
                "ALLOWED_HOSTS=digithings.ai,www.digithings.ai,localhost\n"
            )
        },
    )
    assert rc == 0


# ── the properties this guard actually has on develop ────────────────────────


def test_develop_tree_has_no_non_placeholder_credential_values():
    """Scan the real tracked tree — the property DIG-31 asks to hold."""
    proc = subprocess.run(
        ["python3", str(_SCRIPT)],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
    )
    assert proc.returncode == 0, proc.stderr
    assert proc.stdout.strip() == "OK"


def test_a_workflow_actually_runs_this_guard():
    """The gap that made DIG-31 incomplete: the script had no caller.

    ``scripts/check_example_credentials.py`` shipped in #5030 and was never
    referenced by any workflow, so it could never fail a build.
    """
    workflows = REPO_ROOT / ".github" / "workflows"
    refs = [
        p.name
        for p in sorted(workflows.glob("*.yml"))
        if "check_example_credentials" in p.read_text()
    ]
    assert refs, (
        "no workflow runs scripts/check_example_credentials.py — the guard is "
        "dead code and a planted credential will pass CI"
    )
