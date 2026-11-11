"""P-2 acceptance: the R0 packages are publishable to public npm.

The split moves R2–R5 onto published packages, so every package those repos
import must be publishable: an exact version, no ``private`` flag, a ``files``
list that ships the code and nothing else, and a tarball that carries no test,
secret, client term or LAN address.

The publish list is the P-1 import audit's closed list. ``surface-config``,
``tui-frame`` and ``durable-object-reconnect`` are imported by nobody in
R2–R5, so they stay private and unpublished; the first test pins that.

``npm pack --dry-run --json`` is the authority for the file list, exactly as
P-4 will diff it before publishing, so this test cannot disagree with the
publish step about what ships.
"""

from __future__ import annotations

import json
import re
import shutil
import subprocess
import sys
from fnmatch import fnmatch
from pathlib import Path
from typing import Any

import pytest

pytestmark = pytest.mark.unit

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT / "scripts"))

import check_r0_no_client_literals as client_literals  # noqa: E402
import check_r0_private_terms as private_terms  # noqa: E402

PACKAGES = REPO_ROOT / "packages"
VERSION = "0.1.0"

#: package name -> package directory. Fixed by the P-1 import audit.
PUBLISHABLE: dict[str, str] = {
    "@digithings/perf-math": "perf-math",
    "@digithings/design": "design",
    "@digithings/hero-banner": "hero-banner",
    "@digithings/ui": "ui",
    "@digithings/catalog": "catalog",
    "@digithings/digichat-ui": "digichat-ui",
    "@digiquant/contract": "contract",
}

#: Imported by no split repo, so they are not published (P-1).
MUST_STAY_PRIVATE = ("surface-config", "tui-frame", "durable-object-reconnect")

INTERNAL_SCOPES = ("@digithings/", "@digiquant/")

#: A published tarball never carries a credential file, by name.
SECRET_PATH = re.compile(
    r"(^|/)(?:\.env(?:\.[^/]*)?|\.npmrc|\.htpasswd|secrets?|credentials)"
    r"|[^/]*\.(?:pem|key|p12|pfx|keystore)$|id_(?:rsa|ed25519|ecdsa)(?:\.pub)?$",
    re.IGNORECASE,
)

#: Tests ship in the repo, not in the tarball.
TEST_PATH = re.compile(
    r"(^|/)(?:tests?|__tests__|__mocks__|fixtures?|e2e)/"
    r"|\.(?:test|spec)\.[cm]?[jt]sx?$",
)

#: Private (RFC 1918) addresses; 127.0.0.1 is a documented local default.
LAN_IP = re.compile(r"\b(?:10\.\d{1,3}|192\.168|172\.(?:1[6-9]|2\d|3[01]))\.\d{1,3}\.\d{1,3}\b")

#: TS source, a stylesheet, or a data file the exports point at.
SOURCE_TARGET = re.compile(r"\.(?:ts|tsx|js|jsx|css|json|md)$")


def _package_json(directory: Path) -> dict[str, Any]:
    return json.loads((directory / "package.json").read_text(encoding="utf-8"))


def _all_packages() -> dict[str, tuple[Path, dict[str, Any]]]:
    found: dict[str, tuple[Path, dict[str, Any]]] = {}
    for directory in sorted(p for p in PACKAGES.iterdir() if p.is_dir()):
        manifest = directory / "package.json"
        if not manifest.is_file():
            continue
        package = json.loads(manifest.read_text(encoding="utf-8"))
        found[package["name"]] = (directory, package)
    return found


def _publishable_packages() -> list[tuple[Path, dict[str, Any]]]:
    packages = _all_packages()
    missing = sorted(set(PUBLISHABLE) - set(packages))
    assert not missing, f"publish list names packages that do not exist: {missing}"
    return [(packages[name][0], packages[name][1]) for name in sorted(PUBLISHABLE)]


def _export_targets(exports: object) -> list[str]:
    """Every string in an ``exports`` map, however it is nested."""
    if isinstance(exports, str):
        return [exports]
    if isinstance(exports, list):
        return [target for item in exports for target in _export_targets(item)]
    if isinstance(exports, dict):
        return [target for item in exports.values() for target in _export_targets(item)]
    return []


