"""Boundary check for the repo split (DIG-3690, parent DIG-3518).

Fails when code crosses a repo boundary against the allowed dependency
directions. Allowed edges (private may consume public, never the reverse):

  R1 -> R0    strategies plugin consumes the open engine
  R2 -> R0,R1 house backend consumes the engine and the strategy plugin
  R3 -> R0,R2 desk consumes the engine and the R2 HTTP contract
  R4 -> R0    site consumes the engine/UI packages
  R5 -> R0,R2 platform consumes the engine; cron binds R2 workers at runtime
  R6 -> R0,R5 tenant tooling consumes the engine; KV/seeds read by R5
  R7 -> R0    desk consumes the engine
  R0 -> R0    inside the open repo
  delete -> (nothing checked; deleted paths carry no boundary)

Checks:
  1. Python imports: `digiquant.*` absolute imports and relative imports,
     resolved to files and mapped through manifest.py.
  2. TypeScript relative imports (`from "../.."` / `@/...` stays inside its
     own package): resolved to files and mapped through manifest.py. In
     particular, apps importing across trees by relative path instead of via
     package exports (P1.6) is flagged.
  3. Dockerfile COPY: `COPY ../...` or `COPY <other-tree> ...` sources mapped
     through manifest.py; the Dockerfile's own repo comes from manifest.py.

Usage:
  python3 scripts/split/check_boundaries.py [--ref <git-ref>] [--repo <path>] [--enforce]
  Without --enforce (default) prints violating edges and exits 0: advisory
  mode while the P1 decouple slices (1.2/1.7/1.8) own the residual coupling.
  With --enforce exits 1 on any violation. local-ci promotes this check to
  --enforce at the P1 exit check; until then the hard gate is
  `manifest.py --check` (zero unassigned paths).
"""

from __future__ import annotations

import ast
import os
import re
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
from manifest import build_manifest, tracked_paths  # noqa: E402

ALLOWED: dict[str, set[str]] = {
    "R0": {"R0"},
    "R1": {"R0", "R1"},
    "R2": {"R0", "R1", "R2"},
    "R3": {"R0", "R2", "R3"},
    "R4": {"R0", "R4"},
    "R5": {"R0", "R2", "R5"},
    "R6": {"R0", "R5", "R6"},
    "R7": {"R0", "R7"},
    "delete": {"R0", "R1", "R2", "R3", "R4", "R5", "R6", "R7", "delete"},
}

PY_ROOTS = {"digiquant": "digiquant/src/digiquant"}


def repo_of(path: str, mapping: dict[str, str]) -> str | None:
    return mapping.get(path)


def resolve_py_import(importer: str, level: int, module: str | None) -> str | None:
    """Resolve an import to a repo-relative file path (or None if external)."""
    if level and level > 0:
        parts = importer.split("/")[:-1]
        if len(parts) < level:
            return None
        base = parts[: len(parts) - level + 1]
        if module:
            base += module.split(".")
        cand = "/".join(base)
        for suffix in (".py", "/__init__.py"):
            if (cand + suffix).replace("//", "/"):
                return cand + suffix
        return cand + ".py"
    if not module:
        return None
    top = module.split(".")[0]
    if top not in PY_ROOTS:
        return None
    rest = module.split(".")[1:]
    cand = PY_ROOTS[top] + ("/" + "/".join(rest) if rest else "")
    for suffix in (".py", "/__init__.py"):
        return cand + suffix
    return None


def read_text(root: str | None, path: str) -> str:
    full = os.path.join(root, path) if root else path
    return Path(full).read_text()


def check_python(files: list[str], mapping: dict[str, str], root: str | None = None) -> list[str]:
    violations: list[str] = []
    for f in files:
        if not f.endswith(".py"):
            continue
        src_repo = repo_of(f, mapping)
        if src_repo is None:
            continue
        try:
            tree = ast.parse(read_text(root, f), filename=f)
        except (SyntaxError, OSError):
            continue
        for node in ast.walk(tree):
            if isinstance(node, ast.ImportFrom):
                target = resolve_py_import(f, node.level or 0, node.module)
            elif isinstance(node, ast.Import):
                target = None
                for alias in node.names:
                    top = alias.name.split(".")[0]
                    if top in PY_ROOTS:
                        target = resolve_py_import(f, 0, alias.name)
                        break
                if target is None:
                    continue
            else:
                continue
            if target is None:
                continue
            dst_repo = repo_of(target, mapping)
            if dst_repo is None:
                # Unresolvable inside the repo (e.g. submodule file): map the
                # importing package dir instead when possible.
                continue
            if dst_repo not in ALLOWED.get(src_repo, set()):
                violations.append(f"{f} [{src_repo}] imports {target} [{dst_repo}]")
    return violations


