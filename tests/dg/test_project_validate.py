"""Unit tests for the ``digi project validate`` CLI and validator library."""

from __future__ import annotations

from pathlib import Path

import pytest
import yaml

from digigraph.cli import main as cli_main
from digigraph.project_validate import ValidationReport, validate_project_file

REPO_ROOT = Path(__file__).resolve().parents[2]
TEMPLATE_PATH = REPO_ROOT / "docs" / "templates" / "project" / "digiproject.yaml"


@pytest.fixture
def _clean_env(monkeypatch: pytest.MonkeyPatch) -> None:
    """Unset env vars the template references, so default-resolution is exercised."""
    for var in ("DIGISEARCH_URL", "OPENAI_API_BASE", "DIGIQUANT_URL"):
        monkeypatch.delenv(var, raising=False)


@pytest.mark.unit
def test_template_validates_clean(_clean_env: None) -> None:
    report = validate_project_file(TEMPLATE_PATH)
    assert report.ok, report.render()


@pytest.mark.unit
def test_invalid_llm_mode_fails(tmp_path: Path, _clean_env: None) -> None:
    cfg = tmp_path / "digiproject.yaml"
    cfg.write_text(
        yaml.safe_dump(
            {
                "project": {"name": "x", "version": "0.1.0"},
                "agents": {"enabled": ["research"], "llm_mode": "bogus"},
            }
        )
    )
    report = validate_project_file(cfg)
    assert not report.ok
    assert any("llm_mode" in e for e in report.errors)


@pytest.mark.unit
def test_bad_version_pattern_fails(tmp_path: Path, _clean_env: None) -> None:
    cfg = tmp_path / "digiproject.yaml"
    cfg.write_text(yaml.safe_dump({"project": {"name": "x", "version": "not-semver"}}))
    report = validate_project_file(cfg)
    assert not report.ok
    assert any("version" in e for e in report.errors)


@pytest.mark.unit
def test_additional_properties_rejected(tmp_path: Path, _clean_env: None) -> None:
    cfg = tmp_path / "digiproject.yaml"
    cfg.write_text(yaml.safe_dump({"project": {"name": "x"}, "nonsense_key": 1}))
    report = validate_project_file(cfg)
    assert not report.ok
    assert any("nonsense_key" in e for e in report.errors)


@pytest.mark.unit
def test_unresolved_env_ref_fails(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("DIGI_DOES_NOT_EXIST", raising=False)
    cfg = tmp_path / "digiproject.yaml"
    # No default → must error; also not a URI so schema would fail anyway, but env
    # error must surface first with a clear message.
    cfg.write_text(
        yaml.safe_dump(
            {
                "services": {"digisearch_url": "${DIGI_DOES_NOT_EXIST}"},
            }
        )
    )
    report = validate_project_file(cfg)
    assert not report.ok
    assert any("DIGI_DOES_NOT_EXIST" in e and "unresolved" in e for e in report.errors)


@pytest.mark.unit
def test_env_ref_with_default_resolves(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("DIGI_UNSET_VAR", raising=False)
    cfg = tmp_path / "digiproject.yaml"
    cfg.write_text(
        yaml.safe_dump(
            {
                "services": {
                    "digisearch_url": "${DIGI_UNSET_VAR:-http://fallback:8002}",
                }
            }
        )
    )
    report = validate_project_file(cfg)
    assert report.ok, report.render()


@pytest.mark.unit
def test_env_ref_reads_from_environment(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("DIGI_TEST_URL", "http://set-in-env:9999")
    cfg = tmp_path / "digiproject.yaml"
    cfg.write_text(yaml.safe_dump({"services": {"digisearch_url": "${DIGI_TEST_URL}"}}))
    report = validate_project_file(cfg)
    assert report.ok, report.render()


@pytest.mark.unit
def test_missing_file_reported(tmp_path: Path) -> None:
    report = validate_project_file(tmp_path / "nope.yaml")
    assert not report.ok
    assert any("not found" in e for e in report.errors)


@pytest.mark.unit
def test_yaml_parse_error_reported(tmp_path: Path) -> None:
    cfg = tmp_path / "bad.yaml"
    cfg.write_text("project:\n  name: [unterminated\n")
    report = validate_project_file(cfg)
    assert not report.ok
    assert any("YAML parse error" in e for e in report.errors)


@pytest.mark.unit
def test_report_render_ok_and_errors() -> None:
    assert ValidationReport().render() == "OK"
    r = ValidationReport(errors=["a", "b"])
    rendered = r.render()
    assert "2 error(s)" in rendered
    assert "- a" in rendered and "- b" in rendered


@pytest.mark.unit
def test_cli_exits_zero_on_template(_clean_env: None, capsys: pytest.CaptureFixture[str]) -> None:
    rc = cli_main(["project", "validate", str(TEMPLATE_PATH)])
    assert rc == 0
    out = capsys.readouterr().out
    assert "OK" in out


@pytest.mark.unit
def test_cli_exits_nonzero_on_invalid(
    tmp_path: Path, _clean_env: None, capsys: pytest.CaptureFixture[str]
) -> None:
    cfg = tmp_path / "digiproject.yaml"
    cfg.write_text(yaml.safe_dump({"agents": {"llm_mode": "bogus"}}))
    rc = cli_main(["project", "validate", str(cfg)])
    assert rc == 1
    out = capsys.readouterr().out
    assert "llm_mode" in out
