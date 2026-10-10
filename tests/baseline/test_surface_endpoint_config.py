"""Baseline ratchet: the number of hard-coded company endpoint literals.

DIG-2703 wires every surface (dashboard, previews, web apps, TUIs, the DigiChat
dev env) to one local/cloud config. This test does not decide that config's
shape - it measures the thing the migration has to drive to zero, so the drift
is visible in every PR instead of being rediscovered at review time.

Design rules this file follows deliberately:

* The detector is proven on a synthetic fixture BEFORE any negative case is
  believed. A negative assertion against a scanner that never fires is
  vacuous and reads exactly like a pass.
* Enumeration is proven non-empty (file count AND scanned bytes). A zero-scan
  must never satisfy the pin.
* The scan reads the git INDEX via ``git ls-files``. Untracked files are
  therefore invisible to it. That is correct for a CI gate (the runner checks
  out committed state) and is documented rather than worked around.
* The pin is an exact per-host mapping, not a total. "Something moved" has to
  name what moved. Updating the pin is the migration step, in the open.

Scope note: the pattern covers company-owned hosts only. Third-party hosts,
``example.com``-shaped placeholders, local ports and the client's own domains
are all outside it on purpose - pinning those would couple this gate to
vendors and to client work it has no business watching.
"""

from __future__ import annotations

import collections
import pathlib
import re
import subprocess

import pytest

pytestmark = pytest.mark.baseline

REPO_ROOT = pathlib.Path(__file__).resolve().parents[2]

# A company-owned endpoint host. The first label may not be "*", so wildcard
# templates such as ``https://*.digithings.ai`` do not match. Matched anywhere
# in the line, not only after a scheme, so CSP directives - the single largest
# source of drift - are counted too.
_HOST_RE = re.compile(
    r"(?<![\w.*-])"
    r"([a-z0-9][a-z0-9-]*(?:\.[a-z0-9-]+)*\.(?:digithings\.ai|workers\.dev|digiquant\.io))"
    r"\b",
    re.IGNORECASE,
)

# Measured on github/develop at 2636f1165435cb999c95cab38af1568a5f1307bf:
# 5927 tracked files enumerated, 5826 read, 101 binary/dir entries skipped,
# 50398869 bytes scanned. Per top directory: apps 269, docs 196, infra 30,
# scripts 15, packages 6, tests 6, .github 5, digiquant 4, openwiki 3,
# digibase/digisearch/digitrace 1 each. 537 occurrences over 17 hosts.
PINNED_CENSUS = {
    "api.digithings.ai": 1,
    "atlas.digiquant.io": 3,
    "chat.digithings.ai": 49,
    "dashboard-api.chris-stefan.workers.dev": 3,
    "digichat.digithings.ai": 14,
    "docs.digithings.ai": 1,
    "foundry-tenant.digithings.ai": 2,
    "graph.digithings.ai": 77,
    "key.digithings.ai": 61,
    "langfuse.digithings.ai": 3,
    "mcp.digithings.ai": 50,
    "occ.digithings.ai": 117,
    "search.digithings.ai": 46,
    "trace.digithings.ai": 19,
    "www.digiquant.io": 13,
    "www.digithings.ai": 77,
    "digithings-stack.example.workers.dev": 1,
}


def hosts_in(text: str) -> collections.Counter[str]:
    """Count company-owned endpoint hosts in ``text``."""
    return collections.Counter(m.group(1).lower() for m in _HOST_RE.finditer(text))


def _git(root: pathlib.Path, *args: str) -> str:
    proc = subprocess.run(
        ["git", "-C", str(root), *args],
        capture_output=True,
        text=True,
        check=False,
    )
    if proc.returncode != 0:
        raise RuntimeError(f"git {' '.join(args)} failed in {root}: {proc.stderr.strip()}")
    return proc.stdout


def _tracked_paths(root: pathlib.Path) -> list[str]:
    """List git-tracked files under ``root``, or raise.

    Two distinct failure modes are separated on purpose, because they have
    different causes and both read as "nothing found" if they are not:

    1. ``git`` itself failed - typically a plain directory, not a worktree.
    2. ``git`` succeeded but listed 0 files - a real repo with an empty index,
       or an export made with ``git archive | tar -x``, which writes no index.

    Neither is a pass. A guard that silently reports "no endpoint literals"
    after looking in the wrong place is worse than no guard, because it reads
    as a pass.
    """
    paths = [p for p in _git(root, "ls-files", "-z").split("\0") if p]
    if not paths:
        raise RuntimeError(
            f"git ls-files returned 0 entries under {root}. This test needs a real "
            "git worktree: 'git archive | tar -x' produces no index, so enumeration "
            "finds nothing and every assertion below would be vacuous."
        )
    return paths


