from __future__ import annotations

from pathlib import Path

import pytest

from scripts.docs_onboard.models import OnboardManifest, PageClass, load_manifest

pytestmark = pytest.mark.unit


def test_load_manifest_roundtrip(tmp_path: Path) -> None:
    path = tmp_path / "onboard.yaml"
    path.write_text(
        """
client: example-docs-client
seed_url: https://docs.example.com/
allowed_hosts:
  - docs.example.com
max_pages: 50
max_depth: 3
sinks: [vault, search]
digisearch_index: example_docs
vault_subdir: clients/example
docs_path_prefixes: ["/docs", "/guide", "/api"]
skip_path_prefixes: ["/blog", "/careers"]
""".strip()
        + "\n",
        encoding="utf-8",
    )
    m = load_manifest(path)
    assert m.client == "example-docs-client"
    assert m.seed_url.startswith("https://")
    assert "vault" in m.sinks and "search" in m.sinks
    assert m.digisearch_index == "example_docs"
    assert PageClass.docs.value == "docs"


def test_example_manifest_loads() -> None:
    repo = Path(__file__).resolve().parents[3]
    path = repo / "docs" / "projects" / "example-docs-client" / "onboard.yaml"
    m = load_manifest(path)
    assert isinstance(m, OnboardManifest)
    assert m.client == "example-docs-client"
