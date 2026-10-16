"""Acceptance tests for the agent-runtime projects path guard (DIG-1302).

The guard lives in ``.opencode/plugins/projects-path-guard.js`` and is the
compensating control the CTO approved on DIG-785: reads under ``projects/`` are
default-denied except ``projects/README.md`` and the one engagement subtree bound
to the run.

These tests drive the shipped JavaScript through ``runner_projects_path_guard.mjs``
rather than re-implementing the rules in Python. A Python mirror would be a
second implementation that passes while the real guard is broken — the exact
"tests that pass on stub code" failure mode. pytest owns the assertions so the
suite runs in CI under ``pytest -m unit`` with no npm install.

Every test builds its own repo fixture with real directories and a real symlink,
so the normalisation under test (``..``, absolute paths, symlinks) is exercised
against the filesystem rather than against string manipulation.
"""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import tempfile
from pathlib import Path

import pytest

pytestmark = pytest.mark.unit

REPO_ROOT = Path(__file__).resolve().parents[2]
RUNNER = REPO_ROOT / "tests" / "scripts" / "runner_projects_path_guard.mjs"
MAPPING = {"version": 1, "engagements": {"alpha": {"dir": "alpha"}, "beta": {"dir": "beta"}}}


def _run(
    repo: Path,
    *,
    tool: str,
    args: dict,
    engagement: str | None = "alpha",
    mapping=...,  # type: ignore[assignment]
    cwd: Path | None = None,
) -> dict:
    """Evaluate one tool call against the guard and return its verdict."""
    if mapping is ...:
        mapping = MAPPING
    env = {"DIGI_ENGAGEMENT": engagement} if engagement else {}
    job = {
        "repoRoot": str(repo),
        "cwd": str(cwd or repo),
        "env": env,
        "mapping": mapping,
        "tool": tool,
        "args": args,
    }
    proc = subprocess.run(
        ["node", str(RUNNER)],
        input=json.dumps(job),
        capture_output=True,
        text=True,
        timeout=60,
    )
    assert proc.returncode == 0, f"runner failed: {proc.stderr}"
    return json.loads(proc.stdout)


@pytest.fixture()
def repo():
    """A repo holding two engagements' client data and a cross-engagement symlink."""
    root = Path(tempfile.mkdtemp(prefix="projects-guard.")).resolve()
    projects = root / "projects"
    (projects / "alpha" / "vault").mkdir(parents=True)
    (projects / "beta" / "vault").mkdir(parents=True)
    (projects / "README.md").write_text("not client data\n")
    (projects / "alpha" / "vault" / "brief.md").write_text("alpha brief\n")
    (projects / "beta" / "vault" / "brief.md").write_text("beta brief\n")
    # The symlink the issue calls out by name: a path that looks like it is
    # inside alpha, and resolves into beta.
    os.symlink(projects / "beta", projects / "alpha" / "into-beta")
    yield root
    shutil.rmtree(root, ignore_errors=True)


# --- allowlist: bound engagement and README are readable ------------------------


def test_bound_engagement_is_readable(repo):
    verdict = _run(repo, tool="read", args={"filePath": "projects/alpha/vault/brief.md"})
    assert verdict["decision"] == "allow", verdict


def test_projects_readme_is_always_readable(repo):
    """README.md is tracked in git and deliberately un-ignored — not client data."""
    verdict = _run(repo, tool="read", args={"filePath": "projects/README.md"})
    assert verdict["decision"] == "allow", verdict


def test_projects_readme_allowed_without_engagement(repo):
    verdict = _run(repo, tool="read", args={"filePath": "projects/README.md"}, engagement=None)
    assert verdict["decision"] == "allow", verdict


# --- default-deny: another engagement is refused -------------------------------


def test_other_engagement_is_denied(repo):
    verdict = _run(repo, tool="read", args={"filePath": "projects/beta/vault/brief.md"})
    assert verdict["decision"] == "deny", verdict
    assert verdict["reason"] == "outside_bound_engagement", verdict


def test_projects_root_itself_is_denied(repo):
    """A bare `projects` argument would enumerate every engagement."""
    verdict = _run(repo, tool="bash", args={"command": "ls projects"})
    assert verdict["decision"] == "deny", verdict


def test_unbound_engagement_dir_is_denied(repo):
    """An engagement with no mapping entry resolves to no allowlist at all."""
    verdict = _run(repo, tool="read", args={"filePath": "projects/alpha/vault/brief.md"}, engagement="gamma")
    assert verdict["decision"] == "deny", verdict
    assert verdict["mappingError"] == "mapping_no_entry", verdict


