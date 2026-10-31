"""Phase 3 Task 7: the house digikey on digiquant-runner, now put by hand.

The two GitHub Actions copy workflows (``sync-digiquant-runner-digikey-secret.yml``
and ``sync-digiquant-runner-mail-secrets.yml``) were deleted with the GHA exit
ledger: the secret already lives on the Worker, and a future write is a
workstation ``wrangler secret put`` with Chris's go. What still has to hold:
the names stay forwarded into the container, and the docs describe the by-hand
path, never LangSmith or Langfuse. Tracing is in-house digitrace.
"""

from __future__ import annotations

from pathlib import Path

import pytest

pytestmark = pytest.mark.unit

REPO_ROOT = Path(__file__).resolve().parents[2]
WORKFLOWS = REPO_ROOT / ".github" / "workflows"
WRANGLER = REPO_ROOT / "apps" / "digiquant-runner" / "wrangler.toml"
RUNNER_DOCS = REPO_ROOT / "docs" / "ops" / "digiquant-runner.md"
ENV_TS = REPO_ROOT / "apps" / "digiquant-runner" / "src" / "env.ts"

MUST_PUT = (
    "DIGIQUANT_DIGIKEY_API_KEY",
)
LANGFUSE_NAMES = (
    "LANGFUSE_SECRET_KEY",
    "LANGFUSE_PUBLIC_KEY",
    "LANGFUSE_BASE_URL",
    "DIGITRACE_LANGFUSE_OTLP_ENDPOINT",
)


class TestDigiquantRunnerHouseSecrets:
    def test_the_sync_workflows_are_gone(self) -> None:
        assert not (WORKFLOWS / "sync-digiquant-runner-digikey-secret.yml").exists()
        assert not (WORKFLOWS / "sync-digiquant-runner-mail-secrets.yml").exists()

    def test_env_ts_forwards_synced_names(self) -> None:
        text = ENV_TS.read_text(encoding="utf-8")
        for name in MUST_PUT:
            assert name in text, name
        for name in LANGFUSE_NAMES:
            assert name not in text, name

    def test_docs_are_by_hand_house_put_not_langsmith(self) -> None:
        wrangler = WRANGLER.read_text(encoding="utf-8")
        docs = RUNNER_DOCS.read_text(encoding="utf-8")
        assert "sync-digiquant-runner-digikey-secret.yml" not in wrangler
        assert "wrangler secret put" in wrangler
        assert "DIGIQUANT_DIGIKEY_API_KEY" in wrangler
        assert "LANGFUSE" not in wrangler
        assert "LANGSMITH" not in wrangler
        assert "[env." not in wrangler
        assert "LANGSMITH" not in docs
        assert "LANGFUSE" not in docs
        assert "sync-digiquant-runner-digikey-secret.yml" not in docs
        assert "wrangler secret put DIGIQUANT_DIGIKEY_API_KEY" in docs
        assert "does not resume clocks" in docs.lower() or "do not resume clocks" in docs.lower()
