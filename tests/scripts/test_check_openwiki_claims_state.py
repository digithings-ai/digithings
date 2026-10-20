"""Unit tests for scripts/check_openwiki_claims_state.py (DIG-4382).

The checker exists because a hand-added wiki page can land with a claim sidecar
that has no ``pageVersion`` and no ``openwiki/.page-manifest.json`` entry. That
pair makes ``openwiki code --update`` fail during preflight, so the scheduled
documentation update never opens its PR. These tests pin both halves: the
start-up failure (``pageVersion``) and the finish failure (a sidecar with claims
but no ``verification``), the strict shapes OpenWiki 0.5.0 rejects the same way
at preflight, and the clean tree the real repository must pass.
"""

from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path
from typing import Any  # score:allow untyped any — dynamically loaded module

import pytest

pytestmark = pytest.mark.unit

REPO_ROOT = Path(__file__).resolve().parents[2]
SCRIPT = REPO_ROOT / "scripts" / "check_openwiki_claims_state.py"

VERSION = "sha256:" + "a" * 64
CLAIMS = [{"id": "claim_test", "statement": "s", "evidence": [{"resource": "r", "version": "v"}]}]
VERIFICATION = {"by": "DIG-0000", "at": "2026-01-01T00:00:00.000Z"}


def _load() -> Any:
    spec = importlib.util.spec_from_file_location("check_openwiki_claims_state", SCRIPT)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules["check_openwiki_claims_state"] = module
    spec.loader.exec_module(module)
    return module


def _write(tree: Path, manifest_pages: dict[str, Any], sidecars: dict[str, Any]) -> Path:
    """Create ``tree`` with a manifest and sidecars; sidecars also get their page file."""
    wiki = tree / "openwiki"
    (wiki / ".claims").mkdir(parents=True)
    (wiki / ".page-manifest.json").write_text(
        json.dumps({"schemaVersion": 1, "pages": manifest_pages}), encoding="utf-8"
    )
    for page, payload in sidecars.items():
        relative = page.removeprefix("/openwiki/")
        page_file = wiki / relative
        page_file.parent.mkdir(parents=True, exist_ok=True)
        page_file.write_text("---\ntitle: t\n---\n", encoding="utf-8")
        sidecar = (wiki / ".claims" / relative).with_suffix(".json")
        sidecar.parent.mkdir(parents=True, exist_ok=True)
        sidecar.write_text(json.dumps(payload), encoding="utf-8")
    return tree


def _sidecar(*, version: str | None = VERSION, claims: Any = CLAIMS, verification: Any = VERIFICATION) -> dict[str, Any]:
    payload: dict[str, Any] = {"schemaVersion": 1, "claims": claims}
    if version is not None:
        payload["pageVersion"] = version
    if verification is not None:
        payload["verification"] = verification
    return payload


def _codes(findings: list[Any], severity: str | None = None) -> list[str]:
    return [f.code for f in findings if severity is None or f.severity == severity]


def test_clean_tree_passes(tmp_path: Path) -> None:
    tree = _write(tmp_path, {"/openwiki/digivoice/architecture.md": {"pageVersion": VERSION}}, {"/openwiki/digivoice/architecture.md": _sidecar()})
    assert _load().check(tree) == []


def test_real_repository_is_clean() -> None:
    # The committed sidecars and manifest must satisfy the checker the PR wires in.
    assert _load().check(REPO_ROOT) == []


def test_sidecar_without_page_version_is_reported(tmp_path: Path) -> None:
    tree = _write(tmp_path, {"/openwiki/digivoice/architecture.md": {"pageVersion": VERSION}}, {"/openwiki/digivoice/architecture.md": _sidecar(version=None)})
    findings = _load().check(tree)
    assert "sidecar_missing_page_version" in _codes(findings, "error")
    assert findings[0].path.endswith("openwiki/.claims/digivoice/architecture.json")


def test_sidecar_with_claims_but_no_verification_is_reported(tmp_path: Path) -> None:
    tree = _write(
        tmp_path,
        {"/openwiki/digivoice/architecture.md": {"pageVersion": VERSION}},
        {"/openwiki/digivoice/architecture.md": _sidecar(verification=None)},
    )
    findings = _load().check(tree)
    assert "sidecar_missing_verification" in _codes(findings, "error")


def test_unverified_sidecar_without_manifest_entry_is_an_error(tmp_path: Path) -> None:
    tree = _write(tmp_path, {}, {"/openwiki/digivoice/quickstart.md": _sidecar(verification=None)})
    findings = _load().check(tree)
    assert "sidecar_missing_manifest_entry" in _codes(findings, "error")


def test_verified_sidecar_without_manifest_entry_is_a_warning(tmp_path: Path) -> None:
    tree = _write(tmp_path, {}, {"/openwiki/digivoice/quickstart.md": _sidecar()})
    findings = _load().check(tree)
    assert _codes(findings, "error") == []
    assert "sidecar_missing_manifest_entry" in _codes(findings, "warning")