def _private_term_patterns() -> list["re.Pattern[str]"]:
    """Client terms from the mono list or the R0 CI secret; empty without one.

    A tree with no terms list (a fresh clone of public R0 with no secret) still
    runs the in-source client-literal patterns below, so the scan degrades to
    the tier that ships, never to nothing.
    """
    try:
        return private_terms.load_terms(REPO_ROOT, None)
    except private_terms.ToolError:
        return []


def _pack_file_list(name: str) -> list[str]:
    """The path list ``npm pack --dry-run`` would put in the tarball."""
    npm = shutil.which("npm")
    if npm is None:
        pytest.skip("npm is not on PATH")
    result = subprocess.run(
        [npm, "pack", "--dry-run", "--json", "--workspace", name],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
        timeout=180,
    )
    assert result.returncode == 0, f"npm pack --dry-run failed for {name}:\n{result.stderr}"
    packed = json.loads(result.stdout)
    assert len(packed) == 1, f"{name}: expected one tarball, got {len(packed)}"
    assert packed[0]["name"] == name
    assert packed[0]["version"] == VERSION
    return [entry["path"] for entry in packed[0]["files"]]


def test_publish_list_is_exactly_the_audited_set() -> None:
    public = {
        name
        for name, (_directory, package) in _all_packages().items()
        if not package.get("private")
    }
    assert public == set(PUBLISHABLE), (
        "a package became publishable without the P-1 audit (or stopped being): "
        f"unexpected={sorted(public - set(PUBLISHABLE))} "
        f"missing={sorted(set(PUBLISHABLE) - public)}"
    )


def test_packages_meant_to_stay_private_are_private() -> None:
    packages = _all_packages()
    for directory in MUST_STAY_PRIVATE:
        name = f"@digithings/{directory}"
        assert name in packages, f"{directory} is not a workspace package"
        _path, package = packages[name]
        assert package.get("private") is True, (
            f"{name} is not imported by any split repo, so it must stay private"
        )


@pytest.mark.parametrize("name", sorted(PUBLISHABLE))
def test_publishable_manifest(name: str) -> None:
    packages = _all_packages()
    directory, package = packages[name]

    assert package["version"] == VERSION, f"{name} must be {VERSION}"
    assert "private" not in package, f"{name} still carries a private flag"
    assert package.get("license") == "MIT", f"{name} must declare its license"
    assert package.get("publishConfig", {}).get("access") == "public", (
        f"{name} must publish with public access"
    )
    assert package.get("repository", {}).get("directory") == f"packages/{directory.name}", (
        f"{name} must point repository.directory at packages/{directory.name}"
    )

    files = package.get("files")
    assert isinstance(files, list) and files, f"{name} must list what it ships"
    assert any(not entry.startswith("!") for entry in files), (
        f"{name} 'files' has only negations, so it ships everything"
    )


def _concrete_targets(directory: Path, target: str) -> list[str]:
    """Expand a glob export into the paths it resolves to, relative to the package."""
    relative = target[2:] if target.startswith("./") else target
    if "*" not in relative:
        return [relative]
    return sorted(
        str(path.relative_to(directory)).replace("\\", "/") for path in directory.glob(relative)
    )


def _glob_match(path: str, pattern: str) -> bool:
    """Minimatch's ``**`` spans zero directories; ``fnmatch``'s ``*`` does not."""
    variants = {pattern, pattern.replace("/**/", "/")}
    if "**/" in pattern:
        variants.add(pattern.replace("**/", ""))
    return any(fnmatch(path, variant) for variant in variants)


def _ships(path: str, files: list[str]) -> bool:
    """Whether a non-negated ``files`` entry covers *path* (npm's coarse rules)."""
    for entry in files:
        if entry.startswith("!"):
            continue
        pattern = entry[2:] if entry.startswith("./") else entry
        if path == pattern or path.startswith(pattern.rstrip("/") + "/"):
            return True
        if _glob_match(path, pattern):
            return True
    return False


