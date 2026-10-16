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


def test_tags_with_unterminated_fence_does_not_swallow_next_operations(
    tmp_path: Path,
) -> None:
    """Finding 1: ``tags`` is an ordinary JSON string list, not "prose" — an unbalanced
    fence embedded in a tag must not swallow every following operation, exactly like
    the same hazard in ``description`` (see the fence test above)."""
    spec = {
        "paths": {
            "/a": {"get": {"tags": ["x\n\n```json\nunterminated"]}},
            "/b": {"post": {}},
            "/c": {"get": {}},
        }
    }
    md = openapi_to_markdown(_write(tmp_path, "spec.json", spec), note_type="api_reference")
    labels = [s.label for s in heading_segments(md)]
    assert len(labels) == 4
    assert any(label.endswith("GET /a") for label in labels)
    assert any(label.endswith("POST /b") for label in labels)
    assert any(label.endswith("GET /c") for label in labels)


def test_operation_id_with_unterminated_fence_does_not_swallow_next_operations(
    tmp_path: Path,
) -> None:
    """Finding 1: same hazard via ``operationId``."""
    spec = {
        "paths": {
            "/a": {"get": {"operationId": "op\n\n```json\nunterminated"}},
            "/b": {"post": {}},
            "/c": {"get": {}},
        }
    }
    md = openapi_to_markdown(_write(tmp_path, "spec.json", spec), note_type="api_reference")
    labels = [s.label for s in heading_segments(md)]
    assert len(labels) == 4
    assert any(label.endswith("GET /a") for label in labels)
    assert any(label.endswith("POST /b") for label in labels)
    assert any(label.endswith("GET /c") for label in labels)


def test_parameter_name_with_unterminated_fence_does_not_swallow_next_operations(
    tmp_path: Path,
) -> None:
    """Finding 1: same hazard via a parameter's ``name``."""
    spec = {
        "paths": {
            "/a": {
                "get": {
                    "parameters": [{"name": "x\n\n```json\nunterminated", "in": "query"}],
                }
            },
            "/b": {"post": {}},
            "/c": {"get": {}},
        }
    }
    md = openapi_to_markdown(_write(tmp_path, "spec.json", spec), note_type="api_reference")
    labels = [s.label for s in heading_segments(md)]
    assert len(labels) == 4
    assert any(label.endswith("GET /a") for label in labels)
    assert any(label.endswith("POST /b") for label in labels)
    assert any(label.endswith("GET /c") for label in labels)


def test_tags_with_heading_does_not_hijack_structure(tmp_path: Path) -> None:
    """Finding 1 (heading-hijack variant): a heading embedded in a ``tags`` entry must
    not become a split point that corrupts breadcrumbs for following operations."""
    spec = {
        "paths": {
            "/a": {"get": {"tags": ["x\n\n# Sneaky via tags\n\nmore"]}},
            "/b": {"post": {}},
        }
    }
    md = openapi_to_markdown(_write(tmp_path, "spec.json", spec), note_type="api_reference")
    segments = heading_segments(md)
    labels = [s.label for s in segments]
    assert len(labels) == 3
    assert not any("Sneaky via tags" in label for label in labels)
    assert any(label.endswith("GET /a") for label in labels)
    assert any(label.endswith("POST /b") for label in labels)
    # The words survive even though the heading marker is neutralized.
    assert any("Sneaky via tags" in s.text for s in segments)


def test_fenced_code_is_not_escaped_inside_balanced_fence(tmp_path: Path) -> None:
    """Finding 2: ``_sanitize_free_text`` must not escape a ``#`` that sits inside a
    balanced fenced code block — it can't act as a split point there anyway, because
    the downstream segmenter is itself fence-aware, and escaping it corrupts code that
    should render verbatim."""
    spec = {
        "paths": {
            "/a": {
                "get": {
                    "description": (
                        "Example:\n\n```python\n# This is a comment at line start\n"
                        "x = 1\n```\n\nDone."
                    )
                }
            }
        }
    }
    md = openapi_to_markdown(_write(tmp_path, "spec.json", spec), note_type="api_reference")
    assert "# This is a comment at line start" in md
    assert "\\# This is a comment at line start" not in md


def test_summary_bare_fence_does_not_swallow_next_operations(tmp_path: Path) -> None:
    """Root cause repro: a value whose OWN first line is a bare fence opener defeats
    isolated fence-tracking, because the value is interpolated INLINE after a literal
    prefix ('**') rather than emitted as its own standalone line — a closing fence
    appended by a multi-line sanitizer inherits the template's trailing text (e.g.
    ``` **```), which the real segmenter then reads as a fresh, unbalanced fence
    opener and swallows every following operation."""
    spec = {
        "paths": {
            "/a": {"get": {"summary": "```json\nunterminated"}},
            "/b": {"post": {}},
            "/c": {"get": {}},
        }
    }
    md = openapi_to_markdown(_write(tmp_path, "spec.json", spec), note_type="api_reference")
    labels = [s.label for s in heading_segments(md)]
    assert len(labels) == 4
    assert any(label.endswith("GET /a") for label in labels)
    assert any(label.endswith("POST /b") for label in labels)
    assert any(label.endswith("GET /c") for label in labels)


