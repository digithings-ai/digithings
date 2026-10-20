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
    # OPENROUTER is hosted-only; CHEAPERINFERENCE is required on selfhost and keychain-sourced.
    only = "AUTH_SECRET,CHEAPERINFERENCE_API_KEY"
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


# --- DIG-2959: --force overwrites the FILE, it does not re-roll a secret -----
#
# DIGICHAT_POSTGRES_PASSWORD is BOTH a rendered secret and the credential an
# existing digichat-db volume was initialised with. Re-generating it on every
# --force breaks auth against data that already exists, which is exactly what
# happened on the v3 run: the container came up and could not authenticate.

GENERATED = "DIGICHAT_POSTGRES_PASSWORD"


def rendered(out):
    return dict(row.split("=", 1) for row in out.read_text().splitlines() if "=" in row)


def test_force_preserves_an_already_rendered_generated_value(tmp_path):
    """The regression: --force must not silently change a generated password."""
    out = tmp_path / ".dev.vars"
    run("render", "--no-prompt", "--only", GENERATED, "--output", str(out), expect=0)
    first = rendered(out)[GENERATED]
    assert first, "nothing was rendered"

    run(
        "render", "--no-prompt", "--only", GENERATED, "--output", str(out), "--force", expect=0
    )
    assert rendered(out)[GENERATED] == first, (
        "--force re-generated a password an existing database volume already uses"
    )


def test_rotate_is_the_only_way_to_change_a_preserved_value(tmp_path):
    """Preservation must be escapable, or the value could never be rotated."""
    out = tmp_path / ".dev.vars"
    run("render", "--no-prompt", "--only", GENERATED, "--output", str(out), expect=0)
    first = rendered(out)[GENERATED]

    run(
        "render",
        "--no-prompt",
        "--only",
        GENERATED,
        "--output",
        str(out),
        "--force",
        "--rotate",
        GENERATED,
        expect=0,
    )
    assert rendered(out)[GENERATED] != first, "--rotate did not change the value"


def test_rotate_rejects_a_name_the_manifest_does_not_carry(tmp_path):
    """A typo in --rotate must fail loudly, not silently preserve everything."""
    out = tmp_path / ".dev.vars"
    out.write_text(f"{GENERATED}=kept\n")
    proc = run(
        "render",
        "--no-prompt",
        "--only",
        GENERATED,
        "--output",
        str(out),
        "--force",
        "--rotate",
        "NOT_A_SECRET",
        expect=2,
    )
    assert "NOT_A_SECRET" in proc.stderr
    assert out.read_text() == f"{GENERATED}=kept\n", "a rejected render still wrote"


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
    proc = run("check", "--only", "AUTH_SECRET,CHEAPERINFERENCE_API_KEY", expect=1)
    # A traceback also exits 1, so the exit code alone cannot tell a report from
    # a crash (`check` has no --output flag and once died reading args.output).
    assert "Traceback" not in proc.stderr, proc.stderr
    assert "resolved," in proc.stdout and "missing: CHEAPERINFERENCE_API_KEY" in proc.stdout
    assert not out.exists()


# ------------------------------------------------- the local keychain prefix


def test_the_keychain_prefix_override_comes_first(tool, manifest, monkeypatch):
    """The local stack's material lives under another prefix; the override wins.

    The contract keeps the production prefix, so the local bring-up finds its
    own values without the contract changing (DIG-4501).
    """
    monkeypatch.setenv(tool.KEYCHAIN_PREFIX_ENV, "digithings-local/")
    assert tool.keychain_prefixes(manifest) == ("digithings-local/", "digithings/")
    monkeypatch.delenv(tool.KEYCHAIN_PREFIX_ENV, raising=False)
    assert tool.keychain_prefixes(manifest) == ("digithings/",)


def test_a_keychain_value_is_read_through_the_prefix_list(tool, manifest, entries, monkeypatch):
    entry = next(e for e in entries if e["name"] == "DIGIKEY_ADMIN_TOKEN")
    seen: dict = {}

    def fake_stores(name, prefixes, allow_prompt):
        seen["prefixes"] = prefixes
        return "value"

    monkeypatch.setenv(tool.KEYCHAIN_PREFIX_ENV, "digithings-local/")
    monkeypatch.setattr(tool, "from_stores", fake_stores)
    assert tool.resolve(manifest, entry, {}, allow_prompt=False) == "value"
    assert seen["prefixes"] == ("digithings-local/", "digithings/")


