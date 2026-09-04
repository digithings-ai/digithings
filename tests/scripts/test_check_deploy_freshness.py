"""Unit tests for scripts/check_deploy_freshness.py and its workflow wiring (#1759).

digiquant.io and digithings.ai are both Cloudflare Pages static exports, and a
Pages project that stops producing deployments keeps serving the last good build
with a 200 and no ``last-modified`` header (verified against the live site
2026-08-01). Every probe in ``smoke-site.yml`` therefore passed throughout a
multi-week deploy freeze. The checker turns the build stamp written by
``scripts/write-build-info.sh`` into a pass/fail verdict; these tests pin every
branch of that verdict offline, plus each workflow call site — one freshness job
and one build check per site — since a probe that is never invoked detects
nothing, and a probe that names the wrong site misdirects the operator.
"""

from __future__ import annotations

import importlib.util
import json
import sys
from datetime import UTC, datetime, timedelta
from pathlib import Path, PurePosixPath
from typing import Any  # score:allow untyped any — dynamically loaded module
from urllib.parse import urlsplit

import pytest
import yaml

REPO_ROOT = Path(__file__).resolve().parents[2]
_SCRIPT = REPO_ROOT / "scripts" / "check_deploy_freshness.py"
_SMOKE_WORKFLOW = REPO_ROOT / ".github" / "workflows" / "smoke-site.yml"
_BUILD_CHECK_WORKFLOWS = [
    REPO_ROOT / ".github" / "workflows" / "deploy-digiquant-cloudflare.yml",
    REPO_ROOT / ".github" / "workflows" / "deploy-digithings-cloudflare.yml",
]

#: One ``smoke-site.yml`` job per site: (job key, probed URL, issue label).
#: Both static sites deploy through the same Cloudflare Pages git integration
#: and share the blind spot, so both are pinned here (#1759).
FRESHNESS_JOBS = [
    pytest.param(
        "freshness",
        "https://digiquant.io/build-info.json",
        "component:digiquant",
        id="digiquant.io",
    ),
    pytest.param(
        "freshness-digithings",
        "https://digithings.ai/build-info.json",
        "component:website",
        id="digithings.ai",
    ),
]

NOW = datetime(2026, 8, 1, 12, 0, tzinfo=UTC)
URL = "https://digiquant.io/build-info.json"

pytestmark = pytest.mark.unit


def _load_module() -> Any:
    spec = importlib.util.spec_from_file_location("check_deploy_freshness", _SCRIPT)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


@pytest.fixture(scope="module")
def cdf() -> Any:
    return _load_module()


def _stamp(built_at: datetime) -> str:
    return json.dumps(
        {
            "site": "digiquant.io",
            "commit": "f8d12943da05886567d0ed41c7786252866bca52",
            "branch": "main",
            "builder": "cloudflare-pages",
            "built_at": f"{built_at:%Y-%m-%dT%H:%M:%SZ}",
        }
    )


def _workflow(path: Path) -> dict[str, Any]:
    parsed = yaml.safe_load(path.read_text(encoding="utf-8"))
    assert isinstance(parsed, dict)
    return parsed


def _run_blocks(job: dict[str, Any]) -> list[str]:
    return [step["run"] for step in job.get("steps", []) if isinstance(step.get("run"), str)]


def _site_of(url: str) -> str:
    """``https://digithings.ai/build-info.json`` -> ``digithings.ai``."""
    return urlsplit(url).netloc