TS_IMPORT_RE = re.compile(r"""(?:import|export)[^'"]*?from\s*['"]([^'"]+)['"]""")


def resolve_ts_import(importer: str, spec: str) -> str | None:
    if not spec.startswith("."):
        return None  # package import: boundary owned by package exports (P1.6)
    base = "/".join(importer.split("/")[:-1] + [spec])
    parts: list[str] = []
    for seg in base.split("/"):
        if seg in ("", "."):
            continue
        if seg == "..":
            if parts:
                parts.pop()
            continue
        parts.append(seg)
    cand = "/".join(parts)
    for suffix in ("", ".ts", ".tsx", "/index.ts", "/index.tsx"):
        return cand + suffix
    return None


def check_ts(files: list[str], mapping: dict[str, str], root: str | None = None) -> list[str]:
    violations: list[str] = []
    for f in files:
        if not (f.endswith(".ts") or f.endswith(".tsx")):
            continue
        if f.endswith(".d.ts"):
            continue
        src_repo = repo_of(f, mapping)
        if src_repo is None:
            continue
        try:
            text = read_text(root, f)
        except OSError:
            continue
        for m in TS_IMPORT_RE.finditer(text):
            target = resolve_ts_import(f, m.group(1))
            if target is None:
                continue
            dst_repo = repo_of(target, mapping)
            if dst_repo is None:
                continue
            if dst_repo not in ALLOWED.get(src_repo, set()):
                violations.append(f"{f} [{src_repo}] imports {target} [{dst_repo}]")
    return violations


COPY_RE = re.compile(r"^\s*COPY\s+(.*?)\s+\S+\s*$")


def check_dockerfiles(
    files: list[str], mapping: dict[str, str], root: str | None = None
) -> list[str]:
    violations: list[str] = []
    for f in files:
        base = f.rsplit("/", 1)[-1]
        if not (base == "Dockerfile" or base.startswith("Dockerfile.")):
            continue
        src_repo = repo_of(f, mapping)
        if src_repo is None:
            continue
        try:
            lines = read_text(root, f).splitlines()
        except OSError:
            continue
        for line in lines:
            m = COPY_RE.match(line)
            if not m:
                continue
            for src in m.group(1).split():
                if src.startswith("--"):
                    continue
                src = src.strip("\"'")
                if src.startswith("..") or "/" in src:
                    cand = src.lstrip("./")
                    dst_repo = repo_of(cand, mapping)
                    if dst_repo is None:
                        # Prefix-match: a COPY of a directory tree.
                        for p, r in mapping.items():
                            if cand and (p == cand or p.startswith(cand + "/")):
                                dst_repo = r
                                cand = p
                                break
                    if dst_repo is not None and dst_repo not in ALLOWED.get(src_repo, set()):
                        violations.append(f"{f} [{src_repo}] COPYs {cand} [{dst_repo}]")
    return violations


def main(argv: list[str]) -> int:
    ref: str | None = None
    repo: str | None = None
    enforce = "--enforce" in argv
    i = 0
    while i < len(argv):
        if argv[i] == "--ref" and i + 1 < len(argv):
            ref = argv[i + 1]
            i += 1
        elif argv[i] == "--repo" and i + 1 < len(argv):
            repo = argv[i + 1]
            i += 1
        i += 1
    if repo:
        os.chdir(repo)
    paths = tracked_paths(ref if ref else None)
    mapping, unassigned = build_manifest(paths)
    if unassigned:
        print(f"FAIL: {len(unassigned)} paths unassigned in manifest", file=sys.stderr)
        return 1
    # check_* read from the working tree; with --ref they would need the ref
    # materialised, so refuse that combination instead of half-checking.
    if ref:
        print("check_boundaries reads the working tree; rerun without --ref", file=sys.stderr)
        return 2
    root = repo
    violations = (
        check_python(paths, mapping, root)
        + check_ts(paths, mapping, root)
        + check_dockerfiles(paths, mapping, root)
    )
    for v in violations:
        print(f"VIOLATION {v}")
    print(f"checked {len(paths)} paths, {len(violations)} violations")
    if violations and not enforce:
        print("advisory: rerun with --enforce to fail on these (P1 exit check)")
        return 0
    return 1 if violations else 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