def test_missing_mapping_file_is_denied(repo):
    """Fail closed: an unreadable mapping is not an allow."""
    verdict = _run(repo, tool="read", args={"filePath": "projects/alpha/vault/brief.md"}, mapping=None)
    assert verdict["decision"] == "deny", verdict
    # The error carries the OS code, which is what tells an operator the mapping
    # file is missing rather than malformed.
    assert verdict["mappingError"].startswith("mapping_unreadable"), verdict


def test_malformed_mapping_is_denied(repo):
    verdict = _run(repo, tool="read", args={"filePath": "projects/alpha/vault/brief.md"}, mapping="{not json")
    assert verdict["decision"] == "deny", verdict


def test_mapping_with_traversal_in_dir_is_denied(repo):
    """A mapping that smuggles `..` or a separator is refused, not honoured."""
    mapping = {"version": 1, "engagements": {"alpha": {"dir": "../beta"}}}
    verdict = _run(repo, tool="read", args={"filePath": "projects/beta/vault/brief.md"}, mapping=mapping)
    assert verdict["decision"] == "deny", verdict
    assert verdict["mappingError"] == "mapping_dir_invalid", verdict


def test_paths_outside_projects_are_untouched(repo):
    verdict = _run(repo, tool="read", args={"filePath": "digibase/src/digibase/audit.py"})
    assert verdict["decision"] == "allow", verdict
    assert verdict["reason"] == "outside_projects", verdict


# --- normalisation: the guard must match a real path, not the raw argument -----


def test_dotdot_traversal_into_other_engagement_is_denied(repo):
    """`projects/../projects/sitaas/` style traversal must not pass the string match."""
    verdict = _run(repo, tool="read", args={"filePath": "projects/alpha/../beta/vault/brief.md"})
    assert verdict["decision"] == "deny", verdict


def test_absolute_path_into_other_engagement_is_denied(repo):
    other = repo / "projects" / "beta" / "vault" / "brief.md"
    verdict = _run(repo, tool="read", args={"filePath": str(other)})
    assert verdict["decision"] == "deny", verdict


def test_symlink_into_other_engagement_is_denied(repo):
    """A symlink under alpha pointing at beta resolves before matching."""
    verdict = _run(repo, tool="read", args={"filePath": "projects/alpha/into-beta/vault/brief.md"})
    assert verdict["decision"] == "deny", verdict


def test_symlink_under_other_engagement_is_denied_from_alpha(repo):
    """Same link, resolved from the allowed side of the boundary."""
    verdict = _run(repo, tool="bash", args={"command": "cat projects/alpha/into-beta/vault/brief.md"})
    assert verdict["decision"] == "deny", verdict


def test_absolute_path_to_bound_engagement_is_allowed(repo):
    """Normalisation must not be so aggressive that the allowlist stops working."""
    mine = repo / "projects" / "alpha" / "vault" / "brief.md"
    verdict = _run(repo, tool="read", args={"filePath": str(mine)})
    assert verdict["decision"] == "allow", verdict


# --- coverage: every read path, not just the file-read tool --------------------


def test_grep_path_argument_is_denied(repo):
    verdict = _run(repo, tool="grep", args={"path": "projects/beta", "pattern": "brief"})
    assert verdict["decision"] == "deny", verdict


def test_glob_path_argument_is_denied(repo):
    verdict = _run(repo, tool="glob", args={"path": "projects/beta/**"})
    assert verdict["decision"] == "deny", verdict


def test_grep_without_path_from_repo_root_is_denied(repo):
    """No path argument means the cwd is walked — the repo root contains projects/."""
    verdict = _run(repo, tool="grep", args={"pattern": "brief"})
    assert verdict["decision"] == "deny", verdict


def test_grep_in_bound_engagement_is_allowed(repo):
    verdict = _run(repo, tool="grep", args={"path": "projects/alpha", "pattern": "brief"})
    assert verdict["decision"] == "allow", verdict


def test_shell_path_argument_is_denied(repo):
    verdict = _run(repo, tool="bash", args={"command": "grep -r secret projects/beta/vault"})
    assert verdict["decision"] == "deny", verdict


def test_shell_glob_over_projects_is_denied(repo):
    verdict = _run(repo, tool="bash", args={"command": "cat projects/*/vault/brief.md"})
    assert verdict["decision"] == "deny", verdict


def test_shell_quoted_traversal_is_denied(repo):
    """Quotes must not be a way to hide a path from the tokeniser."""
    verdict = _run(repo, tool="bash", args={"command": "cat 'projects/beta/vault/brief.md'"})
    assert verdict["decision"] == "deny", verdict


def test_shell_pipeline_to_other_engagement_is_denied(repo):
    verdict = _run(repo, tool="bash", args={"command": "echo hi | tee projects/beta/leak.txt"})
    assert verdict["decision"] == "deny", verdict