def test_tags_bare_fence_does_not_swallow_next_operations(tmp_path: Path) -> None:
    """Same root-cause repro via ``tags`` (inline after 'Tags: ')."""
    spec = {
        "paths": {
            "/a": {"get": {"tags": ["```json\nunterminated"]}},
            "/b": {"post": {}},
            "/c": {"get": {}},
        }
    }
    md = openapi_to_markdown(_write(tmp_path, "spec.json", spec), note_type="api_reference")
    labels = [s.label for s in heading_segments(md)]
    assert len(labels) == 4
    assert any(label.endswith("GET /a") for label in labels)
    assert any(label.endswith("POST /b") for label in labels)
    assert any(label.endswith("GET /c") for label in labels)


def test_operation_id_bare_fence_does_not_swallow_next_operations(tmp_path: Path) -> None:
    """Same root-cause repro via ``operationId`` (inline after 'Operation ID: `')."""
    spec = {
        "paths": {
            "/a": {"get": {"operationId": "```json\nunterminated"}},
            "/b": {"post": {}},
            "/c": {"get": {}},
        }
    }
    md = openapi_to_markdown(_write(tmp_path, "spec.json", spec), note_type="api_reference")
    labels = [s.label for s in heading_segments(md)]
    assert len(labels) == 4
    assert any(label.endswith("GET /a") for label in labels)
    assert any(label.endswith("POST /b") for label in labels)
    assert any(label.endswith("GET /c") for label in labels)


def test_parameter_name_bare_fence_does_not_swallow_next_operations(tmp_path: Path) -> None:
    """Same root-cause repro via parameter ``name`` (inline after '- `')."""
    spec = {
        "paths": {
            "/a": {"get": {"parameters": [{"name": "```json\nunterminated", "in": "query"}]}},
            "/b": {"post": {}},
            "/c": {"get": {}},
        }
    }
    md = openapi_to_markdown(_write(tmp_path, "spec.json", spec), note_type="api_reference")
    labels = [s.label for s in heading_segments(md)]
    assert len(labels) == 4
    assert any(label.endswith("GET /a") for label in labels)
    assert any(label.endswith("POST /b") for label in labels)
    assert any(label.endswith("GET /c") for label in labels)


def test_route_bare_fence_does_not_swallow_next_operations(tmp_path: Path) -> None:
    """Same root-cause repro via the route/path key itself (inline after '## ' and
    'Endpoint: '). Other routes use '~'-prefixed names so they sort after the
    poisoned route (backtick > '/' but < '~' in ASCII), keeping them positioned to
    be swallowed if the fix regresses."""
    spec = {
        "paths": {
            "```json\nunterminated": {"get": {}},
            "~b": {"post": {}},
            "~c": {"get": {}},
        }
    }
    md = openapi_to_markdown(_write(tmp_path, "spec.json", spec), note_type="api_reference")
    labels = [s.label for s in heading_segments(md)]
    assert len(labels) == 4
    assert any("unterminated" in label for label in labels)
    assert any(label.endswith("POST ~b") for label in labels)
    assert any(label.endswith("GET ~c") for label in labels)


def test_info_title_bare_fence_does_not_swallow_next_operations(tmp_path: Path) -> None:
    """Same root-cause repro via ``info.title`` (inline after '# ') — the earliest
    possible poison point, capable of swallowing the ENTIRE rest of the document."""
    spec = {
        "info": {"title": "```json\nunterminated"},
        "paths": {
            "/a": {"get": {}},
            "/b": {"post": {}},
        },
    }
    md = openapi_to_markdown(_write(tmp_path, "spec.json", spec), note_type="api_reference")
    labels = [s.label for s in heading_segments(md)]
    assert len(labels) == 3
    assert any(label.endswith("GET /a") for label in labels)
    assert any(label.endswith("POST /b") for label in labels)


def test_response_description_bare_fence_does_not_swallow_next_operations(
    tmp_path: Path,
) -> None:
    """Same root-cause repro via response ``description`` (inline after '- `{code}`: ')."""
    spec = {
        "paths": {
            "/a": {"get": {"responses": {"200": {"description": "```json\nunterminated"}}}},
            "/b": {"post": {}},
            "/c": {"get": {}},
        }
    }
    md = openapi_to_markdown(_write(tmp_path, "spec.json", spec), note_type="api_reference")
    labels = [s.label for s in heading_segments(md)]
    assert len(labels) == 4
    assert any(label.endswith("GET /a") for label in labels)
    assert any(label.endswith("POST /b") for label in labels)
    assert any(label.endswith("GET /c") for label in labels)


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
