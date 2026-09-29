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


def _load_raw_corpus_maps(ccm: Any) -> dict[str, dict[str, Any]]:
    """Parse the three real ``DIGI_TENANT_CORPUS_MAP`` blobs WITHOUT field reduction.

    The drift gate deliberately compares only ``digisearchIndex``/``vaultPathPrefix``
    (sibling keys such as the OCC ``researchSystemPrompt`` are out of its scope),
    so prompt parity is pinned here instead: the compose override's stack-service
    value, the wrangler ``[vars]`` value, and the ``index.ts`` ``??`` fallback
    (TS-decoded first — the runtime TS-evaluates the literal before parsing it).
    """
    import tomllib

    compose_doc = yaml.safe_load(ccm.default_compose_file().read_text(encoding="utf-8"))
    compose_raw = compose_doc["services"]["digithings-stack"]["environment"][
        "DIGI_TENANT_CORPUS_MAP"
    ]
    with open(ccm.default_wrangler_file(), "rb") as fh:
        wrangler_doc = tomllib.load(fh)
    wrangler_raw = wrangler_doc["vars"]["DIGI_TENANT_CORPUS_MAP"]
    index_src = ccm.default_index_ts_file().read_text(encoding="utf-8")
    match = ccm._FALLBACK_RE.search(index_src)
    assert match, "DIGI_TENANT_CORPUS_MAP fallback literal not found in index.ts"
    return {
        "compose": json.loads(compose_raw),
        "wrangler": json.loads(wrangler_raw),
        "index.ts": json.loads(ccm.decode_ts_string_literal(match.group(1))),
    }


def test_decode_ts_string_literal_doubled_escapes(ccm: Any) -> None:
    """The fallback's doubled escapes decode to the JSON the runtime parses."""
    assert ccm.decode_ts_string_literal("a\\\\nb") == "a\\nb"
    assert ccm.decode_ts_string_literal('\\\\"q\\\\"') == '\\"q\\"'
    assert ccm.decode_ts_string_literal("\\\\u0027") == "\\u0027"
    assert ccm.decode_ts_string_literal("\\\\u2014") == "\\u2014"
    assert ccm.decode_ts_string_literal("plain") == "plain"
    with pytest.raises(ValueError, match="unsupported TS escape"):
        ccm.decode_ts_string_literal("\\q")


def test_real_blobs_occ_prompt_parity(ccm: Any) -> None:
    """Each map's occ entry carries the same researchSystemPrompt (#4717 follow-up 2).

    Task 6 wired the OCC prompt into the deployed wrangler map only; the two
    dev-path maps (index.ts fallback, local compose) must carry byte-identical
    prompt text — decoded comparison, so per-file escaping may differ.
    """
    raw = _load_raw_corpus_maps(ccm)
    prompts = {name: blob["occ"].get("researchSystemPrompt") for name, blob in raw.items()}
    assert all(isinstance(p, str) and p.strip() for p in prompts.values()), (
        f"occ researchSystemPrompt missing/empty in: "
        f"{sorted(n for n, p in prompts.items() if not (isinstance(p, str) and p.strip()))}"
    )
    assert len(set(prompts.values())) == 1, "occ researchSystemPrompt drifted across maps"


#: Runtime MCP union exposes Zammad tools as ``zammad_<name>`` (#4749 / #4750).
#: Bare recipe names teach the model ``ticket_report`` etc. → ``Unknown tool``.
_OCC_ZAMMAD_PREFIXED_TOOLS = (
    "zammad_aggregate_tickets",
    "zammad_search_tickets",
    "zammad_get_ticket",
    "zammad_ticket_report",
)


def test_real_blobs_occ_prompt_uses_zammad_prefixed_tool_names(ccm: Any) -> None:
    """OCC recipes must name the prefixed tools the runtime actually exposes (#4750).

    Parity alone is not enough: three identical bare-name prompts still strand
    the model on ``Unknown tool: ticket_report``. Pin the full ``zammad_`` names
    and refuse bare recipe tokens that lack the server prefix.
    """
    raw = _load_raw_corpus_maps(ccm)
    prompt = raw["compose"]["occ"]["researchSystemPrompt"]
    assert isinstance(prompt, str) and prompt.strip()
    for name in _OCC_ZAMMAD_PREFIXED_TOOLS:
        assert name in prompt, f"OCC prompt missing prefixed tool {name!r}"
    # Bare recipe names that previously shipped and caused Unknown-tool misses.
    for bare in (
        "aggregate_tickets",
        "search_tickets",
        "get_ticket",
        "ticket_report",
    ):
        # Allow the substring only as part of the prefixed form.
        assert f"zammad_{bare}" in prompt
        assert bare not in prompt.replace(f"zammad_{bare}", ""), (
            f"OCC prompt still teaches bare tool name {bare!r}"
        )


def test_real_blobs_digithings_carries_no_prompt(ccm: Any) -> None:
    """digithings entries stay prompt-free in all three maps (generic project prompt)."""
    raw = _load_raw_corpus_maps(ccm)
    for name, blob in raw.items():
        entry = blob["digithings"]
        assert "researchSystemPrompt" not in entry, f"{name}[digithings] carries a prompt"
        assert "research_system_prompt" not in entry, f"{name}[digithings] carries a prompt"
