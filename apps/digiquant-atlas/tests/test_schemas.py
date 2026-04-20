"""Unit tests for digiquant_atlas.schemas."""

from __future__ import annotations

import pytest

from digiquant_atlas.schemas import (
    SchemaNotFoundError,
    list_schema_names,
    load_schema,
    validate_payload,
)


@pytest.mark.unit
class TestSchemaLoader:
    def test_nested_schema_loads(self) -> None:
        schema = load_schema("sector-report")
        assert isinstance(schema, dict)
        # Sector reports are JSON objects per templates/schemas/sector-report.schema.json.
        assert schema.get("type") == "object"

    def test_flat_top_level_schema_loads(self) -> None:
        """``digest-snapshot-schema.json`` lives at templates/ root, not under schemas/."""
        schema = load_schema("digest-snapshot")
        assert isinstance(schema, dict)

    def test_missing_schema_raises(self) -> None:
        with pytest.raises(SchemaNotFoundError):
            load_schema("not-a-real-schema")

    def test_list_names_discovers_both_layouts(self) -> None:
        names = list_schema_names()
        # Stable subset covering the two on-disk locations.
        for expected in (
            "sector-report",
            "rebalance-decision",
            "master-digest",
            "digest-snapshot",
            "snapshot",
        ):
            assert expected in names, f"{expected!r} missing from list_schema_names()"


@pytest.mark.unit
class TestValidatePayload:
    # A "minimal valid payload" test needs a golden fixture that actually
    # satisfies the target schema's nested `required` constraints. That
    # belongs with the phase commit that owns the segment model (the sector
    # swarm lands in commit 6). Deliberately not adding a green-on-skip stub
    # here — it would assert nothing.

    def test_invalid_payload_raises(self) -> None:
        from jsonschema import ValidationError

        with pytest.raises(ValidationError):
            validate_payload("sector-report", {"obviously": "wrong"})