def test_shell_bound_engagement_is_allowed(repo):
    verdict = _run(repo, tool="bash", args={"command": "grep -r brief projects/alpha/vault"})
    assert verdict["decision"] == "allow", verdict


def test_shell_outside_projects_is_allowed(repo):
    verdict = _run(repo, tool="bash", args={"command": "ruff check digibase/src"})
    assert verdict["decision"] == "allow", verdict


# --- flag -----------------------------------------------------------------------


def test_flag_off_disables_the_guard(repo):
    """`DIGI_PROJECTS_PATH_GUARD=off` returns no hooks at all — no refusal."""
    node = subprocess.run(
        [
            "node",
            "--input-type=module",
            "-e",
            "const m = await import(process.argv[1]);"
            "const hooks = await m.ProjectsPathGuard({ directory: process.argv[2],"
            " worktree: process.argv[2], client: { app: { log: async () => {} } } });"
            "console.log(Object.keys(hooks).length);",
            (REPO_ROOT / ".opencode" / "plugins" / "projects-path-guard.js").as_uri(),
            str(repo),
        ],
        capture_output=True,
        text=True,
        env={**os.environ, "DIGI_PROJECTS_PATH_GUARD": "off"},
        timeout=60,
    )
    assert node.returncode == 0, node.stderr
    assert node.stdout.strip() == "0", "flag=off must register no tool hooks"


def test_unrecognised_flag_value_fails_closed():
    """An unrecognised flag value must enforce, not silently disable."""
    node = subprocess.run(
        [
            "node",
            "--input-type=module",
            "-e",
            "const m = await import(process.argv[1]); console.log(m.guardEnabled({ [m.FLAG_ENV]: process.argv[2] }));",
            (REPO_ROOT / ".opencode" / "plugins" / "projects-path-guard.js").as_uri(),
            "maybe",
        ],
        capture_output=True,
        text=True,
        timeout=60,
    )
    assert node.returncode == 0, node.stderr
    assert node.stdout.strip() == "true", node.stdout


# --- one engagement per run ------------------------------------------------------


def test_repo_binding_resolves_through_the_repo_mapping(repo):
    """The real config/engagement-paths.json resolves the twelve-x binding to twelve_x.

    This is the assertion that would fail if anyone derived the directory from the
    engagement name by transliteration instead of reading the mapping.
    """
    node = subprocess.run(
        [
            "node",
            "--input-type=module",
            "-e",
            "const m = await import(process.argv[1]);"
            "const g = m.createGuard({ env: { [m.ENGAGEMENT_ENV]: process.argv[2] },"
            " cwd: process.argv[3], repoRoot: process.argv[3],"
            " mappingPath: process.argv[4] });"
            "console.log(JSON.stringify(g.config()));",
            (REPO_ROOT / ".opencode" / "plugins" / "projects-path-guard.js").as_uri(),
            "twelve-x",
            str(repo),
            str(REPO_ROOT / "config" / "engagement-paths.json"),
        ],
        capture_output=True,
        text=True,
        timeout=60,
    )
    assert node.returncode == 0, node.stderr
    config = json.loads(node.stdout)
    # The engagement id is `twelve-x`; the directory is `twelve_x`. Only the
    # mapping can produce that, which is the point of the rule.
    assert config["engagement"] == "twelve-x"
    assert config["engagementDir"] == "twelve_x", config
    assert config["mappingError"] is None, config


def test_repo_mapping_entries_are_single_directory_names():
    """Every mapped directory is one segment under projects/, never a traversal.

    The guard refuses a mapping value that fails this, so a bad entry would
    fail closed and lock a legitimate engagement out. Caught here instead.
    """
    mapping = json.loads((REPO_ROOT / "config" / "engagement-paths.json").read_text())
    entries = mapping["engagements"]
    assert entries, "the mapping must not be empty"
    for engagement, entry in entries.items():
        directory = entry["dir"] if isinstance(entry, dict) else entry
        assert directory, f"{engagement} must map to a directory"
        assert "/" not in directory, f"{engagement} must map to a single directory name"
        assert directory not in (".", ".."), f"{engagement} must not map to a relative hop"
        assert not directory.startswith("."), f"{engagement} must not map to a dotfile"
    # The engagement id is a hyphenated codename. If the mapping were derived
    # from it by transliteration this key would be `twelve_x` instead.
    assert "twelve-x" in entries, "the engagement key is the id, not the directory"
    assert "twelve_x" not in entries, "the directory name is not an engagement id"
    assert entries["twelve-x"]["dir"] == "twelve_x"