class TestEvaluate:
    def test_recent_stamp_passes(self, cdf: Any) -> None:
        verdict = cdf.evaluate(url=URL, status=200, body=_stamp(NOW - timedelta(days=2)), now=NOW)
        assert (verdict.label, verdict.failed) == ("PASS", False)
        assert "age=2.0d" in verdict.message

    def test_stamp_older_than_limit_is_stale(self, cdf: Any) -> None:
        verdict = cdf.evaluate(url=URL, status=200, body=_stamp(NOW - timedelta(days=9)), now=NOW)
        assert (verdict.label, verdict.failed) == ("STALE", True)
        assert "no deploy for 9.0d" in verdict.message

    def test_boundary_at_the_limit_still_passes(self, cdf: Any) -> None:
        # 168h exactly is not yet stale — only strictly older fails, so a build
        # that lands a week apart to the second does not flap the check.
        verdict = cdf.evaluate(
            url=URL, status=200, body=_stamp(NOW - timedelta(hours=168)), now=NOW
        )
        assert verdict.label == "PASS"

    def test_custom_max_age_is_honoured(self, cdf: Any) -> None:
        # The build-check step reuses the evaluator with --max-age-hours 1.
        body = _stamp(NOW - timedelta(hours=3))
        assert cdf.evaluate(url=URL, status=200, body=body, now=NOW, max_age_hours=1).label == (
            "STALE"
        )
        assert cdf.evaluate(url=URL, status=200, body=body, now=NOW, max_age_hours=24).label == (
            "PASS"
        )

    def test_missing_stamp_is_a_failure_not_a_warning(self, cdf: Any) -> None:
        # A 404 is conclusive: the live bundle predates build-info.json. The
        # existing shell probes reserve WARN for inconclusive results only.
        verdict = cdf.evaluate(url=URL, status=404, body="", now=NOW)
        assert (verdict.label, verdict.failed) == ("UNSTAMPED", True)
        assert "predates the build stamp" in verdict.message

    def test_spa_fallback_html_is_unstamped(self, cdf: Any) -> None:
        verdict = cdf.evaluate(
            url=URL, status=200, body="<!DOCTYPE html><title>digiquant</title>", now=NOW
        )
        assert (verdict.label, verdict.failed) == ("UNSTAMPED", True)

    @pytest.mark.parametrize("status", [0, 403, 429])
    def test_bot_challenge_is_warn_only(self, cdf: Any, status: int) -> None:
        verdict = cdf.evaluate(url=URL, status=status, body="", now=NOW)
        assert (verdict.label, verdict.failed) == ("WARN", False)

    def test_server_error_fails(self, cdf: Any) -> None:
        verdict = cdf.evaluate(url=URL, status=502, body="", now=NOW)
        assert (verdict.label, verdict.failed) == ("UNREACHABLE", True)

    @pytest.mark.parametrize(
        "body",
        ['{"built_at": ""}', '{"built_at": "not-a-date"}', '{"commit": "abc"}', '{"built_at": 7}'],
    )
    def test_unparseable_built_at_is_malformed(self, cdf: Any, body: str) -> None:
        verdict = cdf.evaluate(url=URL, status=200, body=body, now=NOW)
        assert (verdict.label, verdict.failed) == ("MALFORMED", True)

    def test_json_array_body_is_malformed(self, cdf: Any) -> None:
        verdict = cdf.evaluate(url=URL, status=200, body="[]", now=NOW)
        assert (verdict.label, verdict.failed) == ("MALFORMED", True)

    def test_far_future_stamp_cannot_mask_a_frozen_deploy(self, cdf: Any) -> None:
        verdict = cdf.evaluate(url=URL, status=200, body=_stamp(NOW + timedelta(days=400)), now=NOW)
        assert (verdict.label, verdict.failed) == ("MALFORMED", True)

    def test_small_clock_skew_still_passes(self, cdf: Any) -> None:
        verdict = cdf.evaluate(
            url=URL, status=200, body=_stamp(NOW + timedelta(minutes=5)), now=NOW
        )
        assert verdict.label == "PASS"

    def test_offset_spelling_of_built_at_parses(self, cdf: Any) -> None:
        body = json.dumps({"built_at": "2026-07-31T12:00:00+00:00"})
        assert cdf.evaluate(url=URL, status=200, body=body, now=NOW).label == "PASS"

    def test_naive_built_at_is_read_as_utc(self, cdf: Any) -> None:
        body = json.dumps({"built_at": "2026-07-20T12:00:00"})
        verdict = cdf.evaluate(url=URL, status=200, body=body, now=NOW)
        assert (verdict.label, verdict.failed) == ("STALE", True)


