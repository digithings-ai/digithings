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
