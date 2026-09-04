"""Keep agents.yml test_cmd path selectors aligned with CI workflows (#1182).

Agent dispatch / task scripts read ``components[].test_cmd`` from agents.yml.
Those commands must select the same trees as ``.github/workflows/test-*.yml``
so a local ``make task`` run exercises the same suite as GitHub Actions.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest
import yaml

pytestmark = pytest.mark.unit

ROOT = Path(__file__).resolve().parents[2]

# Components with a dedicated workflow_call test lane in ci.yml.
WORKFLOW_BY_COMPONENT = {
    "digigraph": "test-digigraph.yml",
    "digiquant": "test-digiquant.yml",
    "digisearch": "test-digisearch.yml",
    "digismith": "test-digismith.yml",
    "digiclaw": "test-digiclaw.yml",
    "digibase": "test-digibase.yml",
    "digikey": "test-digikey.yml",
    "digichat": "test-digichat.yml",
}

# Flags / tokens that are not path selectors (CI may add cov; agents.yml may omit).
_PYTEST_FLAG_TOKENS = frozenset(
    {
        "pytest",
        "-m",
        "unit",
        "-v",
        "--tb=short",
        "--cov=digigraph",
        "--cov-report=term-missing",
        "uv",
        "run",
        "--frozen",
        "--no-sync",
    }
)


def _load_agents_components() -> dict[str, str]:
    data = yaml.safe_load((ROOT / "agents.yml").read_text(encoding="utf-8"))
    out: dict[str, str] = {}
    for comp in data.get("components") or []:
        name = comp.get("name")
        cmd = comp.get("test_cmd")
        if name and cmd:
            out[str(name)] = str(cmd)
    return out


def _pytest_path_args(cmd: str) -> list[str]:
    """Return path-like argv tokens from a pytest (or npm) test_cmd string."""
    # Collapse YAML multi-line / shell line continuations into one argv stream.
    flat = re.sub(r"\\\s*\n", " ", cmd)
    tokens = flat.split()
    paths: list[str] = []
    skip_next = False
    for tok in tokens:
        if skip_next:
            skip_next = False
            continue
        if tok in {"-m", "--tb", "--cov", "--cov-report", "-k"}:
            skip_next = True
            continue
        if tok.startswith("-") or tok in _PYTEST_FLAG_TOKENS:
            continue
        if tok.startswith("tests/") or tok.endswith(".py"):
            paths.append(tok.rstrip("/"))
    return paths


def _workflow_pytest_paths(workflow_name: str) -> list[str]:
    text = (ROOT / ".github" / "workflows" / workflow_name).read_text(encoding="utf-8")
    # Collect every ``pytest …`` run block (may span lines with ``|``).
    found: list[str] = []
    for match in re.finditer(
        r"(?ms)^[ \t]*run:[ \t]*(?:\|[ \t]*\n)?(.*?)(?=^[ \t]*(?:- name:|env:|uses:|\Z))",
        text,
    ):
        block = match.group(1)
        if "pytest" not in block and "npm run test" not in block:
            continue
        found.extend(_pytest_path_args(block))
    return found


class TestAgentsYmlTestCmds:
    def test_every_component_has_test_cmd(self) -> None:
        cmds = _load_agents_components()
        assert cmds, "agents.yml components missing"
        for name, cmd in cmds.items():
            assert cmd.strip(), f"{name} has empty test_cmd"

    def test_python_components_use_path_selectors_not_dash_k(self) -> None:
        cmds = _load_agents_components()
        for name, cmd in cmds.items():
            if cmd.startswith("npm "):
                continue
            assert " -k " not in f" {cmd} ", (
                f"{name} test_cmd still uses pytest -k (prefer path selectors like CI): {cmd}"
            )
            assert _pytest_path_args(cmd), f"{name} test_cmd has no path args: {cmd}"

    def test_workflow_components_match_ci_paths(self) -> None:
        cmds = _load_agents_components()
        for name, workflow in WORKFLOW_BY_COMPONENT.items():
            assert name in cmds, f"agents.yml missing component {name}"
            agent_cmd = cmds[name]
            if name == "digichat":
                assert "npm run test --workspace digichat" in agent_cmd
                wf = (ROOT / ".github" / "workflows" / workflow).read_text(encoding="utf-8")
                assert "npm run test --workspace digichat" in wf
                continue

            agent_paths = set(_pytest_path_args(agent_cmd))
            ci_paths = set(_workflow_pytest_paths(workflow))
            assert ci_paths, f"no pytest paths parsed from {workflow}"
            # Agent cmd may omit CI-only extras (cov) but must cover the same trees.
            missing = ci_paths - agent_paths
            assert not missing, (
                f"{name}: agents.yml paths {sorted(agent_paths)} missing CI paths "
                f"{sorted(missing)} from {workflow}"
            )

    def test_digiskills_points_at_tests_dsk(self) -> None:
        cmds = _load_agents_components()
        assert "digiskills" in cmds
        paths = _pytest_path_args(cmds["digiskills"])
        assert any(p.rstrip("/").endswith("tests/dsk") or p.startswith("tests/dsk") for p in paths)

    def test_ci_docs_runs_agents_init_not_gh_aw_compile(self) -> None:
        text = (ROOT / ".github" / "workflows" / "ci-docs.yml").read_text(encoding="utf-8")
        run_lines = [
            line
            for line in text.splitlines()
            if re.match(r"^[ \t]*run:", line) or (line.strip().startswith("uv run") and "python" in line)
        ]
        joined = "\n".join(run_lines)
        assert "gh aw" not in joined
        assert "agents_init.py --check" in text
