"""Scoped duplicate-stem handling must be prefix-neutral (#4256).

A caller scoped to one corpus (``path_prefix``) must learn nothing about notes
outside that prefix. Before this fix, a duplicate filename stem living in
another corpus changed both ``create_note`` and ``lint``:

- ``create_note`` refused ``<prefix>/<stem>.md`` with "Note already exists"
  purely because ``<other-corpus>/<stem>.md`` existed (existence oracle).
- ``lint`` surfaced a ``duplicate_note`` issue whose message joined every
  colliding path, leaking the out-of-prefix path.

Each test compares the scoped result in two vaults: one where the duplicate
only exists outside the prefix, and a control where it does not exist at all.
The results must be identical.
"""

from __future__ import annotations

from pathlib import Path

import pytest
from digivault.tool_dispatch import (
    TOOL_VAULT_CREATE_NOTE,
    TOOL_VAULT_LINT,
    dispatch_vault_tool,
)
from digivault.vault import Vault

pytestmark = pytest.mark.unit

_PREFIX = "corpusA"
_STEM = "secret"


def _write(root: Path, rel: str, title: str) -> None:
    path = root / rel
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(f"---\ntitle: {title}\n---\n\n", encoding="utf-8")


def _create_vault(root: Path, *, with_outside_dup: bool) -> Vault:
    """corpusA/keep.md, plus corpusB/secret.md when the outside duplicate is wanted."""
    _write(root, f"{_PREFIX}/keep.md", "Keep")
    if with_outside_dup:
        _write(root, f"corpusB/{_STEM}.md", "Outside")
    return Vault(root)


def _lint_vault(root: Path, *, with_outside_dup: bool) -> Vault:
    """corpusA/secret.md, plus corpusB/secret.md when the outside duplicate is wanted."""
    _write(root, f"{_PREFIX}/{_STEM}.md", "Mine")
    if with_outside_dup:
        _write(root, f"corpusB/{_STEM}.md", "Outside")
    return Vault(root)


def test_scoped_create_note_is_prefix_neutral(tmp_path: Path) -> None:
    """Creating a note under the prefix must not depend on an outside duplicate."""
    with_dup = _create_vault(tmp_path / "with_dup", with_outside_dup=True)
    without_dup = _create_vault(tmp_path / "without_dup", with_outside_dup=False)

    args = {"name": _STEM, "title": "Mine", "path_prefix": _PREFIX}
    result_with = dispatch_vault_tool(TOOL_VAULT_CREATE_NOTE, args, with_dup)
    result_without = dispatch_vault_tool(TOOL_VAULT_CREATE_NOTE, args, without_dup)

    assert result_with.ok is result_without.ok
    assert result_with.ok is True, result_with.error
    assert result_with.data is not None and result_without.data is not None
    assert (
        result_with.data["rel_path"] == result_without.data["rel_path"] == f"{_PREFIX}/{_STEM}.md"
    )


def test_scoped_lint_does_not_leak_outside_duplicate(tmp_path: Path) -> None:
    """Scoped lint must not report (or name) a duplicate that lives outside the prefix."""
    with_dup = _lint_vault(tmp_path / "with_dup", with_outside_dup=True)
    without_dup = _lint_vault(tmp_path / "without_dup", with_outside_dup=False)

    args = {"path_prefix": _PREFIX}
    report_with = dispatch_vault_tool(TOOL_VAULT_LINT, args, with_dup)
    report_without = dispatch_vault_tool(TOOL_VAULT_LINT, args, without_dup)

    assert report_with.ok is True and report_without.ok is True
    assert report_with.data == report_without.data, (
        "scoped lint output changed because a duplicate exists outside the prefix"
    )
    assert "corpusB" not in str(report_with.data)


def test_scoped_lint_flags_duplicate_inside_prefix(tmp_path: Path) -> None:
    """A duplicate wholly inside the prefix is still reported, with no outside paths."""
    root = tmp_path / "vault"
    (root / _PREFIX).mkdir(parents=True)
    (root / _PREFIX / f"{_STEM}.md").write_text("---\ntitle: A\n---\n\n", encoding="utf-8")
    (root / _PREFIX / "nested").mkdir(parents=True)
    (root / _PREFIX / "nested" / f"{_STEM}.md").write_text(
        "---\ntitle: B\n---\n\n", encoding="utf-8"
    )
    report = dispatch_vault_tool(TOOL_VAULT_LINT, {"path_prefix": _PREFIX}, Vault(root))
    assert report.ok is True and report.data is not None
    dup_issues = [i for i in report.data["issues"] if i["kind"] == "duplicate_note"]
    assert len(dup_issues) == 1
    assert f"{_PREFIX}/nested/{_STEM}.md" in dup_issues[0]["message"]
