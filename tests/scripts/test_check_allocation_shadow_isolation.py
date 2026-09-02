"""WP10.2 — write-denied allocation shadow isolation checker (#2762)."""

from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path
from types import ModuleType
from typing import Any  # score:allow untyped any — scored-lint: heterogeneous dict / client shapes

import pytest
import yaml

REPO_ROOT = Path(__file__).resolve().parents[2]
_SCRIPT = REPO_ROOT / "digiquant" / "scripts" / "atlas" / "check_allocation_shadow_isolation.py"
_WORKFLOW = REPO_ROOT / ".github" / "workflows" / "pipeline-olympus-allocation-shadow.yml"

pytestmark = pytest.mark.unit


def _load_module() -> ModuleType:
    spec = importlib.util.spec_from_file_location("check_allocation_shadow_isolation", _SCRIPT)
    assert spec and spec.loader
    mod = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = mod
    spec.loader.exec_module(mod)
    return mod


@pytest.fixture(scope="module")
def iso() -> ModuleType:
    return _load_module()


def _codes(findings: list[Any]) -> set[str]:
    return {f.code for f in findings}


def _minimal_good_workflow() -> str:
    return """
name: "Pipeline: Olympus allocation shadow"
on:
  workflow_run:
    workflows:
      - "Pipeline: Olympus research"
    types:
      - completed
    branches:
      - main
  workflow_dispatch:
permissions:
  contents: read
  actions: read
jobs:
  isolate:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - name: check
        run: python digiquant/scripts/atlas/check_allocation_shadow_isolation.py
      - uses: actions/upload-artifact@v4
        with:
          name: report
          path: artifacts/
"""


class TestWorkflowIsolation:
    def test_committed_workflow_passes(self, iso: ModuleType) -> None:
        text = _WORKFLOW.read_text(encoding="utf-8")
        findings = iso.check_workflow_text(text, path=str(_WORKFLOW))
        assert findings == [], [asdict_msg(f) for f in findings]

    def test_rejects_secrets_inherit(self, iso: ModuleType) -> None:
        bad = _minimal_good_workflow() + "\nsecrets: inherit\n"
        assert "secrets_inherit" in _codes(
            iso.check_workflow_text(bad)
        ) or "forbidden_secret" in _codes(iso.check_workflow_text(bad))

    def test_rejects_supabase_secret_reference(self, iso: ModuleType) -> None:
        bad = _minimal_good_workflow().replace(
            "run: python digiquant/scripts/atlas/check_allocation_shadow_isolation.py",
            "env:\n          SUPABASE_URL: ${{ secrets.SUPABASE_URL }}\n"
            "        run: python digiquant/scripts/atlas/check_allocation_shadow_isolation.py",
        )
        assert "forbidden_secret" in _codes(iso.check_workflow_text(bad))

    def test_rejects_provider_secret_reference(self, iso: ModuleType) -> None:
        bad = _minimal_good_workflow().replace(
            "run: python digiquant/scripts/atlas/check_allocation_shadow_isolation.py",
            "env:\n          OPENROUTER_API_KEY: ${{ secrets.OPENROUTER_API_KEY }}\n"
            "        run: echo hi",
        )
        assert "forbidden_secret" in _codes(iso.check_workflow_text(bad))

    def test_rejects_write_permissions(self, iso: ModuleType) -> None:
        bad = _minimal_good_workflow().replace(
            "permissions:\n  contents: read\n  actions: read\n",
            "permissions:\n  contents: write\n  actions: read\n",
        )
        assert "write_permission" in _codes(iso.check_workflow_text(bad))

    def test_rejects_untrusted_source_workflow(self, iso: ModuleType) -> None:
        bad = _minimal_good_workflow().replace(
            '"Pipeline: Olympus research"',
            '"Pipeline: Digiquant prices"',
        )
        assert "untrusted_source" in _codes(iso.check_workflow_text(bad))

    def test_rejects_untrusted_branch_filter(self, iso: ModuleType) -> None:
        bad = _minimal_good_workflow().replace(
            "branches:\n      - main\n",
            "branches:\n      - develop\n",
        )
        assert "untrusted_branch" in _codes(iso.check_workflow_text(bad))

    def test_rejects_network_sink(self, iso: ModuleType) -> None:
        bad = _minimal_good_workflow().replace(
            "run: python digiquant/scripts/atlas/check_allocation_shadow_isolation.py",
            "run: curl https://api.supabase.com/rest/v1/",
        )
        codes = _codes(iso.check_workflow_text(bad))
        assert "network_sink" in codes

    def test_committed_workflow_yaml_parses(self) -> None:
        doc = yaml.safe_load(_WORKFLOW.read_text(encoding="utf-8"))
        assert isinstance(doc, dict)
        perms = doc["permissions"]
        assert perms == {"contents": "read", "actions": "read"}
        assert "secrets" not in doc

    def test_dispatch_verifies_producer_run_via_api(self) -> None:
        """#2832 — dispatch must resolve run metadata; never hardcode a trusted name."""
        text = _WORKFLOW.read_text(encoding="utf-8")
        assert 'gh api "repos/${REPO}/actions/runs/${source_run_id}"' in text
        assert "untrusted producer workflow" in text
        # The pre-fix anti-pattern: assign trusted label without API lookup.
        assert 'source_workflow="Pipeline: Olympus research"' not in text
        assert "TRUSTED_WORKFLOW=" in text
        assert "BRANCH_DISPATCH" in text


