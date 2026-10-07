"""Unit tests for scripts/check_gloomberb_ci_guard.py and its CI wiring (DIG-1322).

The guard only earns its keep if it is actually invoked, so these tests pin the
call site in ``.github/workflows/ci.yml`` and in the ``required-checks`` needs
list as well as the verdict logic. A guard that is never run detects nothing --
the same argument that ``test_check_deploy_freshness.py`` makes for the freshness
probe.

The verdict branches pinned here, offline:

* an enabling value in a **deployed** config fails (wrangler ``[vars]``, Dockerfile
  ``ENV``, a workflow ``env:`` block, a compose ``environment:`` entry);
* an enabling value in a **local** config passes -- that is the stated exemption
  the issue asks for, and it is asserted in code rather than left to prose;
* a **disabled** value anywhere passes, so defence in depth can stay committed;
* a commented-out line passes, including one that mentions an enabling value;
* a line whose *inline* comment mentions an enabling value passes;
* ``tests/`` and ``docs/`` prose and fixtures are never scanned;
* the enabling set is read from the client's ``_TRUTHY_ENV_VALUES``, so this
  guard and the runtime cannot drift apart;
* every tracked ``wrangler.*`` in the repo is claimed by ``DEPLOYED_PATTERNS`` --
  a new Cloudflare app must not land outside the guard unnoticed.
"""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path
from typing import Any  # score:allow untyped any -- dynamically loaded module

import pytest
import yaml

REPO_ROOT = Path(__file__).resolve().parents[2]
_SCRIPT = REPO_ROOT / "scripts" / "check_gloomberb_ci_guard.py"
_CI = REPO_ROOT / ".github" / "workflows" / "ci.yml"
_JOB = "gloomberb-ci-guard"

pytestmark = pytest.mark.unit


def _load_module() -> Any:
    spec = importlib.util.spec_from_file_location("check_gloomberb_ci_guard", _SCRIPT)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


@pytest.fixture(scope="module")
def guard() -> Any:
    return _load_module()


VALUES = frozenset({"1", "true", "yes", "on"})


def _scan(guard: Any, path: str, text: str) -> list[Any]:
    return guard.scan_text(path, text, VALUES)


# ── deployed: an enabling value fails ────────────────────────────────────────


@pytest.mark.parametrize(
    "line",
    [
        'GLOOMBERB_ENABLED = "1"',
        "GLOOMBERB_ENABLED = 'true'",
        'GLOOMBERB_ENABLED = "ON"',
        'GLOOMBERB_ENABLED = " Yes "',
        'GLOOMBERB_ENABLED="1"',
        "GLOOMBERB_ENABLED: 1",
        "- GLOOMBERB_ENABLED=true",
        "ENV GLOOMBERB_ENABLED=on",
        "export GLOOMBERB_ENABLED=1",
        '  "GLOOMBERB_ENABLED": "yes"',
    ],
)
def test_enabling_value_in_deployed_config_is_a_finding(guard: Any, line: str) -> None:
    findings = _scan(guard, "apps/x/wrangler.toml", f"[vars]\n{line}\n")
    assert len(findings) == 1, f"{line!r} should be caught in a deployed config"
    assert findings[0].deployed is True


def test_every_deployed_surface_is_scanned(guard: Any) -> None:
    line = 'GLOOMBERB_ENABLED = "1"'
    deployed_paths = [
        "apps/digithings-stack-cloudflare/wrangler.toml",
        "apps/digichat-cloudflare/wrangler.toml",
        "apps/digiquant-runner/wrangler.jsonc",
        "apps/dashboard-api/wrangler.toml",
        "digiquant/Dockerfile",
        "digivault/Dockerfile",
        "docker-compose.yml",
        ".github/workflows/ci.yml",
        ".github/workflows/nightly.yml",
    ]
    for path in deployed_paths:
        assert guard.is_deployed(path), f"{path} must count as a deployed surface"
        findings = _scan(guard, path, f"{line}\n")
        assert len(findings) == 1, f"{path} should be scanned for GLOOMBERB_ENABLED"


def test_nested_wrangler_and_two_level_dockerfile(guard: Any) -> None:
    assert guard.is_deployed("apps/group/sub/wrangler.toml")
    assert guard.is_deployed("apps/group/sub/wrangler.json")
    assert guard.is_deployed("apps/a/b/Dockerfile")


# ── local/dev exemption: the issue requires it, so it is asserted ────────────


