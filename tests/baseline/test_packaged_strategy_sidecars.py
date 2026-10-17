"""The strategy engine's calibrated sidecars must travel inside the wheel.

Every input the engine is calibrated against — presets, provenance ledgers,
coefficient fits, ``settings.json`` — lives next to the module that opens it and
is opened as ``Path(__file__).parent / "<name>"`` (or ``parents[1]`` for
``settings.json``). setuptools copies a package's ``.py`` files automatically
but **not** its data, so a directory that is missing from
``[tool.setuptools.package-data]`` is invisible in the source tree and absent
from an install. The failure is silent: the module imports cleanly because the
path constant is only a ``Path`` object, and raises ``FileNotFoundError`` on
first use — in a deployed service, never in CI.

This is not hypothetical. Before the ``digiquant.strategies`` entry existed the
built wheel carried all 38 ``strategies/lab`` modules and **zero** of their 16
JSON sidecars, while ``pytest`` was green because tests read the source tree.

Scope is deliberately ``digiquant/strategies/**``. Elsewhere under
``digiquant/src/digiquant`` there are data files that are *not* module-read —
reference docs, the Pine indicator catalogue, the D1 guard SQL — and which the
wheel does not ship. Pinning those here would assert a policy nobody has
decided; this test asserts only what a reader opens at runtime.
"""

from __future__ import annotations

import re
import tomllib
from pathlib import Path

import pytest

pytestmark = pytest.mark.baseline

REPO_ROOT = Path(__file__).resolve().parents[2]
PYPROJECT = REPO_ROOT / "digiquant" / "pyproject.toml"
SRC = REPO_ROOT / "digiquant" / "src"
STRATEGIES = SRC / "digiquant" / "strategies"

# Measured when the guard was added: 16 sidecars under lab/ + 2 at the package
# root. Asserted as a floor so a shrunken walk fails instead of passing empty.
MIN_SIDECARS = 18


def _package_data() -> dict[str, list[str]]:
    cfg = tomllib.loads(PYPROJECT.read_text())
    return cfg["tool"]["setuptools"]["package-data"]


def glob_covers(pattern: str, relpath: str) -> bool:
    """Whether a package-data pattern matches a path relative to its package.

    Mirrors setuptools/``glob`` semantics where it matters here: ``**/`` spans
    zero or more directories, ``*`` does not cross ``/``.
    """
    regex = re.escape(pattern)
    regex = regex.replace(r"\*\*/", r"(?:.*/)?")
    regex = regex.replace(r"\*\*", r".*")
    regex = regex.replace(r"\*", r"[^/]*")
    regex = regex.replace(r"\?", r"[^/]")
    return re.fullmatch(regex, relpath) is not None


def covering_package(path: Path, package_data: dict[str, list[str]]) -> str | None:
    """The package-data key that would ship ``path``, or ``None``."""
    for package, patterns in package_data.items():
        package_dir = SRC / package.replace(".", "/")
        try:
            relpath = path.relative_to(package_dir).as_posix()
        except ValueError:
            continue
        if any(glob_covers(pattern, relpath) for pattern in patterns):
            return package
    return None


def _sidecars() -> list[Path]:
    return sorted(
        p for p in STRATEGIES.rglob("*.json") if p.is_file() and "__pycache__" not in p.parts
    )


def test_the_walk_actually_finds_the_sidecars() -> None:
    """Non-vacuity: an empty or shrunken walk would make every check below pass."""
    sidecars = _sidecars()
    assert len(sidecars) >= MIN_SIDECARS, (
        f"expected at least {MIN_SIDECARS} JSON sidecars under {STRATEGIES}, "
        f"found {len(sidecars)}: {[p.name for p in sidecars]}"
    )
    assert any(p.parent.name == "lab" for p in sidecars), "no lab/ sidecar found"
    assert (STRATEGIES / "settings.json").is_file(), "settings.json is missing"


def test_every_strategy_sidecar_is_claimed_by_package_data() -> None:
    package_data = _package_data()
    uncovered = [
        p.relative_to(REPO_ROOT).as_posix()
        for p in _sidecars()
        if covering_package(p, package_data) is None
    ]
    assert not uncovered, (
        "these sidecars are read by a shipped module but no "
        "[tool.setuptools.package-data] entry would put them in the wheel; an "
        "installed digiquant would raise FileNotFoundError on first use:\n  "
        + "\n  ".join(uncovered)
    )


def test_the_matcher_discriminates_shallow_from_nested() -> None:
    """Control: a matcher that said yes to everything would pass the test above."""
    assert glob_covers("*.json", "settings.json")
    assert not glob_covers("*.json", "lab/presets.json")
    assert glob_covers("lab/*.json", "lab/presets.json")
    assert not glob_covers("lab/*.json", "lab/nested/presets.json")
    assert glob_covers("docs/**/*.md", "docs/a/b/c.md")
    assert glob_covers("docs/**/*.md", "docs/c.md"), "**/ must span zero directories"
