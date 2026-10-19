#!/usr/bin/env python3
"""Build the artifacts the R5 Dockerfiles install.

The images no longer COPY sibling module trees. This script, run from the
repo root before ``docker build``, turns the workspace into wheels, a
frozen requirements set (``uv export --frozen`` of the root lock), npm
tarballs for the digichat packages, and the runner payload those images
lay out at the paths they already execute.

Output is ``image-packages/`` (gitignored). It is not a registry and it
does not push an image.
"""

from __future__ import annotations

import hashlib
import json
import os
import shutil
import subprocess
import sys
import tempfile
import tomllib
from datetime import datetime, timezone
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
OUT = REPO / "image-packages"
#: Written last by ``main()``. The path is resolved from ``OUT`` at call time, not
#: frozen here, so monkeypatching ``OUT`` in a test exercises the whole round trip.
PROVENANCE_NAME = "PROVENANCE.json"
PROVENANCE = OUT / PROVENANCE_NAME
PROVENANCE_VERSION = 1

# Extras match the install lines these Dockerfiles had when they copied source.
STACK_PACKAGES: tuple[tuple[str, tuple[str, ...]], ...] = (
    ("digibase", ()),
    ("digikey", ()),
    ("digitrace", ("tracing",)),
    ("digillm", ()),
    ("digigraph", ("mcp",)),
    ("digifetch", ()),
    ("digiclaw", ()),
    ("digisearch", ("server", "ingestion", "chroma", "web-search", "embedding-multilingual")),
    ("digivault", ("service",)),
)
RUNNER_EXPORTS: tuple[tuple[str, tuple[str, ...]], ...] = (
    ("digiquant", ("prices", "research", "nautilus")),
    ("digigraph", ("checkpoint-postgres",)),
)
RUNNER_WHEELS = (
    "digibase",
    "digikey",
    "digifetch",
    "digiquant",
    "digigraph",
    "digillm",
    "digitrace",
)
RUNNER_WHEEL_EXTRAS: dict[str, tuple[str, ...]] = {
    "digiquant": ("prices", "research", "nautilus"),
    "digigraph": ("checkpoint-postgres",),
}
NPM_PACKAGES = (
    "@digithings/design",
    "@digithings/ui",
    "@digithings/digichat-ui",
    "@digithings/hero-banner",
)
NPM_MANIFESTS = {
    "design": REPO / "packages" / "design" / "package.json",
    "ui": REPO / "packages" / "ui" / "package.json",
    "digichat-ui": REPO / "packages" / "digichat-ui" / "package.json",
    "hero-banner": REPO / "packages" / "hero-banner" / "package.json",
    "dashboard": REPO / "apps" / "dashboard" / "package.json",
}
RUNNER_FILES = (
    "scripts/refresh_market_data_r2.py",
    "scripts/backfill_market_data_r2.py",
    "scripts/execution_cron_check.py",
    "scripts/digiquant_archive_checkpoints.py",
    "scripts/digiquant_checkpoint_size_gate.py",
    "config/byok-providers.json",
    "config/model-policy.json",
    "config/digiquant-model-prices.json",
    ".github/digiquant-pipeline.yml",
    ".github/workflows/pipeline-digiquant-allocation-shadow.yml",
)
RUNNER_OPT = (
    "apps/digiquant-runner/container/exec_job.py",
    "apps/digiquant-runner/container/house_chain_step.py",
    "apps/digiquant-runner/container/wake_stack.py",
    "apps/digiquant-runner/container/web_search_preflight.py",
    "apps/digiquant-runner/commands.json",
)

#: Directories the fallback digest never descends into. Only used when git cannot
#: answer: with git, ``ls-files --exclude-standard`` excludes these — and everything
#: else the repo ignores, ``digiquant/results/`` included — by construction. A list
#: kept by hand cannot win that race, which is why it is not the primary path.
EXCLUDED_DIRS = frozenset(
    {
        "__pycache__",
        ".venv",
        "node_modules",
        ".mypy_cache",
        ".ruff_cache",
        ".pytest_cache",
        "dist",
        "build",
    }
)

