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
* every tracked ``wrangler.*``, ``Dockerfile*`` and compose config in the repo is
  claimed by a rule -- a new Cloudflare app, a new ``Dockerfile.<target>`` or a new
  compose family must not land outside the guard unnoticed.

Dockerfile coverage is asserted with **this repo's real names**
(``digiquant/Dockerfile.mcp``, ``scripts/zammad_mcp/Dockerfile.mcp``,
``Dockerfile.digithings-stack-cloudflare``, ...). The first version of this suite
asserted only the bare ``Dockerfile`` name, which this repo does not use, so all of
it passed while 12 of the 20 tracked Dockerfiles -- every root deploy image among
them -- sat outside the guard. A synthetic ``apps/a/b/Dockerfile`` fixture cannot
catch that class of gap; the names below come from ``git ls-files``.
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
        # This repo names its build recipes Dockerfile.<target>; the bare
        # Dockerfile name is the minority case, not the convention.
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


# ── Dockerfiles named the way this repo actually names them ───────────────────
#
# The review that blocked the first version of this PR appended an enabling
# ``ENV`` to Dockerfile.digithings-stack-cloudflare and the guard passed: its
# patterns were ``*/Dockerfile`` and ``*/*/Dockerfile``, a literal filename match
# against a repo that names 12 of its 20 Dockerfiles ``Dockerfile.<target>``.
# Every assertion below uses a path from ``git ls-files``, so the same class of
# hole cannot be re-introduced by a name this repo never uses.


@pytest.mark.parametrize(
    "path",
    [
        # The five root deploy images, which a `*/Dockerfile` glob cannot reach at
        # all: with no directory component there is no `/` to anchor the glob on.
        "Dockerfile.digichat-cloudflare",
        "Dockerfile.digiquant-runner",
        "Dockerfile.digithings-stack-cloudflare",
        "Dockerfile.digitrace-langfuse-web",
        "Dockerfile.digitrace-langfuse-worker",
        # Nested targets.
        "digiquant/Dockerfile.mcp",
        "digiquant/Dockerfile.sandbox",
        "digivault/Dockerfile.mcp",
        # Under scripts/, which the local exemption covers by path.
        "scripts/zammad_mcp/Dockerfile.mcp",
        # Deeper than the two levels the old `*/*/Dockerfile` reached.
        "infra/containers/Dockerfile.digiclaw",
        "apps/digichat/Dockerfile.prod",
    ],
)
def test_dockerfile_target_naming_is_deployed(guard: Any, path: str) -> None:
    assert guard.is_deployed(path), f"{path} builds a deployed image; ENV is baked into it"
    findings = _scan(guard, path, "ENV GLOOMBERB_ENABLED=1\n")
    assert len(findings) == 1, f"{path} must catch an ENV-baked enabling value"
    assert findings[0].deployed is True


def test_a_bare_dockerfile_is_still_deployed(guard: Any) -> None:
    """The old glob's covered case must not regress while widening it."""
    for path in ("digiquant/Dockerfile", "apps/a/b/Dockerfile"):
        assert guard.is_deployed(path)
        assert _scan(guard, path, "ENV GLOOMBERB_ENABLED=1\n")[0].deployed is True


def test_local_exemption_cannot_claim_a_dockerfile(guard: Any) -> None:
    """scripts/ is local-exempt, but a recipe built there still ships its ENV."""
    assert guard.is_deployed("scripts/zammad_mcp/Dockerfile.mcp")
    assert not guard.is_local("scripts/zammad_mcp/Dockerfile.mcp")


def test_every_tracked_dockerfile_is_covered(guard: Any) -> None:
    """The repo-wide claim: no tracked Dockerfile may sit outside the guard."""
    files = guard.tracked_files(REPO_ROOT)
    dockerfiles = [p for p in files if guard.gap_family(p) == "dockerfile"]
    assert len(dockerfiles) >= 20, f"expected the repo's Dockerfiles, found {len(dockerfiles)}"
    uncovered = [
        p
        for p in dockerfiles
        if not (guard.is_deployed(p) or guard.is_local(p) or guard.is_ignored(p))
    ]
    assert uncovered == [], f"uncovered Dockerfiles: {uncovered}"


