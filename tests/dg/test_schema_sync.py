"""Guard: the JSON Schema embedded in ``docs/spec/project-spec-v1alpha1.md`` must
match the extracted file at ``digigraph/src/digigraph/schemas/digiproject.v1alpha1.json``.

The JSON file is the single source of truth at runtime; the spec doc copy is for
humans. This test catches drift between the two.
"""

from __future__ import annotations

import json
import re
from pathlib import Path

import pytest

from digigraph.schemas import DIGIPROJECT_V1ALPHA1, load_schema, schema_path

REPO_ROOT = Path(__file__).resolve().parents[2]
SPEC_DOC = REPO_ROOT / "docs" / "spec" / "project-spec-v1alpha1.md"

# Match a fenced ```json ... ``` block that contains the DigiProject title.
_JSON_BLOCK = re.compile(
    r"```json\s*\n(?P<body>\{.*?\"title\"\s*:\s*\"DigiProject v1alpha1\".*?\})\s*\n```",
    re.DOTALL,
)


def _extract_embedded_schema() -> dict:
    text = SPEC_DOC.read_text()
    match = _JSON_BLOCK.search(text)
    assert match, (
        f"Could not locate DigiProject v1alpha1 JSON Schema block in {SPEC_DOC}. "
        "Expected a ```json fenced code block containing the schema."
    )
    return json.loads(match.group("body"))


@pytest.mark.unit
def test_spec_doc_contains_schema_block() -> None:
    embedded = _extract_embedded_schema()
    assert embedded.get("title") == "DigiProject v1alpha1"


@pytest.mark.unit
def test_extracted_schema_matches_spec_doc() -> None:
    """Parsed-equality check: embedded block == extracted JSON file (ignores formatting)."""
    embedded = _extract_embedded_schema()
    extracted = load_schema(DIGIPROJECT_V1ALPHA1)
    assert embedded == extracted, (
        f"Schema drift detected. Update either {SPEC_DOC} or {schema_path(DIGIPROJECT_V1ALPHA1)} "
        "so they match."
    )
