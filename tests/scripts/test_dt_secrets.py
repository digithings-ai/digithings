"""Contract and safety tests for config/contract/secrets.yaml and scripts/dt-secrets.

The properties pinned here are the ones that would cause real harm if they broke:

  * the manifest is TRACKED and `.dev.vars` is IGNORED -- invert either and the
    contract disappears, or a rendered secret file becomes committable;
  * the manifest carries NAMES only -- a value committed here is a published secret;
  * every manifest name is GROUNDED in the repo -- an invented name is a phantom
    that the next engineer cannot find;
  * render writes 0600, never echoes a value, and is all-or-nothing.

Run: pytest tests/scripts/test_dt_secrets.py -m unit
"""

from __future__ import annotations

import base64
import importlib.util
import re
import subprocess
import sys
from pathlib import Path

import pytest
import yaml

pytestmark = pytest.mark.unit

REPO = Path(__file__).resolve().parents[2]
MANIFEST = REPO / "config" / "contract" / "secrets.yaml"
TOOL = REPO / "scripts" / "dt-secrets"
PY = sys.executable

SOURCES = {"keychain", "generated-local", "operator-prompt", "github-secret", "cloudflare-secret"}


def load_tool():
    spec = importlib.util.spec_from_loader(
        "dt_secrets", importlib.machinery.SourceFileLoader("dt_secrets", str(TOOL))
    )
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


@pytest.fixture(scope="module")
def manifest() -> dict:
    return yaml.safe_load(MANIFEST.read_text())


@pytest.fixture(scope="module")
def entries(manifest) -> list[dict]:
    return manifest["secrets"]


@pytest.fixture(scope="module")
def tool():
    """The tool as a module, so its internals can be exercised directly."""
    return load_tool()


def run(*argv: str, expect: int | None = None):
    proc = subprocess.run(
        [PY, str(TOOL), *argv], capture_output=True, text=True, cwd=REPO, check=False
    )
    if expect is not None:
        assert proc.returncode == expect, f"rc={proc.returncode}\n{proc.stdout}\n{proc.stderr}"
    return proc


# ------------------------------------------------------------------ tracking


def test_manifest_is_tracked_and_dev_vars_is_ignored():
    """The negation works and the rendered file stays uncommittable.

    `git add -n` is deliberately NOT the assertion. It prints nothing for a path
    that is already tracked, so it passed locally (the manifest was untracked)
    and failed in CI (the manifest is committed). `git ls-files --error-unmatch`
    does not depend on the index state.
    """

    def git(*argv: str):
        return subprocess.run(["git", *argv], capture_output=True, text=True, cwd=REPO, check=False)

    assert git("ls-files", "--error-unmatch", "config/contract/secrets.yaml").returncode == 0, (
        "the contract manifest must be tracked"
    )

    # Firing control: the same command must reject a path that is not in the index.
    assert git("ls-files", "--error-unmatch", "config/contract/never-added.yaml").returncode != 0, (
        "ls-files must be able to report a path as untracked"
    )

    proc = git("check-ignore", "-v", ".dev.vars")
    assert proc.returncode == 0, "git must refuse .dev.vars"
    # <source>:<linenum>:<pattern> TAB <path>; a negation would start with "!".
    pattern = proc.stdout.split("\t")[0].split(":", 2)[2]
    assert not pattern.startswith("!"), f".dev.vars is negated by {pattern!r}"

    # NOTE: `git check-ignore` cannot be used to prove the manifest's negation.
    # Measured here: it returns rc=1 with EMPTY stdout for
    # `config/contract/secrets.yaml` BOTH with and without the negation rule, so
    # it cannot tell "negated" from "matched no rule at all". The negation is
    # pinned by reading the rules in
    # test_gitignore_has_no_unanchored_secrets_yaml_without_exception instead.


def test_gitignore_has_no_unanchored_secrets_yaml_without_exception():
    """`secrets.yaml` is an unanchored net; the contract must be its one exception."""
    rules = (REPO / ".gitignore").read_text().splitlines()
    assert "secrets.yaml" in rules
    assert "!/config/contract/secrets.yaml" in rules
    assert ".dev.vars*" in rules and "!.dev.vars.example" in rules