@pytest.mark.parametrize(
    "path",
    [
        ".env",
        ".env.local",
        "docker-compose.override.yml",
        "compose/docker-compose.dev.yml",
        "dev/env.sh",
        "scripts/some_helper.sh",
    ],
)
def test_enabling_value_allowed_in_local_config(guard: Any, path: str) -> None:
    assert not guard.is_deployed(path)
    assert guard.is_local(path), f"{path} should be a local exemption"
    findings = _scan(guard, path, "GLOOMBERB_ENABLED=true\n")
    assert len(findings) == 1
    assert findings[0].deployed is False, "an exemption must be reported as non-blocking"


def test_local_exemption_still_reported(guard: Any) -> None:
    """An exemption that reported nothing would be indistinguishable from a bug."""
    rendered = guard.render(
        [guard.Finding(".env", 3, "GLOOMBERB_ENABLED=true", False)],
        [],
        "parsed from client.py",
        VALUES,
    )
    assert "local-ok" in rendered
    assert "PASS" in rendered


# ── disabled values, comments, and unrelated files pass ──────────────────────


@pytest.mark.parametrize(
    "line",
    [
        'GLOOMBERB_ENABLED = "0"',
        "GLOOMBERB_ENABLED = 'false'",
        "GLOOMBERB_ENABLED = 'no'",
        "GLOOMBERB_ENABLED = 'off'",
        'GLOOMBERB_ENABLED = ""',
        "GLOOMBERB_ENABLED =",
        '# GLOOMBERB_ENABLED = "1"',
        "  #GLOOMBERB_ENABLED=1",
        "# GLOOMBERB_ENABLED: true  # reference only",
        'GLOOMBERB_ENABLED = "0"  # was "1" in staging',
        'GLOOMBERB_ENABLED="0"   # intentionally off (DIG-1233)',
        'GLOOMBERB_SESSION_COOKIE = "abc"',
        'DIGIKEY_ALLOW_DEV_GLOBAL = "1"',
    ],
)
def test_disabled_commented_and_unrelated_lines_pass(guard: Any, line: str) -> None:
    findings = _scan(guard, "apps/x/wrangler.toml", f"{line}\n")
    assert findings == [], f"{line!r} must not be a finding"


def test_disabled_value_in_deployed_config_is_allowed(guard: Any) -> None:
    """Defence in depth: pinning the flag OFF in a deployed config must pass."""
    assert _scan(guard, "apps/x/wrangler.toml", 'GLOOMBERB_ENABLED = "0"\n') == []


@pytest.mark.parametrize(
    "path",
    [
        "tests/scripts/test_gloomberb_guard.py",
        "docs/ops/gloomberb-session-cookie.md",
        "digiquant/src/digiquant/data/gloomberb/client.py",
        "README.md",
        ".env.example",
        "apps/digichat/reference/assistant-ui-templates/x/Dockerfile",
        "node_modules/pkg/wrangler.toml",
    ],
)
def test_non_config_files_are_never_scanned(guard: Any, path: str) -> None:
    assert not guard.is_deployed(path)
    assert not guard.is_local(path)
    assert _scan(guard, path, 'GLOOMBERB_ENABLED = "1"\n') == []


def test_strip_inline_comment(guard: Any) -> None:
    assert guard.strip_inline_comment('"1"  # enable') == "1"
    assert guard.strip_inline_comment("'yes'") == "yes"
    assert guard.strip_inline_comment("on") == "on"
    assert guard.strip_inline_comment('"0"') == "0"


# ── the enabling set comes from the client, so the two cannot drift ───────────


def test_enabling_values_are_parsed_from_the_client(guard: Any) -> None:
    values, source = guard.enabling_values(REPO_ROOT / guard.CLIENT_REL)
    assert values == VALUES, "the guard must agree with the client on what enables the family"
    assert "parsed" in source


def test_enabling_values_fall_back_when_the_client_is_unreadable(
    guard: Any, tmp_path: Path
) -> None:
    missing = tmp_path / "gone" / "client.py"
    values, source = guard.enabling_values(missing)
    assert values == VALUES
    assert "fallback" in source, "a fallback must announce itself, not scan silently"


def test_enabling_values_fall_back_when_the_set_is_renamed(guard: Any, tmp_path: Path) -> None:
    renamed = tmp_path / "client.py"
    renamed.write_text("_SOMETHING_ELSE = frozenset({'1'})\n", encoding="utf-8")
    values, source = guard.enabling_values(renamed)
    assert values == VALUES
    assert "no _TRUTHY_ENV_VALUES" in source


def test_enabling_values_fall_back_when_the_set_is_empty(guard: Any, tmp_path: Path) -> None:
    empty = tmp_path / "client.py"
    empty.write_text("_TRUTHY_ENV_VALUES = frozenset()\n", encoding="utf-8")
    _, source = guard.enabling_values(empty)
    assert "empty" in source


