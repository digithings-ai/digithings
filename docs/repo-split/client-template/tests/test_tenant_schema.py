"""Offline checks for this client repo. No search, fetch or model call.

Run: make test (runs inside the pinned R0 checkout's environment, so the R0
loaders are importable). The schema itself is R0's: the tenant doc is validated
by R0's `config:check` script when Node deps are installed there.
"""

from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
from pathlib import Path

import pytest
import yaml

ROOT = Path(__file__).resolve().parents[1]
TENANT = ROOT / "tenant"
DOC = TENANT / "digichat.yaml"
R0 = Path(os.environ.get("DIGITHINGS_DIR", ROOT.parent / "digithings"))
# Slug rule from tenant/SCHEMA-NOTES.md §2. Switch to U5a's shared R0 helper once it lands.
SLUG_RE = re.compile(r"^[a-z0-9]+(-[a-z0-9]+)*$")


def _doc() -> dict:
    return yaml.safe_load(DOC.read_text())


def test_tenant_doc_shape() -> None:
    doc = _doc()
    assert doc["version"] == 1
    assert len(doc["hosts"]) == 1, "one deployment per client repo"
    (row,) = doc["hosts"].values()
    assert SLUG_RE.fullmatch(row["slug"])
    assert "token" not in row, "tokens are env names (tokenEnv), never values"



@pytest.mark.parametrize("slug", ["example", "example-b"])
def test_slug_rule_accepts(slug: str) -> None:
    assert SLUG_RE.fullmatch(slug)


@pytest.mark.parametrize("slug", ["-x", "x-", "a--b"])
def test_slug_rule_refuses(slug: str) -> None:
    assert not SLUG_RE.fullmatch(slug)


def test_tenant_doc_passes_the_r0_schema() -> None:
    script = R0 / "apps" / "digichat" / "scripts" / "check-config.ts"
    if not script.exists() or not (R0 / "node_modules").exists() or not shutil.which("npx"):
        pytest.skip("R0 checkout with node deps not available (make link / setup)")
    out = subprocess.run(
        ["npx", "tsx", str(script), str(DOC)],
        cwd=R0 / "apps" / "digichat",
        capture_output=True,
        text=True,
        timeout=120,
    )
    assert out.returncode == 0, out.stderr[-2000:]


def test_corpus_map_names_the_tenant_slug() -> None:
    (row,) = _doc()["hosts"].values()
    assert row["slug"] in json.loads((TENANT / "corpus-map.json").read_text())


def test_env_overlays_hold_names_not_values() -> None:
    for name in ("local", "staging", "prod"):
        env = yaml.safe_load((TENANT / "env" / f"{name}.yaml").read_text())
        assert env["environment"] == name
        for value in (env.get("secrets") or {}).values():
            assert re.fullmatch(r"[A-Z][A-Z0-9_]*", value), (
                f"{name}: secrets must be variable names"
            )


def test_corpus_pages_have_url_front_matter() -> None:
    pages = [p for p in (ROOT / "corpus").rglob("*.md") if p.name != "README.md"]
    assert pages
    for page in pages:
        assert re.search(r"^url:\s*https://\S+", page.read_text(), re.M), page


def test_questions_have_unique_ids() -> None:
    qs = json.loads((ROOT / "tests" / "questions.json").read_text())
    ids = [q["id"] for q in qs]
    assert ids and len(ids) == len(set(ids))
    assert all(q["question"].strip() for q in qs)


def test_no_secret_looking_values() -> None:
    pat = re.compile(
        r"(sk-[A-Za-z0-9]{16,}|ghp_[A-Za-z0-9]{20,}|AKIA[0-9A-Z]{16}|-----BEGIN [A-Z ]*PRIVATE KEY)"
    )
    for p in ROOT.rglob("*"):
        if (
            p.is_file()
            and ".git" not in p.parts
            and p.suffix in {".json", ".yaml", ".yml", ".md", ".sh", ".py", ".ts", ".mjs", ".toml"}
        ):
            assert not pat.search(p.read_text(errors="ignore")), p


def test_env_example_has_names_only_and_covers_tenant_secrets() -> None:
    lines = [
        ln.strip()
        for ln in (ROOT / ".env.example").read_text().splitlines()
        if ln.strip() and not ln.lstrip().startswith("#")
    ]
    names = set()
    for ln in lines:
        m = re.fullmatch(r"([A-Z][A-Z0-9_]*)=", ln)
        assert m, f".env.example must hold NAME= lines with no value: {ln!r}"
        names.add(m.group(1))
    for env_file in sorted((ROOT / "tenant" / "env").glob("*.yaml")):
        secrets = yaml.safe_load(env_file.read_text()).get("secrets") or {}
        missing = set(secrets.values()) - names
        assert not missing, f"{env_file.name}: secret names missing from .env.example: {missing}"
