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

import shutil
import subprocess
import tempfile
import tomllib
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
OUT = REPO / "image-packages"

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
NPM_PACKAGES = ("@digithings/design", "@digithings/ui", "@digithings/digichat-ui")
NPM_MANIFESTS = {
    "design": REPO / "packages" / "design" / "package.json",
    "ui": REPO / "packages" / "ui" / "package.json",
    "digichat-ui": REPO / "packages" / "digichat-ui" / "package.json",
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


def main() -> None:
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
    print(f"wrote {OUT}")


if __name__ == "__main__":
    main()