def test_verified_page_version_mismatch_is_a_warning(tmp_path: Path) -> None:
    tree = _write(
        tmp_path,
        {"/openwiki/digivoice/architecture.md": {"pageVersion": "sha256:" + "b" * 64}},
        {"/openwiki/digivoice/architecture.md": _sidecar()},
    )
    findings = _load().check(tree)
    assert _codes(findings, "error") == []
    assert "page_version_mismatch" in _codes(findings, "warning")


def test_manifest_entry_without_sidecar_is_a_warning(tmp_path: Path) -> None:
    tree = _write(tmp_path, {"/openwiki/digivoice/architecture.md": {"pageVersion": VERSION}}, {})
    findings = _load().check(tree)
    assert _codes(findings, "error") == []
    assert "manifest_missing_sidecar" in _codes(findings, "warning")


def test_manifest_entry_without_page_version_is_an_error(tmp_path: Path) -> None:
    tree = _write(tmp_path, {"/openwiki/digivoice/architecture.md": {}}, {"/openwiki/digivoice/architecture.md": _sidecar()})
    findings = _load().check(tree)
    assert "manifest_bad_page_version" in _codes(findings, "error")


def test_malformed_page_version_is_an_error(tmp_path: Path) -> None:
    tree = _write(
        tmp_path,
        {"/openwiki/digivoice/architecture.md": {"pageVersion": "not-a-version"}},
        {"/openwiki/digivoice/architecture.md": _sidecar(version="not-a-version")},
    )
    findings = _load().check(tree)
    assert "sidecar_bad_page_version" in _codes(findings, "error")


def test_sidecar_without_page_file_is_an_error(tmp_path: Path) -> None:
    tree = _write(tmp_path, {"/openwiki/digivoice/architecture.md": {"pageVersion": VERSION}}, {})
    sidecar = tree / "openwiki" / ".claims" / "digivoice" / "architecture.json"
    sidecar.parent.mkdir(parents=True, exist_ok=True)
    sidecar.write_text(json.dumps(_sidecar()), encoding="utf-8")
    findings = _load().check(tree)
    assert "sidecar_page_missing" in _codes(findings, "error")


def test_malformed_manifest_short_circuits(tmp_path: Path) -> None:
    tree = _write(tmp_path, {}, {"/openwiki/digivoice/architecture.md": _sidecar()})
    (tree / "openwiki" / ".page-manifest.json").write_text("{ not json", encoding="utf-8")
    findings = _load().check(tree)
    assert _codes(findings, "error") == ["manifest_invalid_json"]
    assert len(findings) == 1


def test_malformed_sidecar_json_is_an_error(tmp_path: Path) -> None:
    tree = _write(tmp_path, {}, {})
    sidecar = tree / "openwiki" / ".claims" / "digivoice" / "architecture.json"
    sidecar.parent.mkdir(parents=True, exist_ok=True)
    sidecar.write_text("{ not json", encoding="utf-8")
    findings = _load().check(tree)
    assert "sidecar_invalid_json" in _codes(findings, "error")


def test_cli_exit_code_follows_errors(tmp_path: Path) -> None:
    mod = _load()
    clean = _write(tmp_path / "clean", {"/openwiki/digivoice/architecture.md": {"pageVersion": VERSION}}, {"/openwiki/digivoice/architecture.md": _sidecar()})
    warned = _write(tmp_path / "warned", {}, {"/openwiki/digivoice/architecture.md": _sidecar()})
    broken = _write(tmp_path / "broken", {}, {"/openwiki/digivoice/architecture.md": _sidecar(version=None, verification=None)})
    assert mod.main(["--root", str(clean)]) == 0
    assert mod.main(["--root", str(warned)]) == 0
    assert mod.main(["--root", str(broken)]) == 1