class TestCli:
    def test_exit_code_and_stream_on_stale(
        self, cdf: Any, tmp_path: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        body_file = tmp_path / "build-info.json"
        body_file.write_text(_stamp(datetime(2020, 1, 1, tzinfo=UTC)), encoding="utf-8")
        code = cdf.main(
            [
                "--url",
                URL,
                "--status",
                "200",
                "--body-file",
                str(body_file),
                "--max-age-hours",
                "168",
            ]
        )
        captured = capsys.readouterr()
        assert code == 1
        assert captured.err.startswith("STALE")

    def test_exit_zero_on_fresh_stamp(
        self, cdf: Any, tmp_path: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        body_file = tmp_path / "build-info.json"
        body_file.write_text(_stamp(datetime.now(tz=UTC)), encoding="utf-8")
        assert cdf.main(["--url", URL, "--status", "200", "--body-file", str(body_file)]) == 0
        assert capsys.readouterr().out.startswith("PASS")

    def test_absent_body_file_does_not_crash(self, cdf: Any, tmp_path: Path) -> None:
        # curl never creates the output file when it cannot connect at all.
        missing = tmp_path / "never-written.json"
        assert cdf.main(["--url", URL, "--status", "200", "--body-file", str(missing)]) == 1

    def test_curl_triple_zero_status_is_tolerated(self, cdf: Any) -> None:
        assert cdf.main(["--url", URL, "--status", "000"]) == 0


@pytest.mark.parametrize(("job_key", "live_url", "label"), FRESHNESS_JOBS)
class TestWorkflowWiring:
    """A freshness probe nobody calls detects nothing — pin every call site."""

    def test_smoke_site_runs_the_freshness_check(
        self, job_key: str, live_url: str, label: str
    ) -> None:
        workflow = _workflow(_SMOKE_WORKFLOW)
        assert job_key in workflow["jobs"], f"smoke-site.yml lost the {job_key} job"
        runs = "\n".join(_run_blocks(workflow["jobs"][job_key]))
        assert "scripts/check_deploy_freshness.py" in runs
        # Per-job, not workflow-wide: each site must probe its own URL, so one
        # job cannot satisfy the assertion on behalf of the other.
        assert live_url in runs

    def test_freshness_job_can_check_out_and_file_an_issue(
        self, job_key: str, live_url: str, label: str
    ) -> None:
        job = _workflow(_SMOKE_WORKFLOW)["jobs"][job_key]
        # Declaring any `permissions` block zeroes the rest, so contents:read is
        # required for actions/checkout to fetch the script at all.
        assert job["permissions"]["contents"] == "read"
        assert job["permissions"]["issues"] == "write"
        assert any(
            str(step.get("uses", "")).startswith("actions/checkout") for step in job["steps"]
        )

    def test_stale_deploy_issue_is_not_labelled_as_agent_work(
        self, job_key: str, live_url: str, label: str
    ) -> None:
        job = _workflow(_SMOKE_WORKFLOW)["jobs"][job_key]
        creates = "\n".join(
            step["run"] for step in job["steps"] if "gh issue create" in str(step.get("run", ""))
        )
        assert creates, f"the {job_key} job no longer files an issue"
        # The remedy is a Cloudflare dashboard action, not a code change, so this
        # must not be dispatched to an agent the way the asset probe's issue is.
        assert "agent-task" not in creates
        # A shared issue naming the wrong site is worse than no issue: it sends
        # the operator to the wrong Pages project.
        assert label in creates
        assert _site_of(live_url) in creates


class TestOgAssetCanaries:
    """Pin the #671 MIME-masking canaries to the live OG paths (#800).

    Brand OG cards ship as ``public/og.png`` at each static-export root. The
    smoke job used to probe ``/design/assets/og.png``, which 404'd after the
    brand move and kept filing daily false alarms on #800.
    """

    def test_smoke_probes_root_og_png_not_legacy_design_assets(self) -> None:
        runs = "\n".join(_run_blocks(_workflow(_SMOKE_WORKFLOW)["jobs"]["smoke"]))
        assert "https://digithings.ai/og.png" in runs
        assert "https://digiquant.io/og.png" in runs
        assert "design/assets/og.png" not in runs


class TestPerSiteIsolation:
    """One stale site must not mask, cancel, or misattribute the other."""

    def test_each_site_has_its_own_job(self) -> None:
        jobs = _workflow(_SMOKE_WORKFLOW)["jobs"]
        keys = {job_key for job_key, _, _ in (p.values for p in FRESHNESS_JOBS)}
        assert keys <= set(jobs)
        # A matrix would default to fail-fast, cancelling the sibling site's job
        # before its `if: failure()` issue step could run.
        assert not any("matrix" in str(jobs[key].get("strategy", "")) for key in keys)

    def test_first_run_unstamped_reads_as_a_diagnostic_not_an_alarm(self) -> None:
        # digithings.ai cannot serve a stamp until Cloudflare Pages next builds
        # it, so the first probe after this shipped is expected to be UNSTAMPED.
        job = _workflow(_SMOKE_WORKFLOW)["jobs"]["freshness-digithings"]
        bodies = "\n".join(
            step["run"] for step in job["steps"] if "gh issue create" in str(step.get("run", ""))
        )
        assert "not yet observable" in bodies


@pytest.mark.parametrize("workflow_path", _BUILD_CHECK_WORKFLOWS, ids=lambda p: p.name)
def test_build_check_validates_the_stamp_it_just_wrote(workflow_path: Path) -> None:
    runs = "\n".join(
        run for job in _workflow(workflow_path)["jobs"].values() for run in _run_blocks(job)
    )
    assert "dist/build-info.json" in runs
    assert "scripts/check_deploy_freshness.py" in runs


def _trigger_paths(workflow_path: Path) -> list[str]:
    # PyYAML resolves a bare top-level `on:` key to the boolean True (YAML 1.1), so
    # the trigger block is not reachable under the string "on".
    return _workflow(workflow_path)[True]["pull_request"]["paths"]


@pytest.mark.parametrize("workflow_path", _BUILD_CHECK_WORKFLOWS, ids=lambda p: p.name)
@pytest.mark.parametrize(
    "callee", ["scripts/write-build-info.sh", "scripts/check_deploy_freshness.py"]
)
def test_build_check_watches_the_files_it_runs(workflow_path: Path, callee: str) -> None:
    """A check that does not fire on its own inputs proves nothing about them.

    Both deploy checks listed only ``scripts/build-*.sh``, never its callees. So an
    edit to ``write-build-info.sh`` — which the real Cloudflare build runs under
    ``set -euo pipefail``, and whose absent output hard-fails that build — matched no
    glob and ran neither check; likewise ``check_deploy_freshness.py``, the evaluator
    both the "Assert deploy build stamp" step and the daily probe call.
    """
    assert callee in _trigger_paths(workflow_path)


@pytest.mark.parametrize("workflow_path", _BUILD_CHECK_WORKFLOWS, ids=lambda p: p.name)
@pytest.mark.parametrize(
    "manifest",
    [
        "pyproject.toml",
        "requirements.txt",
        "setup.py",
        "package.json",
        "package-lock.json",
        # Not root-anchored, and the exception proves the rule below: it is an *install*
        # input, not a build input. The root `npm install` resolves all eight workspace
        # manifests before either site compiles, and of the eight this was the only one in
        # no path filter anywhere in the repo — so a bad range there failed both
        # production builds with no CI job running. Nothing derives it, because nothing
        # about it moves: it is not reached through any import edge.
        "frontend/digiweb/reference/package.json",
    ],
)
def test_build_check_watches_the_root_manifests(workflow_path: Path, manifest: str) -> None:
    """The manifests every deploy build resolves, pinned like the callees above.

    Two routes into the same failure. Cloudflare's build image auto-detects languages
    from the repo root and runs ``pip install .`` *before* the configured build command,
    so a Python manifest can freeze a site without a frontend file being touched — #1714
    edited only the root pyproject.toml and uv.lock, and both sites silently built
    nothing for three days with every PR green. The npm manifests break it more
    directly: each build script runs its own root ``npm install`` (#1956), which
    reconciles the lock against the workspace manifests rather than installing from it,
    so a bad resolution fails the build with nothing else touched. Each workflow's own
    comment records both; nothing enforced either.

    Install inputs only — the manifests a build *resolves*. Which workspace *directories*
    a site must watch is a different question, and a moving one: it follows the import
    graph, so it is answered by deriving the closure from the manifests in
    test_deploy_build_inputs.py rather than by a list here. A hardcoded list of those
    would go stale the next time a frontend dependency edge changes, silently, which is
    the failure mode this whole module exists to refuse.
    """
    paths = _trigger_paths(workflow_path)
    # Accept a covering directory glob as well as the literal path. A later PR widening
    # `frontend/digiweb/reference/package.json` to `frontend/digiweb/reference/**`
    # strictly improves coverage; a literal-membership assertion would go red on it and
    # the obvious fix would be to keep both — which is exactly the dead entry the comment
    # at the top of that filter warns #1966 had to remove.
    covering = f"{PurePosixPath(manifest).parent}/**"
    assert manifest in paths or covering in paths