#: What a developer runs when `--check-only` refuses. Quoted verbatim in the
#: abort lines so the remediation is never re-derived by hand at 2am.
REMEDIATION = "rm -rf image-packages && python3 scripts/package_r5_image_inputs.py"


def _excluded(name: str) -> bool:
    return name in EXCLUDED_DIRS or name.endswith(".egg-info")


def _git_listed_files(root: Path) -> list[Path] | None:
    """Git's answer for "which files under ``root`` are source", or None if it cannot say.

    ``--cached`` adds tracked files and ``--others --exclude-standard`` adds untracked,
    not-ignored ones — the second half matters because a brand-new source file that has
    never been ``git add``ed is still packaged by the build, and a plain ``git ls-files``
    would miss it. Git already knows what the repository ignores, so
    ``digiquant/results/``, ``__pycache__``, ``.venv``, ``node_modules``, ``dist``,
    ``build`` and ``*.egg-info`` are excluded by construction: a local backtest writing
    into ``digiquant/results/`` can no longer drift the digest and force a repackage of
    sources that did not change.

    Paths come back relative to ``root``, because git lists relative to its working
    directory. None sends the caller to the filesystem walk — git missing, or ``root``
    outside any repository.
    """
    try:
        completed = subprocess.run(
            ["git", "ls-files", "-z", "--cached", "--others", "--exclude-standard", "--", "."],
            cwd=root,
            capture_output=True,
            check=True,
        )
    except (OSError, subprocess.CalledProcessError):
        return None
    listed = [
        Path(chunk.decode("utf-8", "surrogateescape"))
        for chunk in completed.stdout.split(b"\0")
        if chunk
    ]
    return [path for path in listed if (root / path).is_file()]


def _walked_files(root: Path) -> list[Path]:
    """The fallback enumeration: a filesystem walk, minus ``EXCLUDED_DIRS``."""
    found: list[Path] = []
    for dirpath, dirnames, filenames in os.walk(root):
        dirnames[:] = sorted(name for name in dirnames if not _excluded(name))
        for filename in sorted(filenames):
            path = Path(dirpath) / filename
            if not path.is_file():  # a dangling symlink or a socket, not a file
                continue
            found.append(path.relative_to(root))
    return found


def content_digest(root: Path) -> str:
    """sha256 over (relative POSIX path, working-tree bytes) for an input's sources.

    mtimes are deliberately absent. Git checkout stamps every source file with the
    moment of checkout, so an mtime rule would call a freshly cloned tree stale,
    force a repackage, and rewriting the inputs changes container layer digests —
    re-uploading ~8 layers against the registry. Only real content drift refuses.

    The file set is git's (see ``_git_listed_files``) and the bytes are the working
    tree's, never the index blob's: ``uv build`` packages a dirty edit, so reading the
    index would pass a tree the wheel was not built from.

    Without git this degrades to the old filesystem walk and says so on stderr, rather
    than returning an empty digest that reads as "unchanged".
    """
    digest = hashlib.sha256()
    if root.is_file():
        digest.update(b"file\0")
        digest.update(root.read_bytes())
        return digest.hexdigest()

    listed = _git_listed_files(root)
    if listed is None or not listed:
        walked = _walked_files(root)
        # listed is None: git could not answer. listed == [] over a non-empty tree:
        # every file is ignored, which is not something to trust silently.
        if listed is None or walked:
            print(
                f"warning: provenance for {root} was computed without git "
                "(filesystem walk); gitignored build output under it is not detected.",
                file=sys.stderr,
            )
            listed = walked

    for relative in sorted(listed, key=lambda path: path.as_posix()):
        digest.update(relative.as_posix().encode("utf-8"))
        digest.update(b"\0")
        digest.update((root / relative).read_bytes())
        digest.update(b"\0")
    return digest.hexdigest()