class TestForbiddenImports:
    def test_checker_and_shadow_artifact_clean(self, iso: ModuleType) -> None:
        report = iso.run_isolation_checks(repo_root=REPO_ROOT, artifact_paths=[])
        import_findings = [f for f in report.findings if f.code == "forbidden_import"]
        assert import_findings == []

    def test_rejects_supabase_import(self, iso: ModuleType, tmp_path: Path) -> None:
        mod = tmp_path / "evil.py"
        mod.write_text("import supabase\nfrom digiquant.brokers import ibkr\n", encoding="utf-8")
        findings = iso.check_forbidden_imports(path=mod)
        assert "forbidden_import" in _codes(findings)
        messages = " ".join(f.message for f in findings)
        assert "supabase" in messages
        assert "digiquant.brokers" in messages

    def test_rejects_commit_io_and_network_imports(self, iso: ModuleType, tmp_path: Path) -> None:
        mod = tmp_path / "evil2.py"
        mod.write_text(
            "\n".join(
                [
                    "import httpx",
                    "import nautilus_trader",
                    "from digiquant.olympus.hermes.writers import commit_io",
                    "from digiquant.olympus.hermes.phases.h9_commit_run import commit_run",
                ]
            )
            + "\n",
            encoding="utf-8",
        )
        findings = iso.check_forbidden_imports(path=mod)
        assert len(findings) >= 3
        joined = " ".join(f.message for f in findings)
        assert "httpx" in joined
        assert "nautilus_trader" in joined
        assert "commit_io" in joined or "h9_commit_run" in joined


class TestArtifactTrustGates:
    def test_rejects_untrusted_schema(self, iso: ModuleType) -> None:
        findings = iso.check_artifact_trust(
            {"schema_version": "9.9", "artifact_content_hash": "a" * 64},
            require_hash=False,
        )
        assert "untrusted_schema" in _codes(findings)

    def test_rejects_missing_hash(self, iso: ModuleType) -> None:
        findings = iso.check_artifact_trust(
            {"schema_version": "1.0"},
            require_hash=True,
        )
        assert "untrusted_hash" in _codes(findings)

    def test_rejects_untrusted_source_and_branch(self, iso: ModuleType) -> None:
        findings = iso.check_artifact_trust(
            {"schema_version": "1.0", "artifact_content_hash": "a" * 64},
            source_workflow="evil-workflow",
            source_branch="feature/x",
            require_hash=False,
        )
        codes = _codes(findings)
        assert "untrusted_source" in codes
        assert "untrusted_branch" in codes

    def test_accepts_trusted_metadata_without_full_model(self, iso: ModuleType) -> None:
        findings = iso.check_artifact_trust(
            {"schema_version": "1.0", "artifact_content_hash": "a" * 64},
            source_workflow="Pipeline: Olympus research",
            source_branch="main",
            require_hash=False,
        )
        assert findings == []


class TestEndToEndReport:
    def test_run_writes_file_only_report(self, iso: ModuleType, tmp_path: Path) -> None:
        report = iso.run_isolation_checks(repo_root=REPO_ROOT, artifact_paths=[])
        out = tmp_path / "allocation-shadow-isolation-report.json"
        iso.write_report(report, out)
        payload = json.loads(out.read_text(encoding="utf-8"))
        assert payload["ok"] is True
        assert payload["checked_workflow"]
        assert isinstance(payload["findings"], list)

    def test_cli_exits_zero_on_clean_tree(self, iso: ModuleType, tmp_path: Path) -> None:
        out = tmp_path / "report.json"
        code = iso.main(
            [
                "--repo-root",
                str(REPO_ROOT),
                "--output",
                str(out),
                "--skip-artifact-model-validation",
            ]
        )
        assert code == 0
        assert out.is_file()


def asdict_msg(finding: Any) -> str:
    return f"{finding.code}: {finding.message}"
