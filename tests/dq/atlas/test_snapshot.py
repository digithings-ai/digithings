"""Unit tests for digiquant.olympus.atlas.snapshot.

Covers the SnapshotEnvelope contract and the parity test that catches drift
between this local mirror and the upstream
``digiquant.olympus.atlas.phases.phase7_synthesis.DigestSnapshot``.
"""

from __future__ import annotations

import importlib.util
import json
from datetime import date, datetime, timezone

import pytest
from pydantic import ValidationError

from digiquant.olympus.atlas.snapshot import (
    SCHEMA_VERSION,
    DigestPayload,
    SnapshotEnvelope,
)


# ─── Helpers ────────────────────────────────────────────────────────────────


def _digest_payload_kwargs() -> dict:
    """Hand-built realistic DigestPayload kwargs.

    Mirrors what the Phase 7 synthesis node emits and what
    ``digiquant.olympus.atlas.supabase_io.publish_daily_snapshot`` writes into the
    ``snapshot`` jsonb column.
    """
    return {
        "segment": "master-digest",
        "date": date(2026, 4, 20),
        "bias": "neutral",
        "headline": "Markets digest mixed Fed signals; risk-on intact in tech",
        "material_findings": [
            {
                "label": "Tech leadership widens",
                "summary": "QQQ +1.8%, NVDA +3.1% on AI capex commentary.",
                "source_ids": ["src-1"],
            }
        ],
        "sources": [
            {"id": "src-1", "title": "WSJ Markets Live", "url": "https://wsj.com/x"},
        ],
        "notes": "Volume light into Fed week.",
        "market_regime_snapshot": "Risk-on; growth leadership reasserting.",
        "alt_data_dashboard": "Card-spend trends accelerating in services.",
        "institutional_summary": "Net inflows into US equity ETFs.",
        "asset_classes_summary": "Equities up; bonds flat; commodities mixed.",
        "us_equities_summary": "Tech +1.8%, energy -0.4%; breadth fair.",
        "thesis_tracker": "Long-tech thesis intact.",
        "portfolio_recommendations": "Hold growth; trim defensives 2pp.",
        "actionable_summary": [
            {
                "priority": 1,
                "label": "Trim staples",
                "rationale": "Defensives losing relative momentum.",
            }
        ],
        "risk_radar": [
            {
                "horizon_hours": 24,
                "label": "Hawkish FOMC minutes",
                "trigger": "5y5y reprices >10bps wider.",
            }
        ],
        "segment_freshness": {
            "macro": {"source": "today", "as_of": "2026-04-20"},
        },
    }


def _envelope_kwargs(**overrides) -> dict:
    base = {
        "run_date": date(2026, 4, 20),
        "run_type": "baseline",
        "baseline_date": None,
        "published_at": datetime(2026, 4, 20, 12, 0, 0, tzinfo=timezone.utc),
        "digest": _digest_payload_kwargs(),
    }
    base.update(overrides)
    return base


# ─── Tests ──────────────────────────────────────────────────────────────────


@pytest.mark.unit
class TestSnapshotEnvelope:
    def test_envelope_round_trips_json(self) -> None:
        env = SnapshotEnvelope(**_envelope_kwargs())
        as_json = env.model_dump_json()
        loaded = SnapshotEnvelope.model_validate_json(as_json)
        # Equality via model_dump (mode="json") to canonicalize date/datetime forms.
        assert loaded.model_dump(mode="json") == env.model_dump(mode="json")

    def test_envelope_schema_version_default_is_one(self) -> None:
        env = SnapshotEnvelope(**_envelope_kwargs())
        assert env.schema_version == 1
        assert SCHEMA_VERSION == 1

    def test_extra_field_rejected(self) -> None:
        bad = _envelope_kwargs()
        bad["unexpected_top_level"] = "nope"
        with pytest.raises(ValidationError):
            SnapshotEnvelope(**bad)

    def test_extra_field_rejected_inside_digest(self) -> None:
        bad = _envelope_kwargs()
        bad["digest"]["unexpected_inner"] = "nope"
        with pytest.raises(ValidationError):
            SnapshotEnvelope(**bad)

    def test_delta_run_with_baseline_date(self) -> None:
        env = SnapshotEnvelope(
            **_envelope_kwargs(
                run_type="delta",
                baseline_date=date(2026, 4, 19),
            )
        )
        assert env.run_type == "delta"
        assert env.baseline_date == date(2026, 4, 19)

    def test_run_type_must_be_baseline_or_delta(self) -> None:
        with pytest.raises(ValidationError):
            SnapshotEnvelope(**_envelope_kwargs(run_type="adhoc"))

    def test_envelope_validates_against_published_row(self) -> None:
        """Feed a realistic ``daily_snapshots`` row — the shape ``publish_daily_snapshot`` writes.

        Mirrors the row dict pattern in
        ``tests/dq/atlas/test_supabase_io.py``.
        """
        row = {
            "id": "row-1",
            "date": "2026-04-20",
            "run_type": "baseline",
            "baseline_date": None,
            "snapshot": _digest_payload_kwargs() | {"date": "2026-04-20"},
            "digest_markdown": "# Daily Digest 2026-04-20\n\n…",
            "created_at": "2026-04-20T12:00:00+00:00",
            "updated_at": "2026-04-20T12:30:00+00:00",
        }
        env = SnapshotEnvelope.from_supabase_row(row)
        assert env.run_date == date(2026, 4, 20)
        assert env.run_type == "baseline"
        assert env.baseline_date is None
        # `updated_at` wins over `created_at` per the helper's contract.
        assert env.published_at == datetime(2026, 4, 20, 12, 30, 0, tzinfo=timezone.utc)
        assert env.digest.headline.startswith("Markets digest")

    def test_from_supabase_row_falls_back_to_created_at(self) -> None:
        row = {
            "date": "2026-04-20",
            "run_type": "delta",
            "baseline_date": "2026-04-19",
            "snapshot": _digest_payload_kwargs() | {"date": "2026-04-20"},
            "created_at": "2026-04-20T12:00:00+00:00",
            # No updated_at.
        }
        env = SnapshotEnvelope.from_supabase_row(row)
        assert env.published_at == datetime(2026, 4, 20, 12, 0, 0, tzinfo=timezone.utc)
        assert env.baseline_date == date(2026, 4, 19)

    def test_from_supabase_row_rejects_missing_snapshot(self) -> None:
        bad_row = {
            "date": "2026-04-20",
            "run_type": "baseline",
            "snapshot": None,  # not a dict
            "baseline_date": None,
        }
        with pytest.raises(ValueError, match="missing 'snapshot'"):
            SnapshotEnvelope.from_supabase_row(bad_row)

    def test_serialized_top_level_includes_schema_version(self) -> None:
        """Frontend consumers must be able to read schema_version off the wire."""
        env = SnapshotEnvelope(**_envelope_kwargs())
        as_dict = json.loads(env.model_dump_json())
        assert as_dict["schema_version"] == 1
        assert as_dict["run_type"] == "baseline"
        assert "digest" in as_dict