def input_paths() -> dict[str, Path]:
    """Every packaged input: name -> the source path it is built from."""
    paths: dict[str, Path] = {}
    for package in dict.fromkeys([name for name, _ in STACK_PACKAGES] + list(RUNNER_WHEELS)):
        paths[package] = REPO / package

    # _write_npm() packs each NPM_PACKAGES workspace and copies each NPM_MANIFESTS
    # package.json into the image. The manifest path is the only place that layout
    # is stated, so the source dir is its parent — never a guessed
    # packages/<short-name>. 2026-10-18 was a stale npm package: a packages/ui
    # import of @digithings/hero-banner that the image never packaged.
    covered: set[str] = set()
    for manifest in NPM_MANIFESTS.values():
        meta = json.loads(manifest.read_text(encoding="utf-8"))
        name = str(meta["name"])
        paths[name] = manifest.parent
        covered.add(name)
    unpacked = sorted(name for name in NPM_PACKAGES if name not in covered)
    if unpacked:
        raise SystemExit(
            f"npm workspace(s) {unpacked} are packed but absent from NPM_MANIFESTS; "
            "their sources would go unfingerprinted"
        )

    # The runner payload is COPYd into the image file by file.
    for rel in RUNNER_FILES + RUNNER_OPT:
        paths[f"payload:{rel}"] = REPO / rel
    for rel in ("digiquant/scripts", "digisearch/seeds"):
        paths[f"payload:{rel}"] = REPO / rel
    return paths


def _git_head() -> str | None:
    try:
        head = subprocess.run(
            ["git", "rev-parse", "HEAD"],
            cwd=REPO,
            capture_output=True,
            text=True,
            check=True,
        )
    except (OSError, subprocess.CalledProcessError):
        return None
    return head.stdout.strip() or None


def _combined(packages: dict[str, str]) -> str:
    pairs = "\n".join(f"{name}:{digest}" for name, digest in sorted(packages.items()))
    return hashlib.sha256(pairs.encode("utf-8")).hexdigest()


def provenance_document(paths: dict[str, Path] | None = None) -> dict[str, object]:
    """The provenance record written next to the packaged artifacts."""
    selected = input_paths() if paths is None else paths
    packages = {name: content_digest(path) for name, path in sorted(selected.items())}
    return {
        "version": PROVENANCE_VERSION,
        "packages": packages,
        "combined": _combined(packages),
        "head": _git_head(),
        "built_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
    }


def _provenance_path() -> Path:
    """Where the record lives, resolved from ``OUT`` at call time.

    Not the module constant: a test points ``OUT`` at a temp dir and expects both the
    writer and ``check_only()`` to follow it.
    """
    return OUT / PROVENANCE_NAME


def _write_provenance() -> None:
    document = provenance_document()
    _provenance_path().write_text(json.dumps(document, indent=2) + "\n", encoding="utf-8")


def check_only(paths: dict[str, Path] | None = None, provenance: Path | None = None) -> int:
    """0 when the packaged inputs match the sources, 1 on drift, 2 when unknown.

    ``head`` is informational only: the decision rests on content, so a different
    commit with identical inputs still passes.
    """
    target = _provenance_path() if provenance is None else provenance
    selected = input_paths() if paths is None else paths
    try:
        document = json.loads(target.read_text(encoding="utf-8"))
        recorded = document["packages"]
        if document["version"] != PROVENANCE_VERSION or not isinstance(recorded, dict):
            raise ValueError(f"unsupported provenance version {document['version']!r}")
        if not all(
            isinstance(name, str) and isinstance(value, str) for name, value in recorded.items()
        ):
            raise ValueError("malformed packages table")
    except (OSError, ValueError, KeyError, TypeError) as exc:
        print(f"ABORT: cannot read usable provenance from {target} ({exc}).")
        print("  Unknown provenance is not a pass: a package dir built before this")
        print("  check existed has no fingerprints and must be regenerated once.")
        print(f"  rebuild: {REMEDIATION}")
        return 2

    current = {name: content_digest(path) for name, path in selected.items()}
    added = sorted(set(current) - set(recorded))
    removed = sorted(set(recorded) - set(current))
    changed = sorted(
        name for name in current if name in recorded and current[name] != recorded[name]
    )
    if not (added or removed or changed):
        print(f"ok: image-packages provenance matches {len(current)} packaged input(s)")
        return 0
    print("ABORT: image-packages/ is stale — it would install software that is not")
    print("       the working tree, so the image would ship a stale package.")
    for label, names in (("added", added), ("removed", removed), ("changed", changed)):
        if names:
            print(f"  {label}: {', '.join(names)}")
    print(f"  rebuild: {REMEDIATION}")
    return 1


