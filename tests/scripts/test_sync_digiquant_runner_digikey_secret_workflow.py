"""Phase 3 Task 7: GH → Cloudflare put of digikey + Langfuse names.

Mirrors ``sync-digiquant-runner-mail-secrets.yml``. Values stay inside Actions;
the job logs name + length only. Never LangSmith.
"""

from __future__ import annotations

from pathlib import Path

import pytest
import yaml

from scripts.secret_staleness_check import can_wait, manifest_environments

pytestmark = pytest.mark.unit

REPO_ROOT = Path(__file__).resolve().parents[2]
WORKFLOW = REPO_ROOT / ".github" / "workflows" / "sync-digiquant-runner-digikey-secret.yml"
MAIL = REPO_ROOT / ".github" / "workflows" / "sync-digiquant-runner-mail-secrets.yml"
WRANGLER = REPO_ROOT / "apps" / "digiquant-runner" / "wrangler.toml"
RUNNER_DOCS = REPO_ROOT / "docs" / "ops" / "digiquant-runner.md"
ENV_TS = REPO_ROOT / "apps" / "digiquant-runner" / "src" / "env.ts"

MUST_PUT = (
    "DIGIQUANT_DIGIKEY_API_KEY",
    "LANGFUSE_SECRET_KEY",
    "LANGFUSE_PUBLIC_KEY",
    "LANGFUSE_BASE_URL",
    "DIGITRACE_LANGFUSE_OTLP_ENDPOINT",
    "DIGI_OTEL_HEADERS",
)
PARKED = (
    "LANGSMITH",
    "OPENROUTER",
    "CHEAPERINFERENCE",
)


def _triggers(doc: dict[str | bool, object]) -> dict[str, object]:
    raw: object
    if "on" in doc:
        raw = doc["on"]
    elif True in doc:
        raw = doc[True]
    else:
        raise AssertionError("workflow missing on:")
    assert isinstance(raw, dict)
    return raw


def _run_scripts(path: Path) -> list[str]:
    doc = yaml.safe_load(path.read_text(encoding="utf-8"))
    scripts: list[str] = []
    for job in doc["jobs"].values():
        for step in job.get("steps", []):
            if isinstance(step, dict) and isinstance(step.get("run"), str):
                scripts.append(step["run"])
    return scripts


def _blob(path: Path) -> str:
    return "\n".join(_run_scripts(path))


class TestSyncDigiquantRunnerHouseSecrets:
    def test_workflow_file_exists(self) -> None:
        assert WORKFLOW.is_file()

    def test_dispatch_only_and_contents_read(self) -> None:
        doc = yaml.safe_load(WORKFLOW.read_text(encoding="utf-8"))
        assert _triggers(doc) == {"workflow_dispatch": None}
        assert doc["permissions"] == {"contents": "read"}
        for name, job in doc["jobs"].items():
            # Was `assert "environment" not in job`. #248 gave every job that reads a
            # `secrets.*` name an `environment: cron`, because that is the only way
            # GitHub exposes an environment-scope secret — and this workflow reads
            # `DIGIQUANT_DIGIKEY_API_KEY` and the three `LANGFUSE_*` names. What has to
            # hold instead is that the gate cannot make a run wait: with a required
            # reviewer this job would hold its concurrency group while unapproved and
            # stop the workflow outright (#2541).
            assert job.get("environment") == "cron", (
                f"{name} should declare `environment: cron` so the secrets it reads can "
                "move out of repo scope; without it an environment-scope secret is "
                "invisible to this job"
            )
        assert can_wait(manifest_environments()["cron"]) is False, (
            "`cron` gained a required reviewer or a wait timer, so this workflow can "
            "stall silently (#2541). Remove the rule and refresh "
            "`.github/environments.json`"
        )

    def test_puts_digikey_and_langfuse_on_single_script(self) -> None:
        text = WORKFLOW.read_text(encoding="utf-8")
        blob = _blob(WORKFLOW)
        mail = _blob(MAIL)
        assert 'script="digiquant-runner"' in blob
        assert "workers/scripts/${script}/secrets" in blob
        assert "workers/scripts/${script}/secrets" in mail
        for name in MUST_PUT:
            assert f"put {name}" in blob, name
        assert "${LANGFUSE_BASE_URL%/}/api/public/otel" in blob
        assert 'printf \'%s:%s\' "$LANGFUSE_PUBLIC_KEY" "$LANGFUSE_SECRET_KEY"' in blob
        assert "base64 -w0" in blob
        assert "Authorization=Basic" in blob
        for name in PARKED:
            assert name not in text, name
        assert "[env." not in WRANGLER.read_text(encoding="utf-8")

    def test_logs_name_and_length_never_value(self) -> None:
        blob = _blob(WORKFLOW)
        assert "putting $name" in blob
        assert "len=${#text}" in blob
        assert 'echo "$text"' not in blob
        assert "echo '$text'" not in blob
        assert 'echo "$otlp_endpoint"' not in blob
        assert 'echo "$otel_headers"' not in blob
        assert "printenv" not in blob
        assert "FAIL empty $name" in blob
        assert 'type:"secret_text"' in blob or 'type:"secret_text"' in blob

    def test_env_ts_forwards_synced_names(self) -> None:
        text = ENV_TS.read_text(encoding="utf-8")
        for name in MUST_PUT:
            assert f"{name}: env.{name}" in text, name

    def test_docs_are_house_sync_not_langsmith(self) -> None:
        wrangler = WRANGLER.read_text(encoding="utf-8")
        docs = RUNNER_DOCS.read_text(encoding="utf-8")
        workflow = WORKFLOW.read_text(encoding="utf-8")
        assert "sync-digiquant-runner-digikey-secret.yml" in wrangler
        assert "DIGIQUANT_DIGIKEY_API_KEY" in wrangler
        assert "LANGFUSE_SECRET_KEY" in wrangler
        assert "LANGSMITH" not in wrangler
        assert "LANGSMITH" not in workflow
        assert "LANGSMITH" not in docs
        assert "sync-digiquant-runner-digikey-secret.yml" in docs
        assert "gh workflow run" in docs
        assert "DIGIQUANT_DIGIKEY_API_KEY" in docs
        assert "LANGFUSE_SECRET_KEY" in docs
        assert "DIGITRACE_LANGFUSE_OTLP_ENDPOINT" in docs
        assert "does not resume clocks" in docs.lower() or "do not resume clocks" in docs.lower()
