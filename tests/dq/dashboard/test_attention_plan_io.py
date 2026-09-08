"""Contract tests for AttentionPlan glass-box document IO (#1945)."""

from __future__ import annotations

from datetime import date
from pathlib import Path

import pytest
from digiquant.dashboard.attention_plan import plan_attention_shadow
from digiquant.dashboard.attention_plan_io import (
    ATTENTION_PLAN_DOC_TYPE_COLUMN,
    ATTENTION_PLAN_DOCUMENT_KEY,
    ATTENTION_PLAN_PAYLOAD_DOC_TYPE,
    AttentionPlanPublishError,
    attention_plan_document_payload,
    publish_attention_plan_shadow,
)
from digiquant.dashboard.edit_mode.models import PriorPublished

pytestmark = pytest.mark.unit

REPO_ROOT = Path(__file__).resolve().parents[3]
MIGRATIONS_DIR = REPO_ROOT / "digiquant" / "supabase" / "migrations"
MIGRATION_PATH = MIGRATIONS_DIR / "077_attention_plan_doc_type.sql"
RUN = date(2026, 8, 25)


class _MapPriorLoader:
    def __init__(self, priors: dict[tuple[str, str], PriorPublished | None]) -> None:
        self._priors = priors

    def load(self, artifact_key: tuple[str, str], run_date: date) -> PriorPublished | None:
        return self._priors.get(artifact_key)


class _FakeTable:
    def __init__(self, store: list[dict]) -> None:
        self._store = store
        self._row: dict | None = None

    def upsert(self, row: dict, on_conflict: str = "") -> _FakeTable:
        self._row = row
        self._store.append(row)
        return self

    def execute(self) -> object:
        return type("Resp", (), {"data": [self._row]})()


class _FakeClient:
    def __init__(self) -> None:
        self.rows: list[dict] = []

    def table(self, name: str) -> _FakeTable:
        assert name == "documents"
        return _FakeTable(self.rows)


def test_migration_077_registers_attention_plan_doc_type() -> None:
    assert MIGRATION_PATH.is_file()
    raw = MIGRATION_PATH.read_text(encoding="utf-8")
    assert "COMMIT;" not in raw.upper()
    assert "'Attention Plan'" in raw
    assert "'Beliefs'" in raw
    assert sorted(MIGRATIONS_DIR.glob("077_*.sql")) == [MIGRATION_PATH]


def test_payload_includes_refresh_reasons_and_profile_pin() -> None:
    loader = _MapPriorLoader(
        {
            ("segment", "macro"): PriorPublished(
                date=date(2026, 8, 24),
                document_key="segment:macro",
                payload={"body": "x"},
            )
        }
    )
    result = plan_attention_shadow(
        run_date=RUN,
        artifacts=[("segment", "macro")],
        prior_loader=loader,
        h4_roster=["SPY"],
        planner_mode="shadow",
    )
    payload = attention_plan_document_payload(result)
    assert payload["doc_type"] == ATTENTION_PLAN_PAYLOAD_DOC_TYPE
    assert payload["shadow"] is True
    assert payload["actuated"] is False
    assert payload["profile_pin"]["profile_key"] == "house"
    assert payload["profile_pin"]["is_house_default"] is True
    assert payload["plan"]["decisions"]
    decision = payload["plan"]["decisions"][0]
    assert decision["refresh_reasons"]
    assert decision["refresh_reason_labels"]
    assert len(decision["refresh_reasons"]) == len(decision["refresh_reason_labels"])


def test_off_mode_refuses_document() -> None:
    result = plan_attention_shadow(
        run_date=RUN,
        artifacts=[],
        prior_loader=_MapPriorLoader({}),
        planner_mode="off",
    )
    with pytest.raises(AttentionPlanPublishError, match="off"):
        attention_plan_document_payload(result)


def test_publish_attention_plan_shadow_upserts_document_key() -> None:
    result = plan_attention_shadow(
        run_date=RUN,
        artifacts=[("macro", "macro")],
        prior_loader=_MapPriorLoader({}),
        planner_mode="shadow",
    )
    client = _FakeClient()
    artifact = publish_attention_plan_shadow(client=client, result=result)
    assert artifact.document_key == ATTENTION_PLAN_DOCUMENT_KEY
    assert len(client.rows) == 1
    row = client.rows[0]
    assert row["document_key"] == ATTENTION_PLAN_DOCUMENT_KEY
    assert row["doc_type"] == ATTENTION_PLAN_DOC_TYPE_COLUMN
    assert row["payload"]["doc_type"] == ATTENTION_PLAN_PAYLOAD_DOC_TYPE
    assert row["category"] == "planner"
    assert row["run_type"] == "baseline"