def _run(cmd: list[str], *, cwd: Path | None = None) -> None:
    subprocess.run(cmd, cwd=cwd or REPO, check=True)


def _version(package: str) -> str:
    text = (REPO / package / "pyproject.toml").read_text(encoding="utf-8")
    version = tomllib.loads(text)["project"]["version"]
    if not isinstance(version, str) or not version:
        raise SystemExit(f"{package} has no project.version")
    return version


def _export(package: str, extras: tuple[str, ...], dest: Path) -> None:
    cmd = [
        "uv",
        "export",
        "--frozen",
        "--package",
        package,
        "--no-dev",
        "--no-emit-workspace",
        "--no-hashes",
        "--no-annotate",
        "--no-header",
        "-o",
        str(dest),
    ]
    for extra in extras:
        cmd.extend(["--extra", extra])
    _run(cmd)


def _parse_req(line: str) -> tuple[str, str, str]:
    requirement, _, marker = line.partition(";")
    requirement = requirement.strip()
    marker = marker.strip()
    if "==" not in requirement or " @" in requirement or requirement.startswith("-"):
        raise SystemExit(f"unexpected export line: {line}")
    name, version = requirement.split("==", 1)
    return name.strip().lower(), version.strip(), marker


def _merge(paths: list[Path]) -> list[str]:
    """Union of frozen export lines. Same package at two versions is an error."""
    chosen: dict[tuple[str, str], str] = {}
    for path in paths:
        for raw in path.read_text(encoding="utf-8").splitlines():
            line = raw.strip()
            if not line:
                continue
            name, version, marker = _parse_req(line)
            key = (name, marker)
            previous = chosen.get(key)
            if previous is not None and previous != version:
                raise SystemExit(f"{name} pin {previous} conflicts with {version} ({marker})")
            chosen[key] = version
    lines: list[str] = []
    for (name, marker), version in sorted(chosen.items()):
        spec = f"{name}=={version}"
        if marker:
            spec = f"{spec} ; {marker}"
        lines.append(spec)
    return lines


def _build_wheel(package: str, dest: Path) -> Path:
    dest.mkdir(parents=True, exist_ok=True)
    before = set(dest.glob("*.whl"))
    _run(
        [
            "uv",
            "build",
            "--wheel",
            "--package",
            package,
            "--out-dir",
            str(dest),
        ]
    )
    created = set(dest.glob("*.whl")) - before
    owned = [path for path in created if path.name.startswith(package.replace("-", "_") + "-")]
    # setuptools normalizes '-' to '_' in the wheel name; the package dir does too.
    if len(owned) != 1:
        named = [path for path in created if path.name.startswith(package + "-")]
        owned = named if len(named) == 1 else sorted(created)
    if len(owned) != 1:
        raise SystemExit(f"expected one new wheel for {package}, got {[p.name for p in owned]}")
    return owned[0]


def _requirement(package: str, version: str, extras: tuple[str, ...]) -> str:
    if extras:
        bracket = ",".join(extras)
        return f"{package}[{bracket}]=={version}"
    return f"{package}=={version}"


def _write_runner_project(wheels: dict[str, Path], requirements: list[str]) -> None:
    project = OUT / "runner" / "project"
    wheel_dir = project / "wheels"
    if project.exists():
        shutil.rmtree(project)
    wheel_dir.mkdir(parents=True)
    sources: list[str] = []
    deps: list[str] = []
    for package, wheel in wheels.items():
        target = wheel_dir / wheel.name
        shutil.copy2(wheel, target)
        version = _version(package)
        deps.append(_requirement(package, version, RUNNER_WHEEL_EXTRAS.get(package, ())))
        sources.append(f'{package} = {{ path = "wheels/{wheel.name}" }}')
    deps.extend(requirements)
    dep_lines = "\n".join(f'  "{dep}",' for dep in deps)
    source_lines = "\n".join(sources)
    text = (
        "[project]\n"
        'name = "digiquant-runner-image"\n'
        'version = "0.0.0"\n'
        'description = "Install project for the runner image. '
        'Pins are uv export --frozen of the workspace lock."\n'
        'requires-python = ">=3.12"\n'
        "dependencies = [\n"
        f"{dep_lines}\n"
        "]\n"
        "\n"
        "[tool.uv]\n"
        "package = false\n"
        "\n"
        "[tool.uv.sources]\n"
        f"{source_lines}\n"
    )
    (project / "pyproject.toml").write_text(text, encoding="utf-8")
    # Lock outside the workspace so uv does not attach this project to the monorepo.
    isolated_root = Path(tempfile.mkdtemp(prefix="digiquant-runner-image-"))
    try:
        isolated = isolated_root / "project"
        shutil.copytree(project, isolated)
        _run(["uv", "lock"], cwd=isolated)
        shutil.copy2(isolated / "uv.lock", project / "uv.lock")
    finally:
        shutil.rmtree(isolated_root)


