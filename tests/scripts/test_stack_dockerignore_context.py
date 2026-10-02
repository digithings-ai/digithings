"""Every `scripts/` file the stack Dockerfile COPYs must survive `.dockerignore`.

The root `.dockerignore` excludes `scripts` wholesale, because none of the many
service images built from the root context need it. Anything the Cloudflare
stack image (`Dockerfile.digithings-stack-cloudflare`) copies out of that
directory therefore has to be re-included with a `!scripts/<path>` line, or the
build fails at the COPY with

    failed to calculate checksum of ref ...: "/scripts/<name>": not found

That failure mode is invisible until the production deploy job runs: the stack
deploy workflow's `check` job only typechecks and unit-tests the worker, it
never builds the image (#4988, where two COPY lines added by #4987 were missing
their re-includes and took the deploy down).

These tests read the two committed files, so a future `COPY scripts/...` without
its re-include fails the normal unit suite instead of the deploy.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
STACK_DOCKERFILE = REPO_ROOT / "Dockerfile.digithings-stack-cloudflare"
DOCKERIGNORE = REPO_ROOT / ".dockerignore"

# Directory the `.dockerignore` excludes wholesale, so every COPY out of it needs
# a re-include. Add to this only together with the corresponding exclusion line.
EXCLUDED_ROOTS = ("scripts",)

_COPY_LINE = re.compile(r"^COPY\s+(?P<body>.+)$")


def _dockerignore_lines() -> list[str]:
    return [
        line.strip()
        for line in DOCKERIGNORE.read_text(encoding="utf-8").splitlines()
        if line.strip() and not line.strip().startswith("#")
    ]


def _reincluded_paths() -> set[str]:
    """`!path` entries, normalised without the leading `!`."""
    return {line[1:].strip().strip("/") for line in _dockerignore_lines() if line.startswith("!")}


def _logical_lines() -> list[str]:
    """Dockerfile instructions with `\\` continuations joined."""
    text = STACK_DOCKERFILE.read_text(encoding="utf-8")
    joined = re.sub(r"\\\s*\n\s*", " ", text)
    return [line.strip() for line in joined.splitlines()]


def _copied_scripts_paths() -> list[str]:
    """Source paths under an excluded root that the stack Dockerfile COPYs."""
    found: list[str] = []
    for line in _logical_lines():
        if not line.upper().startswith("COPY "):
            continue
        match = _COPY_LINE.match(line)
        assert match is not None, f"unparsed COPY instruction: {line}"
        tokens = match.group("body").split()
        for source in tokens[:-1]:  # last token is the destination
            source = source.strip("\"'").removeprefix("./").strip("/")
            if source.split("/")[0] in EXCLUDED_ROOTS:
                found.append(source)
    return sorted(found)


def _ancestors(path: str) -> list[str]:
    parts = path.split("/")
    return ["/".join(parts[:index]) for index in range(1, len(parts))]


def test_stack_dockerfile_copies_from_the_excluded_scripts_root() -> None:
    """Guards the premise: a vacuous copy set would make the rest tautological."""
    copied = _copied_scripts_paths()
    assert copied, (
        "no `COPY scripts/...` found in Dockerfile.digithings-stack-cloudflare — if "
        "the COPY lines moved, the exclusion checks below have stopped meaning anything"
    )


def test_excluded_roots_are_still_excluded() -> None:
    """The re-includes are load-bearing only while `scripts` stays excluded."""
    lines = _dockerignore_lines()
    for root in EXCLUDED_ROOTS:
        assert root in lines, (
            f"`.dockerignore` no longer excludes `{root}` — drop the now-redundant "
            f"`!{root}/...` re-includes and re-check this file's premise"
        )


@pytest.mark.parametrize("source", _copied_scripts_paths())
def test_copied_script_is_reincluded_in_dockerignore(source: str) -> None:
    """`!scripts/<path>` (or a re-included parent) must exist for every COPY."""
    reincluded = _reincluded_paths()
    candidates = {source, *_ancestors(source)}
    assert candidates & reincluded, (
        f"Dockerfile.digithings-stack-cloudflare COPYs `{source}` but `.dockerignore` "
        f"has no matching `!{source}` — the image build will fail with "
        f'"failed to calculate checksum ... /{source}: not found". Add the re-include.'
    )


def test_occ_ticket_seed_scripts_are_reincluded() -> None:
    """The #4988 regression itself, named so a revert is obviously wrong.

    `seed_chroma.sh` invokes `python3 -m scripts.build_occ_tickets_seed`, which
    imports `scripts.index_occ_tickets`; without both files in the image the
    OCC `occ_tickets` seed silently degrades to a missing-file WARN and the
    fan-out searches an empty index.
    """
    reincluded = _reincluded_paths()
    for required in ("scripts/index_occ_tickets.py", "scripts/build_occ_tickets_seed.py"):
        assert required in reincluded, f"`.dockerignore` must re-include `{required}`"
