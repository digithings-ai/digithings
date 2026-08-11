"""Tests for OpenAPI markdown enrichment."""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from digisearch.ingestion.segmenters.heading import heading_segments

from scripts.docs_onboard.ingest_openapi import openapi_to_markdown

pytestmark = pytest.mark.unit

_SPEC = {
    "openapi": "3.1.0",
    "info": {"title": "digikey", "version": "0.1.0", "description": "Auth plane."},
    "paths": {
        "/v1/oauth/token": {
            "post": {
                "summary": "Exchange API key for JWT",
                "description": "Trades an opaque API key for a short-lived RS256 JWT.",
                "tags": ["oauth"],
                "requestBody": {
                    "content": {
                        "application/json": {
                            "schema": {"$ref": "#/components/schemas/TokenRequest"}
                        }
                    }
                },
                "responses": {"200": {"description": "Successful Response"}},
            }
        },
        "/healthz": {"get": {"summary": "Liveness", "tags": ["health"], "responses": {}}},
    },
}


def _write_spec(tmp_path: Path) -> Path:
    path = tmp_path / "digikey.json"
    path.write_text(json.dumps(_SPEC), encoding="utf-8")
    return path


def test_emits_one_heading_per_operation(tmp_path: Path) -> None:
    md = openapi_to_markdown(_write_spec(tmp_path), note_type="api_reference")
    assert "## GET /healthz" in md
    assert "## POST /v1/oauth/token" in md


def test_includes_operation_detail(tmp_path: Path) -> None:
    md = openapi_to_markdown(_write_spec(tmp_path), note_type="api_reference")
    assert "Trades an opaque API key" in md
    assert "TokenRequest" in md
    assert "oauth" in md


def test_operations_become_heading_segments(tmp_path: Path) -> None:
    md = openapi_to_markdown(_write_spec(tmp_path), note_type="api_reference")
    labels = [s.label for s in heading_segments(md)]
    assert any(label.endswith("GET /healthz") for label in labels)
    assert any(label.endswith("POST /v1/oauth/token") for label in labels)


def test_unparsable_spec_still_returns_markdown(tmp_path: Path) -> None:
    bad = tmp_path / "bad.json"
    bad.write_text("{not json", encoding="utf-8")
    md = openapi_to_markdown(bad, note_type="api_reference")
    assert md.startswith("# OpenAPI (unparsed)")


def test_output_ends_with_single_newline(tmp_path: Path) -> None:
    md = openapi_to_markdown(_write_spec(tmp_path), note_type="api_reference")
    assert md.endswith("\n")
    assert not md.endswith("\n\n")


def _write(tmp_path: Path, name: str, spec: dict) -> Path:
    path = tmp_path / name
    path.write_text(json.dumps(spec), encoding="utf-8")
    return path


def test_unterminated_fence_in_description_does_not_swallow_next_operation(
    tmp_path: Path,
) -> None:
    """Finding 1: an unbalanced ``` fence in a description must not make every
    following operation look like it's still inside a code block."""
    spec = {
        "paths": {
            "/a": {"get": {"description": 'Example usage:\n\n```json\n{"key": "value"}\n'}},
            "/b": {
                "post": {
                    "summary": "Second op",
                    "responses": {"201": {"description": "created"}},
                }
            },
        }
    }
    md = openapi_to_markdown(_write(tmp_path, "spec.json", spec), note_type="api_reference")
    labels = [s.label for s in heading_segments(md)]
    # One segment for the doc title/info block, plus one per operation.
    assert len(labels) == 3
    assert any(label.endswith("GET /a") for label in labels)
    assert any(label.endswith("POST /b") for label in labels)


def test_heading_in_description_does_not_hijack_structure(tmp_path: Path) -> None:
    """Finding 2: a bare ``#`` heading inside a description must not become a split
    point that steals content and corrupts breadcrumbs."""
    spec = {
        "paths": {
            "/a": {
                "get": {
                    "description": (
                        "See details below.\n\n# Danger heading\n\nThis text follows..."
                    ),
                    "responses": {"200": {"description": "ok"}},
                }
            },
            "/b": {
                "post": {
                    "summary": "Second op",
                    "responses": {"201": {"description": "created"}},
                }
            },
        }
    }
    md = openapi_to_markdown(_write(tmp_path, "spec.json", spec), note_type="api_reference")
    segments = heading_segments(md)
    labels = [s.label for s in segments]
    assert len(labels) == 3
    assert not any("Danger heading" in label for label in labels)
    assert any(label.endswith("GET /a") for label in labels)
    assert any(label.endswith("POST /b") for label in labels)
    # The words survive even though the heading marker is neutralized.
    assert any("Danger heading" in s.text for s in segments)


def test_contentless_operation_gets_its_own_segment(tmp_path: Path) -> None:
    """Finding 3: an operation with no summary/description/parameters/responses must
    still survive as its own segment instead of being merged into its neighbour."""
    spec = {
        "paths": {
            "/a/empty": {"get": {}},
            "/b/full": {
                "get": {"summary": "Has content", "responses": {"200": {"description": "ok"}}}
            },
        }
    }
    md = openapi_to_markdown(_write(tmp_path, "spec.json", spec), note_type="api_reference")
    labels = [s.label for s in heading_segments(md)]
    assert len(labels) == 3
    assert any(label.endswith("GET /a/empty") for label in labels)
    assert any(label.endswith("GET /b/full") for label in labels)


def test_array_type_schema_renders_readably(tmp_path: Path) -> None:
    """Finding 4: OpenAPI 3.1 array-type schemas (e.g. ``["string", "null"]``) must
    not render as a Python list repr."""
    spec = {
        "paths": {
            "/a": {
                "get": {
                    "parameters": [
                        {
                            "name": "x",
                            "in": "query",
                            "schema": {"type": ["string", "null"]},
                        }
                    ],
                    "responses": {},
                }
            }
        }
    }
    md = openapi_to_markdown(_write(tmp_path, "spec.json", spec), note_type="api_reference")
    assert "['string', 'null']" not in md
    assert "string | null" in md
