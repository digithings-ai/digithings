"""Tests for the self-host <-> hosted parity checks (DIG-2767).

What these pin, and why each one is here:

* The file lists in `scripts/self_host_parity.py` must cover the repo. A parity
  check that silently skips `infra/self-host/compose.ghcr.yml` -- the self-host
  surface itself -- would be green and blind. The census tests compare the
  module's lists against a glob of the tree, so adding a compose file without
  covering it turns these red.
* `diff_surface` must fire on a new binding, a new var, a new compose env key, a
  new file, a removal, and a changed binding kind. A detector that finds nothing
  is indistinguishable from a detector that is not wired up, so every case is
  stated as a synthetic input rather than only run against the real tree.
* `compare_failures` is an equivalence, not a ratchet: a new gap AND a recorded
  gap that stopped happening must both fail.
* The committed baseline must hold NAMES and binding KINDS only. A `var` value
  or a binding id in this file is a secret-shaped accident, so the kinds are
  asserted against the closed set.
* The migration runner refuses any database that is not clearly disposable. This
  host runs three other people's PostgreSQL servers, so "the port answers" is not
  evidence that the server is ours.
"""

from __future__ import annotations

import importlib.util
import json
import subprocess
from pathlib import Path

import pytest

pytestmark = pytest.mark.unit

REPO_ROOT = Path(__file__).resolve().parents[2]
SCRIPT = REPO_ROOT / "scripts" / "self_host_parity.py"
RUNNER = REPO_ROOT / "scripts" / "self_host_migrations_check.sh"
BASELINE = REPO_ROOT / "config" / "self-host" / "parity-baseline.json"

_spec = importlib.util.spec_from_file_location("self_host_parity", SCRIPT)
parity = importlib.util.module_from_spec(_spec)
assert _spec.loader is not None
_spec.loader.exec_module(parity)

ALLOWED_KINDS = {
    "var",
    "r2_bucket",
    "durable_object_namespace",
    "kv_namespace",
    "d1_database",
    "service",
    "queue",
    "container",
    "analytics_engine_dataset",
    "hyperdrive",
    "mtls_certificate",
}


# --------------------------------------------------------------------- census
def test_wrangler_files_are_discovered_not_hardcoded():
    on_disk = sorted(
        str(p.relative_to(REPO_ROOT))
        for p in REPO_ROOT.rglob("wrangler.toml")
        if "node_modules" not in p.parts
    )
    assert len(on_disk) == parity.EXPECTED_WRANGLER_FILES, on_disk
    assert set(parity.wrangler_surface()) == set(on_disk)


def test_compose_file_list_covers_every_compose_file_in_the_repo():
    on_disk = sorted(
        str(p.relative_to(REPO_ROOT))
        for p in REPO_ROOT.rglob("*.yml")
        if "node_modules" not in p.parts
        and (p.name.startswith("compose") or p.name.startswith("docker-compose"))
    )
    missing = sorted(set(on_disk) - set(parity.COMPOSE_FILES))
    assert not missing, f"compose files not covered by the parity check: {missing}"
    # And the list must not name a file that does not exist, which would make the
    # census above pass while covering nothing.
    absent = [rel for rel in parity.COMPOSE_FILES if not (REPO_ROOT / rel).exists()]
    assert not absent, absent


def test_env_example_list_covers_every_env_example_in_the_repo():
    """Every `.env.example` on disk is either censused or excluded on purpose.

    An exclusion is not a gap: it has to be named, carry the guard that owns the
    file, and exist. Anything else would be a file this check is silently blind
    to, which is the failure this test exists to prevent.
    """
    on_disk = sorted(
        str(p.relative_to(REPO_ROOT))
        for p in REPO_ROOT.rglob("*.env.example")
        if "node_modules" not in p.parts
    )
    covered = set(parity.ENV_EXAMPLE_FILES) | set(parity.HOUSE_GUARDED_FILES)
    missing = sorted(set(on_disk) - covered)
    assert not missing, f".env.example files neither censused nor excluded: {missing}"
    assert not (set(parity.ENV_EXAMPLE_FILES) & set(parity.HOUSE_GUARDED_FILES)), (
        "a file is both censused and excluded"
    )
    for path, reason in parity.HOUSE_GUARDED_FILES.items():
        assert (REPO_ROOT / path).exists(), f"excluded file does not exist: {path}"
        assert reason.strip(), f"exclusion without a reason: {path}"


