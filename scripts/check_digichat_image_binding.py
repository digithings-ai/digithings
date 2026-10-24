#!/usr/bin/env python3
"""Assert a digichat image is bound to the commit its tag names (DIG-1242).

The problem
-----------
Until this script existed, "which commit is running in prod?" was answerable
only by trusting whoever last ran a build. A git tag (``digichat-v2.3.2``) did
resolve to a commit, but nothing tied the *image* to it: the ACR ledger held
hand-pushed tags (``v2.1.0-error1``..``-error3``, ``v2.0.0-main.7263272-counter1``..``9``,
``v2.2.0-boot1``) that no workflow produced, and the image itself carried no
annotation naming its build. Digest pinning closes part of that gap, but a
digest alone says only *that* bytes are fixed, not *which source* they are.

The check
---------
Resolve the release tag to a commit, read the image's
``org.opencontainers.image.revision``, and require agreement. Both the tag's
version and the image's version must equal ``apps/digichat/package.json``.

Design note -- why this takes facts on stdin
--------------------------------------------
The checker is pure. It does not shell out to git, ``az`` or ``docker``, and it
does not read a registry. A caller collects the facts and pipes them in. That
keeps every branch here testable offline, and it keeps a network outage from
reading as a binding failure -- a missing fact is a *verdict* (``UNKNOWN``), never
a silent pass.

Facts (``facts.json`` or stdin)
-------------------------------
===========================  ===============================================
``version``                 the image's ``org.opencontainers.image.version``
``package_version``         ``apps/digichat/package.json`` version **at the tag**
``tag``                     the release tag, e.g. ``digichat-v2.3.2``
``tag_commit``              the commit that tag resolves to (full sha)
``image_ref``               what was deployed, e.g. ``registry/digichat:v2.3.2``
``image_revision``          the image's ``org.opencontainers.image.revision``
``image_digest``            ``registry/digichat@sha256:...`` (optional; absence
                            is a note, not a failure)
===========================  ===============================================

Two caller traps this deliberately does not paper over: ``docker inspect``
without ``--format`` emits a JSON *array* and is rejected as bad input, and
``a; b | checker`` pipes only ``b``. The full working recipe, with both traps
explained, is in ``docs/ops/digichat-datatap-aca.md`` §2.

Fail closed on missing facts
----------------------------
An image with no ``org.opencontainers.image.revision`` **fails**. This is the
deliberate choice that makes the script worth having: every image built before
DIG-1242 looks exactly like that, so "no annotation" is the common case here and
cannot be allowed to read as fine.

Usage
-----
::

    # offline, from a facts file
    python3 scripts/check_digichat_image_binding.py --facts facts.json

    # from the real world (recipe in docs/ops/digichat-datatap-aca.md)
    jq -n --arg tag "$TAG" ... '{...}' \
      | python3 scripts/check_digichat_image_binding.py --facts -

Exit codes: ``0`` bound, ``1`` not bound (a real finding), ``2`` bad input.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any  # score:allow untyped any -- JSON payload from a caller

TAG_RE = re.compile(r"^digichat-v(?P<version>[0-9]+\.[0-9]+\.[0-9]+)$")
SHA_RE = re.compile(r"^[0-9a-f]{7,40}$")

#: Facts a caller may omit. Their absence is a finding, never a pass.
REQUIRED_FACTS = ("version", "package_version", "tag", "image_ref")


@dataclass
class Result:
    """Outcome of one binding check."""

    ok: bool
    commit: str | None
    digest: str | None
    problems: list[str] = field(default_factory=list)
    unknown: list[str] = field(default_factory=list)

    def as_dict(self) -> dict[str, Any]:
        return {
            "ok": self.ok,
            "commit": self.commit,
            "digest": self.digest,
            "problems": list(self.problems),
            "unknown": list(self.unknown),
        }


def _clean(value: Any) -> str | None:
    """Normalise an optional fact to a non-empty trimmed string, else None."""
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def _sha_eq(a: str, b: str) -> bool:
    """Compare shas by their common prefix (a label may be abbreviated)."""
    width = min(len(a), len(b))
    return width >= 7 and a[:width].lower() == b[:width].lower()


def check(facts: dict[str, Any]) -> Result:
    """Return the verdict for one set of facts. Never raises on bad input."""
    problems: list[str] = []
    unknown: list[str] = []

    version = _clean(facts.get("version"))
    package_version = _clean(facts.get("package_version"))
    tag = _clean(facts.get("tag"))
    tag_commit = _clean(facts.get("tag_commit"))
    image_digest = _clean(facts.get("image_digest"))
    image_revision = _clean(facts.get("image_revision"))

    # --- the facts we cannot do without -------------------------------
    for name in REQUIRED_FACTS:
        if _clean(facts.get(name)) is None:
            problems.append(f"missing required fact: {name}")

    # --- the tag must name a version, and that version must be current
    if tag is not None:
        m = TAG_RE.match(tag)
        if not m:
            problems.append(f"tag {tag!r} is not a digichat-vX.Y.Z release tag")
        else:
            tag_version = m.group("version")
            if version is not None and tag_version != version:
                problems.append(
                    f"tag {tag} names version {tag_version}, "
                    f"but the image reports version {version}"
                )

    if version is not None and package_version is not None and version != package_version:
        problems.append(
            f"image version {version} does not match "
            f"apps/digichat/package.json version {package_version}"
        )

    # --- the tag must resolve ------------------------------------------
    # An unresolvable tag is a failure, not a footnote: with nothing to bind
    # against, a valid-looking image revision proves only that *something*
    # built it. That is the exact hole DIG-1242 found.
    if tag_commit is None:
        problems.append(
            f"tag {tag or '(unset)'} does not resolve to a commit, "
            "so the image cannot be bound to a release"
        )
    elif not SHA_RE.match(tag_commit.lower()):
        problems.append(f"tag_commit {tag_commit!r} is not a commit sha")

    # --- the image must name the commit --------------------------------
    if image_revision is None:
        problems.append(
            "image carries no org.opencontainers.image.revision annotation, "
            "so it cannot be bound to a commit (expected for every image built "
            "before DIG-1242)"
        )
    elif not SHA_RE.match(image_revision.lower()):
        problems.append(f"org.opencontainers.image.revision {image_revision!r} is not a commit sha")

    # --- and the two must agree -----------------------------------------
    if tag_commit and image_revision and SHA_RE.match(tag_commit.lower()):
        if not SHA_RE.match(image_revision.lower()) or not _sha_eq(image_revision, tag_commit):
            problems.append(
                f"image revision {image_revision} does not match the commit "
                f"{tag_commit} named by {tag}"
            )

    # A digest is not required to bind, but a missing one on a released image
    # means the caller could not read the registry, so say so rather than let
    # the verdict imply a stronger check than ran.
    if image_digest is None:
        unknown.append("no image digest supplied; binding checked, immutability not")

    return Result(
        ok=not problems,
        commit=tag_commit or image_revision,
        digest=image_digest,
        problems=problems,
        unknown=unknown,
    )


def _load_facts(source: str) -> dict[str, Any]:
    if source == "-":
        raw = sys.stdin.read()
    else:
        raw = Path(source).read_text()
    payload = json.loads(raw)
    if not isinstance(payload, dict):
        raise ValueError("facts must be a JSON object")
    return payload


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(
        description="Assert a digichat image is bound to its release tag's commit."
    )
    ap.add_argument(
        "--facts",
        required=True,
        help="path to a JSON facts object, or '-' for stdin",
    )
    ap.add_argument("--json", action="store_true", help="emit the verdict as JSON")
    args = ap.parse_args(argv)

    try:
        facts = _load_facts(args.facts)
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        print(f"error: could not read facts: {exc}", file=sys.stderr)
        return 2

    result = check(facts)

    if args.json:
        print(json.dumps(result.as_dict(), indent=2))
        return 0 if result.ok else 1

    if result.ok:
        print(f"OK   bound: {result.commit} via {facts.get('tag')} -> {result.digest}")
    else:
        print(f"FAIL not bound ({facts.get('image_ref')})")
        for problem in result.problems:
            print(f"  - {problem}")
    for note in result.unknown:
        print(f"  note: {note}")
    return 0 if result.ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
