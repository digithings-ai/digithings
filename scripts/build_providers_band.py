#!/usr/bin/env python3
"""Build the integrations-band provider list from the dependencies this repo
actually declares and imports.

The two scrolling "connected package" rows on the digiquant.io integrations band
were a hand-maintained literal in apps/digiquant-web/app/_bands/integrations.tsx.
It named providers this tree has no direct dependency on (Coinbase, Interactive
Brokers, Kraken, Tradier, Binance) and, before that, a FRED row for a macro series
we read from a sealed R2 parquet rather than from FRED. Nothing noticed: a literal
only goes stale when someone remembers to edit it. DIG-2814 removed two of those
providers from the chart feed and left the rows behind.

This script replaces the literal with the real answer. A provider reaches the band
only when BOTH arms hold:

  declared  a manifest names one of its packages, in a base `dependencies` list or
            in a `[project.optional-dependencies]` extra (pyproject.toml) or in a
            package.json `dependencies` block. Development and peer dependencies
            are not counted: a provider the product does not ship does not belong
            in a product band.
  imported  a non-test source file in this repo imports that package. A distribution
            whose import name differs from its distribution name (alpaca-py imports
            as `alpaca`) is matched on the module the code actually imports.

Either arm alone is not enough, and the difference is the point. `fredapi` is
declared by digiquant's `m2` extra but imported by nothing -- that extra backs the
sealed R2 `fred__M2SL` parquet, not a live fetch -- so FRED stays out. A
declared-but-unimported package is a capability we carry, not a dependency we use.

Usage:
    python3 scripts/build_providers_band.py           # write the JSON
    python3 scripts/build_providers_band.py --check   # exit 1 if the JSON is stale

tests/scripts/test_providers_band_is_current.py runs --check in CI, so a
dependency change the band has not caught up with fails the build instead of
silently shipping a marketing claim about a provider we do not use.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
import tomllib
from dataclasses import dataclass
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
BAND_JSON = Path("apps/digiquant-web/app/_bands/integrations.providers.json")
MARKS_TSX = Path("apps/digiquant-web/components/integrations/marks.tsx")

# Directories that hold no shipped source: vendored installs, build output and
# generated caches. Walking them would import-register every dependency that ever
# touched this repo, which is exactly the bug this script exists to remove.
PRUNE_DIRS = frozenset(
    {
        ".git",
        ".next",
        ".turbo",
        ".venv",
        ".worktrees",
        "__pycache__",
        "build",
        "dist",
        "node_modules",
        "reference",
        "site-packages",
    }
)

# Path fragments that mark a file as a test. A test may import a package to assert
# on it; that is not a dependency the band may claim.
TEST_FRAGMENTS = ("tests/", "test_", "_test.", ".test.", "conftest.py", "e2e/")

# This script names every package in PROVIDERS, so scanning it would register a
# module import that does not exist. The exclusion is a named constant rather than
# an inline skip so that widening it is a visible diff, not a silent hole.
# Paths are repo-relative posix, matching how iter_source_files compares them.
# Comparing a bare filename against a relative path never matches, which left
# this exclusion a no-op until the walk was instrumented.
EXCLUDED_FROM_SCAN = frozenset({Path(__file__).resolve().relative_to(REPO_ROOT).as_posix()})


@dataclass(frozen=True)
class Provider:
    """One vendor the band may name, and the packages that prove we use it."""

    id: str
    label: str
    packages: tuple[str, ...]
    modules: tuple[str, ...]


# The vocabulary, not a result. Membership is decided by the two arms below, never
# by this table. A provider with no package in this map can only reach the band if
# someone adds one here -- which is the point: the band grows from a dependency,
# not from a marketing decision.
PROVIDERS: tuple[Provider, ...] = (
    Provider(
        id="alpaca",
        label="Alpaca · broker adapter",
        packages=("alpaca-py",),
        modules=("alpaca",),
    ),
    Provider(
        id="supabase",
        label="Supabase · stored prices",
        packages=("supabase", "@supabase/supabase-js"),
        modules=("supabase",),
    ),
    Provider(
        id="yahoo",
        label="Yahoo Finance · quote history",
        packages=("yfinance",),
        modules=("yfinance",),
    ),
    Provider(
        id="fred",
        label="FRED · macro series",
        packages=("fredapi",),
        modules=("fredapi",),
    ),
)

_PY_NAME = re.compile(r"^[A-Za-z0-9._-]+")
# The module path must be captured DOTTED. Anchoring on [\w]* instead makes
# `from alpaca.trading.client import X` fail to match, which silently drops a
# provider we really do depend on -- a green artefact over a wrong list.
_PY_IMPORT = re.compile(
    r"^\s*(?:from\s+([A-Za-z_][\w.]*)\s+import\b|import\s+([A-Za-z_][\w.]*))",
    re.MULTILINE,
)
# Anchored on the import/require form. Matching any quoted string instead would
# register every module name this repo merely mentions in a message, a docstring
# or a spec key -- which is the same over-claim the two arms exist to prevent.
_TS_IMPORT = re.compile(
    r"\bfrom\s*[\"']([^\"']+)[\"']"
    r"""|\bimport\s*["']([^"']+)["']"""
    r"""|\brequire\(\s*["']([^"']+)["']"""
    r"""|\bimport\(\s*["']([^"']+)["']"""
)

_ROW_MARKS_BLOCK = re.compile(r"const\s+ROW_MARKS[^=]*=\s*\{(.*?)\n\};", re.DOTALL)
_ROW_MARK_KEY = re.compile(r"^\s*([a-z0-9_]+):\s*si([A-Za-z0-9]+),", re.MULTILINE)
_SIMPLE_ICONS_VERSION = re.compile(r'"simple-icons":\s*"\^?([0-9][^"]*)"')


def _is_test(path: Path) -> bool:
    posix = path.as_posix()
    return any(fragment in posix for fragment in TEST_FRAGMENTS)


def iter_source_files(root: Path, *, exclude: frozenset = EXCLUDED_FROM_SCAN):
    """Yield every shipped .py/.ts/.tsx file, pruned, test- and self-filtered."""
    for dirpath, dirnames, filenames in os.walk(root):
        dirnames[:] = sorted(d for d in dirnames if d not in PRUNE_DIRS)
        for name in sorted(filenames):
            if not name.endswith((".py", ".ts", ".tsx")):
                continue
            path = Path(dirpath) / name
            if _is_test(path.relative_to(root)):
                continue
            if path.relative_to(root).as_posix() in exclude:
                continue
            yield path


def declared_packages(root: Path) -> dict[str, list[str]]:
    """Map package name -> the manifest surfaces that declare it.

    Extras count as declarations. digiquant declares alpaca-py, yfinance and
    supabase behind `brokers-alpaca`, `prices` and `research`, and those extras are
    how the product installs them; treating only the base list as "declared" would
    empty the band.
    """
    found: dict[str, list[str]] = {}

    def add(name: str, surface: str) -> None:
        found.setdefault(name, []).append(surface)

    for path in sorted(root.rglob("pyproject.toml")):
        rel = path.relative_to(root).as_posix()
        if any(part in PRUNE_DIRS for part in path.relative_to(root).parts):
            continue
        project = tomllib.loads(path.read_text(encoding="utf-8")).get("project", {})
        for name in project.get("dependencies", []) or []:
            match = _PY_NAME.match(name)
            if match:
                add(match.group(0), f"{rel}: dependencies")
        for extra, names in (project.get("optional-dependencies", {}) or {}).items():
            for name in names:
                match = _PY_NAME.match(name)
                if match:
                    add(match.group(0), f"{rel}: optional-dependencies.{extra}")

    for path in sorted(root.rglob("package.json")):
        rel = path.relative_to(root).as_posix()
        if any(part in PRUNE_DIRS for part in path.relative_to(root).parts):
            continue
        manifest = json.loads(path.read_text(encoding="utf-8"))
        for field in ("dependencies", "optionalDependencies"):
            for name in manifest.get(field, {}) or {}:
                add(name, f"{rel}: {field}")

    return found


def imported_modules(root: Path, *, exclude: frozenset = EXCLUDED_FROM_SCAN) -> set[str]:
    """Every top-level module name a shipped source file imports."""
    modules: set[str] = set()
    for path in iter_source_files(root, exclude=exclude):
        try:
            text = path.read_text(encoding="utf-8")
        except (UnicodeDecodeError, OSError):
            continue
        for left, right in _PY_IMPORT.findall(text):
            # The top-level package is the dependency: `import a.b.c` requires a.
            modules.add((left or right).split(".")[0])
        for groups in _TS_IMPORT.findall(text):
            modules.add(next(g for g in groups if g))
    return modules


def row_mark_slugs(root: Path) -> tuple[set[str], str]:
    """The simple-icons slugs marks.tsx registers for row providers.

    Read out of the live file rather than a hardcoded list, so "does this provider
    have a logo path" stays true when someone adds one. The marks are Simple Icons
    paths; a provider absent here has no official monochrome mark and is flagged,
    never faked with a recoloured favicon.
    """
    text = (root / MARKS_TSX).read_text(encoding="utf-8")
    block = _ROW_MARKS_BLOCK.search(text)
    if block is None:
        raise AssertionError(f"ROW_MARKS block not found in {MARKS_TSX}")
    slugs = set()
    for _key, slug in _ROW_MARK_KEY.findall(block.group(1)):
        slugs.add(slug.lower())
    version_match = _SIMPLE_ICONS_VERSION.search(
        (root / "apps/digiquant-web/package.json").read_text(encoding="utf-8")
    )
    return slugs, version_match.group(1) if version_match else "unknown"


def build(root: Path = REPO_ROOT) -> dict:
    declared = declared_packages(root)
    imported = imported_modules(root)
    slugs, icons_version = row_mark_slugs(root)

    providers = []
    for provider in sorted(PROVIDERS, key=lambda p: p.id):
        surfaces = sorted({s for pkg in provider.packages for s in declared.get(pkg, [])})
        if not surfaces:
            continue
        if not any(module in imported for module in provider.modules):
            continue
        if provider.id in slugs:
            logo = {
                "slug": provider.id,
                "source": f"simple-icons@{icons_version}",
                "registry": MARKS_TSX.as_posix(),
            }
        else:
            logo = {
                "missing": True,
                "reason": "no official monochrome mark registered in ROW_MARKS",
            }
        providers.append(
            {
                "id": provider.id,
                "label": provider.label,
                "declaredIn": surfaces,
                "logo": logo,
            }
        )

    return {
        "generatedBy": "scripts/build_providers_band.py",
        "rule": (
            "a provider ships only when a manifest declares one of its packages "
            "and a non-test source file imports it"
        ),
        "providers": providers,
    }


def render(payload: dict) -> str:
    return json.dumps(payload, indent=2, ensure_ascii=False) + "\n"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument(
        "--check",
        action="store_true",
        help="exit 1 when the committed JSON differs from a fresh run",
    )
    args = parser.parse_args(argv)

    target = REPO_ROOT / BAND_JSON
    rendered = render(build())

    if args.check:
        if not target.exists():
            print(f"missing generated file: {BAND_JSON}", file=sys.stderr)
            return 1
        if target.read_text(encoding="utf-8") != rendered:
            print(
                f"stale generated file: {BAND_JSON}\nrun: python3 {Path(__file__).name}",
                file=sys.stderr,
            )
            return 1
        print(f"{BAND_JSON} is current")
        return 0

    target.write_text(rendered, encoding="utf-8")
    print(f"wrote {BAND_JSON}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