def _write_payload() -> None:
    payload = OUT / "runner" / "payload"
    if payload.exists():
        shutil.rmtree(payload)
    for rel in RUNNER_FILES:
        src = REPO / rel
        dest = payload / rel
        dest.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(src, dest)
    opt = payload / "opt" / "runner"
    opt.mkdir(parents=True)
    for rel in RUNNER_OPT:
        shutil.copy2(REPO / rel, opt / Path(rel).name)
    scripts = REPO / "digiquant" / "scripts"
    shutil.copytree(scripts, payload / "digiquant" / "scripts")


def _write_npm() -> None:
    npm_dir = OUT / "digichat" / "npm"
    manifests = OUT / "digichat" / "manifests"
    if npm_dir.exists():
        shutil.rmtree(npm_dir)
    if manifests.exists():
        shutil.rmtree(manifests)
    npm_dir.mkdir(parents=True)
    for name in NPM_PACKAGES:
        _run(["npm", "pack", "--workspace", name, "--pack-destination", str(npm_dir)])
    for key, src in NPM_MANIFESTS.items():
        dest = manifests / key
        dest.mkdir(parents=True)
        shutil.copy2(src, dest / "package.json")


def main(argv: list[str] | None = None) -> int:
    args = sys.argv[1:] if argv is None else argv
    if args == ["--check-only"]:
        return check_only()
    if args:
        raise SystemExit(f"unknown argument(s): {' '.join(args)} (want --check-only)")

    if OUT.exists():
        shutil.rmtree(OUT)
    wheel_dir = OUT / "wheels"
    wheel_dir.mkdir(parents=True)
    built: dict[str, Path] = {}
    packages = list(dict.fromkeys([name for name, _ in STACK_PACKAGES] + list(RUNNER_WHEELS)))
    for package in packages:
        built[package] = _build_wheel(package, wheel_dir)

    stack_exports: list[Path] = []
    export_dir = OUT / "exports"
    export_dir.mkdir()
    for package, extras in STACK_PACKAGES:
        dest = export_dir / f"stack-{package}.txt"
        _export(package, extras, dest)
        stack_exports.append(dest)
    stack_req = OUT / "stack" / "requirements.txt"
    stack_req.parent.mkdir(parents=True)
    stack_req.write_text("\n".join(_merge(stack_exports)) + "\n", encoding="utf-8")
    stack_wheels = OUT / "stack" / "wheels"
    stack_wheels.mkdir()
    for package, _extras in STACK_PACKAGES:
        shutil.copy2(built[package], stack_wheels / built[package].name)
    seeds = REPO / "digisearch" / "seeds"
    shutil.copytree(seeds, OUT / "stack" / "digisearch-seeds")

    runner_exports: list[Path] = []
    for package, extras in RUNNER_EXPORTS:
        dest = export_dir / f"runner-{package}.txt"
        _export(package, extras, dest)
        runner_exports.append(dest)
    runner_req = _merge(runner_exports)
    runner_wheels = {package: built[package] for package in RUNNER_WHEELS}
    _write_runner_project(runner_wheels, runner_req)
    _write_payload()
    _write_npm()
    # Last, so the record describes the artifacts on disk. DIG-4423: this is what
    # lets deploy_worker.sh refuse a stale image-packages/ instead of trusting that
    # the directory merely exists.
    _write_provenance()
    print(f"wrote {OUT}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
