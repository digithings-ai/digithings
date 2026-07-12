"""P2 dogfood (ADR-0023 / epic #1453): compile skills from DigiThings' own
modules — their real `ARCHITECTURE.md` + `AGENTS.md` — as a known-good corpus
that validates the compiler pipeline end-to-end (ingest -> synthesize ->
package) against real repo content, not synthetic fixtures.

Uses `TemplateSynthesizer` (no LLM call, deterministic) — this validates
ingestion/packaging correctness, not `DigiLLMSynthesizer` prose quality (that
needs a live model and is a manual/human check, not a CI-safe one).
"""

from __future__ import annotations

import shutil
from pathlib import Path

import pytest

from digiskills.compiler import compile_skill
from digiskills.frontmatter import parse_skill_md
from digiskills.models import SkillSource, SourceKind
from digiskills.package import write_skill_package

pytestmark = pytest.mark.unit

REPO_ROOT = Path(__file__).resolve().parents[2]

# Every DigiThings module with doc files a real client-style user would point
# the compiler at (name -> path relative to repo root). Not every module has
# both files (e.g. digillm has no AGENTS.md yet) — _doc_files below tolerates
# that, requiring at least one.
_MODULES = {
    "digigraph": "digigraph",
    "digiquant": "digiquant",
    "digisearch": "digisearch",
    "digismith": "digismith",
    "digiclaw": "digiclaw",
    "digibase": "digibase",
    "digikey": "digikey",
    "digivault": "digivault",
    "digifetch": "digifetch",
    "digillm": "digillm",
    "digiskills": "digiskills",
    "digichat": "frontend/digichat",
}


def _doc_files(module: str) -> list[Path]:
    module_dir = REPO_ROOT / _MODULES[module]
    return [p for p in (module_dir / "ARCHITECTURE.md", module_dir / "AGENTS.md") if p.is_file()]


@pytest.mark.parametrize("module", list(_MODULES))
def test_dogfood_compiles_each_module(module: str, tmp_path: Path) -> None:
    """compile_skill succeeds and emits a well-formed, installable SKILL.md."""
    docs = _doc_files(module)
    assert docs, f"{module} has no ARCHITECTURE.md/AGENTS.md to dogfood against"

    staging = tmp_path / "src"
    staging.mkdir()
    for doc in docs:
        shutil.copy(doc, staging / doc.name)

    source = SkillSource(
        kind=SourceKind.LOCAL_PATH,
        name=module,
        description_hint=f"How to work with the DigiThings {module} module",
        local_path=staging,
    )
    result = compile_skill(source)

    assert result.document_count == len(docs)
    assert result.warnings == [], "real module docs should never hit the size/count caps"
    assert result.package.manifest.name == module

    package_dir = write_skill_package(result.package, tmp_path / "out")
    manifest, body = parse_skill_md((package_dir / "SKILL.md").read_text())
    assert manifest.name == module
    assert body.strip()
    for doc in docs:
        assert (package_dir / "references" / doc.name).is_file()