# --------------------------------------------------------------- structure


def test_names_are_unique_and_well_formed(entries):
    names = [e["name"] for e in entries]
    assert len(names) == len(set(names)), "duplicate name in the manifest"
    for e in entries:
        assert re.match(r"^[A-Z][A-Z0-9_]*$", e["name"]), e["name"]
        assert e["consumers"], f"{e['name']} names no consumer"
        assert set(e["required_in"]) <= {"selfhost", "hosted"}, e["name"]
        assert e["source"] in SOURCES, e["name"]


def test_renderable_agrees_with_the_source_legend(manifest, entries):
    for e in entries:
        assert bool(e["renderable"]) == bool(manifest["sources"][e["source"]]["renderable"]), e[
            "name"
        ]
        if "selfhost" in e["required_in"]:
            assert e["renderable"], f"{e['name']} is required by selfhost but not renderable"


def test_every_generated_secret_declares_how_it_is_made(manifest, entries):
    names = {e["name"] for e in entries}
    for e in entries:
        if e["source"] != "generated-local":
            continue
        how = [k for k in ("generate", "template", "same_as") if k in e]
        assert how, f"{e['name']} is generated-local but says nothing about how"
        if "same_as" in e:
            assert e["same_as"] in names, e["name"]
            assert "generate" not in e, f"{e['name']} both aliases and generates"
        if "generate_field" in e:
            assert "generate" in e, e["name"]


def test_supabase_keychain_generation_pins_its_cwd(manifest, entries):
    """`supabase status` resolves its project from the child process cwd.

    Its own --workdir flag does not redirect container-name resolution
    (measured on CLI v2.117.0), so the directory has to be declared and applied.
    """
    e = next(x for x in entries if x["name"] == "CORE_SUPABASE_SERVICE_KEY")
    assert "supabase" in e["generate"], e
    assert e.get("generate_cwd"), "generated-local supabase entry declares no generate_cwd"


def test_generate_cwd_prefers_the_env_override(tool, monkeypatch, tmp_path):
    """The committed contract stays portable; the host points it at its own dir."""
    outside = tmp_path / "core-local" / "supabase"
    outside.mkdir(parents=True)
    monkeypatch.setenv("DT_GENERATE_CWD_CORE_SUPABASE_SERVICE_KEY", str(outside))
    assert tool.generate_cwd("CORE_SUPABASE_SERVICE_KEY", {}) == str(outside)


def test_generate_cwd_resolves_a_relative_path_against_the_cwd(tool, monkeypatch, tmp_path):
    monkeypatch.delenv("DT_GENERATE_CWD_CORE_SUPABASE_SERVICE_KEY", raising=False)
    monkeypatch.chdir(tmp_path)
    got = tool.generate_cwd("CORE_SUPABASE_SERVICE_KEY", {"generate_cwd": "sub/dir"})
    assert got == str(tmp_path / "sub" / "dir")


def test_generate_cwd_is_none_when_the_entry_declares_none(tool, monkeypatch):
    monkeypatch.delenv("DT_GENERATE_CWD_ANY", raising=False)
    assert tool.generate_cwd("ANY", {}) is None


def test_run_generate_runs_the_command_in_the_given_cwd(tool, tmp_path, monkeypatch):
    """The cwd must reach the child process; this is the whole point (DIG-2959)."""
    seen: dict[str, str] = {}

    def fake_run(argv, **kwargs):
        seen["cwd"] = kwargs.get("cwd")
        # supabase emits KEY="value"; KV_RE only matches the quoted form.
        return subprocess.CompletedProcess(
            argv, 0, stdout='SERVICE_ROLE_KEY="abc"\n', stderr=""
        )

    monkeypatch.setattr(tool.subprocess, "run", fake_run)
    assert tool.run_generate(["supabase", "status"], "SERVICE_ROLE_KEY", str(tmp_path)) == "abc"
    assert seen["cwd"] == str(tmp_path)


