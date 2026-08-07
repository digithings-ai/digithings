"""Each deploy build check must watch every workspace its build actually compiles.

Both static sites deploy through Cloudflare Pages running one build script, and each
site's `Deploy: … build check` workflow re-runs that script on PRs matching its
``paths:`` filter. Those filters are maintained by hand against a moving import graph and
fell behind it: `frontend/digithings-web` took a dependency on `@digithings/digichat-ui`
in #1384, and the digithings.ai filter was never updated. PR #1490 then edited
`frontend/digichat-ui/src/DigiChatSession.tsx` — a file that site renders — alongside
digichat-only changes, matched no glob in that filter, and ran no deploy build check at
all. PR #1859 repeated it.

So this derives the answer instead of restating it. For each site: read the workspaces the
build script compiles, walk their transitive workspace dependencies, and require a glob for
every directory in that closure. A future dependency edge fails here until the filter
learns about it.

That guarantee is real-time for the case that matters. A PR adding a workspace dependency
rewrites the root `package-lock.json` (npm mirrors each workspace's deps there, and
`test-web.yml`'s `npm ci` hard-fails if manifest and lock disagree), and `package-lock.json`
is in `ruff_and_scripts` — so this test runs on that PR, not on some later one. The one
half that is not yet armed is deletion: a PR that *removes* a glob from a deploy workflow
touches only `.github/workflows/`, which reaches `ruff_and_scripts` only once #1964 adds
those two files to it.

Deliberately out of scope: the root ``npm install`` resolves all eight workspaces, so a
broken manifest in any of them fails both builds before either compiles. Gating both checks
on all eight would fire them on every unrelated workspace — the trade #1956 declines for
`**/package.json`, for the same reason. This test asserts *build* inputs, not *install*
inputs.
"""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any  # score:allow untyped any — parsed JSON/YAML documents

import pytest
import yaml

REPO_ROOT = Path(__file__).resolve().parents[2]

#: (deploy build check workflow, the build script it re-runs), one per static site.
DEPLOY_CHECKS = [
    pytest.param(
        REPO_ROOT / ".github" / "workflows" / "deploy-digithings-cloudflare.yml",
        REPO_ROOT / "scripts" / "build-digithings.sh",
        id="digithings.ai",
    ),
    pytest.param(
        REPO_ROOT / ".github" / "workflows" / "deploy-digiquant-cloudflare.yml",
        REPO_ROOT / "scripts" / "build-digiquant.sh",
        id="digiquant.io",
    ),
]

#: A line that builds a workspace. `run build:analyze` is deliberately not one.
_BUILD_LINE = re.compile(r"\bnpm\b.*\brun\s+build(?:\s|$)")
#: npm accepts `--workspace X`, `--workspace=X`, `-w X` and `-w=X`, and either argument
#: order — the repo uses several. Matching only one form would let a stylistic rewrite
#: silently drop a workspace out of the closure and leave this guard green.
_WORKSPACE_FLAG = re.compile(r"(?:--workspace|-w)[=\s]+(\S+)")

pytestmark = pytest.mark.unit


def _workspace_packages() -> dict[str, tuple[str, set[str]]]:
    """Map every workspace package name to its repo-relative dir and workspace deps.

    Globbed from the root manifest's own ``workspaces`` patterns rather than a hardcoded
    list, so `frontend/digiweb/brand` and `frontend/digiweb/scripts` — directories with no
    package.json, and therefore not workspaces — are excluded for the right reason.
    """
    root: dict[str, Any] = json.loads((REPO_ROOT / "package.json").read_text(encoding="utf-8"))
    manifests = sorted(
        {m for pattern in root["workspaces"] for m in REPO_ROOT.glob(f"{pattern}/package.json")}
    )
    assert manifests, "no workspace manifests found — the root `workspaces` patterns moved"

    packages: dict[str, tuple[str, set[str]]] = {}
    for manifest in manifests:
        pkg: dict[str, Any] = json.loads(manifest.read_text(encoding="utf-8"))
        deps = {
            name
            for field in ("dependencies", "devDependencies", "peerDependencies")
            for name in (pkg.get(field) or {})
            if name.startswith("@digithings/")
        }
        packages[pkg["name"]] = (str(manifest.parent.relative_to(REPO_ROOT)), deps)
    return packages


