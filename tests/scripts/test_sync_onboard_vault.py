from __future__ import annotations

from pathlib import Path

import pytest
from digivault.vault import Vault

from scripts.sync_onboard_vault import _assert_not_confidential, main

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
