"""WP13.5 — evaluate_research_policy_shadow CLI tests (#2934)."""

from __future__ import annotations

import importlib.util
import json
import os
import subprocess
import sys
from datetime import UTC, datetime
from decimal import Decimal
from pathlib import Path
from types import ModuleType
from uuid import UUID, uuid4

import pytest
from digiquant.dashboard.research_retrieval.planner import (
    AttentionMode,
    AttentionRolloutMode,
    AttentionTargetKind,
    H6DecisionFeatures,
    default_research_policy_path,
    load_research_attention_policy,
    plan_research_attention,
)
from digiquant.dashboard.research_retrieval.shadow_evaluation import ShadowProviderAttemptDetail

pytestmark = pytest.mark.unit

REPO_ROOT = Path(__file__).resolve().parents[2]
_SCRIPT = REPO_ROOT / "digiquant" / "scripts" / "atlas" / "evaluate_research_policy_shadow.py"
_TS = datetime(2026, 8, 26, 16, 30, tzinfo=UTC)
_STATE = UUID("aaaaaaaa-bbbb-4ccc-8ddd-eeeeeeeeeeee")


def _load_module() -> ModuleType:
    spec = importlib.util.spec_from_file_location("evaluate_research_policy_shadow", _SCRIPT)
    assert spec and spec.loader
    mod = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = mod
    spec.loader.exec_module(mod)
    return mod


@pytest.fixture(scope="module")
def cli() -> ModuleType:
    return _load_module()


def _plan_bundle(tmp_path: Path) -> tuple[Path, Path, Path]:
    from digiquant.dashboard.research_retrieval.planner import AttentionFeatures

    policy = load_research_attention_policy(default_research_policy_path())
    features = AttentionFeatures(
        target_kind=AttentionTargetKind.TICKER,
        target_key="AAPL",
        state_version_id=str(_STATE),
        has_prior=True,
        h6=H6DecisionFeatures.model_validate(
            {
                "ticker": "AAPL",
                "roster_reason": "held",
                "held": True,
                "weight_pct": 8.0,
                "stance": "hold",
                "conviction_score": 2,
                "raw_uncertainty": "low",
            }
        ),
    )
    plan = plan_research_attention(
        run_id="run-cli",
        state_version_id=_STATE,
        features=[features],
        policy=policy,
        rollout_mode=AttentionRolloutMode.SHADOW,
    )
    decision = plan.decisions[0]
    attempt_id = uuid4()
    store_path = tmp_path / "store.json"
    store_path.write_text(
        json.dumps(
            {
                "plan_id": str(plan.plan_id),
                "attempt_id": "attempt-cli",
                "recorded_at": _TS.isoformat(),
                "plan": plan.model_dump(mode="json"),
                "provider_attempt_links": {
                    decision.target_key: [str(attempt_id)],
                },
            },
            indent=2,
        ),
        encoding="utf-8",
    )
    attempts_path = tmp_path / "attempts.json"
    attempts_path.write_text(
        json.dumps(
            {
                decision.target_key: [
                    ShadowProviderAttemptDetail(
                        provider_attempt_id=attempt_id,
                        node_run_id="node-h5",
                        prompt_tokens=50,
                        completion_tokens=25,
                        cost_usd=Decimal("0.01"),
                        latency_ms=200,
                    ).model_dump(mode="json")
                ]
            },
            indent=2,
        ),
        encoding="utf-8",
    )
    downstream_path = tmp_path / "downstream.json"
    if decision.mode is AttentionMode.CARRY:
        downstream_payload = {
            "target_key": decision.target_key,
            "carried": True,
            "node_run_id": "node-carry",
        }
    else:
        downstream_payload = {
            "target_key": decision.target_key,
            "node_run_id": "node-h5",
            "forecast_assessment_id": "forecast-aapl",
            "artifact_refs": ["bundle:aapl"],
        }
    downstream_path.write_text(
        json.dumps({decision.target_key: downstream_payload}, indent=2),
        encoding="utf-8",
    )
    return store_path, attempts_path, downstream_path


class TestEvaluateResearchPolicyShadowCli:
    def test_cli_writes_report(self, cli: ModuleType, tmp_path: Path) -> None:
        store_path, attempts_path, downstream_path = _plan_bundle(tmp_path)
        output = tmp_path / "report.json"

        code = cli.main(
            [
                "--store-snapshot",
                str(store_path),
                "--attempt-details",
                str(attempts_path),
                "--downstream",
                str(downstream_path),
                "--recorded-at",
                _TS.isoformat(),
                "--output",
                str(output),
            ]
        )

        assert output.is_file()
        payload = json.loads(output.read_text(encoding="utf-8"))
        assert payload["eligible"] is True
        assert "evaluation" in payload
        assert code in {0, 1}

    def test_script_module_invocable(self) -> None:
        env = os.environ.copy()
        env["PYTHONPATH"] = str(REPO_ROOT / "digiquant" / "src")
        proc = subprocess.run(
            [sys.executable, str(_SCRIPT), "--help"],
            capture_output=True,
            text=True,
            check=False,
            env=env,
            cwd=str(REPO_ROOT),
        )
        assert proc.returncode == 0
        assert "shadow" in proc.stdout.lower()