def test_the_dig337_guarded_file_is_really_absent_from_the_committed_baseline():
    """The point of the exclusion: no committed file of this slice may reproduce
    the retired provider-key names that DIG-337's guard keeps out of the tree.

    The pattern is read from that guard instead of being retyped here, for two
    reasons. It is the guard's rule, not this slice's, and this file is itself a
    tracked file the guard scans -- a retyped copy would make this slice the very
    thing DIG-337 exists to prevent.
    """
    guarded_test = REPO_ROOT / "tests" / "scripts" / "test_retired_provider_keys.py"
    spec = importlib.util.spec_from_file_location("_dig337_guard", guarded_test)
    guard = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(guard)

    surface = json.loads((REPO_ROOT / "config" / "self-host" / "parity-baseline.json").read_text())
    for section in ("wrangler", "composeEnv", "envExample"):
        for guarded in parity.HOUSE_GUARDED_FILES:
            assert guarded not in surface["surface"].get(section, {}), (
                f"{guarded} is still censused under {section}"
            )
    assert set(surface["surface"]["houseGuarded"]) == set(parity.HOUSE_GUARDED_FILES)

    text = (REPO_ROOT / "config" / "self-host" / "parity-baseline.json").read_text()
    assert not guard.PATTERN.search(text), "a retired provider-key name is back in the baseline"
    for mine in (SCRIPT, RUNNER, Path(__file__)):
        assert not guard.PATTERN.search(mine.read_text()), f"retired vendor name in {mine.name}"


def test_the_self_host_compose_file_is_actually_covered():
    assert "infra/self-host/compose.ghcr.yml" in parity.COMPOSE_FILES


# ----------------------------------------------------------- diff_surface arms
BASE = {
    "wrangler": {"apps/x/wrangler.toml": {"A": "var", "B": "r2_bucket"}},
    "composeEnv": {"docker-compose.yml": ["ONE", "TWO"]},
    "envExample": {".env.example": ["ONE"]},
}


def _mutate(**section_changes):
    import copy

    data = copy.deepcopy(BASE)
    data.update(section_changes)
    return data


def test_diff_surface_is_empty_for_identical_surfaces():
    assert parity.diff_surface(BASE, _mutate()) == []


def test_diff_surface_flags_a_new_binding():
    current = _mutate()
    current["wrangler"]["apps/x/wrangler.toml"]["C"] = "durable_object_namespace"
    problems = parity.diff_surface(BASE, current)
    assert any("NEW binding/var C" in p and "durable_object_namespace" in p for p in problems), (
        problems
    )


def test_diff_surface_flags_a_new_plain_var():
    current = _mutate()
    current["wrangler"]["apps/x/wrangler.toml"]["D"] = "var"
    problems = parity.diff_surface(BASE, current)
    assert any("NEW binding/var D" in p for p in problems), problems


def test_diff_surface_flags_a_changed_binding_kind():
    current = _mutate()
    current["wrangler"]["apps/x/wrangler.toml"]["B"] = "service"
    problems = parity.diff_surface(BASE, current)
    assert any("kind r2_bucket -> service" in p for p in problems), problems


def test_diff_surface_flags_a_removed_binding():
    current = _mutate()
    del current["wrangler"]["apps/x/wrangler.toml"]["A"]
    problems = parity.diff_surface(BASE, current)
    assert any("REMOVED binding/var A" in p for p in problems), problems


def test_diff_surface_flags_a_new_compose_env_key():
    current = _mutate()
    current["composeEnv"]["docker-compose.yml"] = ["ONE", "TWO", "THREE"]
    problems = parity.diff_surface(BASE, current)
    assert any("NEW env key THREE" in p for p in problems), problems


