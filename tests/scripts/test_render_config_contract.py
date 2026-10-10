"""Tests for scripts/render_config_contract.py (epic DIG-2758 S1).

Network-free. Fixture tests render into a tmp root (never the real tree);
mapping tests read the real tree without writing.
"""

from __future__ import annotations

import importlib.util
import shutil
import tomllib
from pathlib import Path

import pytest
import yaml

REPO = Path(__file__).resolve().parent.parent.parent
SPEC = importlib.util.spec_from_file_location(
    "render_config_contract", REPO / "scripts" / "render_config_contract.py"
)
render = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(render)

MINI_WRANGLER = """\
name = "mini"
main = "src/index.ts"

[vars]
EXISTING = "keep-me"

# Secrets (wrangler secret put):
#   SOME_SECRET

[[services]]
binding = "OTHER"
service = "other-worker"
"""

MINI_ENV_EXAMPLE = """\
# mini stack
FOO=bar
"""


@pytest.fixture()
def tmp_root(tmp_path: Path) -> Path:
    shutil.copytree(REPO / "config" / "contract", tmp_path / "config" / "contract")
    (tmp_path / "apps" / "mini").mkdir(parents=True)
    (tmp_path / "apps" / "mini" / "wrangler.toml").write_text(MINI_WRANGLER, encoding="utf-8")
    (tmp_path / ".env.example").write_text(MINI_ENV_EXAMPLE, encoding="utf-8")
    return tmp_path


def _contract_with_mini_worker(root: Path) -> dict:
    contract = render.load_contract(root)
    workers = contract["services"]["workers"]
    contract["services"]["workers"] = [
        {**w, "file": "apps/mini/wrangler.toml"} if w.get("contract_vars") else w
        for w in workers
    ]
    return contract


def _render_all(tmp_root: Path) -> list[tuple[Path, str]]:
    contract = _contract_with_mini_worker(tmp_root)
    targets = [render.render_env_example(contract, tmp_root)]
    # Point every contract_vars worker at the single mini fixture.
    hosted = contract["variants"]["variants"]["hosted"]
    body = render.identity_block(hosted, toml=True)
    path = tmp_root / "apps" / "mini" / "wrangler.toml"
    targets.append((path, render.replace_vars_block(path.read_text(), body)))
    targets.append(render.render_compose_env(contract, tmp_root))
    for p, content in targets:
        p.write_text(content, encoding="utf-8")
    return targets


def test_render_is_idempotent(tmp_root: Path) -> None:
    first = {str(p): c for p, c in _render_all(tmp_root)}
    second = {str(p): c for p, c in _render_all(tmp_root)}
    assert first == second


def test_wrangler_block_lands_inside_vars(tmp_root: Path) -> None:
    _render_all(tmp_root)
    parsed = tomllib.loads((tmp_root / "apps" / "mini" / "wrangler.toml").read_text())
    assert parsed["vars"]["DT_VARIANT"] == "hosted"
    assert parsed["vars"]["DT_TARGET"] == "hosted"
    assert parsed["vars"]["DT_BASE_URL"] == "https://digithings.ai"
    assert parsed["vars"]["EXISTING"] == "keep-me" # untouched
    assert "DT_VARIANT" not in parsed["services"]


def test_hosted_identity_pinned(tmp_root: Path) -> None:
    contract = render.load_contract(tmp_root)
    hosted = contract["variants"]["variants"]["hosted"]
    assert hosted["DT_VARIANT"] == "hosted"
    assert hosted["DT_TARGET"] == "hosted"
    assert hosted["DT_BASE_URL"] == "https://digithings.ai"
    selfhost = contract["variants"]["variants"]["selfhost"]
    assert selfhost["DT_BASE_URL"] == "http://digithings.localhost"


def test_no_nulls_emitted(tmp_root: Path) -> None:
    for _, content in _render_all(tmp_root):
        assert "None" not in content.splitlines() or all(
            line.lstrip().startswith("#") for line in content.splitlines() if "None" in line
        ), "null contract value leaked into an artifact"


def test_secrets_manifest_carries_names_only() -> None:
    manifest = yaml.safe_load((REPO / "config" / "contract" / "secrets.yaml").read_text())
    allowed = {"name", "consumers", "required_in", "source", "note"}
    for entry in manifest["secrets"]:
        assert set(entry) <= allowed, entry.get("name")
        assert entry["name"] and entry["consumers"]


def test_shared_env_maps_to_an_artifact() -> None:
    """Plan §8a (scoped): every contract-managed env var must be consumed by
    at least one of docker-compose.yml, a wrangler.toml, or .env.example."""
    contract = render.load_contract()
    compose = (REPO / "docker-compose.yml").read_text()
    env_example = (REPO / ".env.example").read_text()
    wrangler = "".join(
        (REPO / w["file"]).read_text() for w in contract["services"]["workers"]
    )
    unmapped = [
        e["name"]
        for e in contract["services"]["shared_env"]
        if e["name"] not in compose and e["name"] not in wrangler and e["name"] not in env_example
    ]
    assert not unmapped, f"contract vars with no consumer: {unmapped}"


def test_real_tree_check_is_clean() -> None:
    """The committed artifacts match a fresh render (S9 runs this as --check)."""
    assert render.main(["--check"]) == 0