@pytest.mark.unit
class TestParityWithPipelineDigest:
    """Drift guard between the local mirror and the upstream pipeline model.

    These tests skip cleanly when ``digiquant.olympus.atlas`` is not importable (e.g.
    in environments that only install the ``digiquant`` library). When it is
    importable, the field-name set must match exactly — otherwise this fails
    loud and we fix the mirror or bump the schema version.
    """

    @staticmethod
    def _digest_snapshot_class():
        if importlib.util.find_spec("digiquant.olympus.atlas") is None:
            pytest.skip("digiquant.olympus.atlas not installed in this test env")
        from digiquant.olympus.atlas.phases.phase7_synthesis import DigestSnapshot

        return DigestSnapshot

    def test_payload_matches_pipeline_digest(self) -> None:
        """Field-name parity between DigestPayload and DigestSnapshot."""
        DigestSnapshot = self._digest_snapshot_class()
        local_fields = set(DigestPayload.model_fields)
        upstream_fields = set(DigestSnapshot.model_fields)
        assert local_fields == upstream_fields, (
            "DigestPayload (digiquant.olympus.atlas.snapshot) drifted from "
            "DigestSnapshot (digiquant.olympus.atlas.phases.phase7_synthesis). "
            f"Only-local: {local_fields - upstream_fields}; "
            f"only-upstream: {upstream_fields - local_fields}"
        )

    def test_actionable_item_field_parity(self) -> None:
        DigestSnapshot = self._digest_snapshot_class()
        from digiquant.olympus.atlas.snapshot import ActionableItem as LocalActionableItem
        from digiquant.olympus.atlas.phases.phase7_synthesis import ActionableItem as UpstreamItem

        assert set(LocalActionableItem.model_fields) == set(UpstreamItem.model_fields)
        # Touch the upstream digest class so the import is exercised.
        assert "actionable_summary" in DigestSnapshot.model_fields

    def test_risk_item_field_parity(self) -> None:
        self._digest_snapshot_class()  # gate skip on availability
        from digiquant.olympus.atlas.snapshot import RiskItem as LocalRiskItem
        from digiquant.olympus.atlas.phases.phase7_synthesis import RiskItem as UpstreamRiskItem

        assert set(LocalRiskItem.model_fields) == set(UpstreamRiskItem.model_fields)


@pytest.mark.unit
class TestExportedSchemaArtifact:
    """Sanity-check the on-disk schema export."""

    def test_exported_schema_matches_model(self) -> None:
        """The committed schema file must match the model's current shape."""
        from pathlib import Path

        repo_root = Path(__file__).resolve().parents[3]
        schema_path = (
            repo_root / "digiquant" / "docs" / "schemas" / f"atlas_snapshot.v{SCHEMA_VERSION}.json"
        )
        assert schema_path.exists(), (
            f"missing schema artifact at {schema_path}; "
            "run python3 scripts/export_atlas_snapshot_schema.py"
        )
        on_disk = json.loads(schema_path.read_text(encoding="utf-8"))
        live = SnapshotEnvelope.model_json_schema()
        assert on_disk == live, (
            "Schema drift between digiquant/docs/schemas/atlas_snapshot.v1.json "
            "and SnapshotEnvelope.model_json_schema(). "
            "Re-run scripts/export_atlas_snapshot_schema.py."
        )
