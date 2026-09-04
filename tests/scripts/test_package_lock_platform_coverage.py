"""Pins the Linux native bindings into package-lock.json, so a truncated lock fails here.

WHAT WENT WRONG. `@tailwindcss/oxide` declares twelve platform `optionalDependencies`,
but the root lock carried `oxide-darwin-arm64` alone — every Linux entry was missing. So
`npm ci` put no Linux oxide binary in the tree, and six build files papered over it by
hand-installing `@tailwindcss/oxide-linux-x64-{gnu,musl}`: three CI lanes, both Cloudflare
Pages build scripts, and `frontend/digichat/Dockerfile`. Their comments described the gap
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

import json
from pathlib import Path
from typing import Any  # score:allow untyped any — scored-lint: heterogeneous lockfile entries

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
LOCK = REPO_ROOT / "package-lock.json"

# Parent package -> the prefix its platform bindings are published under.
NATIVE_FAMILIES = {
    "node_modules/@tailwindcss/oxide": "@tailwindcss/oxide-",
    "node_modules/unrs-resolver": "@unrs/resolver-binding-",
}

# Never installable: no real platform reports cpu "wasm32".
EXCLUDED = "wasm32-wasi"

# The two the deleted hand-installs covered — glibc runners and Alpine images.
REQUIRED_LINUX_X64 = {
    "@tailwindcss/oxide-linux-x64-gnu": "glibc",
    "@tailwindcss/oxide-linux-x64-musl": "musl",
    "@unrs/resolver-binding-linux-x64-gnu": "glibc",
    "@unrs/resolver-binding-linux-x64-musl": "musl",
}


def _packages() -> dict[str, Any]:
    return json.loads(LOCK.read_text(encoding="utf-8"))["packages"]


@pytest.mark.unit
def test_every_installable_platform_binding_is_locked() -> None:
    """A parent that declares a binding must have a lock entry for it, at its version."""
    packages = _packages()
    missing: list[str] = []
    mismatched: list[str] = []

    for parent_key, prefix in NATIVE_FAMILIES.items():
        parent = packages.get(parent_key)
        assert parent is not None, f"{parent_key} absent from the lock"
        declared = parent.get("optionalDependencies") or {}
        assert declared, f"{parent_key} declares no optionalDependencies — check the family map"

        for name, version in declared.items():
            if EXCLUDED in name:
                continue
            assert name.startswith(prefix), f"unexpected optionalDependency {name} on {parent_key}"
            entry = packages.get(f"node_modules/{name}")
            if entry is None:
                missing.append(f"{name}@{version}")
            elif entry.get("version") != version:
                mismatched.append(
                    f"{name}: lock has {entry.get('version')}, parent wants {version}"
                )

    assert not missing, (
        "package-lock.json is missing platform bindings its own tree declares: "
        f"{sorted(missing)}. This is what a regenerate with node_modules present produces; "
        "graft the entries back at their locked versions rather than hand-installing them "
        "in CI lanes, build scripts and Dockerfiles."
    )
    assert not mismatched, (
        "a platform binding is locked at a version its parent does not declare, so the JS "
        f"wrapper and the native binary would disagree: {sorted(mismatched)}"
    )


@pytest.mark.unit
def test_the_linux_x64_bindings_carry_the_libc_that_selects_them() -> None:
    """`libc` is what makes npm pick gnu on the runners and musl in the Alpine images.

    Without it npm filters on os/cpu alone and would install both variants everywhere, so
    an entry that loses the field is a real regression even though it stays present.
    """
    packages = _packages()
    for name, libc in REQUIRED_LINUX_X64.items():
        entry = packages.get(f"node_modules/{name}")
        assert entry is not None, f"{name} absent — the Linux builds have no native binary"
        assert entry.get("libc") == [libc], (
            f"{name} should declare libc [{libc}], got {entry.get('libc')}"
        )
        assert entry.get("os") == ["linux"], (
            f"{name} should declare os [linux], got {entry.get('os')}"
        )
        assert entry.get("cpu") == ["x64"], (
            f"{name} should declare cpu [x64], got {entry.get('cpu')}"
        )
        assert entry.get("optional") is True, f"{name} must stay optional: true"


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
        REPO_ROOT / "frontend" / "digichat" / "Dockerfile",
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
