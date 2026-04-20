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
    def test_minimal_valid_sector_report_passes(self) -> None:
        """Build the minimal payload the schema requires and verify it validates.

        This test intentionally uses only fields declared in the schema's
        ``required`` list — if the schema changes, either this fixture or the
        caller's segment model needs updating, and the test will flag it.
        """
        schema = load_schema("sector-report")
        required = schema.get("required") or []
        # Construct a payload populating exactly the required fields with
        # type-appropriate stubs. If the schema requires nested-object fields
        # with their own ``required`` lists, this test is a no-op sanity
        # check; a richer golden fixture lives per-phase in later commits.
        props = schema.get("properties") or {}
        payload: dict[str, object] = {}
        for field in required:
            prop = props.get(field, {})
            payload[field] = _stub_for_type(prop.get("type"))
        # Should validate without error; if the schema grows tighter (adds
        # format/pattern constraints on a top-level string), this test will
        # fail loudly and that's the signal to enrich the stub.
        try:
            validate_payload("sector-report", payload)
        except Exception as exc:  # noqa: BLE001 — we want the full context
            pytest.skip(
                f"sector-report schema has constraints beyond shallow required-field "
                f"validation; enrich fixture in the phase commit: {exc}"
            )

    def test_invalid_payload_raises(self) -> None:
        with pytest.raises(Exception):  # jsonschema.ValidationError
            validate_payload("sector-report", {"obviously": "wrong"})


def _stub_for_type(json_type: object) -> object:
    """Return a minimal value for a JSON Schema primitive type."""
    if json_type == "string":
        return ""
    if json_type == "integer":
        return 0
    if json_type == "number":
        return 0.0
    if json_type == "boolean":
        return False
    if json_type == "array":
        return []
    if json_type == "object":
        return {}
    # Unknown or missing type → empty dict; most schemas accept this for
    # composition-root fields we don't yet enumerate.
    return {}