def census(root: pathlib.Path = REPO_ROOT) -> tuple[collections.Counter[str], int, int]:
    """Return (per-host counts, tracked files walked, bytes scanned)."""
    paths = _tracked_paths(root)
    root = pathlib.Path(root)

    counts: collections.Counter[str] = collections.Counter()
    scanned_bytes = 0
    walked = 0
    for rel in paths:
        path = root / rel
        try:
            raw = path.read_bytes()
        except (OSError, IsADirectoryError):
            continue
        if b"\0" in raw[:8192]:
            continue
        walked += 1
        scanned_bytes += len(raw)
        try:
            text = raw.decode("utf-8")
        except UnicodeDecodeError:
            text = raw.decode("utf-8", "replace")
        counts.update(hosts_in(text))
    return counts, walked, scanned_bytes


def test_detector_fires_on_company_host_literals(tmp_path: pathlib.Path) -> None:
    """Positive control. Without this, every negative case below is vacuous."""
    sample = tmp_path / "fixture.txt"
    sample.write_text(
        "\n".join(
            [
                "https://graph.digithings.ai/dashboard-api",
                "connect-src https://mcp.digithings.ai",
                "https://dashboard-api.chris-stefan.workers.dev/health",
                # An env var whose value is an endpoint is a real drift site and
                # must be counted, so it belongs here and not in the negatives.
                "DIGISEARCH_URL=https://graph.digithings.ai",
            ]
        )
        + "\n"
    )
    assert hosts_in(sample.read_text()) == {
        "graph.digithings.ai": 2,
        "mcp.digithings.ai": 1,
        "dashboard-api.chris-stefan.workers.dev": 1,
    }


def test_detector_ignores_non_company_and_non_endpoint_forms() -> None:
    """Negatives, only trustworthy because the positive control fires."""
    assert (
        hosts_in(
            "\n".join(
                [
                    "https://*.digithings.ai",  # wildcard template, not an endpoint
                    "frame-src 'self' https://api.github.com",  # third party
                    "https://example.com/digithings.ai",  # placeholder domain
                    "http://localhost:8002",
                    "http://127.0.0.1:8005",
                    "http://digisearch:8002",  # compose service name
                    "DIGITHINGS_AI_URL=",  # env var NAME, no endpoint value
                    "see packages/digithings.ai/notes.md",  # path fragment
                ]
            )
        )
        == {}
    )


def test_enumeration_walks_files_and_reads_bytes() -> None:
    """Mechanism control: a scan that reads nothing cannot satisfy the pin."""
    counts, walked, scanned_bytes = census()
    assert walked > 1000, f"only walked {walked} tracked files"
    assert scanned_bytes > 1_000_000, f"only scanned {scanned_bytes} bytes"
    assert sum(counts.values()) > 0, "scan found no company endpoint literals"


def test_census_matches_pinned_baseline() -> None:
    """The ratchet. Any movement fails here and names what moved."""
    counts, walked, _ = census()
    pinned = collections.Counter(PINNED_CENSUS)
    if counts == pinned:
        return

    drifted = {
        host: {"was": pinned.get(host, 0), "now": counts.get(host, 0)}
        for host in sorted(set(counts) | set(pinned))
        if counts.get(host, 0) != pinned.get(host, 0)
    }
    detail = "\n".join(f"  {host}: was {v['was']} -> now {v['now']}" for host, v in drifted.items())
    pytest.fail(
        f"company endpoint literals drifted in {walked} tracked files.\n{detail}\n\n"
        "DIG-2703 moves these endpoints into one local/cloud config. A decrease "
        "is the migration landing and is expected: update PINNED_CENSUS in the "
        "same PR. An increase is new drift and needs a follow-up leaf on the "
        "owning surface."
    )


def test_missing_git_index_fails_loudly(tmp_path: pathlib.Path) -> None:
    """Pin the anti-vacuity decision: no index is an error, never a pass.

    Both failure modes are exercised and each is pinned to its own message, so
    a change that quietly removes one arm fails here instead of hiding.
    """
    # Arm 1: not a repository at all. git exits non-zero.
    with pytest.raises(RuntimeError, match="git ls-files -z failed"):
        _tracked_paths(tmp_path)

    # Arm 2: a real repository whose index is empty. git exits zero and prints
    # nothing, which is what an `git archive | tar -x` export looks like.
    empty_repo = tmp_path / "empty"
    empty_repo.mkdir()
    subprocess.run(
        ["git", "-C", str(empty_repo), "init", "--quiet"],
        check=True,
        capture_output=True,
    )
    assert _git(empty_repo, "ls-files", "-z") == "", "empty repo listed a file"
    with pytest.raises(RuntimeError, match="returned 0 entries"):
        _tracked_paths(empty_repo)
