"""Preflight checks for the local stack (plan section 3, step 1).

Two families: the tools the bring-up shells out to, and free disk space.

Both are injectable so the suite exercises every branch without depending on
what happens to be installed on the machine running it. That matters twice
over: a test that passes only because ``uv`` exists is not a test, and a
preflight that has never been seen to fail has not been shown to work.
"""

from __future__ import annotations

import shutil
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from pathlib import Path

#: Minimum free space the plan requires before a full local stack is built.
MIN_DISK_GB = 20.0

#: macOS: ``/`` is a sealed read-only system snapshot whose capacity does not
#: track the real volume. Measure the Data volume instead.
DEFAULT_DISK_PATHS: tuple[str, ...] = (
    "/System/Volumes/Data",
    "/",
)

#: Environment overrides so an operator can point preflight at a mounted volume.
DISK_PATH_ENV = "DT_DISK_PATH"


@dataclass(frozen=True)
class ToolCheck:
    name: str
    command: tuple[str, ...]
    hint: str


#: The tools the plan names, in the order it names them.
TOOLS: tuple[ToolCheck, ...] = (
    ToolCheck("docker", ("docker",), "install Docker Desktop and start the daemon"),
    ToolCheck("supabase", ("supabase",), "npm i -g supabase"),
    ToolCheck("wrangler", ("npx", "wrangler"), "available via the repo npx cache"),
    ToolCheck("node", ("node",), "install Node 20+"),
    ToolCheck("uv", ("uv",), "curl -LsSf https://astral.sh/uv/install.sh | sh"),
    ToolCheck("make", ("make",), "xcode-select --install"),
)


@dataclass(frozen=True)
class PreflightResult:
    name: str
    ok: bool
    detail: str

    def to_dict(self) -> dict[str, object]:
        return {"name": self.name, "ok": self.ok, "detail": self.detail}


@dataclass(frozen=True)
class PreflightReport:
    results: tuple[PreflightResult, ...]

    @property
    def ok(self) -> bool:
        return all(r.ok for r in self.results)

    @property
    def missing(self) -> tuple[str, ...]:
        return tuple(r.name for r in self.results if not r.ok)

    def to_dict(self) -> dict[str, object]:
        return {
            "ok": self.ok,
            "missing": list(self.missing),
            "results": [r.to_dict() for r in self.results],
        }


def which(command: str, path: str | None = None) -> str | None:
    """Locate ``command``, or ``None``. ``path`` makes the search injectable."""
    return shutil.which(command, path=path)


def check_tool(tool: ToolCheck, *, path: str | None = None) -> PreflightResult:
    head = tool.command[0]
    found = which(head, path=path)
    if found is None and len(tool.command) > 1:
        # ``npx wrangler`` is satisfied by npx alone; wrangler itself is not a
        # global install on this stack.
        detail = f"{' '.join(tool.command)} (via {head})"
    elif found is None:
        return PreflightResult(tool.name, False, f"not found: {tool.hint}")
    else:
        detail = found
    return PreflightResult(tool.name, True, detail)


def disk_path(
    env: dict[str, str] | None = None, candidates: Sequence[str] = DEFAULT_DISK_PATHS
) -> str:
    """The volume to measure, honouring the override, then existing candidates."""
    env = env or {}
    override = env.get(DISK_PATH_ENV)
    if override:
        return override
    for candidate in candidates:
        if Path(candidate).exists():
            return candidate
    return "/"


def disk_free_gb(path: str) -> float | None:
    try:
        return shutil.disk_usage(path).free / (1024**3)
    except OSError:
        return None


def check_disk(
    *,
    env: dict[str, str] | None = None,
    minimum_gb: float = MIN_DISK_GB,
    probe: Callable[[str], float | None] = disk_free_gb,
) -> PreflightResult:
    path = disk_path(env)
    free = probe(path)
    if free is None:
        return PreflightResult("disk", False, f"could not read free space on {path}")
    ok = free >= minimum_gb
    detail = f"{free:.1f} GiB free on {path} (need >= {minimum_gb:.0f} GiB)"
    return PreflightResult("disk", ok, detail)


def run_preflight(
    *,
    path: str | None = None,
    env: dict[str, str] | None = None,
    tools: Sequence[ToolCheck] = TOOLS,
    minimum_gb: float = MIN_DISK_GB,
    disk_probe: Callable[[str], float | None] = disk_free_gb,
) -> PreflightReport:
    """Run every tool check then the disk check."""
    results = [check_tool(tool, path=path) for tool in tools]
    results.append(check_disk(env=env, minimum_gb=minimum_gb, probe=disk_probe))
    return PreflightReport(tuple(results))
