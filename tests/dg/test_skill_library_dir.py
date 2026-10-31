"""External skill packs via DIGIGRAPH_SKILLS_DIR, with the packaged library as fallback."""

from __future__ import annotations

from pathlib import Path

import pytest

pytestmark = pytest.mark.unit

PACK = "example"
SKILL = "answer-briefly"


def _write(root: Path, pack: str, name: str, body: str) -> None:
    folder = root / pack / name
    folder.mkdir(parents=True)
    (folder / "SKILL.md").write_text(
        f"---\nname: {name}\ndescription: One line.\n---\n{body}\n",
        encoding="utf-8",
    )


@pytest.mark.unit
def test_external_dir_serves_the_example_pack(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from digigraph.skill_library.loader import (
        SKILLS_DIR_ENV,
        SkillDocumentError,
        list_skill_documents,
        load_skill_document,
        pack_dir,
        skills_dir,
    )

    _write(tmp_path, PACK, SKILL, "Be brief.")
    _write(tmp_path, PACK, "cite-sources", "Cite the source.")
    _write(tmp_path, "house", "house-note", "House only.")
    monkeypatch.setenv(SKILLS_DIR_ENV, str(tmp_path))

    assert skills_dir() == Path(str(tmp_path))
    assert pack_dir(PACK) == tmp_path / PACK
    docs = list_skill_documents(PACK)
    assert [doc.name for doc in docs] == [SKILL, "cite-sources"]
    loaded = load_skill_document(SKILL, PACK)
    assert loaded.body == "Be brief."
    assert loaded.description == "One line."
    assert loaded.source == f"skill_library/{PACK}/{SKILL}/SKILL.md"
    assert list_skill_documents(None) == []
    assert [doc.name for doc in list_skill_documents("house")] == ["house-note"]
    with pytest.raises(SkillDocumentError, match="unknown skill"):
        load_skill_document(SKILL, "house")


@pytest.mark.unit
def test_external_dir_wins_over_the_packaged_library(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from digigraph.skill_library import loader

    external = tmp_path / "external"
    packaged = tmp_path / "packaged"
    _write(external, PACK, SKILL, "From the directory.")
    _write(packaged, PACK, SKILL, "From the package.")
    _write(packaged, PACK, "packaged-only", "Package only.")
    monkeypatch.setattr(loader, "SKILL_LIBRARY_DIR", packaged)
    monkeypatch.setenv(loader.SKILLS_DIR_ENV, str(external))

    assert loader.load_skill_document(SKILL, PACK).body == "From the directory."
    with pytest.raises(loader.SkillDocumentError, match="unknown skill"):
        loader.load_skill_document("packaged-only", PACK)


@pytest.mark.unit
def test_unset_or_blank_env_reads_the_packaged_library(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from digigraph.skill_library import loader

    external = tmp_path / "external"
    packaged = tmp_path / "packaged"
    _write(external, PACK, SKILL, "From the directory.")
    _write(packaged, PACK, SKILL, "From the package.")
    monkeypatch.setattr(loader, "SKILL_LIBRARY_DIR", packaged)

    monkeypatch.delenv(loader.SKILLS_DIR_ENV, raising=False)
    assert loader.skills_dir() == packaged
    assert loader.pack_dir(PACK) == packaged / PACK
    assert loader.load_skill_document(SKILL, PACK).body == "From the package."

    monkeypatch.setenv(loader.SKILLS_DIR_ENV, "   ")
    assert loader.skills_dir() == packaged
    assert loader.load_skill_document(SKILL, PACK).body == "From the package."


@pytest.mark.unit
def test_external_dir_keeps_the_path_guard(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    from digigraph.skill_library import loader

    root = tmp_path / "skills"
    _write(root, PACK, SKILL, "Be brief.")
    # A document sitting just outside the root. The pack pattern is what keeps
    # a "../secret" pack name from joining onto it.
    outside = tmp_path / "secret" / SKILL
    outside.mkdir(parents=True)
    (outside / "SKILL.md").write_text(
        f"---\nname: {SKILL}\ndescription: no\n---\nescaped\n",
        encoding="utf-8",
    )
    monkeypatch.setenv(loader.SKILLS_DIR_ENV, str(root))

    escapes = (
        "../secret",
        "/etc",
        "example/../example",
        "..",
        "example/../../secret",
        "ex ample",
    )
    for pack in escapes:
        assert loader.pack_dir(pack) is None, pack
        assert loader.list_skill_documents(pack) == [], pack
        with pytest.raises(loader.SkillDocumentError, match="unknown skill"):
            loader.load_skill_document(SKILL, pack)
    for name in ("../answer-briefly", "/etc/passwd", "answer-briefly/../../secret", "Answer"):
        with pytest.raises(loader.SkillDocumentError, match="not a valid skill id"):
            loader.load_skill_document(name, PACK)
    assert loader.load_skill_document(SKILL, PACK).body == "Be brief."
