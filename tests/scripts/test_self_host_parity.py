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
    on_disk = sorted(
        str(p.relative_to(REPO_ROOT))
        for p in REPO_ROOT.rglob("*.env.example")
        if "node_modules" not in p.parts
    )
    missing = sorted(set(on_disk) - set(parity.ENV_EXAMPLE_FILES))
    assert not missing, f".env.example files not covered by the parity check: {missing}"


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


def test_runner_help_documents_the_exclusions():
    proc = _run_runner(["--help"])
    assert proc.returncode == 0
    assert "cutover" in proc.stdout
    assert "parity_" in proc.stdout
