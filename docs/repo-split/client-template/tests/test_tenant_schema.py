"""Offline checks for this client repo. No search, fetch or model call.

Run: make test (runs inside the pinned R0 checkout's environment, so the R0
loaders are importable). The schema itself is R0's: the tenant doc is validated
by R0's `config:check` script when Node deps are installed there. Locally that
check skips without Node deps; in CI (`CI` set) it fails instead, and it runs in
its own Node-image Woodpecker step (`r0-schema`).
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
# Slug rule from tenant/SCHEMA-NOTES.md §2: R0's TENANT_PATH_SLUG (U5a #6680,
# apps/digichat/src/lib/deploy-config/tenant-chrome.ts). Keep the two identical.
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


def test_tenant_doc_chat_slug_lives_at_chrome_slug() -> None:
    (row,) = _doc()["hosts"].values()
    chrome = row["chrome"]
    assert SLUG_RE.fullmatch(chrome["slug"]), "chrome.slug must be a plain lowercase slug"
    # New docs write the slug only: no legacy full path, and no flat registry-row names.
    assert "pathPrefix" not in chrome and "pathPrefix" not in row
    assert "chatSlug" not in row and "chatSlug" not in chrome
    assert "productChat" not in row, "productChat lives at chrome.productChat"
    if "productChat" in chrome:
        assert isinstance(chrome["productChat"], bool)
    # access.invite is written by the deploy from tenant/env/, server-only (SCHEMA-NOTES §1).
    assert "access" not in row


@pytest.mark.parametrize("slug", ["example", "example-b"])
def test_slug_rule_accepts(slug: str) -> None:
    assert SLUG_RE.fullmatch(slug)


@pytest.mark.parametrize("slug", ["-x", "x-", "a--b"])
def test_slug_rule_refuses(slug: str) -> None:
    assert not SLUG_RE.fullmatch(slug)


# The Woodpecker Python `test` step sets this: the R0 schema check runs in the
# Node-image `r0-schema` step instead (.woodpecker.yml), not in a step with no Node.
OWN_STEP_ENV = "R0_SCHEMA_CHECK_STEP"


def _r0_schema_check_missing(r0: Path) -> str | None:
    """What stops R0's config:check from running here, or None if it can run."""
    if not (r0 / "apps" / "digichat" / "scripts" / "check-config.ts").exists():
        return f"no R0 checkout with apps/digichat/scripts/check-config.ts at {r0}"
    if not (r0 / "node_modules").exists():
        return f"R0 Node deps not installed (no {r0 / 'node_modules'})"
    if not shutil.which("npx"):
        return "npx is not on PATH"
    return None


def _require_r0_schema_check(r0: Path) -> Path:
    """Skip locally when the check can't run; in CI, fail with the reason."""
    if os.environ.get(OWN_STEP_ENV):
        pytest.skip(f"R0 schema check runs in the {os.environ[OWN_STEP_ENV]} CI step")
    missing = _r0_schema_check_missing(r0)
    if missing:
        if os.environ.get("CI"):
            pytest.fail(
                f"R0 schema check cannot run in CI: {missing}. Install R0's Node deps "
                "(npm ci in the R0 checkout) and Node in this step; CI never skips it.",
                pytrace=False,
            )
        pytest.skip(f"{missing} (make link / setup; skipped locally only)")
    return r0 / "apps" / "digichat" / "scripts" / "check-config.ts"


# Remove with the lock bump past U5a (#6680, chrome.slug): the bump makes this XPASS,
# and strict turns that into a failure (SCHEMA-NOTES §0). raises=AssertionError keeps a
# CI "cannot run" failure (pytest.fail) a real failure instead of an expected one.
@pytest.mark.xfail(strict=True, raises=AssertionError, reason="needs R0 >= U5a")
def test_tenant_doc_passes_the_r0_schema() -> None:
    script = _require_r0_schema_check(R0)
    out = subprocess.run(
        ["npx", "tsx", str(script), str(DOC)],
        cwd=R0 / "apps" / "digichat",
        capture_output=True,
        text=True,
        timeout=120,
    )
    assert out.returncode == 0, out.stderr[-2000:]


def test_r0_schema_check_fails_in_ci_without_node_deps(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    (tmp_path / "apps" / "digichat" / "scripts").mkdir(parents=True)
    (tmp_path / "apps" / "digichat" / "scripts" / "check-config.ts").write_text("")
    monkeypatch.delenv(OWN_STEP_ENV, raising=False)
    monkeypatch.setenv("CI", "woodpecker")
    with pytest.raises(pytest.fail.Exception, match="cannot run in CI: R0 Node deps"):
        _require_r0_schema_check(tmp_path)
    monkeypatch.delenv("CI")
    with pytest.raises(pytest.skip.Exception, match="skipped locally only"):
        _require_r0_schema_check(tmp_path)


def test_r0_schema_check_fails_in_ci_without_an_r0_checkout(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.delenv(OWN_STEP_ENV, raising=False)
    monkeypatch.setenv("CI", "true")
    with pytest.raises(pytest.fail.Exception, match="cannot run in CI: no R0 checkout"):
        _require_r0_schema_check(tmp_path / "absent")


def test_r0_schema_xfail_does_not_hide_a_ci_failure() -> None:
    (mark,) = [m for m in test_tenant_doc_passes_the_r0_schema.pytestmark if m.name == "xfail"]
    assert mark.kwargs == {"strict": True, "raises": AssertionError, "reason": "needs R0 >= U5a"}
    assert not issubclass(pytest.fail.Exception, AssertionError)


def test_woodpecker_runs_the_r0_schema_check_in_a_node_step() -> None:
    steps = {s["name"]: s for s in yaml.safe_load((ROOT / ".woodpecker.yml").read_text())["steps"]}
    names = list(steps)
    assert names.index("fetch-r0") < names.index("r0-schema")
    node = steps["r0-schema"]
    assert node["image"].startswith("node:22") and "@sha256:" in node["image"]
    assert OWN_STEP_ENV not in (node.get("environment") or {}), "r0-schema must not skip itself"
    cmds = "\n".join(node["commands"])
    assert "npm ci" in cmds and "--ignore-scripts" in cmds
    assert "tests/test_tenant_schema.py::test_tenant_doc_passes_the_r0_schema" in cmds
    assert steps["test"]["environment"][OWN_STEP_ENV] == "r0-schema"


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
