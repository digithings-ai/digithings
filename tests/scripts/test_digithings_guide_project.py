"""Unit tests for the DigiThings-guide project config.

Validates that:
  1. digiproject.yaml parses as valid YAML and conforms to the v1alpha1
     JSON Schema that is documented in docs/spec/project-spec-v1alpha1.md.
  2. The index manifest at indexes/docs.yaml has the fields that
     digigraph.project_config._discover_indexes_from_dir expects.
  3. The reindex script resolves at least one source file from the
     manifest globs (catches regressions where a rename silently empties
     the source list).
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

import pytest

yaml = pytest.importorskip("yaml")

REPO_ROOT = Path(__file__).resolve().parents[2]
PROJECT_DIR = REPO_ROOT / "docs" / "projects" / "digithings-guide"
PROJECT_CONFIG = PROJECT_DIR / "digiproject.yaml"
INDEX_MANIFEST = PROJECT_DIR / "indexes" / "docs.yaml"
SPEC_MD = REPO_ROOT / "docs" / "spec" / "project-spec-v1alpha1.md"


pytestmark = pytest.mark.unit


def _load_yaml_with_env_substitution(path: Path) -> dict:
    """Read YAML, stripping ``${VAR:-default}`` defaults so safe_load tolerates them.

    digigraph.project_config performs env substitution before parsing; we do a
    minimal equivalent here so the test isn't coupled to that module.
    """
    raw = path.read_text()
    # Replace ${NAME:-default} / ${NAME} with the default (or empty string).
    raw = re.sub(r"\$\{([A-Z_][A-Z0-9_]*):-([^}]*)\}", r"\2", raw)
    raw = re.sub(r"\$\{([A-Z_][A-Z0-9_]*)\}", "", raw)
    return yaml.safe_load(raw) or {}


def _extract_schema_from_spec() -> dict:
    """Extract the JSON Schema block from docs/spec/project-spec-v1alpha1.md."""
    import json

    text = SPEC_MD.read_text()
    match = re.search(r"```json\n(\{.*?\})\n```", text, re.DOTALL)
    assert match is not None, "could not find JSON Schema block in project-spec-v1alpha1.md"
    return json.loads(match.group(1))


def test_project_config_is_valid_yaml() -> None:
    data = _load_yaml_with_env_substitution(PROJECT_CONFIG)
    assert data["project"]["name"] == "digithings-guide"
    assert re.match(r"^\d+\.\d+\.\d+", data["project"]["version"])


def test_project_config_conforms_to_v1alpha1_schema() -> None:
    jsonschema = pytest.importorskip("jsonschema")
    schema = _extract_schema_from_spec()
    data = _load_yaml_with_env_substitution(PROJECT_CONFIG)
    # Raises jsonschema.ValidationError on mismatch.
    jsonschema.validate(instance=data, schema=schema)


def test_index_manifest_has_required_fields() -> None:
    data = yaml.safe_load(INDEX_MANIFEST.read_text())
    # _discover_indexes_from_dir reads these:
    assert data["index_name"] == "docs"
    assert data["backend"] in {"azure_search", "chroma"}
    # Forward-looking sources extension (consumed by reindex script + GH Action):
    assert isinstance(data["sources"], list)
    assert len(data["sources"]) > 0


def test_reindex_script_resolves_source_files() -> None:
    # Import the script as a module.
    scripts_dir = REPO_ROOT / "scripts"
    sys.path.insert(0, str(scripts_dir))
    try:
        import reindex_digithings_guide as rix  # type: ignore[import-not-found]
    finally:
        sys.path.pop(0)

    index_name, paths = rix.resolve_sources(INDEX_MANIFEST)
    assert index_name == "docs"
    # Sanity: at minimum README.md, ROADMAP.md, ARCHITECTURE.md, docs/VISION.md,
    # and the ADR index should resolve. If this drops to zero something is very wrong.
    assert len(paths) >= 5
    rels = {p.relative_to(REPO_ROOT).as_posix() for p in paths}
    assert "README.md" in rels
    assert "ROADMAP.md" in rels
    assert "ARCHITECTURE.md" in rels
    assert "docs/VISION.md" in rels
    assert any(r.startswith("docs/adr/") for r in rels)


def test_workflow_paths_match_manifest_sources() -> None:
    """The GH Action's `paths:` filter should be a superset of the manifest's
    `sources:` (minus the meta paths that trigger on config changes). Drift here
    means the Action won't fire when a tracked doc changes."""
    workflow = REPO_ROOT / ".github" / "workflows" / "reindex-digithings-guide.yml"
    manifest = yaml.safe_load(INDEX_MANIFEST.read_text())
    wf = yaml.safe_load(workflow.read_text())
    # PyYAML parses the `on:` key as the boolean True. Support both spellings.
    push_cfg = (wf.get("on") or wf.get(True) or {}).get("push", {})
    wf_paths = set(push_cfg.get("paths", []))
    missing = [src for src in manifest["sources"] if src not in wf_paths]
    assert not missing, f"workflow paths missing sources: {missing}"


def test_manifest_sources_match_workflow_paths() -> None:
    """Every workflow `paths:` entry must correspond to a manifest source (or a
    known meta path). An orphan `paths:` entry that doesn't map to any source
    means the Action triggers on files that won't actually be reindexed.

    Reverse of test_workflow_paths_match_manifest_sources — together they ensure
    the two lists stay in sync (paths ⊆ sources ∪ META_PATHS and sources ⊆ paths).
    """
    # These workflow paths legitimately have no matching manifest source — they
    # exist to trigger the Action when project config or the script itself changes.
    META_PATHS = {
        "docs/projects/digithings-guide/**",
        "scripts/reindex_digithings_guide.py",
        ".github/workflows/reindex-digithings-guide.yml",
    }
    workflow = REPO_ROOT / ".github" / "workflows" / "reindex-digithings-guide.yml"
    manifest = yaml.safe_load(INDEX_MANIFEST.read_text())
    wf = yaml.safe_load(workflow.read_text())
    # PyYAML parses the `on:` key as the boolean True. Support both spellings.
    push_cfg = (wf.get("on") or wf.get(True) or {}).get("push", {})
    wf_paths = set(push_cfg.get("paths", []))
    sources = set(manifest["sources"])
    orphans = [p for p in wf_paths if p not in sources and p not in META_PATHS]
    assert not orphans, f"workflow paths not covered by manifest sources: {orphans}"
