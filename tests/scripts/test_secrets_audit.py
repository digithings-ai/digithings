"""Unit tests for scripts/secrets_audit.py (#4335, #4338, DIG-4717)."""

from __future__ import annotations

import importlib.util
import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

_REPO_ROOT = Path(__file__).resolve().parents[2]
_SCRIPT = _REPO_ROOT / "scripts" / "secrets_audit.py"


def _load() -> object:
    spec = importlib.util.spec_from_file_location("secrets_audit", _SCRIPT)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.fixture(scope="module")
def audit() -> object:
    return _load()


@pytest.mark.unit
def test_extract_secret_reads_dedupes_and_scans_all_github_yaml(
    audit: object, tmp_path: Path
) -> None:
    workflows = tmp_path / ".github" / "workflows"
    workflows.mkdir(parents=True)
    (workflows / "a.yml").write_text(
        "env:\n"
        "  A: ${{ secrets.FRED_API_KEY }}\n"
        "  B: ${{ secrets.CORE_SUPABASE_URL }}\n"
        "  C: ${{ secrets.FRED_API_KEY }}\n"
        "jobs:\n"
        "  x:\n"
        "    secrets: inherit\n"
        "    steps: []\n",
        encoding="utf-8",
    )
    (tmp_path / ".github" / "pipeline.yml").write_text(
        "env:\n  D: ${{ secrets.CORE_SUPABASE_URL }}\n  E: ${{ github.token }}\n",
        encoding="utf-8",
    )
    (tmp_path / "not-github").mkdir()
    (tmp_path / "not-github" / "c.yml").write_text(
        "env:\n  F: ${{ secrets.SHOULD_NOT_BE_SEEN }}\n", encoding="utf-8"
    )

    assert audit.extract_secret_reads(tmp_path) == {
        ".github/pipeline.yml": {"CORE_SUPABASE_URL"},
        ".github/workflows/a.yml": {"FRED_API_KEY", "CORE_SUPABASE_URL"},
    }


@pytest.mark.unit
def test_classify_splits_dead_from_unmanaged_and_drops_implicit(audit: object) -> None:
    report = audit.classify(
        {".github/workflows/a.yml": {"A", "B", "C", "GITHUB_TOKEN"}}, {"A", "B", "D"}
    )

    assert report.dead == {"D"}
    assert report.unmanaged == {"C"}
    assert report.reads == {"A", "B", "C"}


@pytest.mark.unit
def test_cli_strict_exits_nonzero_only_for_dead_secrets(tmp_path: Path) -> None:
    workflows = tmp_path / ".github" / "workflows"
    workflows.mkdir(parents=True)
    (workflows / "a.yml").write_text(
        "env:\n  A: ${{ secrets.USED_ONE }}\n  B: ${{ secrets.MISSING_ONE }}\n",
        encoding="utf-8",
    )
    names = tmp_path / "names.txt"
    names.write_text("USED_ONE\nDEAD_ONE\n", encoding="utf-8")

    plain = subprocess.run(
        [sys.executable, str(_SCRIPT), "--root", str(tmp_path), "--secrets-file", str(names)],
        capture_output=True,
        text=True,
        check=False,
    )
    assert plain.returncode == 0, plain.stderr
    assert "DEAD_ONE" in plain.stdout
    assert "MISSING_ONE" in plain.stdout

    strict = subprocess.run(
        [
            sys.executable,
            str(_SCRIPT),
            "--root",
            str(tmp_path),
            "--secrets-file",
            str(names),
            "--strict",
        ],
        capture_output=True,
        text=True,
        check=False,
    )
    assert strict.returncode == 1
    assert "DEAD_ONE" in strict.stderr