# ── compose: release and self-host deploy sets, plus the local override ───────


@pytest.mark.parametrize(
    "path",
    [
        "docker-compose.yml",
        "infra/self-host/compose.ghcr.yml",
        "infra/digichat-release/compose.digichat-release.yml",
        "infra/digichat-release/compose.profile-a.yml",
        "infra/digichat-release/compose.profile-b.yml",
        "infra/digichat-release/compose.profile-a-bundle.yml",
    ],
)
def test_compose_deploy_sets_are_deployed(guard: Any, path: str) -> None:
    assert guard.is_deployed(path), f"{path} starts containers; environment entries apply"
    findings = _scan(guard, path, "  - GLOOMBERB_ENABLED=true\n")
    assert len(findings) == 1
    assert findings[0].deployed is True


def test_the_root_override_stays_local(guard: Any) -> None:
    """LOCAL wins over the deployed compose glob — the override is layered locally.

    Widening the compose glob to basename matching must not capture
    docker-compose.override.yml, which docker compose layers on top of the deployed
    root stack at run time.
    """
    assert guard.is_deployed("docker-compose.yml")
    assert not guard.is_deployed("docker-compose.override.yml")
    assert guard.is_local("docker-compose.override.yml")


@pytest.mark.parametrize(
    "path",
    [
        "docker-compose.override.yml",
        "docker-compose.override.yaml",
        "apps/digitrace-langfuse/docker-compose.local.yml",
    ],
)
def test_local_compose_files_stay_local(guard: Any, path: str) -> None:
    assert guard.is_local(path), f"{path} is a local/dev compose file"
    assert not guard.is_deployed(path)
    assert _scan(guard, path, "  - GLOOMBERB_ENABLED=true\n")[0].deployed is False


def test_every_tracked_compose_file_is_covered(guard: Any) -> None:
    files = guard.tracked_files(REPO_ROOT)
    composes = [p for p in files if guard.gap_family(p) == "compose"]
    assert len(composes) >= 5, f"expected the repo's compose files, found {len(composes)}"
    uncovered = [
        p
        for p in composes
        if not (guard.is_deployed(p) or guard.is_local(p) or guard.is_ignored(p))
    ]
    assert uncovered == [], f"uncovered compose files: {uncovered}"


# ── .github/ config that carries env: outside .github/workflows/ ───────────────


def test_pipeline_env_file_outside_workflows_is_deployed(guard: Any) -> None:
    """`.github/digiquant-pipeline.yml` is loaded into $GITHUB_ENV by a workflow.

    Its `env:` block reaches a deployed pipeline, so it must be inside the guard
    even though path filtering on .github/workflows/ cannot see it.
    """
    path = ".github/digiquant-pipeline.yml"
    assert guard.is_deployed(path)
    findings = _scan(guard, path, '  GLOOMBERB_ENABLED: "1"\n')
    assert len(findings) == 1
    assert findings[0].deployed is True


def test_github_issue_templates_are_not_deploy_surfaces(guard: Any) -> None:
    for path in (".github/ISSUE_TEMPLATE/agent_task.yml", ".github/ISSUE_TEMPLATE/config.yml"):
        assert not guard.is_deployed(path), f"{path} is a PR form template, not a workflow"
        assert _scan(guard, path, 'GLOOMBERB_ENABLED: "1"\n') == []


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
        # NOT here: GLOOMBERB_SESSION_COOKIE used to be listed here as an
        # "unrelated line". DIG-2752 made it the opposite — a committed cookie
        # value is a finding in every file, this one included. Its cases live in
        # the cookie-half section below.
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
        # A compose file that is prose-in-a-template, not this repo's stack.
        "docs/templates/project/docker-compose.yml",
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
        f"uncovered config files: {guard.coverage_gaps(files)} -- claim them in a rule"
    )