def test_an_operator_prompt_value_is_read_from_the_store_before_it_is_asked_for(
    tool, manifest, entries, monkeypatch
):
    """A value that is in the credential store must not need the operator.

    The local stack's operator-supplied values (the digikey API key the local
    digikey mints, the digigraph upstream key, the digisearch seed key, the
    e2e bearer token) are in the store under the local prefix, so a scripted
    render (--no-prompt) finds them instead of failing on them.
    """
    entry = next(e for e in entries if e["name"] == "E2E_BEARER_TOKEN")
    asked: list = []

    def fake_stores(name, prefixes, allow_prompt):
        return "from-the-store"

    def fake_prompt(label):
        asked.append(label)
        return "typed"

    monkeypatch.setenv(tool.KEYCHAIN_PREFIX_ENV, "digithings-local/")
    monkeypatch.setattr(tool, "from_stores", fake_stores)
    monkeypatch.setattr(tool, "prompt", fake_prompt)

    assert tool.resolve(manifest, entry, {}, allow_prompt=False) == "from-the-store"
    assert asked == []

    # a value that is nowhere in the store still falls back to the prompt
    monkeypatch.setattr(tool, "from_stores", lambda name, prefixes, allow_prompt: None)
    assert tool.resolve(manifest, entry, {}, allow_prompt=True) == "typed"
    assert asked == ["E2E_BEARER_TOKEN: "]
    # and a scripted render reports it as missing rather than blocking
    assert tool.resolve(manifest, entry, {}, allow_prompt=False) is None


def test_from_store_still_reads_one_prefix(tool, monkeypatch):
    """The single-prefix entry point keeps its behaviour (it is the only caller
    of the store lookups outside the prefix list)."""
    monkeypatch.setattr(tool, "_from_one_store", lambda name, prefix: f"value-for-{prefix}")
    assert tool.from_store("NAME", "digithings/", allow_prompt=False) == "value-for-digithings/"
    monkeypatch.setattr(tool, "_from_one_store", lambda name, prefix: None)
    assert tool.from_store("NAME", "digithings/", allow_prompt=False) is None


# ------------------------------------- operator-prompt never reads the shared store


# The entries the contract marks "must never be copied from production" /
# "never taken from production": a per-workspace or locally-issued credential.
OPERATOR_PROMPT_NAMES = (
    "DIGICLAW_DIGIKEY_API_KEY",
    "DIGIGRAPH_UPSTREAM_API_KEY",
    "DIGISEARCH_SEED_API_KEY",
    "E2E_BEARER_TOKEN",
)


def _operator_entry(entries, name="DIGISEARCH_SEED_API_KEY"):
    return next(e for e in entries if e["name"] == name)


def test_an_operator_prompt_value_is_never_read_from_the_shared_prefix(
    tool, manifest, entries, monkeypatch
):
    """A per-workspace credential must not come out of the shared store.

    The contract says an operator-prompt value is "not a shared digithings
    secret", and the entries themselves say they are "never taken from
    production". The shared prefix "digithings/" IS the production store, so
    the local render must stop there and ask the operator instead
    (DIG-4659).
    """
    entry = _operator_entry(entries)
    asked: list = []

    def fake_one_store(name, prefix):
        asked.append(prefix)
        return "production-value" if prefix == "digithings/" else None

    monkeypatch.setenv(tool.KEYCHAIN_PREFIX_ENV, "digithings-local/")
    monkeypatch.setattr(tool, "_from_one_store", fake_one_store)
    monkeypatch.setattr(tool, "prompt", lambda label: "typed-by-the-operator")

    assert tool.resolve(manifest, entry, {}, allow_prompt=False) is None
    assert "production-value" not in asked
    assert "digithings/" not in asked


def test_the_shared_prefix_is_never_queried_for_an_operator_prompt_entry(
    tool, manifest, entries, monkeypatch
):
    """The shared store is not even asked: the value is asked for instead."""
    entry = _operator_entry(entries)
    asked: list = []
    prompted: list = []

    def fake_one_store(name, prefix):
        asked.append(prefix)
        return None

    def fake_prompt(label):
        prompted.append(label)
        return "typed-by-the-operator"

    monkeypatch.setenv(tool.KEYCHAIN_PREFIX_ENV, "digithings-local/")
    monkeypatch.setattr(tool, "_from_one_store", fake_one_store)
    monkeypatch.setattr(tool, "prompt", fake_prompt)

    assert tool.resolve(manifest, entry, {}, allow_prompt=True) == "typed-by-the-operator"
    assert asked == ["digithings-local/"]
    assert prompted == ["DIGISEARCH_SEED_API_KEY: "]