@pytest.mark.unit
def test_cli_clean_tree_reports_no_drift(tmp_path: Path) -> None:
    workflows = tmp_path / ".github" / "workflows"
    workflows.mkdir(parents=True)
    (workflows / "a.yml").write_text("env:\n  A: ${{ secrets.ONLY_ONE }}\n", encoding="utf-8")
    names = tmp_path / "names.txt"
    names.write_text("ONLY_ONE\n", encoding="utf-8")

    result = subprocess.run(
        [sys.executable, str(_SCRIPT), "--root", str(tmp_path), "--secrets-file", str(names)],
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 0, result.stderr
    assert "dead: none" in result.stdout
    assert "not repo-level: none" in result.stdout


@pytest.mark.unit
def test_reads_ignore_commented_out_names(audit: object, tmp_path: Path) -> None:
    workflows = tmp_path / ".github" / "workflows"
    workflows.mkdir(parents=True)
    (workflows / "a.yml").write_text(
        "env:\n"
        "  # A: ${{ secrets.COMMENTED_OUT }}\n"
        "  B: ${{ secrets.LIVE_ONE }}  # was ${{ secrets.TRAILING_COMMENT }}\n"
        "  C: secrets.BARE_NOT_AN_EXPRESSION\n",
        encoding="utf-8",
    )

    assert audit.reads_in((workflows / "a.yml").read_text(encoding="utf-8")) == {"LIVE_ONE"}


@pytest.mark.unit
def test_cli_strict_ignores_unmanaged_reads(tmp_path: Path) -> None:
    workflows = tmp_path / ".github" / "workflows"
    workflows.mkdir(parents=True)
    (workflows / "a.yml").write_text(
        "env:\n  A: ${{ secrets.ONLY_ONE }}\n  B: ${{ secrets.MISSING_ONE }}\n",
        encoding="utf-8",
    )
    names = tmp_path / "names.txt"
    names.write_text("ONLY_ONE\n", encoding="utf-8")

    strict = subprocess.run(
        [
            sys.executable,
            str(_SCRIPT),
            "--root",
            str(tmp_path),
            "--secrets-file",
            str(names),
            "--strict",
        ],
        capture_output=True,
        text=True,
        check=False,
    )

    assert strict.returncode == 0, strict.stderr
    assert "MISSING_ONE" in strict.stdout


@pytest.mark.unit
def test_cli_strict_fails_when_secret_list_unavailable(tmp_path: Path) -> None:
    workflows = tmp_path / ".github" / "workflows"
    workflows.mkdir(parents=True)
    (workflows / "a.yml").write_text("env:\n  A: ${{ secrets.ONLY_ONE }}\n", encoding="utf-8")
    no_path = {**os.environ, "PATH": ""}

    plain = subprocess.run(
        [sys.executable, str(_SCRIPT), "--root", str(tmp_path)],
        capture_output=True,
        text=True,
        check=False,
        env=no_path,
    )
    assert plain.returncode == 0, plain.stderr
    assert "repo secret list unavailable" in plain.stdout

    strict = subprocess.run(
        [sys.executable, str(_SCRIPT), "--root", str(tmp_path), "--strict"],
        capture_output=True,
        text=True,
        check=False,
        env=no_path,
    )
    assert strict.returncode == 1
    assert "repo secret list unavailable" in strict.stdout


def _level_fixture(tmp_path: Path, reads: list[str]) -> dict[str, Path]:
    """A tree whose reads are `reads`, plus one file per level to hand to the CLI."""
    workflows = tmp_path / ".github" / "workflows"
    workflows.mkdir(parents=True)
    body = "".join(f"  {name}: ${{{{ secrets.{name} }}}}\n" for name in reads)
    (workflows / "a.yml").write_text(f"env:\n{body}", encoding="utf-8")

    files = {
        "secrets": tmp_path / "secrets.txt",
        "variables": tmp_path / "variables.txt",
        "org": tmp_path / "org.txt",
        "env": tmp_path / "env.txt",
    }
    files["secrets"].write_text("REPO_ONLY\nDUPLICATED\n", encoding="utf-8")
    files["variables"].write_text("VAR_BACKED\n", encoding="utf-8")
    files["org"].write_text("ORG_BACKED\nDUPLICATED\n", encoding="utf-8")
    files["env"].write_text("production:ENV_BACKED\n", encoding="utf-8")
    return files


def _run_levels(files: dict[str, Path], tmp_path: Path, *extra: str) -> subprocess.CompletedProcess:
    return subprocess.run(
        [
            sys.executable,
            str(_SCRIPT),
            "--root",
            str(tmp_path),
            "--secrets-file",
            str(files["secrets"]),
            "--variables-file",
            str(files["variables"]),
            "--org-secrets-file",
            str(files["org"]),
            "--env-secrets-file",
            str(files["env"]),
            *extra,
        ],
        capture_output=True,
        text=True,
        check=False,
    )


@pytest.mark.unit
def test_classify_levels_splits_explained_unresolved_and_shadowed(audit: object) -> None:
    surface = audit.Surface(
        repo_secrets={"REPO_ONLY", "DUPLICATED", "ENV_AND_REPO"},
        repo_variables={"VAR_BACKED"},
        org_secrets={"ORG_BACKED", "DUPLICATED"},
        environment_secrets={"production": {"ENV_BACKED", "ENV_AND_REPO"}},
    )

    levels = audit.classify_levels(
        {
            "REPO_ONLY",
            "VAR_BACKED",
            "ORG_BACKED",
            "ENV_BACKED",
            "DUPLICATED",
            "ENV_AND_REPO",
            "PHANTOM",
        },
        surface,
    )

    assert surface.complete is True
    assert levels.explained == {"VAR_BACKED", "ORG_BACKED", "ENV_BACKED"}
    assert levels.unresolved == {"PHANTOM"}
    assert levels.shadowed == {"DUPLICATED"}
    assert levels.env_over_repo == {"ENV_AND_REPO"}


@pytest.mark.unit
def test_surface_incomplete_until_every_level_is_known(audit: object) -> None:
    assert audit.Surface(repo_secrets={"A"}).complete is False
    assert audit.Surface(repo_secrets={"A"}, repo_variables=set()).complete is False
    assert (
        audit.Surface(
            repo_secrets={"A"}, repo_variables=set(), environment_secrets={}, org_secrets=set()
        ).complete
        is True
    )


@pytest.mark.unit
def test_cli_reports_levels_from_files(tmp_path: Path) -> None:
    files = _level_fixture(
        tmp_path, ["REPO_ONLY", "DUPLICATED", "VAR_BACKED", "ORG_BACKED", "ENV_BACKED", "PHANTOM"]
    )

    result = _run_levels(files, tmp_path)

    assert result.returncode == 0, result.stderr
    assert "levels: 1 repo variables, 2 org secrets, 1 environments" in result.stdout
    assert "dead: none" in result.stdout
    assert "unresolved: PHANTOM" in result.stdout
    assert "repo-over-org: DUPLICATED" in result.stdout
    assert "not repo-level: ENV_BACKED, ORG_BACKED, VAR_BACKED" in result.stdout


@pytest.mark.unit
def test_cli_strict_unresolved_needs_every_level_and_fails_on_phantom(tmp_path: Path) -> None:
    files = _level_fixture(tmp_path, ["REPO_ONLY", "PHANTOM"])

    phantom = _run_levels(files, tmp_path, "--strict-unresolved")
    assert phantom.returncode == 1
    assert "PHANTOM" in phantom.stderr

    files["org"].write_text("ORG_BACKED\nDUPLICATED\nPHANTOM\n", encoding="utf-8")
    explained = _run_levels(files, tmp_path, "--strict-unresolved")
    assert explained.returncode == 0, explained.stderr

    offline = subprocess.run(
        [
            sys.executable,
            str(_SCRIPT),
            "--root",
            str(tmp_path),
            "--secrets-file",
            str(files["secrets"]),
            "--strict-unresolved",
        ],
        capture_output=True,
        text=True,
        check=False,
    )
    assert offline.returncode == 1
    assert "needs every level" in offline.stderr


@pytest.mark.unit
def test_cli_reports_env_over_repo_shadowing(tmp_path: Path) -> None:
    files = _level_fixture(tmp_path, ["REPO_ONLY", "ENV_AND_REPO"])
    files["secrets"].write_text("REPO_ONLY\nENV_AND_REPO\n", encoding="utf-8")
    files["env"].write_text("production:ENV_BACKED\nproduction:ENV_AND_REPO\n", encoding="utf-8")

    result = _run_levels(files, tmp_path)

    assert result.returncode == 0, result.stderr
    assert "env-over-repo: ENV_AND_REPO" in result.stdout


@pytest.mark.unit
def test_cli_strict_flags_fail_when_repo_list_is_unavailable(tmp_path: Path) -> None:
    _level_fixture(tmp_path, ["REPO_ONLY"])
    no_path = {"PATH": ""}

    for flag in ("--strict", "--strict-unresolved"):
        result = subprocess.run(
            [sys.executable, str(_SCRIPT), "--root", str(tmp_path), flag],
            capture_output=True,
            text=True,
            check=False,
            env=no_path,
        )
        assert result.returncode == 1, f"{flag} passed without a repo secret list"
        assert "could not provide it" in result.stderr

    plain = subprocess.run(
        [sys.executable, str(_SCRIPT), "--root", str(tmp_path)],
        capture_output=True,
        text=True,
        check=False,
        env=no_path,
    )
    assert plain.returncode == 0, plain.stderr
    assert "repo secret list unavailable" in plain.stdout


# --- DIG-4717: the committed names-only manifest ----------------------------
#
# The manifest exists because the live listings cannot be read from a workflow:
# `GET repos/{owner}/{repo}/actions/secrets` and the org and environment
# equivalents need the `repo` scope, and a workflow's GITHUB_TOKEN is an App
# installation token whose `permissions:` vocabulary has no key for secrets.
# Run 37235973852 (#5063) proved `actions: read` does not change that. So CI
# reads a committed manifest of NAMES, and an operator refreshes it.

_COMMITTED_MANIFEST = _REPO_ROOT / ".github" / "secret-names.json"


def _acceptance(audit: object, name: str, *workflows: str) -> object:
    """One accepted-missing entry, as the manifest would carry it."""
    return audit.Acceptance(
        name=name,
        workflows=tuple(workflows),
        reason="the credential is a different one from the same-named secret elsewhere",
        owner="chris",
        since="2026-10-20",
        review_by="2026-11-03",
    )


def _write_manifest(
    audit: object,
    path: Path,
    *,
    repo_secrets: set[str],
    repo_variables: set[str] | None = set(),
    org_secrets: set[str] | None = set(),
    environments: dict[str, set[str]] | None = None,
    accepted: dict[str, object] | None = None,
    generated_at: str = "2026-10-20T12:00:00Z",
) -> None:
    """A manifest on disk, written the way the script writes one."""
    surface = audit.Surface(
        repo_secrets=repo_secrets,
        repo_variables=repo_variables,
        org_secrets=org_secrets,
        environment_secrets=environments,
    )
    audit.write_manifest(
        path,
        audit.manifest_payload(
            surface,
            generated_at=generated_at,
            org="digithings-ai",
            repo="digithings-ai/digithings",
            accepted=accepted or {},
        ),
    )


def _workflow(root: Path, name: str, body: str) -> None:
    workflows = root / ".github" / "workflows"
    workflows.mkdir(parents=True, exist_ok=True)
    (workflows / name).write_text(body, encoding="utf-8")


def _keys(payload: object) -> set[str]:
    """Every key name anywhere in a JSON document."""
    found: set[str] = set()
    if isinstance(payload, dict):
        for key, value in payload.items():
            found.add(str(key))
            found |= _keys(value)
    elif isinstance(payload, list):
        for item in payload:
            found |= _keys(item)
    return found


@pytest.mark.unit
def test_manifest_round_trips_every_level(audit: object, tmp_path: Path) -> None:
    path = tmp_path / "secret-names.json"
    _write_manifest(
        audit,
        path,
        repo_secrets={"A"},
        repo_variables={"V"},
        org_secrets={"O"},
        environments={"production": {"E"}},
    )

    manifest = audit.manifest_from_file(path)

    assert manifest.surface.repo_secrets == {"A"}
    assert manifest.surface.repo_variables == {"V"}
    assert manifest.surface.org_secrets == {"O"}
    assert manifest.surface.environment_secrets == {"production": {"E"}}
    assert manifest.surface.complete is True
    assert manifest.accepted == {}


@pytest.mark.unit
def test_manifest_carries_names_and_never_values(audit: object, tmp_path: Path) -> None:
    """A committed file of names adds no exposure, and that has to stay true."""
    path = tmp_path / "secret-names.json"
    _write_manifest(audit, path, repo_secrets={"A"}, environments={})

    raw = json.loads(path.read_text(encoding="utf-8"))

    assert set(raw["levels"]["repo_secrets"]) == {"read", "names"}
    assert set(raw["levels"]["environments"]) == {"read", "environments"}
    assert raw["levels"]["repo_secrets"]["names"] == ["A"]
    assert "value" not in _keys(raw), "a value key would mean a secret value in the file"


@pytest.mark.unit
def test_manifest_records_an_unlistable_level_as_unknown(audit: object, tmp_path: Path) -> None:
    """`read: false` must not collapse into "there is nothing at that level"."""
    path = tmp_path / "secret-names.json"
    _write_manifest(audit, path, repo_secrets={"A"}, environments={})
    payload = json.loads(path.read_text(encoding="utf-8"))
    payload["levels"]["org_secrets"] = {"read": False}
    path.write_text(json.dumps(payload), encoding="utf-8")

    manifest = audit.manifest_from_file(path)

    assert manifest.surface.org_secrets is None
    assert manifest.surface.complete is False
    assert audit.unread_levels(manifest.surface) == ["org secrets"]


@pytest.mark.unit
def test_manifest_refuses_a_shape_it_does_not_know(audit: object, tmp_path: Path) -> None:
    path = tmp_path / "secret-names.json"
    _write_manifest(audit, path, repo_secrets={"A"})
    payload = json.loads(path.read_text(encoding="utf-8"))
    payload["schema_version"] = 99
    path.write_text(json.dumps(payload), encoding="utf-8")

    with pytest.raises(audit.ManifestError):
        audit.manifest_from_file(path)


@pytest.mark.unit
def test_manifest_refuses_a_malformed_acceptance(audit: object, tmp_path: Path) -> None:
    """An exemption that cannot be read must not quietly become a passing check."""
    path = tmp_path / "secret-names.json"
    _write_manifest(audit, path, repo_secrets={"A"})
    payload = json.loads(path.read_text(encoding="utf-8"))
    payload["accepted_missing"] = {"A": {"workflows": [], "reason": "x", "owner": "chris"}}
    path.write_text(json.dumps(payload), encoding="utf-8")

    with pytest.raises(audit.ManifestError):
        audit.manifest_from_file(path)


@pytest.mark.unit
def test_cli_manifest_fails_on_a_name_no_level_defines(audit: object, tmp_path: Path) -> None:
    _workflow(tmp_path, "a.yml", "env:\n  A: ${{ secrets.MISSING_ONE }}\n")
    manifest = tmp_path / "secret-names.json"
    _write_manifest(audit, manifest, repo_secrets={"OTHER"}, environments={})

    result = subprocess.run(
        [
            sys.executable,
            str(_SCRIPT),
            "--root",
            str(tmp_path),
            "--manifest",
            str(manifest),
            "--strict-unresolved",
        ],
        capture_output=True,
        text=True,
        check=False,
    )

    assert result.returncode == 1
    assert "MISSING_ONE" in result.stderr
    assert ".github/workflows/a.yml" in result.stderr


@pytest.mark.unit
def test_cli_manifest_reads_no_live_api(audit: object, tmp_path: Path) -> None:
    """The manifest is what makes the check runnable from CI, so prove it runs offline."""
    _workflow(tmp_path, "a.yml", "env:\n  A: ${{ secrets.ONLY_ONE }}\n")
    manifest = tmp_path / "secret-names.json"
    _write_manifest(audit, manifest, repo_secrets={"ONLY_ONE"}, environments={})

    result = subprocess.run(
        [
            sys.executable,
            str(_SCRIPT),
            "--root",
            str(tmp_path),
            "--manifest",
            str(manifest),
            "--strict-unresolved",
        ],
        capture_output=True,
        text=True,
        check=False,
        env={"PATH": ""},
    )

    assert result.returncode == 0, result.stderr
    assert "repo secret list unavailable" not in result.stdout
    assert "unresolved: none" in result.stdout


@pytest.mark.unit
def test_cli_an_acceptance_covers_only_the_workflows_it_names(
    audit: object, tmp_path: Path
) -> None:
    """The same name read by another workflow is no longer covered."""
    _workflow(tmp_path, "allowed.yml", "env:\n  A: ${{ secrets.TOLERATED }}\n")
    manifest = tmp_path / "secret-names.json"
    accepted = {"TOLERATED": _acceptance(audit, "TOLERATED", ".github/workflows/allowed.yml")}
    _write_manifest(audit, manifest, repo_secrets=set(), environments={}, accepted=accepted)

    tolerated = subprocess.run(
        [
            sys.executable,
            str(_SCRIPT),
            "--root",
            str(tmp_path),
            "--manifest",
            str(manifest),
            "--strict-unresolved",
        ],
        capture_output=True,
        text=True,
        check=False,
    )
    assert tolerated.returncode == 0, tolerated.stderr
    assert "accepted-missing: TOLERATED" in tolerated.stdout
    assert "owner chris" in tolerated.stdout

    _workflow(tmp_path, "other.yml", "env:\n  B: ${{ secrets.TOLERATED }}\n")
    blocked = subprocess.run(
        [
            sys.executable,
            str(_SCRIPT),
            "--root",
            str(tmp_path),
            "--manifest",
            str(manifest),
            "--strict-unresolved",
        ],
        capture_output=True,
        text=True,
        check=False,
    )
    assert blocked.returncode == 1
    assert "TOLERATED" in blocked.stderr
    assert ".github/workflows/other.yml" in blocked.stderr


@pytest.mark.unit
def test_cli_strict_unresolved_fails_when_a_level_could_not_be_listed(
    audit: object, tmp_path: Path
) -> None:
    """A level nobody could read is not a level with nothing in it."""
    _workflow(tmp_path, "a.yml", "env:\n  A: ${{ secrets.ONLY_ONE }}\n")
    manifest = tmp_path / "secret-names.json"
    _write_manifest(audit, manifest, repo_secrets={"ONLY_ONE"}, environments={})
    payload = json.loads(manifest.read_text(encoding="utf-8"))
    payload["levels"]["org_secrets"] = {"read": False}
    manifest.write_text(json.dumps(payload), encoding="utf-8")

    result = subprocess.run(
        [
            sys.executable,
            str(_SCRIPT),
            "--root",
            str(tmp_path),
            "--manifest",
            str(manifest),
            "--strict-unresolved",
        ],
        capture_output=True,
        text=True,
        check=False,
    )

    assert result.returncode == 1
    assert "needs every level" in result.stderr
    assert "org secrets" in result.stderr


@pytest.mark.unit
def test_cli_reports_the_age_of_a_stale_manifest(audit: object, tmp_path: Path) -> None:
    _workflow(tmp_path, "a.yml", "env:\n  A: ${{ secrets.ONLY_ONE }}\n")
    manifest = tmp_path / "secret-names.json"
    _write_manifest(
        audit,
        manifest,
        repo_secrets={"ONLY_ONE"},
        environments={},
        generated_at="2020-01-01T00:00:00Z",
    )

    result = subprocess.run(
        [sys.executable, str(_SCRIPT), "--root", str(tmp_path), "--manifest", str(manifest)],
        capture_output=True,
        text=True,
        check=False,
    )

    assert result.returncode == 0, result.stderr
    assert "day(s) ago" in result.stdout
    assert "make secrets-audit-refresh" in result.stderr


@pytest.mark.unit
def test_write_manifest_keeps_the_acceptances_of_the_previous_file(
    audit: object, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A refresh replaces the facts, not somebody's dated decision."""
    _workflow(tmp_path, "a.yml", "env:\n  A: ${{ secrets.ONLY_ONE }}\n")
    manifest = tmp_path / "secret-names.json"
    _write_manifest(
        audit,
        manifest,
        repo_secrets={"ONLY_ONE"},
        environments={},
        accepted={"ONLY_ONE": _acceptance(audit, "ONLY_ONE")},
    )

    monkeypatch.setattr(audit, "repo_secret_names", lambda root, secrets_file: {"ONLY_ONE"})
    monkeypatch.setattr(audit, "repo_variable_names", lambda root: set())
    monkeypatch.setattr(audit, "org_secret_names", lambda org, root: set())
    monkeypatch.setattr(audit, "repo_slug", lambda root: "digithings-ai/digithings")
    monkeypatch.setattr(audit, "environment_secret_names", lambda root, repo: {})

    assert audit.main(["--root", str(tmp_path), "--write-manifest", str(manifest)]) == 0

    refreshed = audit.manifest_from_file(manifest)
    assert "ONLY_ONE" in refreshed.accepted
    assert refreshed.accepted["ONLY_ONE"].owner == "chris"


@pytest.mark.unit
def test_the_committed_manifest_names_every_level(audit: object) -> None:
    """The committed manifest is what CI checks against, so it has to be complete."""
    manifest = audit.manifest_from_file(_COMMITTED_MANIFEST)

    assert manifest.surface.complete is True, (
        "a level the manifest could not list makes the check refuse to claim it looked "
        "at everything, and the CI gate then fails on every read it cannot place"
    )
    assert manifest.surface.repo_secrets
    assert manifest.surface.org_secrets is not None
    for name, entry in manifest.accepted.items():
        assert entry.reason, name
        assert entry.owner, name
        assert entry.review_by, name


@pytest.mark.unit
def test_the_committed_manifest_passes_its_own_gate(audit: object) -> None:
    """The CI lane runs exactly this command, so run it here."""
    result = subprocess.run(
        [
            sys.executable,
            str(_SCRIPT),
            "--manifest",
            str(_COMMITTED_MANIFEST),
            "--strict-unresolved",
        ],
        capture_output=True,
        text=True,
        check=False,
    )

    assert result.returncode == 0, result.stderr


@pytest.mark.unit
def test_every_acceptance_still_describes_a_real_gap(audit: object) -> None:
    """An acceptance is a promise that a gap is still open. Two ways that stops being true.

    The secret gets created — then the name resolves at a level, and the acceptance
    hides a name that needs no hiding any more, so the entry has to go. Or the
    workflow stops reading the name — then the acceptance covers nothing at all.

    Both are checked against the committed manifest, which is the same source the
    gate reads, so refreshing the manifest after the secret is minted fails here
    and forces the entry to be removed rather than lingering as a silent hole.
    """
    manifest = audit.manifest_from_file(_COMMITTED_MANIFEST)
    reads = audit.extract_secret_reads(_REPO_ROOT)

    assert manifest.accepted, (
        "the committed manifest carries no acceptance. Either the gap is closed — "
        "refresh the manifest so the name lands at a level — or the acceptance was "
        "dropped before the gap was actually closed"
    )

    for name, acceptance in manifest.accepted.items():
        defined = manifest.surface.levels_of(name)
        assert not defined, (
            f"{name} is accepted as missing, but the manifest defines it at {defined}. "
            "Either the secret now exists — drop the acceptance and run "
            "`make secrets-audit-refresh` — or the acceptance is wrong"
        )
        assert acceptance.workflows, (
            f"{name} is accepted as missing without naming a workflow, so it would "
            "tolerate the name in every workflow that reads it. Name the workflows"
        )
        readers = [
            path for path in acceptance.workflows if name in reads.get(path, set())
        ]
        assert readers, (
            f"{name} is accepted as missing, but no workflow it names reads it any "
            f"more: {list(acceptance.workflows)}. Drop the acceptance"
        )
        assert acceptance.reason.strip(), name
        assert acceptance.owner.strip(), name
        assert acceptance.since.strip(), name
        assert acceptance.review_by.strip(), name