@pytest.mark.parametrize(
    ("path", "family"),
    [
        ("infra/brand-new/wrangler.toml", "wrangler"),
        ("infra/brand-new/wrangler.jsonc", "wrangler"),
        ("deploy/nested/wrangler.json", "wrangler"),
    ],
)
def test_coverage_gaps_detects_an_uncovered_config(guard: Any, path: str, family: str) -> None:
    """A new deploy family must fail the build, not land quietly.

    coverage_gaps() originally only knew wrangler.*, so a Dockerfile or compose
    family added later escaped it — the exact failure mode the function exists to
    prevent.
    """
    gaps = guard.coverage_gaps([path])
    assert gaps == [guard.Gap(family=family, path=path)], f"{path} should be a {family} gap"


# Because the Dockerfile and compose families are matched by basename at any depth,
# a new file in either family is covered the moment it lands — coverage_gaps() has
# nothing left to catch there by construction. What it is left to catch is a
# regression in the patterns themselves, which is the hole this PR is fixing. These
# two tests are that claim, executed: they narrow DEPLOYED_BASENAMES back to the
# literal-filename match the first version shipped and assert the coverage check
# reports the real files that match would miss. If someone later re-narrows the
# patterns, these fail instead of the hole landing quietly.


def test_coverage_gaps_would_have_caught_the_bare_dockerfile_patterns(
    guard: Any, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Regressing to a literal-filename Dockerfile match must fail the build."""
    monkeypatch.setattr(guard, "DEPLOYED_BASENAMES", ("Dockerfile",))
    monkeypatch.setattr(guard, "NEVER_LOCAL_BASENAMES", ())
    gaps = {gap.path for gap in guard.coverage_gaps(guard.tracked_files(REPO_ROOT))}
    missed = {
        "Dockerfile.digichat-cloudflare",
        "Dockerfile.digiquant-runner",
        "Dockerfile.digithings-stack-cloudflare",
        "Dockerfile.digitrace-langfuse-web",
        "Dockerfile.digitrace-langfuse-worker",
        "digiquant/Dockerfile.mcp",
        "digiquant/Dockerfile.sandbox",
        "digivault/Dockerfile.mcp",
    }
    assert missed <= gaps, f"coverage_gaps missed {sorted(missed - gaps)}"
    # scripts/ is a local path prefix, so under the original design the zammad image
    # was silently claimed LOCAL instead of reported. NEVER_LOCAL_BASENAMES is what
    # stops that, and it is asserted directly in
    # test_local_exemption_cannot_claim_a_dockerfile.
    assert "scripts/zammad_mcp/Dockerfile.mcp" not in gaps


def test_a_dockerfile_is_deployed_even_with_no_pattern_listing_it(
    guard: Any, monkeypatch: pytest.MonkeyPatch
) -> None:
    """`Dockerfile*` is deployed by name, not by an entry in a pattern list.

    A Dockerfile is never a local file — ENV is baked into the image — so coverage
    cannot depend on someone remembering to add a glob for the new one.
    """
    monkeypatch.setattr(guard, "DEPLOYED_BASENAMES", ())
    monkeypatch.setattr(guard, "NEVER_LOCAL_BASENAMES", ("Dockerfile", "Dockerfile.*"))
    for path in ("Dockerfile.anything", "deep/nested/Dockerfile.worker"):
        assert guard.is_deployed(path), path
        assert guard.coverage_gaps([path]) == []


def test_coverage_gaps_would_have_caught_the_bare_compose_patterns(
    guard: Any, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(
        guard, "DEPLOYED_BASENAMES", ("Dockerfile", "Dockerfile.*", "docker-compose.yml")
    )
    gaps = {gap.path for gap in guard.coverage_gaps(guard.tracked_files(REPO_ROOT))}
    missed = {
        "infra/self-host/compose.ghcr.yml",
        "infra/digichat-release/compose.digichat-release.yml",
        "infra/digichat-release/compose.profile-a.yml",
        "infra/digichat-release/compose.profile-b.yml",
        "infra/digichat-release/compose.profile-a-bundle.yml",
        "infra/digichat-release/compose.profile-a-bundle.override.yml",
    }
    assert missed <= gaps, f"coverage_gaps missed {sorted(missed - gaps)}"
    # The local override is claimed by the exemption, so narrowing must not turn it
    # into a gap: it is a local file, not a missing deploy surface.
    assert "docker-compose.override.yml" not in gaps


@pytest.mark.parametrize(
    "path",
    [
        # Each of these is claimed by a rule, so none may be reported as a gap.
        "apps/x/wrangler.toml",
        "digiquant/Dockerfile",
        "digiquant/Dockerfile.mcp",
        "scripts/zammad_mcp/Dockerfile.mcp",
        "docker-compose.yml",
        "docker-compose.override.yml",
        "infra/self-host/compose.ghcr.yml",
        "apps/digichat/reference/assistant-ui-templates/x/Dockerfile",
    ],
)
def test_a_claimed_config_is_never_a_gap(guard: Any, path: str) -> None:
    assert guard.coverage_gaps([path]) == []


def test_coverage_gaps_is_sorted_by_family_then_path(
    guard: Any, monkeypatch: pytest.MonkeyPatch
) -> None:
    # Narrow the families so the paths below are genuinely unclaimed, then check the
    # ordering the report depends on.
    monkeypatch.setattr(guard, "DEPLOYED_BASENAMES", ("Dockerfile", "docker-compose.yml"))
    monkeypatch.setattr(guard, "NEVER_LOCAL_BASENAMES", ())
    gaps = guard.coverage_gaps(
        [
            "infra/b/Dockerfile.x",
            "infra/a/compose.b.yml",
            "infra/a/Dockerfile.y",
            "infra/b/wrangler.toml",
        ]
    )
    assert [(g.family, g.path) for g in gaps] == [
        ("compose", "infra/a/compose.b.yml"),
        ("dockerfile", "infra/a/Dockerfile.y"),
        ("dockerfile", "infra/b/Dockerfile.x"),
        ("wrangler", "infra/b/wrangler.toml"),
    ]


def test_coverage_families_widen_past_wrangler(guard: Any) -> None:
    labels = {label for label, _ in guard.COVERAGE_BASENAME_FAMILIES}
    assert labels == {"wrangler", "dockerfile", "compose"}


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
        guard,
        "scan",
        lambda *a, **k: ([], [guard.Gap("dockerfile", "infra/x/Dockerfile.mcp")], VALUES, "test"),
    )
    assert guard.main([]) == 1


def test_coverage_gap_render_names_the_family(guard: Any) -> None:
    rendered = guard.render(
        [], [guard.Gap("dockerfile", "infra/x/Dockerfile.mcp")], "parsed from client.py", VALUES
    )
    assert "COVERAGE GAP" in rendered
    assert "dockerfile" in rendered
    assert "infra/x/Dockerfile.mcp" in rendered


def test_json_output_carries_gap_families(
    guard: Any, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    import json

    monkeypatch.setattr(
        guard,
        "scan",
        lambda *a, **k: ([], [guard.Gap("compose", "infra/x/compose.y.yml")], VALUES, "test"),
    )
    assert guard.main(["--json"]) == 1
    payload = json.loads(capsys.readouterr().out)
    assert payload["ok"] is False
    assert payload["coverageGaps"] == [{"family": "compose", "path": "infra/x/compose.y.yml"}]


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


# ── DIG-2752: the cookie half ─────────────────────────────────────────────────
#
# The flag half above answers "is the family reachable?". These answer "is it
# authenticated, and is the credential safe where it lives?". Three checks, and
# each one has a negative control in the block below it: a rule that cannot be
# shown to fire measures nothing, which is the exact failure mode this suite was
# written to avoid in the first place.


COOKIE = "GLOOMBERB_SESSION_COOKIE"
SUBSTACK = "SUBSTACK_SESSION_COOKIE"

#: A value shaped like a real paste: the upstream ``name=value`` form, a
#: separator, and a high-entropy blob. The name is deliberately NEUTRAL rather
#: than the vendor's real cookie name, for two reasons that each cost a run to
#: learn:
#:   * `scripts/check_vendor_content.py` rules V3/V5 fire on the vendor's own
#:     storage-slot name, and this repo's vendor gate then fails the PR. That
#:     gate is right and this file must not argue with it.
#:   * the guard never pattern-matches the value -- it asks whether the value is
#:     a placeholder or a secret reference. A fixture pinned to the real name
#:     would keep passing if the guard grew a name-pattern arm, which would stop
#:     testing what it claims to test.
#: Nothing here inspects entropy; the point is that a real-looking value is
#: classified as a value.
REAL_COOKIE = "gl-session=Kx9pQm2vT7wR4yU8nB1sD5gF0hJ3lZ6aCeJ"


@pytest.mark.parametrize(
    ("name", "value"),
    [
        (COOKIE, REAL_COOKIE),
        (COOKIE, "gl-session=abc123def456ghi789"),
        (COOKIE, "bare-token-value"),
        (SUBSTACK, "substack.sid=eyJhbGciOiJIUzI1NiJ9abc"),
    ],
)
@pytest.mark.parametrize(
    "path",
    [
        "apps/digichat-cloudflare/wrangler.toml",
        "Dockerfile.digithings-stack-cloudflare",
        "docker-compose.yml",
        ".github/workflows/deploy-digithings-cloudflare.yml",
        ".env",
        ".env.local",
        "docker-compose.override.yml",
        "dev/env.sh",
        "scripts/some_helper.sh",
    ],
)
def test_committed_cookie_value_fails_everywhere(
    guard: Any, path: str, name: str, value: str
) -> None:
    """DIG-2752: a committed cookie is an exposure wherever it sits.

    The local paths are the point of the check. The local exemption exists so a
    developer can *run* the tools with their own cookie in an untracked ``.env``;
    it was never an authorisation to commit the credential that authenticates
    them. A tracked cookie in a local file is a leaked cookie, not a dev
    convenience, so there is no local pass for this kind.
    """
    findings = _scan(guard, path, f'{name} = "{value}"\n')
    kinds = [f.kind for f in findings]
    assert "cookie_value" in kinds, f"{path} must reject a committed {name}; got {kinds}"
    for finding in findings:
        if finding.kind == "cookie_value":
            assert guard.is_blocking(finding), "a cookie value blocks even in a local file"


@pytest.mark.parametrize(
    "value",
    [
        "",
        "<cookie-value>",
        "<paste-value-here>",
        "{paste-here}",
        "[redacted]",
        "REDACTED",
        "CHANGEME",
        "placeholder",
    ],
)
def test_placeholder_or_empty_cookie_value_passes(guard: Any, value: str) -> None:
    """A value the guard can *prove* is a stand-in is not a credential.

    An empty value passes in a local file (already tested above); in a deployed
    file it is caught by the plaintext-slot check instead, which is what makes
    that check worth having.
    """
    assert guard.is_placeholder(value) is True, value
    findings = _scan(guard, "dev/env.sh", f"{COOKIE}={value}\n")
    assert findings == [], f"{value!r} is a placeholder, not a cookie; got {findings}"


@pytest.mark.parametrize(
    "line",
    [
        f'{COOKIE} = "${{{{ secrets.{COOKIE} }}}}"',
        f'{COOKIE} = "${{{{ secrets.{SUBSTACK} }}}}"',
        f"{COOKIE}: env.{COOKIE}",
        f"{COOKIE} = os.environ.get('{COOKIE}', '')",
    ],
)
def test_a_deployed_config_may_name_the_cookie_through_a_secret(guard: Any, line: str) -> None:
    """The sanctioned shape must pass, or the guard would force people to invent one.

    A bare ``$NAME`` / ``${NAME}`` is deliberately NOT in this list. It is the
    shape a Dockerfile ``ENV`` uses to bake a shell passthrough into an image, and
    ``wrangler.toml`` does not expand shell variables at all — it would ship the
    literal string to the edge. A secret reference points at a store, not at a
    variable.
    """
    findings = _scan(guard, "apps/digichat-cloudflare/wrangler.toml", line + "\n")
    assert findings == [], f"{line!r} is a secret reference; got {findings}"


@pytest.mark.parametrize(
    "line",
    [
        f"{COOKIE} = $GLOOMBERB_SESSION_COOKIE",
        f"{COOKIE} = ${{GLOOMBERB_SESSION_COOKIE}}",
    ],
)
def test_a_shell_passthrough_is_not_a_secret_reference(guard: Any, line: str) -> None:
    """Fail-closed: the guard cannot tell where ``$NAME`` came from, so it refuses it.

    This is a judgement call and it is recorded as one, because the alternative
    reading — "$NAME is an indirection, therefore it is fine" — is what lets a
    Dockerfile bake a cookie into a layer. The sanctioned forward is ``env.NAME``
    (a Worker binding) or ``${{ secrets.NAME }}``.
    """
    assert guard.is_secret_reference(line.split("=", 1)[1].strip()) is False, line
    findings = _scan(guard, "Dockerfile.digithings-stack-cloudflare", line + "\n")
    kinds = [f.kind for f in findings]
    assert kinds == ["cookie_value"], f"{line!r} must fail; got {kinds}"


@pytest.mark.parametrize(
    "line",
    [
        f'{COOKIE} = ""',
        f"{COOKIE} =",
        f"{COOKIE}=",
        f'{COOKIE} = "<cookie-value>"',
        f"{COOKIE} = CHANGEME",
    ],
)
def test_a_deployed_plaintext_cookie_slot_fails_even_when_empty(guard: Any, line: str) -> None:
    """The empty-slot case the cookie-value check cannot see.

    ``GLOOMBERB_SESSION_COOKIE = ""`` in ``[vars]`` leaks nothing today and is
    still wrong: it is a slot in git that invites the value, and a per-deployer
    secret belongs in ``wrangler secret put`` / ``secrets.*``.
    """
    findings = _scan(guard, "apps/digichat-cloudflare/wrangler.toml", line + "\n")
    kinds = [f.kind for f in findings]
    assert "plaintext_cookie_slot" in kinds, f"{line!r} must fail; got {kinds}"
    assert all(guard.is_blocking(f) for f in findings)


@pytest.mark.parametrize(
    "line",
    [
        f"{COOKIE} = {REAL_COOKIE}",
        "GLOOMBERB_ENABLED=1",
    ],
)
@pytest.mark.parametrize(
    "path",
    [
        "apps/digichat-cloudflare/wrangler.toml",
        "Dockerfile.digithings-stack-cloudflare",
        "docker-compose.yml",
        ".github/workflows/deploy-digithings-cloudflare.yml",
        ".env",
        "docker-compose.override.yml",
    ],
)
def test_a_workflow_env_block_cannot_hold_a_cookie_either(guard: Any, path: str, line: str) -> None:
    """A workflow ``env:`` block is a deployed surface: it runs in CI and in deploys."""
    assert guard.is_deployed(path) or guard.is_local(path), path
    findings = _scan(guard, path, f"        {line}\n")
    assert findings, f"{line!r} in {path} must be caught"


@pytest.mark.parametrize(
    "line",
    [
        'GLOOMBERB_ENABLED: "${{ vars.GLOOMBERB_ENABLED }}"',
        "GLOOMBERB_ENABLED: $GLOOMBERB_ENABLED",
        "GLOOMBERB_ENABLED = ${GLOOMBERB_ENABLED}",
        "GLOOMBERB_ENABLED = $GLOOMBERB_ENABLED",
        "GLOOMBERB_ENABLED = env.GLOOMBERB_ENABLED",
        "GLOOMBERB_ENABLED = process.env.GLOOMBERB_ENABLED",
        "GLOOMBERB_ENABLED = os.environ.get('GLOOMBERB_ENABLED')",
    ],
)
def test_a_deployed_config_advertising_without_a_secret_fails(guard: Any, line: str) -> None:
    """A repository variable is a settings field, not a secret store.

    This is the "advertises the tools without a secret" case. A literal enabling
    value is already caught by the original rule; what only this one sees is a
    family switched on through an indirection, with nothing in the file that
    supplies the cookie through a secret store.
    """
    findings = _scan(guard, "apps/digichat-cloudflare/wrangler.toml", line + "\n")
    kinds = [f.kind for f in findings]
    assert "advertised_without_secret" in kinds, f"{line!r} must fail; got {kinds}"


def test_advertising_with_a_secret_slot_in_the_file_passes(guard: Any) -> None:
    """The fix the rule points at has to be reachable, or the rule is a dead end."""
    text = (
        'GLOOMBERB_ENABLED: "${{ vars.GLOOMBERB_ENABLED }}"\n'
        f"# npx wrangler secret put {COOKIE}\n"
    )
    findings = _scan(guard, "apps/digichat-cloudflare/wrangler.toml", text)
    assert findings == [], (
        f"a file that names wrangler secret put {COOKIE} supplies it; got {findings}"
    )


def test_an_indirect_flag_in_a_local_config_is_not_deployed(guard: Any) -> None:
    """Local stays local: the exemption is about deployment, not about indirection."""
    findings = _scan(guard, ".env.local", "GLOOMBERB_ENABLED=$GLOOMBERB_ENABLED\n")
    assert findings == [], f"a local config is not a deployed surface; got {findings}"


def test_a_literal_enabling_value_is_still_reported_as_enabled(guard: Any) -> None:
    """The original rule keeps its own kind, so its reason string is unchanged."""
    findings = _scan(guard, "apps/digichat-cloudflare/wrangler.toml", 'GLOOMBERB_ENABLED = "1"\n')
    assert [f.kind for f in findings] == ["enabled"]


def test_cookie_names_are_the_two_the_client_reads(guard: Any) -> None:
    """The names are a contract with the runbook, so they are asserted, not implied."""
    assert set(guard.COOKIE_VARS) == {COOKIE, SUBSTACK}
    text = (REPO_ROOT / "digiquant/src/digiquant/data/gloomberb/client.py").read_text(
        encoding="utf-8"
    )
    for name in guard.COOKIE_VARS:
        assert f'"{name}"' in text, f"{name} is not an env name the client reads"


def test_the_runbook_and_this_guard_agree_on_the_cookie_names(guard: Any) -> None:
    """Cross-check against the sibling suite rather than duplicating its list.

    The runbook suite pins the Gloomberb names an operator-facing document may
    carry. This guard has its own list because it answers a different question
    (what must never be *committed*, not what may be *written about*), and the
    two are only kept honest if something asserts they agree.
    """
    from tests.scripts.test_gloomberb_session_cookie_runbook import (
        ALLOWED_ENV_NAMES,
    )

    # ALLOWED_ENV_NAMES is scoped to `GLOOMBERB_*` names (the sibling suite's own
    # regex only matches that prefix), so the cross-check can only speak for the
    # GLOOMBERB half. SUBSTACK_SESSION_COOKIE is held to the client's constants
    # by test_cookie_names_are_the_two_the_client_reads instead.
    gloomberb_names = {n for n in guard.COOKIE_VARS if n.startswith("GLOOMBERB_")}
    assert gloomberb_names <= ALLOWED_ENV_NAMES, sorted(gloomberb_names - ALLOWED_ENV_NAMES)


def test_findings_render_their_own_reason(guard: Any) -> None:
    """Each kind must say what to do; a bare path is a finding nobody can act on."""
    for kind, reason in guard.FINDING_REASONS.items():
        assert reason and reason.strip(), f"{kind} needs a reason string"
    # The three cookie kinds are the ones DIG-2752 added; `enabled` is unchanged
    # from the original guard and is pinned by exact text.
    assert {
        "enabled",
        "cookie_value",
        "plaintext_cookie_slot",
        "advertised_without_secret",
    } <= set(guard.FINDING_REASONS)
    assert guard.FINDING_REASONS["enabled"] == (
        "GLOOMBERB_ENABLED must never be enabled in a deployed config"
    )
    rendered = guard.render(
        [
            guard.Finding(".env", 3, f"{COOKIE}=x", False, "cookie_value"),
            guard.Finding(
                "apps/x/wrangler.toml", 9, f'{COOKIE} = ""', True, "plaintext_cookie_slot"
            ),
            guard.Finding(
                "apps/x/wrangler.toml",
                10,
                "GLOOMBERB_ENABLED: $GLOOMBERB_ENABLED",
                True,
                "advertised_without_secret",
            ),
        ],
        [],
        "parsed from client.py",
        VALUES,
    )
    assert "COOKIE" in rendered
    for kind in ("cookie_value", "plaintext_cookie_slot", "advertised_without_secret"):
        assert guard.FINDING_REASONS[kind] in rendered, f"{kind} reason missing from the render"


def test_json_output_names_the_cookie_vars(guard: Any, monkeypatch: pytest.MonkeyPatch) -> None:
    """A machine consumer has to be able to see which names the guard policed."""
    import io
    import json as json_mod

    monkeypatch.setattr(guard, "scan", lambda *a, **k: ([], [], VALUES, "parsed from client.py"))
    buf = io.StringIO()
    monkeypatch.setattr("sys.stdout", buf)
    assert guard.main(["--json"]) == 0
    payload = json_mod.loads(buf.getvalue())
    assert payload["cookieVars"] == list(guard.COOKIE_VARS)
    assert payload["ok"] is True


def test_the_cookie_checks_are_not_vacuous_on_this_repo(guard: Any) -> None:
    """``test_repo_passes`` proves nothing unless the repo can also fail.

    Each new rule is exercised against the real repository by seeding one line
    into a real tracked config, so the control cannot pass for the wrong reason
    (a rule that never fires, a path class that does not exist here, or a file
    the guard does not read). The file is restored byte-for-byte afterwards.
    """

    target = REPO_ROOT / "apps/digichat-cloudflare/wrangler.toml"
    assert target.is_file(), f"the control needs a real deployed config; {target} is gone"
    original = target.read_bytes()

    def seed(line: str) -> list[Any]:
        target.write_bytes(original + line.encode("utf-8"))
        try:
            return guard.scan_text(
                "apps/digichat-cloudflare/wrangler.toml",
                original.decode("utf-8") + line + "\n",
                VALUES,
            )
        finally:
            target.write_bytes(original)

    try:
        assert [f.kind for f in seed(f'{COOKIE} = "{REAL_COOKIE}"\n')] == ["cookie_value"]
        assert [f.kind for f in seed(f'{COOKIE} = ""\n')] == ["plaintext_cookie_slot"]
        assert [f.kind for f in seed("GLOOMBERB_ENABLED = $GLOOMBERB_ENABLED\n")] == [
            "advertised_without_secret"
        ]
        assert [f.kind for f in seed('GLOOMBERB_ENABLED = "1"\n')] == ["enabled"]
        assert seed(f'{COOKIE} = "${{{{ secrets.{COOKIE} }}}}"\n') == []
    finally:
        target.write_bytes(original)
    assert target.read_bytes() == original, "the control must leave the file byte-identical"