@pytest.mark.parametrize("name", sorted(PUBLISHABLE))
def test_exports_are_source_and_resolve(name: str) -> None:
    directory, package = _all_packages()[name]
    exports = package.get("exports")
    assert isinstance(exports, dict) and exports, f"{name} must declare exports"
    files = package.get("files") or []

    targets = _export_targets(exports)
    assert targets, f"{name} has no export targets"
    for target in targets:
        concrete = _concrete_targets(directory, target)
        assert concrete, f"{name}: export {target} matches nothing"
        for path in concrete:
            assert (directory / path).exists(), f"{name}: export {target} is a dangling path"
            assert SOURCE_TARGET.search(path), (
                f"{name}: export {path} is not source (ts/tsx/js/css/json/md)"
            )
            assert not path.startswith("dist/") and "/dist/" not in path, (
                f"{name}: export {path} points at a build output; exports stay TypeScript source"
            )
            assert _ships(path, files), (
                f"{name}: export {path} is not covered by 'files', so the published tarball "
                "would not contain it"
            )


@pytest.mark.parametrize("name", sorted(PUBLISHABLE))
def test_internal_dependencies_are_exact(name: str) -> None:
    _directory, package = _all_packages()[name]
    for section in ("dependencies", "devDependencies", "peerDependencies", "optionalDependencies"):
        for dependency, specifier in package.get(section, {}).items():
            if not dependency.startswith(INTERNAL_SCOPES):
                continue
            assert specifier == VERSION, (
                f"{name}: {section}.{dependency} is {specifier!r}; internal deps are "
                f"pinned exact to {VERSION}, because a published tarball cannot resolve a "
                "workspace"
            )


@pytest.mark.parametrize("name", sorted(PUBLISHABLE))
def test_tarball_carries_only_publishable_files(name: str) -> None:
    paths = _pack_file_list(name)
    asserted_nonempty = [path for path in paths if path.strip()]
    assert asserted_nonempty, f"{name}: the tarball is empty"
    assert "package.json" in paths, f"{name}: the tarball is missing package.json"
    assert "README.md" in paths, f"{name}: the tarball is missing its README"

    terms = _private_term_patterns()
    offenders: list[str] = []
    for path in paths:
        reasons = []
        if SECRET_PATH.search(path):
            reasons.append("secret")
        if TEST_PATH.search(path):
            reasons.append("test")
        if LAN_IP.search(path):
            reasons.append("lan-ip")
        if any(pattern.search(path) for pattern in terms):
            reasons.append("private-term")
        if any(label for label, pattern in client_literals.PATTERNS if pattern.search(path)):
            reasons.append("client-literal")
        if reasons:
            offenders.append(f"{path} ({', '.join(reasons)})")

    assert not offenders, f"{name}: the tarball would ship {'; '.join(offenders)}"


def test_packed_sources_do_not_use_workspace_aliases() -> None:
    """A tarball consumer has no tsconfig paths, so ``@/`` imports cannot ship."""
    packages = _all_packages()
    for name in PUBLISHABLE:
        directory, _package = packages[name]
        offenders: list[str] = []
        for relpath in _pack_file_list(name):
            if not relpath.endswith((".ts", ".tsx")):
                continue
            source = (directory / relpath).read_text(encoding="utf-8")
            for line in source.splitlines():
                stripped = line.lstrip()
                if stripped.startswith(("*", "//")):
                    continue
                match = re.search(r"""(?:from\s+|import\s*\(|require\s*\()["']([^"']+)["']""", line)
                if match and match.group(1).startswith("@/"):
                    offenders.append(f"{relpath}: {match.group(1)}")
        assert not offenders, f"{name} packs workspace aliases: {offenders[:5]}"


def test_ui_declares_imports_used_by_packed_skins() -> None:
    package = _package_json(PACKAGES / "ui")
    deps = {**package.get("dependencies", {}), **package.get("peerDependencies", {})}
    for dependency in ("cmdk", "@assistant-ui/react-lexical"):
        assert dependency in deps, f"packages/ui must declare {dependency}"


def test_design_declares_next_for_the_font_export() -> None:
    package = _package_json(PACKAGES / "design")
    assert "next" in package.get("peerDependencies", {})
    assert package.get("peerDependenciesMeta", {}).get("next", {}).get("optional") is True