# ── coverage self-check: the allowlist must not have holes ───────────────────


def test_every_tracked_wrangler_config_is_inside_the_guard(guard: Any) -> None:
    """A new Cloudflare app must not be able to land outside DEPLOYED_PATTERNS."""
    files = guard.tracked_files(REPO_ROOT)
    configs = [p for p in files if p.rsplit("/", 1)[-1] in guard.COVERAGE_FAMILIES]
    assert len(configs) >= 7, f"expected the repo's wrangler configs, found {configs}"
    assert guard.coverage_gaps(files) == [], (
        f"uncovered config files: {guard.coverage_gaps(files)} -- add them to DEPLOYED_PATTERNS"
    )


def test_coverage_gaps_detects_an_uncovered_config(guard: Any) -> None:
    gaps = guard.coverage_gaps(["infra/brand-new/wrangler.toml"])
    assert gaps == ["infra/brand-new/wrangler.toml"]


# ── the repo itself is clean today ───────────────────────────────────────────


def test_repo_passes(guard: Any) -> None:
    findings, gaps, values, _ = guard.scan(REPO_ROOT)
    deployed = [f for f in findings if f.deployed]
    assert gaps == []
    assert deployed == [], f"deployed findings on develop: {deployed}"
    assert values == VALUES


def test_main_exits_nonzero_on_a_deployed_finding(
    guard: Any, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """End-to-end on the real tree, with one enabling value injected."""
    findings = [guard.Finding("apps/x/wrangler.toml", 9, 'GLOOMBERB_ENABLED = "1"', True)]
    monkeypatch.setattr(guard, "scan", lambda *a, **k: (findings, [], VALUES, "test"))
    assert guard.main([]) == 1
    out = capsys.readouterr().out
    assert "DEPLOYED" in out


def test_main_exits_nonzero_on_a_coverage_gap(guard: Any, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        guard, "scan", lambda *a, **k: ([], ["infra/x/wrangler.toml"], VALUES, "test")
    )
    assert guard.main([]) == 1


def test_main_exits_zero_when_clean(
    guard: Any, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.setattr(guard, "scan", lambda *a, **k: ([], [], VALUES, "test"))
    assert guard.main([]) == 0
    assert "PASS" in capsys.readouterr().out


def test_warn_mode_reports_but_exits_zero(guard: Any, monkeypatch: pytest.MonkeyPatch) -> None:
    findings = [guard.Finding("apps/x/wrangler.toml", 9, 'GLOOMBERB_ENABLED = "1"', True)]
    monkeypatch.setattr(guard, "scan", lambda *a, **k: (findings, [], VALUES, "test"))
    assert guard.main(["--warn"]) == 0


def test_json_output(
    guard: Any, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    import json

    findings = [guard.Finding(".env", 2, "GLOOMBERB_ENABLED=1", False)]
    monkeypatch.setattr(guard, "scan", lambda *a, **k: (findings, [], VALUES, "test"))
    assert guard.main(["--json"]) == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["ok"] is True
    assert payload["enablingValues"] == sorted(VALUES)
    assert payload["findings"][0]["path"] == ".env"


# ── CI wiring: a guard that is never invoked detects nothing ──────────────────


def _ci() -> dict[str, Any]:
    doc = yaml.safe_load(_CI.read_text(encoding="utf-8"))
    assert isinstance(doc, dict)
    return doc


def test_ci_has_the_guard_job_and_calls_the_script() -> None:
    jobs = _ci()["jobs"]
    assert _JOB in jobs, f"ci.yml must define the {_JOB} job"
    steps = jobs[_JOB]["steps"]
    runs = "\n".join(str(s.get("run", "")) for s in steps)
    assert "scripts/check_gloomberb_ci_guard.py" in runs


def test_ci_guard_job_needs_no_install_step() -> None:
    """Stdlib-only: the job must not need pip or npm to run."""
    steps = _ci()["jobs"][_JOB]["steps"]
    runs = "\n".join(str(s.get("run", "")) for s in steps)
    for banned in ("pip install", "npm ci", "npm install", "uv run"):
        assert banned not in runs, f"the guard is stdlib-only; {banned!r} must not appear"


def test_guard_job_is_in_required_checks_needs() -> None:
    """Otherwise the guard can go red and still merge."""
    needs = _ci()["jobs"]["required-checks"]["needs"]
    flat: list[str] = []
    for item in needs:
        flat.extend(item if isinstance(item, list) else [item])
    assert _JOB in flat, f"{_JOB} must be in required-checks needs; got {flat}"
