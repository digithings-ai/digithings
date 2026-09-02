from __future__ import annotations

from pathlib import Path

import pytest
from digivault.vault import Vault

from scripts.sync_onboard_vault import _assert_not_confidential, _prune_stale_children, main

pytestmark = pytest.mark.unit


def test_assert_not_confidential_allows_tmp(tmp_path: Path) -> None:
    _assert_not_confidential(str(tmp_path))


def test_assert_not_confidential_refuses_projects(tmp_path: Path) -> None:
    bad = tmp_path / "projects" / "secret"
    bad.mkdir(parents=True)
    with pytest.raises(SystemExit):
        _assert_not_confidential(str(bad))


def test_sync_onboard_vault_dry_run(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    vault_root = tmp_path / "vault"
    vault_root.mkdir()
    Vault(vault_root).write_note(
        "arch",
        frontmatter={
            "title": "Arch",
            "tags": ["onboard", "repo_doc"],
            "type": "reference",
            "status": "published",
            "page_class": "repo_doc",
        },
        body="> Tagline\n\nBody about digigraph.\n",
        subdir="clients/digithings",
        overwrite=True,
    )
    rc = main(["--vault", str(vault_root), "--dry-run"])
    assert rc == 0
    out = capsys.readouterr().out
    assert "Arch" in out
    assert "body_chars" in out


def test_prune_stale_children_deletes_only_matching_parent_and_directory() -> None:
    class Connector:
        def __init__(self) -> None:
            self.deleted: list[str] = []

        def select(self, _table: str, **_kwargs: object) -> object:
            return type(
                "Result",
                (),
                {
                    "success": True,
                    "rows": [
                        {"vault_path": "clients/acme/guide__stale"},
                        {"vault_path": "clients/other/guide__stale"},
                    ],
                    "error": "",
                },
            )()

        def delete(self, _table: str, *, in_: dict[str, list[str]]) -> object:
            self.deleted.extend(in_["vault_path"])
            return type("Result", (), {"success": True, "rows": len(self.deleted), "error": ""})()

    connector = Connector()
    rows = [
        {"slug": "guide", "vault_path": "clients/acme/guide", "frontmatter": {}},
        {
            "slug": "guide__current",
            "vault_path": "clients/acme/guide__current",
            "frontmatter": {"parent_doc": "guide"},
        },
    ]

    deleted = _prune_stale_children(connector, "architecture_notes", rows)

    assert deleted == ["clients/acme/guide__stale"]
    assert connector.deleted == ["clients/acme/guide__stale"]
