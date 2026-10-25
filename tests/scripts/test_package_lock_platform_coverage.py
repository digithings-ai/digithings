"""Pins the Linux native bindings into package-lock.json, so a truncated lock fails here.

WHAT WENT WRONG. `@tailwindcss/oxide` declares twelve platform `optionalDependencies`,
but the root lock carried `oxide-darwin-arm64` alone — every Linux entry was missing. So
`npm ci` put no Linux oxide binary in the tree, and six build files papered over it by
hand-installing `@tailwindcss/oxide-linux-x64-{gnu,musl}`: three CI lanes, both Cloudflare
Pages build scripts, and `apps/digichat/Dockerfile`. Their comments described the gap
as intrinsic ("the one native tree the root lock cannot supply"). It was not — it was a
truncated lock, repaired by grafting the missing entries at their locked versions.

`unrs-resolver` had the same gap (one of nineteen bindings locked). That one never broke a
build, which is worse: it self-heals through its `napi-postinstall` postinstall, so every
install silently made a network fetch to replace a lock entry that should have been there.

WHAT THIS PINS. Removing those six hand-installs removed the safety net with them. Nothing
else in the repo asserts the lock still carries the bindings, and the truncation is easy to
reintroduce — it is what `npm install --package-lock-only` produces when `node_modules` is
present. Without this test that regression is silent until an Alpine image fails to build
on `main`, or Cloudflare Pages ships a stylesheet built by a fallback path.

THE ANALYSIS LIVES IN ONE PLACE. The binding logic is `scripts/check_deploy_lane_contract.py`'s
`platform_bindings`, `binding_defects` and `libc_defects`, and this file imports it rather
than keeping a second copy. That check reads every family in the lock — the sharp tree under
`apps/digiquant-app/node_modules` is what the root-only version of this test could not see
(#6062) — so this file is now a pin on the two families that broke, plus the libc selectors,
and the deploy lane's own check is the wider net.

The expected set is derived from each parent's own `optionalDependencies` rather than
hardcoded, so a version bump does not need this file edited — it only needs the lock to
stay complete.

`wasm32-wasi` is excluded deliberately: `cpu: ["wasm32"]` matches no real platform, so npm
never installs it, and its nested `@emnapi` subtree would collide with the `@emnapi/runtime`
already hoisted at the top level.

This lane fires on lockfile edits because `package-lock.json` is in the `ruff_and_scripts`
path filter (`scripts/ci_paths.yaml`). Note that `.github/workflows/test-web.yml` is NOT in
that filter, which is why this guard lives on the lock and not on a workflow's text.
"""

from __future__ import annotations

import importlib.util
from pathlib import Path
from types import ModuleType

import pytest

pytestmark = pytest.mark.unit

REPO_ROOT = Path(__file__).resolve().parents[2]
LOCK = REPO_ROOT / "package-lock.json"
CHECK = REPO_ROOT / "scripts" / "check_deploy_lane_contract.py"

#: The families that broke, and the lock key each parent lives at. Named so this test
#: fails if the shared analysis stops seeing them, instead of passing over an empty set.
BROKEN_FAMILIES = ("node_modules/@tailwindcss/oxide", "node_modules/unrs-resolver")

#: The two the deleted hand-installs covered — glibc runners and Alpine images.
REQUIRED_LINUX_X64 = {
    "@tailwindcss/oxide-linux-x64-gnu": "glibc",
    "@tailwindcss/oxide-linux-x64-musl": "musl",
    "@unrs/resolver-binding-linux-x64-gnu": "glibc",
    "@unrs/resolver-binding-linux-x64-musl": "musl",
}


def _check_module() -> ModuleType:
    spec = importlib.util.spec_from_file_location("check_deploy_lane_contract", CHECK)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


CHECK_MODULE = _check_module()


def _packages() -> dict[str, object]:
    return CHECK_MODULE.load_lock(LOCK)


@pytest.mark.unit
def test_every_installable_platform_binding_is_locked() -> None:
    """A parent that declares a binding must have a lock entry for it, at its version."""
    packages = _packages()

    analysed = {parent for parent, _declared in CHECK_MODULE.platform_bindings(packages)}
    missing_families = [family for family in BROKEN_FAMILIES if family not in analysed]
    assert not missing_families, (
        "the shared analysis no longer sees these platform families in the lock, so the "
        f"guard below would pass over an empty set: {missing_families}"
    )

    missing, mismatched = CHECK_MODULE.binding_defects(packages)
    assert not missing, (
        "package-lock.json is missing platform bindings its own tree declares: "
        f"{missing}. This is what a regenerate with node_modules present produces; "
        "regenerate the lock with npm 10.9.9 (the lane's `node-version: 22`) rather than "
        "hand-installing the binding in CI lanes, build scripts and Dockerfiles."
    )
    assert not mismatched, (
        "a platform binding is locked at a version its parent does not declare, so the JS "
        f"wrapper and the native binary would disagree: {mismatched}"
    )


@pytest.mark.unit
def test_the_linux_x64_bindings_carry_the_libc_that_selects_them() -> None:
    """`libc` is what makes npm pick gnu on the runners and musl in the Alpine images.

    Without it npm filters on os/cpu alone and would install both variants everywhere, so
    an entry that loses the field is a real regression even though it stays present. The
    four that must carry it, and the libc each one needs, are the check's own set: this
    test would be a second copy of that decision, and the two would drift.
    """
    assert CHECK_MODULE.REQUIRED_LINUX_X64 == REQUIRED_LINUX_X64, (
        "the required-bindings set moved; update this test with it so the pin stays explicit"
    )
    defects = CHECK_MODULE.libc_defects(_packages())
    assert not defects, (
        "a required Linux x64 binding lost the fields that select it: "
        f"{defects}. Restore them from the last lockfile that had them; the versions do not move."
    )


@pytest.mark.unit
def test_the_bindings_are_not_hand_installed_anywhere() -> None:
    """The lock supplies them now; a reintroduced pin would shadow what the lock resolves.

    Commands only — the build scripts' comments name the package while explaining why it is
    no longer installed, and matching prose would fail on the explanation.
    """
    sites = [
        REPO_ROOT / ".github" / "workflows" / "test-web.yml",
        REPO_ROOT / ".github" / "workflows" / "test-digichat.yml",
        REPO_ROOT / ".github" / "workflows" / "test-dashboard.yml",
        REPO_ROOT / "scripts" / "build-digithings.sh",
        REPO_ROOT / "scripts" / "build-digiquant.sh",
        REPO_ROOT / "apps" / "digichat" / "Dockerfile",
    ]
    for site in sites:
        assert site.exists(), f"{site} moved — update this guard"
        commands = "\n".join(
            line
            for line in site.read_text(encoding="utf-8").splitlines()
            if not line.lstrip().startswith("#")
        )
        assert "@tailwindcss/oxide" not in commands, (
            f"{site.relative_to(REPO_ROOT)} hand-installs the oxide binding again — "
            "the lock carries every installable platform entry, so this pin is redundant "
            "and can shadow the resolved one"
        )
