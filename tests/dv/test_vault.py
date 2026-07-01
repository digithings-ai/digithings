"""Vault index, backlinks, maintenance ops, and lint tests."""

from __future__ import annotations

from pathlib import Path

import pytest

from digivault import Vault, VaultError

pytestmark = pytest.mark.unit


def _write(root: Path, name: str, text: str) -> None:
    (root / f"{name}.md").write_text(text, encoding="utf-8")


def _vault_with_notes(root: Path) -> Vault:
    _write(root, "a", "---\ntitle: A\ntags: [module]\n---\nlinks to [[b]] and [[c]]\n")
    _write(root, "b", "---\ntitle: B\ntags: [module, shipped]\n---\nlinks to [[c]]\n")
    _write(root, "c", "---\ntitle: C\n---\nleaf note\n")
    return Vault(root)


def test_index_and_backlinks(tmp_path: Path) -> None:
    vault = _vault_with_notes(tmp_path)
    assert {n.name for n in vault.list_notes()} == {"a", "b", "c"}
    assert vault.backlinks("c") == ("a", "b")
    assert vault.backlinks("b") == ("a",)
    assert vault.backlinks("a") == ()


def test_search_by_tag(tmp_path: Path) -> None:
    vault = _vault_with_notes(tmp_path)
    assert [n.name for n in vault.search_by_tag("shipped")] == ["b"]
    assert [n.name for n in vault.search_by_tag("module")] == ["a", "b"]


def test_create_note(tmp_path: Path) -> None:
    vault = _vault_with_notes(tmp_path)
    note = vault.create_note("d", frontmatter={"title": "D"}, body="points at [[a]]\n")
    assert note.name == "d"
    assert (tmp_path / "d.md").is_file()
    assert vault.backlinks("a") == ("d",)


def test_create_duplicate_rejected(tmp_path: Path) -> None:
    vault = _vault_with_notes(tmp_path)
    with pytest.raises(VaultError):
        vault.create_note("a")


def test_create_rejects_path_escape(tmp_path: Path) -> None:
    vault = _vault_with_notes(tmp_path)
    with pytest.raises(VaultError):
        vault.create_note("../evil")


def test_rename_rewrites_inbound_links(tmp_path: Path) -> None:
    vault = _vault_with_notes(tmp_path)
    vault.rename("c", "gamma")
    assert vault.get_note("c") is None
    assert vault.get_note("gamma") is not None
    # a and b should now link to gamma
    assert "[[gamma]]" in (tmp_path / "a.md").read_text()
    assert "[[gamma]]" in (tmp_path / "b.md").read_text()
    assert vault.backlinks("gamma") == ("a", "b")


def test_set_frontmatter(tmp_path: Path) -> None:
    vault = _vault_with_notes(tmp_path)
    note = vault.set_frontmatter("c", {"status": "shipped"})
    assert note.frontmatter["status"] == "shipped"


def test_lint_clean_vault(tmp_path: Path) -> None:
    vault = _vault_with_notes(tmp_path)
    report = vault.lint()
    assert report.ok is True
    assert report.note_count == 3


def test_lint_flags_unresolved_link(tmp_path: Path) -> None:
    _write(tmp_path, "a", "links to [[missing]]\n")
    report = Vault(tmp_path).lint()
    assert report.ok is False
    assert any(i.kind == "unresolved_link" for i in report.issues)


def test_lint_required_frontmatter(tmp_path: Path) -> None:
    (tmp_path / ".digivault.yml").write_text("required_frontmatter: [title]\n", encoding="utf-8")
    _write(tmp_path, "a", "no frontmatter here\n")
    report = Vault(tmp_path).lint()
    assert any(i.kind == "missing_frontmatter" for i in report.issues)


def test_manifest_taxonomy_flags_unknown_tag(tmp_path: Path) -> None:
    (tmp_path / ".digivault.yml").write_text("allowed_tags: [module]\n", encoding="utf-8")
    _write(tmp_path, "a", "---\ntags: [bogus]\n---\nbody\n")
    report = Vault(tmp_path).lint()
    assert any("taxonomy" in i.message for i in report.issues)
    # Taxonomy violations carry their own kind, not 'missing_frontmatter'.
    assert any(i.kind == "disallowed_tag" for i in report.issues)
    assert not any(i.kind == "missing_frontmatter" for i in report.issues)


def test_lint_flags_duplicate_stems(tmp_path: Path) -> None:
    _write(tmp_path, "a", "first copy\n")
    sub = tmp_path / "sub"
    sub.mkdir()
    (sub / "a.md").write_text("second copy\n", encoding="utf-8")
    vault = Vault(tmp_path)
    # Only the first (deterministic) note is indexed; the collision is not lost.
    assert vault.get_note("a") is not None
    report = vault.lint()
    assert report.ok is False
    dups = [i for i in report.issues if i.kind == "duplicate_note"]
    assert len(dups) == 1
    assert "a.md" in dups[0].message and "sub/a.md" in dups[0].message


def test_missing_root_raises(tmp_path: Path) -> None:
    with pytest.raises(VaultError):
        Vault(tmp_path / "does-not-exist")
