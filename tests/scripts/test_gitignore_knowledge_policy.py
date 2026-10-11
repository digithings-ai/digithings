"""Pin that Counsel's client policy under knowledge/ can never be swept into a commit.

`knowledge/data-policy.md` is Counsel's client-facing data and data protection
policy. It is not source code and must not be published under this repository's
MIT licence — Counsel version-controls it as a Paperclip issue document on DIG-1502
instead.

Until DIG-1522 the directory was merely *untracked*, not ignored, and that is a
different thing. `dt-snapshot`'s capture step stages the whole working tree with
`git read-tree HEAD` into a temporary index followed by `git add -A`, and
`git add -A` stages every path that is not ignored. Five
`refs/backup/chris/digithings/detached/*` refs on the **public** `github` remote
therefore carried the policy on 2026-10-06, fetchable anonymously.

`/projects/*` already keeps the other confidential tree out of the same sweep, so
this pins the same treatment for `knowledge/`. The anchoring matters as much as
the rule: an unanchored `projects/` rule would also have captured
`docs/projects/`, which ADR-0006 reserves for public dogfood. The probes below
check the leading slash directly, so a later "just match the name" edit is caught
here rather than in a published ref.

These assertions run the real `git check-ignore`, so the pin fails if the rule is
deleted, narrowed, unanchored, or replaced by a rule somewhere else — not only if
the text is edited. Git never descends into an excluded directory, so a
`.gitignore` inside `knowledge/` could not shadow the rule even if one existed;
what the last test guards is the rule being *moved* out of the repo root.

DIG-1522.
"""

from __future__ import annotations

import subprocess
from pathlib import Path

import pytest

pytestmark = pytest.mark.unit

REPO_ROOT = Path(__file__).resolve().parents[2]

# Probe paths with a comment on why each must be ignored. None are real files;
# `git check-ignore` resolves rules for paths that do not exist.
IGNORED = (
    # The policy itself, and the sibling Counsel wrote next to it.
    "knowledge/data-policy.md",
    "knowledge/oss-policy.md",
    # Anything Counsel drops in that directory later, without editing this file.
    "knowledge/anything-at-all.md",
)

# Tracked source that must stay committable. Two of these carry "knowledge" in
# their name and one lives under the sibling confidential tree, so they catch a
# rule matched by name or widened past the repo root.
TRACKED = (
    "AGENTS.md",
    "docs/agents/CODE_REVIEW_POLICY.md",
    "digiquant/supabase/migrations/118_knowledge_notes_vault_namespace.sql",
    "scripts/seed_knowledge_vault.py",
    # The `/projects/*` allowlist exception must survive an edit next to it.
    "projects/README.md",
)

# Paths under other directories that merely look like the confidential ones. The
# leading slash is what keeps these committable (ADR-0006 reserves docs/projects/
# for public dogfood; the same reasoning applies here).
NOT_IGNORED_BY_NAME = (
    "docs/knowledge/README.md",
    "apps/digichat/knowledge/notes.md",
)


def _check_ignore(paths: tuple[str, ...]) -> dict[str, str]:
    """Map each ignored path to the rule that ignores it; the rest are omitted.

    `check-ignore -v` also prints the last-matching rule when that rule is a
    negation, so `!/projects/README.md` comes back as a "hit" for a path that is
    in fact committable. Skipping negated patterns is what keeps the
    `projects/README.md` probe below meaningful.

    Splitting the leading fields assumes no `.gitignore` rule in this repo
    contains a colon; none does, and a colon would only ever make the parse
    ambiguous, never make a committed file look committable by accident here.
    """
    out = subprocess.run(
        ["git", "check-ignore", "-v", "--no-index", *paths],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
        check=False,
    )
    hits: dict[str, str] = {}
    for line in out.stdout.splitlines():
        # <source>:<lineno>:<pattern>\t<pathname>
        source_with_lineno, pathname = line.split("\t", 1)
        pattern = source_with_lineno.rsplit(":", 1)[1]
        if pattern.startswith("!"):
            continue
        # git prints the rule's own path relative to the repo root, so anchor it
        # for comparison against REPO_ROOT.
        hits[pathname] = str((REPO_ROOT / source_with_lineno.rsplit(":", 2)[0]).resolve())
    return hits


def test_the_knowledge_tree_is_ignored() -> None:
    hits = _check_ignore(IGNORED)
    missed = [p for p in IGNORED if p not in hits]
    assert not missed, f"not ignored by any rule: {missed}\nresolved: {hits}"


def test_nothing_under_knowledge_is_tracked() -> None:
    """Close the one escape the `--no-index` probes cannot see.

    The probes above answer "would this path be ignored if it were untracked".
    A path that has been committed is in HEAD, so every capture inherits it from
    `git read-tree HEAD` with no rule consulted — the ignore rule stops
    protecting the policy the moment that happens, and every other test here
    would still pass. Nothing under `knowledge/` may be tracked.
    """
    tracked = subprocess.run(
        ["git", "ls-files", "-z", "--", "knowledge/"],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
        check=False,
    ).stdout
    assert not tracked, (
        "tracked paths under knowledge/ are inherited by every snapshot from HEAD, "
        f"ignore rule or not: {[p for p in tracked.split(chr(0)) if p]}"
    )


def test_no_tracked_source_is_shadowed() -> None:
    hits = _check_ignore(TRACKED)
    assert not hits, f"root rules now ignore tracked source: {hits}"


def test_the_rule_is_anchored_to_the_repo_root() -> None:
    """The leading slash is load-bearing, so assert it rather than trust it.

    An unanchored rule would also swallow `docs/knowledge/`, the vault directory
    `scripts/seed_knowledge_vault.py` writes to — the same failure ADR-0006
    records for an unanchored `projects/` rule.
    """
    hits = _check_ignore(NOT_IGNORED_BY_NAME)
    assert not hits, f"the rule lost its root anchor and now matches by name: {hits}"


def test_the_rule_that_covers_knowledge_lives_in_the_root_gitignore() -> None:
    """The root rule is the whole fix: no nearer `.gitignore` can replace it.

    `knowledge/` exists only in the main checkout, so a rule written into some
    app-level `.gitignore` would not be read at all. Asserting the resolving file
    is the repo-root `.gitignore` is what makes that failure mode visible.
    """
    hits = _check_ignore(("knowledge/data-policy.md",))
    assert hits == {
        "knowledge/data-policy.md": str(REPO_ROOT / ".gitignore"),
    }
