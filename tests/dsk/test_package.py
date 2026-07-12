"""write_skill_package / write_skill_zip tests."""

from __future__ import annotations

import zipfile
from pathlib import Path

import pytest

from digiskills.frontmatter import parse_skill_md
from digiskills.models import SkillManifest, SkillPackage, SkillReference
from digiskills.package import write_skill_package, write_skill_zip

pytestmark = pytest.mark.unit


def _package() -> SkillPackage:
    manifest = SkillManifest(name="acme-sdk", description="How to use the Acme SDK")
    return SkillPackage(
        manifest=manifest,
        body="# acme-sdk\n\nDo the thing.\n",
        references=[SkillReference(relative_path="references/readme.md", content="ref content")],
    )


def test_writes_skill_md_and_references(tmp_path: Path) -> None:
    package_dir = write_skill_package(_package(), tmp_path)

    assert package_dir == tmp_path / "acme-sdk"
    manifest, body = parse_skill_md((package_dir / "SKILL.md").read_text())
    assert manifest.name == "acme-sdk"
    assert "Do the thing." in body
    assert (package_dir / "references" / "readme.md").read_text() == "ref content"


def test_write_skill_package_creates_missing_out_dir(tmp_path: Path) -> None:
    nested = tmp_path / "does" / "not" / "exist"
    package_dir = write_skill_package(_package(), nested)
    assert package_dir.is_dir()
    assert (package_dir / "SKILL.md").exists()


def test_write_skill_package_rejects_escaping_reference(tmp_path: Path) -> None:
    manifest = SkillManifest(name="acme-sdk", description="d")
    # Bypass SkillReference's own traversal guard to exercise the writer's
    # defense-in-depth check directly.
    escaping_ref = SkillReference.model_construct(relative_path="../escape.md", content="x")
    package = SkillPackage.model_construct(
        manifest=manifest, body="body", references=[escaping_ref]
    )

    with pytest.raises(ValueError, match="escapes package root"):
        write_skill_package(package, tmp_path)


def test_write_skill_zip(tmp_path: Path) -> None:
    zip_path = write_skill_zip(_package(), tmp_path / "out" / "acme-sdk.zip")

    assert zip_path.exists()
    with zipfile.ZipFile(zip_path) as zf:
        names = set(zf.namelist())
        assert "acme-sdk/SKILL.md" in names
        assert "acme-sdk/references/readme.md" in names
        assert zf.read("acme-sdk/references/readme.md").decode() == "ref content"
