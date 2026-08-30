"""P6: leftover house ops ``documents`` reads ignore overlay same-key rows."""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path
from typing import Any  # score:allow untyped any — PostgREST row dicts in fixtures

import pytest
from digiquant.olympus.tenancy import house_workspace_id

from tests.fixtures.fake_supabase import FakeSupabaseClient

pytestmark = pytest.mark.unit

_SCRIPTS = Path(__file__).resolve().parents[3] / "digiquant" / "scripts" / "atlas"
_HOUSE = str(house_workspace_id())
_OVERLAY = "aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa"
_DATE = "2026-08-31"


def _load(name: str) -> Any:
    path = _SCRIPTS / f"{name}.py"
    if str(_SCRIPTS) not in sys.path:
        sys.path.insert(0, str(_SCRIPTS))
    sys.modules.pop("position_entry_from_events", None)
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec is not None and spec.loader is not None
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def _doc(
    *,
    workspace_id: str,
    document_key: str = "digest",
    content: str | None = None,
    payload: dict[str, Any] | None = None,
    date: str = _DATE,
) -> dict[str, Any]:
    row: dict[str, Any] = {
        "date": date,
        "document_key": document_key,
        "workspace_id": workspace_id,
    }
    if content is not None:
        row["content"] = content
    if payload is not None:
        row["payload"] = payload
    return row


