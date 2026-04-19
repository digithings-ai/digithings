"""Unit tests for ``digi project migrate`` CLI and migration library."""

from __future__ import annotations

from pathlib import Path

import pytest
import yaml

from digigraph.cli import main as cli_main
from digigraph.project_migrate import migrate_mapping, migrate_project_file
from digigraph.project_validate import validate_project_file


@pytest.fixture
def _clean_env(monkeypatch: pytest.MonkeyPatch) -> None:
    for var in ("DIGISEARCH_URL", "OPENAI_API_BASE", "DIGIQUANT_URL"):
        monkeypatch.delenv(var, raising=False)


LEGACY_CONFIG: dict[str, object] = {
    "project": {"name": "legacy", "description": "old config", "version": "0.1.0"},
    "agents": {"enabled": ["research"], "llm_mode": "test"},
    "run_storage": {"dir": "/data/run", "backend": "local"},
    "graph": {"workflow_profile": "research_rag", "extra": "ignored"},
    "mcp": {"enabled": False, "port": 8765, "tools": ["digigraph_workflow"]},
    "services": {"digisearch_url": "http://ds:8002"},
    "unknown_top": {"foo": "bar"},
}

EXPECTED_MIGRATED: dict[str, object] = {
    "project": {"name": "legacy", "description": "old config", "version": "0.1.0"},
    "agents": {
        "enabled": ["research"],
        "llm_mode": "test",
        "workflow_profile": "research_rag",
    },
    "mcp": {"enabled": False, "port": 8765, "tools": ["digigraph_workflow"]},
    "services": {"digisearch_url": "http://ds:8002"},
    "run_data_dir": "/data/run",
}


@pytest.mark.unit
def test_migrate_snapshot_matches_expected_shape() -> None:
    with pytest.warns(UserWarning):
        out, report = migrate_mapping(LEGACY_CONFIG)
    assert out == EXPECTED_MIGRATED
    # warnings: run_storage extras, graph extras, unknown_top
    joined = "\n".join(report.warnings)
    assert "run_storage" in joined
    assert "graph" in joined
    assert "unknown_top" in joined


@pytest.mark.unit
def test_migrate_unknown_key_warns(recwarn: pytest.WarningsRecorder) -> None:
    out, report = migrate_mapping({"project": {"name": "x"}, "mystery": 42})
    assert "mystery" not in out
    assert any("mystery" in w for w in report.warnings)
    assert any("mystery" in str(w.message) for w in recwarn.list)


@pytest.mark.unit
def test_migrate_legacy_indexes_list_warns() -> None:
    with pytest.warns(UserWarning, match="indexes"):
        out, report = migrate_mapping(
            {"project": {"name": "x"}, "indexes": [{"name": "a", "backend": "azure_search"}]}
        )
    assert "indexes" not in out
    assert any("indexes" in w for w in report.warnings)


@pytest.mark.unit
def test_migrate_agents_workflow_profile_wins_over_graph() -> None:
    out, _ = migrate_mapping(
        {
            "agents": {"workflow_profile": "plan_execute"},
            "graph": {"workflow_profile": "research_rag"},
        }
    )
    assert out["agents"]["workflow_profile"] == "plan_execute"


@pytest.mark.unit
def test_migrate_file_writes_valid_digiproject(tmp_path: Path, _clean_env: None) -> None:
    src = tmp_path / "config.yaml"
    src.write_text(yaml.safe_dump(LEGACY_CONFIG))

    with pytest.warns(UserWarning):
        dest, mig_report, val_report = migrate_project_file(src)

    assert dest == tmp_path / "digiproject.yaml"
    assert dest.exists()
    assert val_report.ok, val_report.render()
    assert mig_report.warnings  # at least one warning emitted

    # Parse YAML rather than comparing raw text to avoid whitespace flakes.
    written = yaml.safe_load(dest.read_text())
    assert written == EXPECTED_MIGRATED

    # Output passes the validator module end-to-end.
    post = validate_project_file(dest)
    assert post.ok, post.render()


@pytest.mark.unit
def test_migrate_file_explicit_output(tmp_path: Path, _clean_env: None) -> None:
    src = tmp_path / "config.yaml"
    src.write_text(yaml.safe_dump({"project": {"name": "x", "version": "0.1.0"}}))
    dest = tmp_path / "out" / "custom.yaml"
    dest.parent.mkdir()

    result, _, val_report = migrate_project_file(src, dest)
    assert result == dest
    assert dest.exists()
    assert val_report.ok


@pytest.mark.unit
def test_migrate_file_refuses_existing_without_force(tmp_path: Path, _clean_env: None) -> None:
    src = tmp_path / "config.yaml"
    src.write_text(yaml.safe_dump({"project": {"name": "x", "version": "0.1.0"}}))
    dest = tmp_path / "digiproject.yaml"
    dest.write_text("# existing\n")

    with pytest.raises(FileExistsError):
        migrate_project_file(src, dest)

    # --force overwrites.
    result, _, val_report = migrate_project_file(src, dest, force=True)
    assert result == dest
    assert val_report.ok
    assert "existing" not in dest.read_text()


@pytest.mark.unit
def test_migrate_file_missing_source(tmp_path: Path) -> None:
    with pytest.raises(FileNotFoundError):
        migrate_project_file(tmp_path / "nope.yaml")


@pytest.mark.unit
def test_migrate_file_aborts_on_invalid_result(tmp_path: Path, _clean_env: None) -> None:
    # A legacy file whose migration produces a still-invalid shape: bogus llm_mode
    # passes through untouched and trips the schema.
    src = tmp_path / "config.yaml"
    src.write_text(
        yaml.safe_dump(
            {
                "project": {"name": "x", "version": "0.1.0"},
                "agents": {"llm_mode": "bogus"},
            }
        )
    )
    with pytest.raises(ValueError, match="failed validation"):
        migrate_project_file(src)

    # Destination must not be written on failure.
    assert not (tmp_path / "digiproject.yaml").exists()


@pytest.mark.unit
def test_cli_migrate_happy_path(
    tmp_path: Path, _clean_env: None, capsys: pytest.CaptureFixture[str]
) -> None:
    src = tmp_path / "config.yaml"
    src.write_text(yaml.safe_dump(LEGACY_CONFIG))

    rc = cli_main(["project", "migrate", str(src)])
    assert rc == 0
    out = capsys.readouterr().out
    assert "digiproject.yaml" in out

    dest = tmp_path / "digiproject.yaml"
    assert dest.exists()
    # And the produced file passes the validate subcommand.
    assert cli_main(["project", "validate", str(dest)]) == 0


@pytest.mark.unit
def test_cli_migrate_sad_path_missing_source(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    rc = cli_main(["project", "migrate", str(tmp_path / "nope.yaml")])
    assert rc == 1
    err = capsys.readouterr().err
    assert "error" in err.lower()


@pytest.mark.unit
def test_cli_migrate_sad_path_existing_dest(
    tmp_path: Path, _clean_env: None, capsys: pytest.CaptureFixture[str]
) -> None:
    src = tmp_path / "config.yaml"
    src.write_text(yaml.safe_dump({"project": {"name": "x", "version": "0.1.0"}}))
    dest = tmp_path / "digiproject.yaml"
    dest.write_text("# existing\n")

    rc = cli_main(["project", "migrate", str(src)])
    assert rc == 1
    err = capsys.readouterr().err
    assert "already exists" in err

    # --force succeeds.
    rc2 = cli_main(["project", "migrate", str(src), "--force"])
    assert rc2 == 0