def test_an_operator_prompt_value_is_read_from_the_operator_prefix(
    tool, manifest, entries, monkeypatch
):
    """The local stack's own prefix still answers for its own credentials."""
    entry = _operator_entry(entries)

    def fake_one_store(name, prefix):
        return "local-value" if prefix == "digithings-local/" else None

    monkeypatch.setenv(tool.KEYCHAIN_PREFIX_ENV, "digithings-local/")
    monkeypatch.setattr(tool, "_from_one_store", fake_one_store)

    assert tool.resolve(manifest, entry, {}, allow_prompt=False) == "local-value"


def test_without_an_operator_prefix_the_value_is_asked_for_not_taken_from_the_shared_store(
    tool, manifest, entries, monkeypatch
):
    """No prefix for this workspace means the operator is asked for the value.

    The shared store is not a fallback here: it is the production store.
    """
    entry = _operator_entry(entries)
    asked: list = []

    def fake_one_store(name, prefix):
        asked.append(prefix)
        return "shared-value"

    monkeypatch.delenv(tool.KEYCHAIN_PREFIX_ENV, raising=False)
    monkeypatch.setattr(tool, "_from_one_store", fake_one_store)
    monkeypatch.setattr(tool, "prompt", lambda label: "typed-by-the-operator")

    assert tool.resolve(manifest, entry, {}, allow_prompt=True) == "typed-by-the-operator"
    assert asked == []


def test_a_keychain_value_still_falls_back_to_the_shared_prefix(
    tool, manifest, entries, monkeypatch
):
    """A shared secret keeps the full prefix list: the local one, then the shared one."""
    entry = next(e for e in entries if e["name"] == "DIGIKEY_ADMIN_TOKEN")
    asked: list = []

    def fake_one_store(name, prefix):
        asked.append(prefix)
        return "shared-value" if prefix == "digithings/" else None

    monkeypatch.setenv(tool.KEYCHAIN_PREFIX_ENV, "digithings-local/")
    monkeypatch.setattr(tool, "_from_one_store", fake_one_store)

    assert tool.resolve(manifest, entry, {}, allow_prompt=False) == "shared-value"
    assert asked == ["digithings-local/", "digithings/"]


def test_the_contract_marks_the_never_from_production_entries_as_operator_prompt(entries):
    """The contract says it; the renderer must honour it."""
    for name in OPERATOR_PROMPT_NAMES:
        entry = next(e for e in entries if e["name"] == name)
        assert entry["source"] == "operator-prompt", name


@pytest.mark.parametrize("name", OPERATOR_PROMPT_NAMES)
def test_the_render_fails_for_any_never_from_production_entry_without_its_own_value(
    tool, manifest, entries, monkeypatch, name
):
    """Each of the four FAILS the render instead of taking the production value.

    This is the local stack's own path: the local render runs with --no-prompt,
    so a missing operator value has to be a failure. A render that quietly took
    the credential under "digithings/" would bind a production credential into
    the local stack (DIG-4659).
    """
    entry = next(e for e in entries if e["name"] == name)
    monkeypatch.setenv(tool.KEYCHAIN_PREFIX_ENV, "digithings-local/")
    monkeypatch.setattr(
        tool,
        "_from_one_store",
        lambda n, prefix: "production-value" if prefix == "digithings/" else None,
    )

    values, missing, skipped = tool.resolve_all(manifest, [entry], allow_prompt=False, verbose=False)

    assert name in missing
    assert "production-value" not in values.values()


@pytest.mark.parametrize("name", OPERATOR_PROMPT_NAMES)
def test_the_own_prefix_answers_for_any_never_from_production_entry(
    tool, manifest, entries, monkeypatch, name
):
    """The fix must not break the local flow: the workspace store still answers."""
    entry = next(e for e in entries if e["name"] == name)
    monkeypatch.setenv(tool.KEYCHAIN_PREFIX_ENV, "digithings-local/")
    monkeypatch.setattr(
        tool,
        "_from_one_store",
        lambda n, prefix: "local-value" if prefix == "digithings-local/" else None,
    )

    assert tool.resolve(manifest, entry, {}, allow_prompt=False) == "local-value"


def test_the_local_stack_names_its_own_keychain_prefix():
    """The local stack names the prefix the operator values are read from.

    `dt up` renders the secret file with this prefix in the environment, so the
    operator-supplied values are read from the local store and the shared
    "digithings/" store is never asked (DIG-4659). Without the prefix, the
    render would ask for every operator value instead.
    """
    from scripts.localstack import localenv

    env = localenv.apply_defaults(REPO, {})
    assert env[localenv.KEYCHAIN_PREFIX_ENV] == "digithings-local/"
