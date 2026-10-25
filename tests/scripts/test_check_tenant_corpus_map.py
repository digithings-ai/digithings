"""Unit tests for scripts/check_tenant_corpus_map.py (refs #3854).

The tenant corpus map is carried in two blobs that must stay identical: the
``DIGICHAT_EMBED_TENANTS`` JSON in the profile-a compose override and the
wrangler ``[vars]`` PAIR ``DIGI_TENANT_CORPUS_MAP`` + ``DIGI_TENANT_CORPUS_MAP_EXTRA``
(split on 2026-10-25 because one Cloudflare text binding may not exceed 5.1 kB;
the single value was 5285 bytes and failed the deploy with code 10054). This
drift check compares key sets AND per-key ``digisearchIndex``/``vaultPathPrefix``
values across them, and separately refuses an inline corpus map or a dropped half
in ``src/index.ts``, which is what the retired ``??`` fallback literal used to be.
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

#: What ``src/index.ts`` must contain: both halves named, composed by name.
_INDEX_WIRING = (
    "const x = {\n"
    "  DIGI_TENANT_CORPUS_MAP: composeCorpusMap(\n"
    "    env.DIGI_TENANT_CORPUS_MAP,\n"
    "    env.DIGI_TENANT_CORPUS_MAP_EXTRA,\n"
    "  ),\n"
    "};\n"
)


def _tenants(extra: dict[str, Any] | None = None) -> dict[str, Any]:
    tenants: dict[str, Any] = {
        "digithings.ai": {"slug": "digithings", "backend": {"type": "digigraph", **_CORPUS_A}},
        "occ.digithings.ai": {"slug": "occ", "backend": {"type": "digigraph", **_CORPUS_B}},
    }
    if extra:
        tenants.update(extra)
    return tenants


def _split_corpus(corpus: dict[str, Any]) -> tuple[dict[str, Any], dict[str, Any]]:
    """The house entry in the unsuffixed var, every other tenant in the extra one."""
    primary = {"digithings": corpus["digithings"]}
    extra = {slug: entry for slug, entry in corpus.items() if slug != "digithings"}
    return primary, extra


def _write_blobs(
    tmp_path: Path,
    tenants: dict[str, Any],
    corpus: dict[str, Any],
    *,
    drop_extra: bool = False,
    index_ts_source: str = _INDEX_WIRING,
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
    primary, extra = _split_corpus(corpus)
    wrangler = tmp_path / "wrangler.toml"
    escaped = json.dumps(primary).replace("\\", "\\\\").replace('"', '\\"')
    body = f'[vars]\nDIGI_TENANT_CORPUS_MAP = "{escaped}"\n'
    if not drop_extra:
        extra_escaped = json.dumps(extra).replace("\\", "\\\\").replace('"', '\\"')
        body += f'DIGI_TENANT_CORPUS_MAP_EXTRA = "{extra_escaped}"\n'
    wrangler.write_text(body, encoding="utf-8")
    index_ts = tmp_path / "index.ts"
    index_ts.write_text(index_ts_source, encoding="utf-8")
    return compose, wrangler, index_ts


def _args(compose: Path, wrangler: Path, index_ts: Path) -> list[str]:
    return [
        "--compose-file",
        str(compose),
        "--wrangler-file",
        str(wrangler),
        "--index-ts-file",
        str(index_ts),
    ]


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
    # The pair is joined, not just the first half: a loader that read only
    # DIGI_TENANT_CORPUS_MAP would answer with the house tenant alone.
    assert ccm.load_wrangler_map(wrangler) == expected
    assert ccm.check_index_ts_wiring(index_ts) == []


def test_compose_corpus_vars_lets_the_primary_half_win(ccm: Any) -> None:
    """A stale extra must never shadow the house entry it does not own."""
    merged = ccm.compose_corpus_vars(
        json.dumps({"digithings": {"digisearchIndex": "house"}}),
        json.dumps(
            {
                "digithings": {"digisearchIndex": "stale"},
                "occ": {"digisearchIndex": "occ_help"},
            }
        ),
    )
    assert merged["digithings"]["digisearchIndex"] == "house"
    assert merged["occ"]["digisearchIndex"] == "occ_help"


def test_index_ts_wiring_refuses_a_reintroduced_literal(ccm: Any, tmp_path: Path) -> None:
    """The 5.1 kB regression, stated as a property of the source."""
    index_ts = tmp_path / "index.ts"
    index_ts.write_text(
        _INDEX_WIRING.replace(
            "    env.DIGI_TENANT_CORPUS_MAP,\n",
            '    env.DIGI_TENANT_CORPUS_MAP ?? \'{"digithings":{"researchSystemPrompt":"x"}}\',\n',
        ),
        encoding="utf-8",
    )
    problems = ccm.check_index_ts_wiring(index_ts)
    assert any("inline corpus map" in problem for problem in problems), problems


def test_index_ts_wiring_refuses_a_dropped_half(ccm: Any, tmp_path: Path) -> None:
    """Reading one half strips those tenants off the container and fails nothing."""
    index_ts = tmp_path / "index.ts"
    index_ts.write_text(
        "const x = {\n"
        "  DIGI_TENANT_CORPUS_MAP: composeCorpusMap(env.DIGI_TENANT_CORPUS_MAP),\n"
        "};\n",
        encoding="utf-8",
    )
    problems = ccm.check_index_ts_wiring(index_ts)
    assert any("does not compose the [vars] pair" in problem for problem in problems), problems


def test_compare_maps_passes_when_all_agree(ccm: Any) -> None:
    agreed = {"digithings": dict(_CORPUS_A), "occ": dict(_CORPUS_B)}
    report = ccm.compare_maps([("embed", agreed), ("wrangler", agreed)])
    assert report["ok"] is True
    assert report["problems"] == []


def test_compare_maps_catches_value_drift(ccm: Any) -> None:
    base = {"digithings": dict(_CORPUS_A), "occ": dict(_CORPUS_B)}
    drifted = {"digithings": dict(_CORPUS_A), "occ": {**_CORPUS_B, "digisearchIndex": "occ_stale"}}
    report = ccm.compare_maps([("embed", base), ("wrangler", drifted)])
    assert report["ok"] is False
    assert any("occ" in problem for problem in report["problems"])
    assert "---" in report["diff"] and "+++" in report["diff"]


def test_compare_maps_catches_key_set_drift(ccm: Any) -> None:
    base = {"digithings": dict(_CORPUS_A), "occ": dict(_CORPUS_B)}
    dropped = {"digithings": dict(_CORPUS_A)}
    report = ccm.compare_maps([("embed", base), ("wrangler", dropped)])
    assert report["ok"] is False
    assert any("occ" in problem for problem in report["problems"])


def test_compare_maps_catches_prefix_drift(ccm: Any) -> None:
    base = {"digithings": dict(_CORPUS_A), "occ": dict(_CORPUS_B)}
    drifted = {
        "digithings": {**_CORPUS_A, "vaultPathPrefix": "clients/renamed"},
        "occ": dict(_CORPUS_B),
    }
    report = ccm.compare_maps([("embed", drifted), ("wrangler", base)])
    assert report["ok"] is False
    assert "clients/renamed" in report["diff"]


def test_main_exit_zero_on_agreeing_blobs(ccm: Any, tmp_path: Path) -> None:
    compose, wrangler, index_ts = _write_blobs(
        tmp_path, _tenants(), {"digithings": dict(_CORPUS_A), "occ": dict(_CORPUS_B)}
    )
    assert ccm.main(_args(compose, wrangler, index_ts)) == 0


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
    assert ccm.main(_args(compose, wrangler, index_ts)) == 1
    out = capsys.readouterr().out
    assert "occ_stale" in out
    assert "---" in out and "+++" in out


def test_main_exit_nonzero_when_the_extra_half_is_dropped(
    ccm: Any, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """The vars are one map in two bindings, not two independent opts-in."""
    compose, wrangler, index_ts = _write_blobs(
        tmp_path,
        _tenants(),
        {"digithings": dict(_CORPUS_A), "occ": dict(_CORPUS_B)},
        drop_extra=True,
    )
    assert ccm.main(_args(compose, wrangler, index_ts)) == 1
    assert "occ" in capsys.readouterr().out


def test_real_repo_blobs_agree(ccm: Any) -> None:
    """The real blobs agree at this commit — the drift gate has a green baseline."""
    report = ccm.compare_maps(
        [
            ("embed", ccm.load_embed_map(ccm.default_compose_file())),
            ("wrangler", ccm.load_wrangler_map(ccm.default_wrangler_file())),
        ]
    )
    assert report["ok"] is True, f"repo blobs drifted: {report['problems']}"
    assert ccm.check_index_ts_wiring(ccm.default_index_ts_file()) == []


def _load_raw_corpus_maps(ccm: Any) -> dict[str, dict[str, Any]]:
    """Parse the real corpus-map blobs WITHOUT field reduction.

    The drift gate deliberately compares only ``digisearchIndex``/``vaultPathPrefix``
    (sibling keys such as the OCC ``researchSystemPrompt`` are out of its scope),
    so prompt parity is pinned here instead: the compose override's stack-service
    value and the wrangler ``[vars]`` pair, joined. ``index.ts`` is no longer a
    blob — it composes the pair, and `corpus-map-compose.test.js` in the app
    asserts the composed value is byte-identical to the compose one.
    """

    compose_doc = yaml.safe_load(ccm.default_compose_file().read_text(encoding="utf-8"))
    compose_raw = compose_doc["services"]["digithings-stack"]["environment"][
        "DIGI_TENANT_CORPUS_MAP"
    ]
    primary, extra = ccm.load_wrangler_vars(ccm.default_wrangler_file())
    return {
        "compose": json.loads(compose_raw),
        "wrangler": ccm.compose_corpus_vars(primary, extra),
    }


def test_real_blobs_occ_prompt_parity(ccm: Any) -> None:
    """Each map's occ entry carries the same researchSystemPrompt (#4717 follow-up 2).

    Task 6 wired the OCC prompt into the deployed wrangler map only; the two
    dev-path maps (the app's fallback, local compose) must carry byte-identical
    prompt text — decoded comparison, so per-file escaping may differ.
    """
    raw = _load_raw_corpus_maps(ccm)
    prompts = {name: blob["occ"].get("researchSystemPrompt") for name, blob in raw.items()}
    assert all(isinstance(p, str) and p.strip() for p in prompts.values()), (
        f"occ researchSystemPrompt missing/empty in: "
        f"{sorted(n for n, p in prompts.items() if not (isinstance(p, str) and p.strip()))}"
    )
    assert len(set(prompts.values())) == 1, "occ researchSystemPrompt drifted across maps"


def test_real_blobs_digithings_prompt_parity(ccm: Any) -> None:
    """Each map's digithings entry carries the same short house prompt."""
    raw = _load_raw_corpus_maps(ccm)
    prompts = {name: blob["digithings"].get("researchSystemPrompt") for name, blob in raw.items()}
    assert all(isinstance(p, str) and "Web search is on." in p for p in prompts.values()), prompts
