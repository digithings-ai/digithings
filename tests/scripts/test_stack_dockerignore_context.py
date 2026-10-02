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

`pytestmark = pytest.mark.unit` is load-bearing, not boilerplate: `ci.yml`
collects with `-m "unit or baseline"` and `make test-unit` with `-m unit`, so a
module without the marker is silently deselected and the guard never runs
(same trap `test-digifetch.yml:50-53` calls out).
"""

from __future__ import annotations

import fnmatch
import re
from pathlib import Path

import pytest

pytestmark = pytest.mark.unit

REPO_ROOT = Path(__file__).resolve().parents[2]
STACK_DOCKERFILE = REPO_ROOT / "Dockerfile.digithings-stack-cloudflare"
DOCKERIGNORE = REPO_ROOT / ".dockerignore"

# Directory the `.dockerignore` excludes wholesale, so every COPY out of it needs
# a re-include. Add to this only together with the corresponding exclusion line.
EXCLUDED_ROOTS = ("scripts",)

_COPY_LINE = re.compile(r"^COPY\s+(?P<body>.+)$")


def _dockerignore_patterns() -> list[str]:
    """Effective patterns, comments and blanks dropped, order preserved."""
    return [
        line.strip()
        for line in DOCKERIGNORE.read_text(encoding="utf-8").splitlines()
        if line.strip() and not line.strip().startswith("#")
    ]


def _dockerignore_lines() -> list[str]:
    return _dockerignore_patterns()


def _reincluded_paths() -> set[str]:
    """`!path` entries, normalised without the leading `!`."""
    return {line[1:].strip().strip("/") for line in _dockerignore_lines() if line.startswith("!")}


def _is_included(path: str, patterns: list[str] | None = None) -> bool:
    """Docker's `.dockerignore` semantics: last matching pattern wins.

    A bare directory pattern (`scripts`) excludes the whole subtree; a later
    `!scripts/<path>` re-includes that entry. Order matters, so this cannot be a
    set lookup — verified against Docker 29.2.1 with a two-line fixture: moving
    `!scripts/thing.py` *above* `scripts` fails the build with
    `"not found"`, so the re-include must come after the exclusion.
    """
    patterns = _dockerignore_patterns() if patterns is None else patterns
    included = True
    for pattern in patterns:
        negated = pattern.startswith("!")
        candidate = pattern[1:] if negated else pattern
        candidate = candidate.strip().rstrip("/")
        if candidate in ("", "**"):
            matches = True
        elif candidate == path or path.startswith(f"{candidate}/"):
            matches = True
        elif any(ch in candidate for ch in "*?["):
            matches = fnmatch.fnmatch(path, candidate) or fnmatch.fnmatch(
                f"{path}/", f"{candidate}/*"
            )
        else:
            matches = False
        if matches:
            included = negated
    return included


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
        body = match.group("body")
        if body.startswith("["):  # JSON-array form: COPY ["src", "dst"]
            import json

            tokens = json.loads(body)
            assert isinstance(tokens, list), f"unparsed COPY JSON form: {line}"
            sources = tokens[:-1]
        else:
            sources = body.split()[:-1]  # last token is the destination
        for source in sources:
            source = str(source).strip("\"'").removeprefix("./").strip("/")
            if source.split("/")[0] in EXCLUDED_ROOTS:
                found.append(source)
    return sorted(found)


def _all_copied_paths() -> list[str]:
    """Every COPY source the stack Dockerfile names, excluded roots or not."""
    found: list[str] = []
    for line in _logical_lines():
        if not line.upper().startswith("COPY "):
            continue
        match = _COPY_LINE.match(line)
        assert match is not None, f"unparsed COPY instruction: {line}"
        for source in match.group("body").split()[:-1]:
            found.append(source.strip("\"'").removeprefix("./").strip("/"))
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
def test_copied_script_survives_dockerignore(source: str) -> None:
    """Each `COPY scripts/...` source must end up in the build context."""
    patterns = _dockerignore_patterns()
    assert _is_included(source, patterns), (
        f"Dockerfile.digithings-stack-cloudflare COPYs `{source}` but `.dockerignore` "
        f"excludes it — the image build will fail with "
        f'"failed to calculate checksum ... /{source}: not found". Add a `!{source}` '
        f"re-include AFTER the exclusion line (last match wins)."
    )


@pytest.mark.parametrize("source", _all_copied_paths())
def test_no_copied_source_is_excluded(source: str) -> None:
    """Blanket check: no COPY source, in any excluded root, is filtered out."""
    patterns = _dockerignore_patterns()
    assert _is_included(source, patterns), (
        f"`{source}` is COPYed by Dockerfile.digithings-stack-cloudflare but excluded "
        f"by `.dockerignore`; the production image build fails on it"
    )


def test_reinclude_above_the_exclusion_is_detected() -> None:
    """Docker is last-match-wins, so `!scripts/x` above `scripts` does nothing."""
    reordered = ["!scripts/thing.py", "scripts", "tests"]
    assert not _is_included("scripts/thing.py", reordered)
    assert _is_included("scripts/thing.py", ["scripts", "!scripts/thing.py"])


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