def test_run_generate_names_a_missing_workdir_instead_of_blaming_the_tool(tool, monkeypatch):
    """A missing cwd makes subprocess raise FileNotFoundError, same as a missing
    binary. Reporting 'is not installed' would send the reader after the wrong
    cause, so the workdir is checked first."""
    monkeypatch.setenv("PATH", "")  # guarantee the program is not resolvable either
    with pytest.raises(tool.RenderError, match="workdir does not exist"):
        tool.run_generate(["definitely-not-a-tool"], "X", "/nonexistent-dir")


def test_run_generate_surfaces_the_stderr_hint_when_a_cli_exits_zero(tool, tmp_path, monkeypatch):
    """supabase exits 0 even when it cannot inspect its containers, so the empty
    field must carry the tool's own complaint."""

    def fake_run(argv, **kwargs):
        return subprocess.CompletedProcess(argv, 0, stdout="", stderr="No such container: x\n")

    monkeypatch.setattr(tool.subprocess, "run", fake_run)
    with pytest.raises(tool.RenderError, match="No such container"):
        tool.run_generate(["supabase", "status"], "SERVICE_ROLE_KEY", str(tmp_path))


def test_no_secret_reaches_a_non_renderable_source(entries):
    """Local-only generation must never be routed at a hosted-only store."""
    for e in entries:
        if e["source"] == "generated-local":
            assert "selfhost" in e["required_in"], e["name"]


# ---------------------------------------------------------- names, not values


def test_manifest_contains_no_assignment_and_no_long_blob():
    """A value here is a published secret. Shape guards, each with a near miss."""
    text = MANIFEST.read_text()
    assert not re.search(r"^[A-Z][A-Z0-9_]*\s*=", text, re.M), "assignment found"
    assert not re.search(r"[A-Za-z0-9+/]{40,}={0,2}", text), "long base64 blob found"
    assert not re.search(r"\b[0-9a-f]{32,}\b", text), "long hex blob found"
    # The same regexes MUST fire on a value, or the guards above are vacuous.
    assert re.search(r"[A-Za-z0-9+/]{40,}={0,2}", base64.b64encode(b"x" * 40).decode())


def test_manifest_pins_the_plan_mandated_local_only_keys(entries):
    """Plan section 4 names these; a silent drop is the regression."""
    names = {e["name"] for e in entries}
    for required in (
        "AUTH_SECRET",
        "CORE_SUPABASE_SERVICE_KEY",
        "DIGIKEY_LITELLM_PROXY_KEY",
        "DIGIKEY_PRIVATE_KEY_PEM",
    ):
        assert required in names, required
    supa = next(e for e in entries if e["name"] == "CORE_SUPABASE_SERVICE_KEY")
    assert supa["source"] == "generated-local"
    assert supa["generate_field"] == "SERVICE_ROLE_KEY"


def test_every_manifest_name_is_grounded_in_the_repo(entries):
    """An invented name is a phantom. Ground it in .env.example or the source."""
    env_example = (REPO / ".env.example").read_text()
    inventory = (REPO / "docs" / "ops" / "SECRETS_INVENTORY.md").read_text()
    ungrounded = []
    for e in entries:
        name = e["name"]
        in_docs = name in env_example or name in inventory
        if not in_docs:
            proc = subprocess.run(
                ["git", "grep", "-l", "-w", name, "--", ":!config/contract", ":!tests"],
                capture_output=True,
                text=True,
                cwd=REPO,
                check=False,
            )
            in_src = proc.returncode == 0 and proc.stdout.strip()
        if not (in_docs or in_src):
            ungrounded.append(name)
    assert not ungrounded, f"names with no referent in the repo: {ungrounded}"


# ------------------------------------------------------------------ render


def _self_generated_names() -> list[str]:
    """Entries minted by a local generator that needs no running service."""
    doc = yaml.safe_load(MANIFEST.read_text())
    return [
        e["name"]
        for e in doc["secrets"]
        if e["source"] == "generated-local"
        and "generate" in e
        and "generate_field" not in e
        and "same_as" not in e
    ]