def test_diff_surface_flags_a_new_worker_file():
    current = _mutate()
    current["wrangler"]["apps/y/wrangler.toml"] = {}
    problems = parity.diff_surface(BASE, current)
    assert any("NEW wrangler file" in p for p in problems), problems


def test_diff_surface_flags_a_new_durable_object_table_shape():
    """`[[durable_objects.bindings]]` parses as a dict, not a list of tables.

    Reading it as a list drops every Durable Object binding silently, which is
    the exact class of binding this check exists to notice.
    """
    surface = parity.wrangler_surface()
    do_files = {
        path: names
        for path, names in surface.items()
        if any(kind == "durable_object_namespace" for kind in names.values())
    }
    assert do_files, "no Durable Object bindings discovered at all -- the reader is broken"


# ------------------------------------------------------------------- baseline
def test_committed_baseline_records_names_and_kinds_only():
    data = json.loads(BASELINE.read_text())
    assert data["surface"], "baseline has an empty surface"
    kinds = {kind for entries in data["surface"]["wrangler"].values() for kind in entries.values()}
    assert kinds <= ALLOWED_KINDS, kinds - ALLOWED_KINDS
    # wrangler values are always "name -> kind", never "name -> value".
    for path, entries in data["surface"]["wrangler"].items():
        for name, kind in entries.items():
            assert kind in ALLOWED_KINDS, f"{path}:{name} recorded a value, not a kind: {kind!r}"


def test_committed_baseline_matches_the_tree_today():
    assert (
        parity.diff_surface(json.loads(BASELINE.read_text())["surface"], parity.surface_signature())
        == []
    )


def test_every_recorded_migration_gap_carries_a_class_and_a_reason():
    rows = json.loads(BASELINE.read_text())["migrations"]["knownFromEmptyFailures"]
    assert rows, "no from-empty gaps recorded, but the chain was measured and 11 failed"
    for row in rows:
        assert row["class"] and row["reason"], row
        assert len(row["reason"]) > 60, f"{row['migration']} has a token reason, not a real one"


def test_the_baseline_excludes_the_staged_cutover_migrations():
    text = BASELINE.read_text()
    assert "cutover/113_drop_legacy_book_uniques.sql" not in text
    assert "900_drop_anon_read_cutover" not in text


# -------------------------------------------------------- compare_failures arms
def test_compare_failures_accepts_an_exact_match():
    measured = {"a.sql": "boom"}
    known = {"a.sql": {"migration": "a.sql", "error": "boom"}}
    assert parity.compare_failures(measured, known) == ([], [], [])


def test_compare_failures_flags_a_new_gap():
    measured = {"a.sql": "boom", "b.sql": "new boom"}
    known = {"a.sql": {"migration": "a.sql", "error": "boom"}}
    new, stale, changed = parity.compare_failures(measured, known)
    assert new == ["b.sql"] and stale == [] and changed == []


def test_compare_failures_flags_a_repaired_gap_as_stale():
    """The anti-ratchet half: a recorded failure that stopped happening is a
    finding, not a cleanup. Without this the baseline can rot in both directions."""
    measured: dict[str, str] = {}
    known = {"a.sql": {"migration": "a.sql", "error": "boom"}}
    new, stale, changed = parity.compare_failures(measured, known)
    assert stale == ["a.sql"] and new == []


def test_compare_failures_flags_a_changed_error_message():
    measured = {"a.sql": "a different boom"}
    known = {"a.sql": {"migration": "a.sql", "error": "boom"}}
    new, stale, changed = parity.compare_failures(measured, known)
    assert changed == ["a.sql"]


# --------------------------------------------------------------- contract arm
def test_contract_arm_is_not_run_while_the_contract_is_absent(capsys):
    if parity.CONTRACT_DIR.exists():
        pytest.skip("config/contract/ has landed; arm (a) is live and this test is obsolete")
    assert parity.mode_contract() == 3
    out = capsys.readouterr().out
    assert "NOT RUN" in out
    assert "PASS" not in out.replace("NOT RUN (arm a)", "")