def test_cli_json_formats_within_a_clean_tree(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    tree = _write(tmp_path, {"/openwiki/digivoice/architecture.md": {"pageVersion": VERSION}}, {"/openwiki/digivoice/architecture.md": _sidecar()})
    assert _load().main(["--root", str(tree), "--format", "json"]) == 0
    assert json.loads(capsys.readouterr().out) == []


def test_sidecar_schema_version_bool_is_an_error(tmp_path: Path) -> None:
    payload = _sidecar()
    payload["schemaVersion"] = True
    tree = _write(tmp_path, {"/openwiki/digivoice/architecture.md": {"pageVersion": VERSION}}, {"/openwiki/digivoice/architecture.md": payload})
    findings = _load().check(tree)
    assert "sidecar_schema" in _codes(findings, "error")


def test_sidecar_schema_version_wrong_is_an_error(tmp_path: Path) -> None:
    payload = _sidecar()
    payload["schemaVersion"] = 2
    tree = _write(tmp_path, {"/openwiki/digivoice/architecture.md": {"pageVersion": VERSION}}, {"/openwiki/digivoice/architecture.md": payload})
    findings = _load().check(tree)
    assert "sidecar_schema" in _codes(findings, "error")


def test_sidecar_without_claims_array_is_an_error(tmp_path: Path) -> None:
    payload = _sidecar()
    del payload["claims"]
    tree = _write(tmp_path, {"/openwiki/digivoice/architecture.md": {"pageVersion": VERSION}}, {"/openwiki/digivoice/architecture.md": payload})
    findings = _load().check(tree)
    assert "sidecar_missing_claims" in _codes(findings, "error")
    # No verification requirement is charged on top of the absent claims array.
    assert "sidecar_missing_verification" not in _codes(findings)


def test_sidecar_with_unknown_key_is_an_error(tmp_path: Path) -> None:
    payload = _sidecar()
    payload["gitHead"] = "abc123"
    tree = _write(tmp_path, {"/openwiki/digivoice/architecture.md": {"pageVersion": VERSION}}, {"/openwiki/digivoice/architecture.md": payload})
    findings = _load().check(tree)
    assert "sidecar_schema" in _codes(findings, "error")


def test_sidecar_claim_without_evidence_is_an_error(tmp_path: Path) -> None:
    payload = _sidecar()
    payload["claims"] = [{"id": "claim_test", "statement": "s", "evidence": []}]
    tree = _write(tmp_path, {"/openwiki/digivoice/architecture.md": {"pageVersion": VERSION}}, {"/openwiki/digivoice/architecture.md": payload})
    findings = _load().check(tree)
    assert "sidecar_bad_claim" in _codes(findings, "error")


def test_sidecar_verification_with_extra_key_is_an_error(tmp_path: Path) -> None:
    payload = _sidecar()
    payload["verification"] = dict(VERIFICATION, by="x")
    payload["verification"]["extra"] = "y"
    tree = _write(tmp_path, {"/openwiki/digivoice/architecture.md": {"pageVersion": VERSION}}, {"/openwiki/digivoice/architecture.md": payload})
    findings = _load().check(tree)
    assert "sidecar_bad_verification" in _codes(findings, "error")


def test_uppercase_page_version_hex_is_an_error(tmp_path: Path) -> None:
    tree = _write(
        tmp_path,
        {"/openwiki/digivoice/architecture.md": {"pageVersion": "sha256:" + "A" * 64}},
        {"/openwiki/digivoice/architecture.md": _sidecar(version="sha256:" + "A" * 64)},
    )
    findings = _load().check(tree)
    assert "sidecar_bad_page_version" in _codes(findings, "error")
    assert "manifest_bad_page_version" in _codes(findings, "error")


def test_manifest_with_unknown_top_level_key_is_an_error(tmp_path: Path) -> None:
    tree = _write(tmp_path, {}, {})
    manifest = tree / "openwiki" / ".page-manifest.json"
    manifest.write_text(json.dumps({"schemaVersion": 1, "pages": {}, "gitHead": "abc"}), encoding="utf-8")
    findings = _load().check(tree)
    assert "manifest_schema" in _codes(findings, "error")


def test_manifest_schema_version_bool_is_an_error(tmp_path: Path) -> None:
    tree = _write(tmp_path, {}, {})
    manifest = tree / "openwiki" / ".page-manifest.json"
    manifest.write_text(json.dumps({"schemaVersion": True, "pages": {}}), encoding="utf-8")
    findings = _load().check(tree)
    assert "manifest_schema" in _codes(findings, "error")


def test_manifest_entry_with_unknown_key_is_an_error(tmp_path: Path) -> None:
    tree = _write(tmp_path, {"/openwiki/digivoice/architecture.md": {"pageVersion": VERSION, "gitHand": "abc"}}, {"/openwiki/digivoice/architecture.md": _sidecar()})
    findings = _load().check(tree)
    assert "manifest_bad_entry" in _codes(findings, "error")


def test_manifest_entry_with_bad_completed_run_id_is_an_error(tmp_path: Path) -> None:
    tree = _write(tmp_path, {"/openwiki/digivoice/architecture.md": {"pageVersion": VERSION, "completedRunId": "nope"}}, {"/openwiki/digivoice/architecture.md": _sidecar()})
    findings = _load().check(tree)
    assert "manifest_bad_entry" in _codes(findings, "error")


def test_manifest_entry_not_an_object_is_an_error(tmp_path: Path) -> None:
    tree = _write(tmp_path, {}, {"/openwiki/digivoice/architecture.md": _sidecar()})
    manifest = tree / "openwiki" / ".page-manifest.json"
    manifest.write_text(json.dumps({"schemaVersion": 1, "pages": {"/openwiki/digivoice/architecture.md": "broken"}}), encoding="utf-8")
    findings = _load().check(tree)
    assert "manifest_bad_entry" in _codes(findings, "error")


def test_manifest_with_non_canonical_page_key_is_an_error(tmp_path: Path) -> None:
    tree = _write(tmp_path, {"/openwiki/digivoice/architecture": {"pageVersion": VERSION}}, {"/openwiki/digivoice/architecture.md": _sidecar()})
    findings = _load().check(tree)
    assert "manifest_bad_page_path" in _codes(findings, "error")


def test_manifest_with_reserved_page_key_is_an_error(tmp_path: Path) -> None:
    tree = _write(tmp_path, {"/openwiki/index.md": {"pageVersion": VERSION}}, {})
    findings = _load().check(tree)
    assert "manifest_bad_page_path" in _codes(findings, "error")