def _built_workspaces(build_script: Path) -> list[str]:
    """The workspace token of every ``npm … run build`` line in a build script.

    Every build line must yield a token. Returning only the ones a single regex form
    happens to match would shrink the closure on a stylistic rewrite and leave the caller's
    assertion passing over a workspace nobody watches — the failure this whole file exists
    to prevent, reintroduced one level down.
    """
    tokens: list[str] = []
    for line in build_script.read_text(encoding="utf-8").splitlines():
        stripped = line.strip()
        if stripped.startswith("#") or not _BUILD_LINE.search(stripped):
            continue
        flag = _WORKSPACE_FLAG.search(stripped)
        assert flag, f"{build_script.name}: cannot tell which workspace this builds: {stripped!r}"
        tokens.append(flag.group(1))
    assert tokens, f"{build_script.name} builds no workspace — did the invocation change?"
    return tokens


def _build_input_dirs(build_script: Path) -> set[str]:
    """Every workspace dir a build script compiles, transitively."""
    packages = _workspace_packages()
    # npm takes a workspace by name or by path, and the repo uses both spellings.
    by_token = {name: name for name in packages} | {
        directory: name for name, (directory, _) in packages.items()
    }

    pending = []
    for token in _built_workspaces(build_script):
        assert token in by_token, (
            f"{build_script.name} builds '{token}', which is not a workspace. "
            f"Known: {sorted(by_token)}"
        )
        pending.append(by_token[token])

    closure: set[str] = set()
    while pending:
        name = pending.pop()
        assert name in packages, f"'{name}' is depended on but is not a workspace in this repo"
        directory, deps = packages[name]
        if directory in closure:
            continue
        closure.add(directory)
        pending.extend(deps)
    return closure


def _trigger_paths(workflow: Path) -> list[str]:
    # PyYAML resolves a bare top-level `on:` key to the boolean True (YAML 1.1), so the
    # trigger block is not reachable under the string "on".
    parsed: dict[Any, Any] = yaml.safe_load(workflow.read_text(encoding="utf-8"))
    return parsed[True]["pull_request"]["paths"]


def _closure_for(site: str) -> set[str]:
    """The build-input closure of one site, selected by id rather than list position."""
    workflow, build_script = next(p.values for p in DEPLOY_CHECKS if p.id == site)
    assert isinstance(build_script, Path) and isinstance(workflow, Path)
    return _build_input_dirs(build_script)


@pytest.mark.parametrize(("workflow", "build_script"), DEPLOY_CHECKS)
def test_deploy_check_watches_every_workspace_it_builds(workflow: Path, build_script: Path) -> None:
    paths = _trigger_paths(workflow)
    missing = sorted(d for d in _build_input_dirs(build_script) if f"{d}/**" not in paths)
    assert not missing, (
        f"{workflow.name} does not watch {missing}, which {build_script.name} compiles. "
        f"An edit there would run neither this check nor any production `next build`. "
        f"Add each as '<dir>/**' to the `paths:` filter."
    )


def test_digichat_ui_is_a_digithings_build_input_but_not_a_digiquant_one() -> None:
    """Pin the asymmetry, so the one-sided fix stays legible.

    Only digithings.ai gained an entry. A reader who finds one workflow changed and the
    other untouched should be able to see that this was computed, not overlooked.
    """
    digithings = _closure_for("digithings.ai")
    digiquant = _closure_for("digiquant.io")
    assert "frontend/digichat-ui" in digithings
    assert "frontend/digichat-ui" not in digiquant
    # The walk follows dependencies, not dependents: `digichat` consumes digichat-ui but is
    # built by neither site, so it must not be pulled in. Each check watches its own inputs,
    # never all eight workspaces.
    assert "frontend/digichat" not in digithings | digiquant