def test_contract_arm_fails_on_a_name_the_contract_does_not_declare(tmp_path, monkeypatch, capsys):
    monkeypatch.setattr(parity, "CONTRACT_DIR", tmp_path)
    (tmp_path / "env.yaml").write_text("env:\n  - name: ONE\n")
    monkeypatch.setattr(
        parity,
        "surface_signature",
        lambda: {
            "wrangler": {"apps/x/wrangler.toml": {"ONE": "var", "UNDECLARED": "var"}},
            "composeEnv": {},
            "envExample": {},
        },
    )
    assert parity.mode_contract() == 1
    assert "UNDECLARED" in capsys.readouterr().out


def test_contract_arm_passes_when_every_name_is_declared(tmp_path, monkeypatch):
    """The non-vacuity control for the test above: same shape, fully declared."""
    monkeypatch.setattr(parity, "CONTRACT_DIR", tmp_path)
    (tmp_path / "env.yaml").write_text("env:\n  - name: ONE\nsecrets:\n  - name: UNDECLARED\n")
    monkeypatch.setattr(
        parity,
        "surface_signature",
        lambda: {
            "wrangler": {"apps/x/wrangler.toml": {"ONE": "var", "UNDECLARED": "var"}},
            "composeEnv": {},
            "envExample": {},
        },
    )
    assert parity.mode_contract() == 0


# --------------------------------------------------------------- runner guards
def _run_runner(args, env_extra=None):
    import os

    env = dict(os.environ)
    env.update(env_extra or {})
    return subprocess.run(
        ["bash", str(RUNNER), *args],
        capture_output=True,
        text=True,
        env=env,
        check=False,
        cwd=str(REPO_ROOT),
    )


@pytest.mark.parametrize("database", ["postgres", "dig1781", "paperclip", "production"])
def test_runner_refuses_any_database_that_is_not_clearly_disposable(database):
    """This host runs three other people's PostgreSQL servers, including
    Paperclip's own board database. The runner must never be one `PGDATABASE`
    typo away from applying 137 migrations into someone else's data."""
    proc = _run_runner([], {"PGDATABASE": database})
    assert proc.returncode == 1, proc.stderr
    assert "refusing to touch database" in proc.stderr
    assert "disposable" in proc.stderr


def test_runner_plan_excludes_the_staged_cutover_directory():
    proc = _run_runner(["--plan"])
    assert proc.returncode == 0, proc.stderr
    assert "cutover/       excluded" in proc.stdout
    assert "137 migrations" in proc.stdout, proc.stdout


def test_runner_plan_rejects_an_unparsable_migration_name(tmp_path, monkeypatch):
    (tmp_path / "001_ok.sql").write_text("select 1;")
    (tmp_path / "not-a-number.sql").write_text("select 1;")
    proc = _run_runner(["--plan"], {"PARITY_MIGRATIONS_DIR": str(tmp_path)})
    assert proc.returncode == 1
    assert "naming guard" in proc.stderr


def test_runner_is_valid_bash():
    proc = subprocess.run(["bash", "-n", str(RUNNER)], capture_output=True, text=True, check=False)
    assert proc.returncode == 0, proc.stderr


# ------------------------------------------- the measure/judge exit contract
_STUB_PSQL = r"""#!/usr/bin/env bash
# A stub psql for the exit-contract tests. It answers the two probe queries the
# runner asks (server version, public table count), drains nothing, and fails
# ONLY for a migration file named 002_bad.sql -- so "the chain applied" and "one
# file failed" are both reachable without a PostgreSQL server.
prev=""; last=""
for a in "$@"; do
  if [ "$prev" = "-f" ]; then last="$a"; fi
  if [ "$prev" = "-c" ]; then
    case "$a" in
      *server_version*) echo "17.11"; exit 0 ;;
      *information_schema*) echo "42"; exit 0 ;;
    esac
  fi
  prev="$a"
done
case " $* " in *' --version '*) echo "psql (PostgreSQL) 17.11"; exit 0 ;; esac
case "$last" in
  *002_bad.sql)
    echo "psql:${last}:3: ERROR:  relation \"public.nope\" does not exist" >&2
    exit 1 ;;
esac
exit 0
"""

