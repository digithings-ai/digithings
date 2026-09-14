"""Unit tests for scripts/check_tenant_corpus_map.py (refs #3854).

The tenant corpus map lives in three blobs that must stay identical: the
``DIGICHAT_EMBED_TENANTS`` JSON in the profile-a compose override, the
``DIGI_TENANT_CORPUS_MAP`` var in the stack wrangler.toml, and the ``??``
fallback literal in the stack ``src/index.ts``. This drift check compares key
sets AND per-key ``digisearchIndex``/``vaultPathPrefix`` values across all
three and fails non-zero with a unified diff on drift.
"""

from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path
from typing import Any  # score:allow untyped any — dynamically loaded module

import pytest
import yaml

REPO_ROOT = Path(__file__).resolve().parents[2]
_SCRIPT = REPO_ROOT / "scripts" / "check_tenant_corpus_map.py"

pytestmark = pytest.mark.unit


def _load_module() -> Any:
    spec = importlib.util.spec_from_file_location("check_tenant_corpus_map", _SCRIPT)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


@pytest.fixture(scope="module")
def ccm() -> Any:
    return _load_module()


_CORPUS_A = {"digisearchIndex": "digithings_docs", "vaultPathPrefix": "clients/digithings"}
_CORPUS_B = {"digisearchIndex": "occ_help", "vaultPathPrefix": "clients/online-compliance-center"}


def _tenants(extra: dict[str, Any] | None = None) -> dict[str, Any]:
    tenants: dict[str, Any] = {
        "digithings.ai": {"slug": "digithings", "backend": {"type": "digigraph", **_CORPUS_A}},
        "occ.digithings.ai": {"slug": "occ", "backend": {"type": "digigraph", **_CORPUS_B}},
    }
    if extra:
        tenants.update(extra)
    return tenants


def _write_blobs(
    tmp_path: Path, tenants: dict[str, Any], corpus: dict[str, Any]
) -> tuple[Path, Path, Path]:
    compose = tmp_path / "compose.override.yml"
    compose.write_text(
        yaml.safe_dump(
            {
                "services": {
                    "digichat": {"environment": {"DIGICHAT_EMBED_TENANTS": json.dumps(tenants)}}
                }
            }
        ),
        encoding="utf-8",
    )
    wrangler = tmp_path / "wrangler.toml"
    escaped = json.dumps(corpus).replace("\\", "\\\\").replace('"', '\\"')
    wrangler.write_text(f'[vars]\nDIGI_TENANT_CORPUS_MAP = "{escaped}"\n', encoding="utf-8")
    index_ts = tmp_path / "index.ts"
    index_ts.write_text(
        "const x = {\n  DIGI_TENANT_CORPUS_MAP:\n"
        f"    env.DIGI_TENANT_CORPUS_MAP ?? '{json.dumps(corpus)}',\n}};\n",
        encoding="utf-8",
    )
    return compose, wrangler, index_ts


def test_extract_embed_uses_slug_and_skips_entries_without_backend_index(ccm: Any) -> None:
    """Only entries carrying a backend with digisearchIndex count (the two hosts)."""
    tenants = _tenants({"status.example": {"slug": "status", "backend": {"type": "digigraph"}}})
    assert ccm.extract_embed_corpus(tenants) == {
        "digithings": dict(_CORPUS_A),
        "occ": dict(_CORPUS_B),
    }


def test_loaders_agree_on_tmp_blobs(ccm: Any, tmp_path: Path) -> None:
    compose, wrangler, index_ts = _write_blobs(
        tmp_path, _tenants(), {"digithings": dict(_CORPUS_A), "occ": dict(_CORPUS_B)}
    )
    expected = {"digithings": dict(_CORPUS_A), "occ": dict(_CORPUS_B)}
    assert ccm.load_embed_map(compose) == expected
    assert ccm.load_wrangler_map(wrangler) == expected
    assert ccm.load_index_ts_map(index_ts) == expected


def test_compare_maps_passes_when_all_three_agree(ccm: Any) -> None:
    agreed = {"digithings": dict(_CORPUS_A), "occ": dict(_CORPUS_B)}
    report = ccm.compare_maps([("embed", agreed), ("wrangler", agreed), ("index.ts", agreed)])
    assert report["ok"] is True
    assert report["problems"] == []


def test_compare_maps_catches_value_drift(ccm: Any) -> None:
    base = {"digithings": dict(_CORPUS_A), "occ": dict(_CORPUS_B)}
    drifted = {"digithings": dict(_CORPUS_A), "occ": {**_CORPUS_B, "digisearchIndex": "occ_stale"}}
    report = ccm.compare_maps([("embed", base), ("wrangler", drifted), ("index.ts", base)])
    assert report["ok"] is False
    assert any("occ" in problem for problem in report["problems"])
    assert "---" in report["diff"] and "+++" in report["diff"]


def test_compare_maps_catches_key_set_drift(ccm: Any) -> None:
    base = {"digithings": dict(_CORPUS_A), "occ": dict(_CORPUS_B)}
    dropped = {"digithings": dict(_CORPUS_A)}
    report = ccm.compare_maps([("embed", base), ("wrangler", dropped), ("index.ts", base)])
    assert report["ok"] is False
    assert any("occ" in problem for problem in report["problems"])


def test_compare_maps_catches_prefix_drift(ccm: Any) -> None:
    base = {"digithings": dict(_CORPUS_A), "occ": dict(_CORPUS_B)}
    drifted = {
        "digithings": {**_CORPUS_A, "vaultPathPrefix": "clients/renamed"},
        "occ": dict(_CORPUS_B),
    }
    report = ccm.compare_maps([("embed", drifted), ("wrangler", base), ("index.ts", base)])
    assert report["ok"] is False
    assert "clients/renamed" in report["diff"]


def test_main_exit_zero_on_agreeing_blobs(ccm: Any, tmp_path: Path) -> None:
    compose, wrangler, index_ts = _write_blobs(
        tmp_path, _tenants(), {"digithings": dict(_CORPUS_A), "occ": dict(_CORPUS_B)}
    )
    assert (
        ccm.main(
            [
                "--compose-file",
                str(compose),
                "--wrangler-file",
                str(wrangler),
                "--index-ts-file",
                str(index_ts),
            ]
        )
        == 0
    )


def test_main_exit_nonzero_with_unified_diff_on_drift(
    ccm: Any, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    tenants = _tenants()
    tenants["occ.digithings.ai"] = {
        "slug": "occ",
        "backend": {"type": "digigraph", **_CORPUS_B, "digisearchIndex": "occ_stale"},
    }
    compose, wrangler, index_ts = _write_blobs(
        tmp_path, tenants, {"digithings": dict(_CORPUS_A), "occ": dict(_CORPUS_B)}
    )
    assert (
        ccm.main(
            [
                "--compose-file",
                str(compose),
                "--wrangler-file",
                str(wrangler),
                "--index-ts-file",
                str(index_ts),
            ]
        )
        == 1
    )
    out = capsys.readouterr().out
    assert "occ_stale" in out
    assert "---" in out and "+++" in out


def test_real_repo_blobs_agree(ccm: Any) -> None:
    """The three real blobs agree at this commit — the drift gate has a green baseline."""
    report = ccm.compare_maps(
        [
            ("embed", ccm.load_embed_map(ccm.default_compose_file())),
            ("wrangler", ccm.load_wrangler_map(ccm.default_wrangler_file())),
            ("index.ts", ccm.load_index_ts_map(ccm.default_index_ts_file())),
        ]
    )
    assert report["ok"] is True, f"repo blobs drifted: {report['problems']}"