class TestMaterializeDigestSyncIgnoresOverlay:
    def test_house_digest_documents_drops_overlay_listed_first(self) -> None:
        mod = _load("materialize_snapshot")
        sb = FakeSupabaseClient(
            canned_reads={
                "documents": [
                    _doc(workspace_id=_OVERLAY, content="OVERLAY-DIGEST"),
                    _doc(workspace_id=_HOUSE, content="HOUSE-DIGEST"),
                ]
            }
        )
        rows = mod.house_digest_documents(sb, [_DATE])
        assert [r["content"] for r in rows] == ["HOUSE-DIGEST"]

    def test_overlay_only_digest_does_not_overwrite_house_brief(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        mod = _load("materialize_snapshot")
        sb = FakeSupabaseClient(
            canned_reads={"documents": [_doc(workspace_id=_OVERLAY, content="OVERLAY-DIGEST")]},
            store={"daily_snapshots": [{"date": _DATE, "digest_markdown": "PRIOR"}]},
        )
        monkeypatch.setattr(mod, "_sb", lambda: sb)
        mod.sync_digest_markdown_from_documents([_DATE])
        assert sb.store["daily_snapshots"][0]["digest_markdown"] == "PRIOR"


class TestValidateDbFirstDocsIgnoresOverlay:
    def test_overlay_research_delta_does_not_pass_house_validation(self) -> None:
        mod = _load("validate_db_first")
        sb = FakeSupabaseClient(
            canned_reads={
                "documents": [
                    _doc(
                        workspace_id=_OVERLAY,
                        document_key="research-delta",
                        payload={"doc_type": "research_delta"},
                    )
                ]
            }
        )
        assert mod._has_research_delta(sb, _DATE) is False
        assert mod._has_research_doc(sb, _DATE) is False

    def test_house_digest_on_date_drops_overlay_listed_first(self) -> None:
        mod = _load("validate_db_first")
        sb = FakeSupabaseClient(
            canned_reads={
                "documents": [
                    _doc(
                        workspace_id=_OVERLAY,
                        payload={"marker": "overlay"},
                    ),
                    _doc(
                        workspace_id=_HOUSE,
                        payload={"marker": "house"},
                    ),
                ]
            }
        )
        rows = mod.house_digest_on_date(sb, _DATE)
        assert len(rows) == 1
        assert rows[0]["payload"]["marker"] == "house"

    def test_overlay_rebalance_does_not_count_as_house(self) -> None:
        mod = _load("validate_db_first")
        sb = FakeSupabaseClient(
            canned_reads={
                "documents": [
                    _doc(
                        workspace_id=_OVERLAY,
                        document_key="rebalance-decision.json",
                        payload={"doc_type": "rebalance_decision", "marker": "overlay"},
                    ),
                    _doc(
                        workspace_id=_HOUSE,
                        document_key="rebalance-decision.json",
                        payload={"doc_type": "rebalance_decision", "marker": "house"},
                    ),
                ]
            }
        )
        assert mod._has_rebalance_doc(sb, _DATE) is True
        # limit(1) without the house pin would return overlay (listed first).
        overlay_only = FakeSupabaseClient(
            canned_reads={
                "documents": [
                    _doc(
                        workspace_id=_OVERLAY,
                        document_key="rebalance-decision.json",
                        payload={"doc_type": "rebalance_decision"},
                    )
                ]
            }
        )
        assert mod._has_rebalance_doc(overlay_only, _DATE) is False


class TestBackfillEventReasonsDocsIgnoresOverlay:
    def test_rebalance_payload_drops_overlay_listed_first(self) -> None:
        mod = _load("backfill_position_event_reasons")
        sb = FakeSupabaseClient(
            canned_reads={
                "documents": [
                    _doc(
                        workspace_id=_OVERLAY,
                        document_key="rebalance-decision.json",
                        payload={"doc_type": "rebalance_decision", "marker": "overlay"},
                    ),
                    _doc(
                        workspace_id=_HOUSE,
                        document_key="rebalance-decision.json",
                        payload={"doc_type": "rebalance_decision", "marker": "house"},
                    ),
                ]
            }
        )
        payload = mod._rebalance_json_payload_for_date(sb, _DATE)
        assert payload is not None
        assert payload["marker"] == "house"

    def test_document_payload_for_key_drops_overlay_listed_first(self) -> None:
        mod = _load("backfill_position_event_reasons")
        key = "asset-recommendations/2026-08-31/IAU.json"
        sb = FakeSupabaseClient(
            canned_reads={
                "documents": [
                    _doc(
                        workspace_id=_OVERLAY,
                        document_key=key,
                        payload={"marker": "overlay"},
                    ),
                    _doc(
                        workspace_id=_HOUSE,
                        document_key=key,
                        payload={"marker": "house"},
                    ),
                ]
            }
        )
        payload = mod._document_payload_for_key(sb, _DATE, key)
        assert payload == {"marker": "house"}


class TestExportStateDocsIgnoresOverlay:
    def test_documents_export_drops_overlay_listed_first(self) -> None:
        mod = _load("backfill_export_state")
        sb = FakeSupabaseClient(
            canned_reads={
                "documents": [
                    _doc(workspace_id=_OVERLAY, document_key="digest", content="ov"),
                    _doc(workspace_id=_HOUSE, document_key="digest", content="hs"),
                ]
            }
        )
        rows = mod.house_documents_in_range(sb, "2026-08-01", "2026-08-31")
        assert [r["content"] for r in rows] == ["hs"]
        assert [r["workspace_id"] for r in rows] == [_HOUSE]


class TestFoldDocumentDeltasIgnoresOverlay:
    def test_fetch_payload_drops_overlay_listed_first(self) -> None:
        mod = _load("fold_document_deltas")
        key = "macro"
        sb = FakeSupabaseClient(
            canned_reads={
                "documents": [
                    _doc(workspace_id=_OVERLAY, document_key=key, payload={"marker": "overlay"}),
                    _doc(workspace_id=_HOUSE, document_key=key, payload={"marker": "house"}),
                ]
            }
        )
        assert mod.fetch_payload(sb, _DATE, key) == {"marker": "house"}

    def test_fetch_all_document_deltas_drops_overlay_listed_first(self) -> None:
        mod = _load("fold_document_deltas")
        sb = FakeSupabaseClient(
            canned_reads={
                "documents": [
                    _doc(
                        workspace_id=_OVERLAY,
                        document_key="document-deltas/overlay.json",
                        payload={"doc_type": "document_delta", "ops": ["overlay"]},
                    ),
                    _doc(
                        workspace_id=_HOUSE,
                        document_key="document-deltas/house.json",
                        payload={"doc_type": "document_delta", "ops": ["house"]},
                    ),
                ]
            }
        )
        deltas = mod.fetch_all_document_deltas(sb, _DATE)
        assert [key for key, _p in deltas] == ["document-deltas/house.json"]
        assert deltas[0][1]["ops"] == ["house"]


class TestValidatePipelineStepDocsIgnoresOverlay:
    def test_fetch_document_rows_drops_overlay_listed_first(self) -> None:
        mod = _load("validate_pipeline_step")
        sb = FakeSupabaseClient(
            canned_reads={
                "documents": [
                    _doc(
                        workspace_id=_OVERLAY,
                        document_key="digest",
                        payload={"doc_type": "digest", "marker": "overlay"},
                    ),
                    _doc(
                        workspace_id=_HOUSE,
                        document_key="digest",
                        payload={"doc_type": "digest", "marker": "house"},
                    ),
                ]
            }
        )
        rows = mod.fetch_document_rows(sb, _DATE)
        assert [r["payload"]["marker"] for r in rows] == ["house"]


class TestBackfillPmDocsIgnoresOverlay:
    def test_document_payload_pins_eq_house_workspace(self) -> None:
        # Module import loads execute_at_open via a ROOT/scripts path that is
        # not importable from tests/_load; pin the house filter in source.
        text = (_SCRIPTS / "backfill_pm_rebalance_and_activity.py").read_text(encoding="utf-8")
        assert 'eq_house_workspace(sb.table("documents").select("payload"))' in text
        assert (
            'sb.table("documents")\n        .select("payload")\n        .eq("date", date_iso)'
            not in text
        )