_STUB_NOOP = "#!/usr/bin/env bash\nexit 0\n"


def _stub_env(tmp_path, with_bad_file):
    """A stubbed runner environment: no server, no real database, no real
    migrations. Returns (env, json_path)."""
    mig = tmp_path / "migrations"
    mig.mkdir(exist_ok=True)
    (mig / "001_ok.sql").write_text("select 1;\n")
    if with_bad_file:
        (mig / "002_bad.sql").write_text("select * from public.nope;\n")
    stub = tmp_path / "psql"
    stub.write_text(_STUB_PSQL)
    stub.chmod(0o755)
    for name in ("createdb", "dropdb"):
        path = tmp_path / name
        path.write_text(_STUB_NOOP)
        path.chmod(0o755)
    return {
        "PARITY_PSQL": str(stub),
        "PARITY_CREATEDB": str(tmp_path / "createdb"),
        "PARITY_DROPDB": str(tmp_path / "dropdb"),
        "PARITY_MIGRATIONS_DIR": str(mig),
        "PGDATABASE": "parity_exit_contract",
    }


def test_runner_passes_when_every_migration_applies(tmp_path):
    """The control for the two tests below. Without it, a stub that can only
    fail would make both of them pass for the wrong reason."""
    for args in ([], ["--continue-on-error"]):
        proc = _run_runner(
            [*args, "--json-out", str(tmp_path / "ok.json")], _stub_env(tmp_path, False)
        )
        assert proc.returncode == 0, proc.stdout + proc.stderr
        assert "SELF-HOST MIGRATIONS CHECK: PASS (1/1 applied)" in proc.stdout, proc.stdout


def test_continue_on_error_reports_a_gap_as_data_not_as_a_verdict(tmp_path):
    """PR #5351, both jobs red: this step exited 1 on a gap that the judge
    (`--mode migrations`) calls known, so a step that MEASURES and a step that
    JUDGES disagreed and the job went red. With --continue-on-error the chain is
    a measurement: exit 0, gaps reported, the judge decides."""
    proc = _run_runner(
        ["--continue-on-error", "--json-out", str(tmp_path / "m.json")], _stub_env(tmp_path, True)
    )
    assert proc.returncode == 0, proc.stdout + proc.stderr
    assert (
        "SELF-HOST MIGRATIONS CHECK: MEASURED (1/2 applied, 1 known-gap candidate(s))"
        in proc.stdout
    )
    assert "does not exist" in proc.stdout, proc.stdout
    assert (
        json.loads((tmp_path / "m.json").read_text())["failures"][0]["migration"] == "002_bad.sql"
    )


def test_without_continue_on_error_a_failing_migration_still_fails(tmp_path):
    proc = _run_runner([], _stub_env(tmp_path, True))
    assert proc.returncode != 0, proc.stdout
    assert "did not apply" in proc.stderr, proc.stderr


def test_the_contract_step_cannot_die_before_it_captures_the_exit_code():
    """GitHub runs every `run:` block under `bash -e {0}`. A bare `cmd; rc=$?`
    is dead code there: `cmd` exiting 3 kills the step first, which is how the
    contract check printed NOT RUN and still went red on PR #5351. Only a
    command on the left of `||` is exempt from errexit."""
    import yaml

    wf = yaml.safe_load((REPO_ROOT / ".github" / "workflows" / "self-host-parity.yml").read_text())
    steps = wf["jobs"]["drift"]["steps"]
    contract = next(s for s in steps if s.get("name", "").startswith("contract lint"))
    body = contract["run"]
    assert "|| rc=$?" in body, body
    bare = [ln for ln in body.splitlines() if ln.strip() == "rc=$?"]
    assert bare == [], f"a bare `rc=$?` is unreachable under `bash -e`: {body}"


def test_runner_help_documents_the_exclusions():
    proc = _run_runner(["--help"])
    assert proc.returncode == 0
    assert "cutover" in proc.stdout
    assert "parity_" in proc.stdout