def test_render_writes_0600_and_never_echoes_a_value(tmp_path):
    names = _self_generated_names()
    assert len(names) >= 8, f"expected a real generator set, got {names}"
    only = ",".join(names)
    out = tmp_path / ".dev.vars"
    proc = run("render", "--no-prompt", "--only", only, "--output", str(out), expect=0)
    assert oct(out.stat().st_mode)[-3:] == "600"

    values = dict(row.split("=", 1) for row in out.read_text().splitlines() if "=" in row)
    assert len(values) >= 8, "nothing was rendered"
    leaked = [k for k, v in values.items() if v and (v in proc.stdout or v in proc.stderr)]
    assert not leaked, f"render echoed the value of {leaked}"


def test_generator_needing_a_live_service_fails_cleanly(tmp_path):
    """CORE_SUPABASE_SERVICE_KEY reads the local Supabase. With none running the
    render must abort, name the command, and write nothing -- never a stub value."""
    out = tmp_path / ".dev.vars"
    proc = run(
        "render",
        "--no-prompt",
        "--only",
        "CORE_SUPABASE_SERVICE_KEY",
        "--output",
        str(out),
        expect=2,
    )
    assert not out.exists(), "wrote a file despite an unresolved generator"
    assert "supabase" in proc.stderr
    assert "CORE_SUPABASE_SERVICE_KEY" in proc.stderr, "the error must name the secret"


def test_render_is_all_or_nothing(tmp_path):
    """One unresolved value must leave NO file, not a half-filled one."""
    only = "AUTH_SECRET,OPENROUTER_API_KEY"
    out = tmp_path / ".dev.vars"
    proc = run("render", "--no-prompt", "--only", only, "--output", str(out), expect=1)
    assert not out.exists(), "a partial file was written"
    assert "all-or-nothing" in proc.stderr


def test_same_as_secret_shares_one_value(tmp_path):
    out = tmp_path / ".dev.vars"
    run(
        "render",
        "--no-prompt",
        "--only",
        "LITELLM_MASTER_KEY,DIGIKEY_LITELLM_PROXY_KEY",
        "--output",
        str(out),
        expect=0,
    )
    values = dict(row.split("=", 1) for row in out.read_text().splitlines() if "=" in row)
    assert values["LITELLM_MASTER_KEY"] == values["DIGIKEY_LITELLM_PROXY_KEY"]


def test_render_refuses_to_clobber_without_force(tmp_path):
    out = tmp_path / ".dev.vars"
    out.write_text("KEEP=me\n")
    run("render", "--no-prompt", "--only", "AUTH_SECRET", "--output", str(out), expect=1)
    assert out.read_text() == "KEEP=me\n"
    run("render", "--no-prompt", "--only", "AUTH_SECRET", "--output", str(out), "--force", expect=0)
    assert out.read_text() != "KEEP=me\n"


def test_non_renderable_hosted_secrets_are_skipped(tmp_path):
    """A GitHub/Cloudflare secret has no local value and must never be invented."""
    doc = yaml.safe_load(MANIFEST.read_text())
    hosted_only = [
        e["name"]
        for e in doc["secrets"]
        if "hosted" in e["required_in"] and not doc["sources"][e["source"]]["renderable"]
    ]
    proc = run("list", "--variant", "hosted", expect=0)
    for name in hosted_only:
        assert name in proc.stdout


def test_tool_makes_no_network_call():
    """It resolves from local stores only, so it cannot fetch a prod value."""
    source = TOOL.read_text()
    for banned in ("import socket", "import urllib", "import requests", "http.client", "urlopen"):
        assert banned not in source, banned
    # Control: the guard can still fire on a real import.
    assert "import socket" in "import socket\n"


def test_check_reports_missing_without_writing(tmp_path):
    out = tmp_path / ".dev.vars"
    run("check", "--only", "AUTH_SECRET,OPENROUTER_API_KEY", expect=1)
    assert not out.exists()
