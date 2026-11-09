"""R0 privacy guard: the staged export carries no personal identity (#6751).

Two must-fix items from the R0 export review, both public-facing:

1. PII-shaped docstrings and README text — a real person's name, handle or
   address anywhere in the exported tree.
2. the private mirror setup (host, remote-setup commands, namespace) left in
   the public ``AGENTS.md``/``BRANCHING.md``.

The test models the export in memory: it takes the split manifest's R0 paths,
runs them through the same ``r0_rewrite`` table ``stage_r0.py`` applies, and
scans the rewritten bytes and paths against a mono-only pattern list. That is
the exact content the staged commit holds, without rebuilding the export.

The pattern list never ships in R0 (``config/private/`` is mapped out), so the
test skips outside the mono, where both the list and the split manifest are
absent. Findings name a path and line, never the matched value: R0 CI logs are
public.
"""

from __future__ import annotations

import importlib.util
import re
import subprocess
import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[2]
PII_REL = "config/private/r0-personal-identifiers.txt"
MANIFEST_REL = "scripts/split/manifest.py"
REWRITE_REL = "scripts/split/r0_rewrite.py"

#: The docs that carried the private mirror instructions in the last export.
MIRROR_DOCS = ("AGENTS.md", "BRANCHING.md")

#: A below-this floor scan means the matcher broke, not that the tree is clean.
MIN_SCANNED = 1000


def _load(name: str, rel: str):
    path = REPO / rel
    if not path.is_file():
        return None
    spec = importlib.util.spec_from_file_location(name, path)
    mod = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    sys.modules[name] = mod  # dataclasses resolve their module by name
    spec.loader.exec_module(mod)
    return mod


def _patterns() -> list[re.Pattern[str]]:
    """The mono-only personal-identifier patterns (case-sensitive by design)."""
    path = REPO / PII_REL
    if not path.is_file():
        pytest.skip(f"{PII_REL} is mono-only; nothing to scan in this checkout")
    patterns = []
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if line and not line.startswith("#"):
            patterns.append(re.compile(line))
    assert patterns, "the personal-identifier list is empty"
    return patterns


def _rewriter():
    rw = _load("r0_rewrite", REWRITE_REL)
    if rw is None:
        pytest.skip("mono-only split tooling is absent in this checkout")
    return rw, rw.Rewriter.load(REPO / rw.TABLE_REL)


def _r0_paths(manifest) -> list[str]:
    paths = manifest.tracked_paths("HEAD", str(REPO))
    mapping, unassigned = manifest.build_manifest(paths)
    assert not unassigned, f"{len(unassigned)} unassigned path(s)"
    return sorted(p for p, repo in mapping.items() if repo == "R0")


def _export_view() -> tuple[dict[str, str], int]:
    """Rewritten paths -> text of every R0 file, as the staged export holds them."""
    manifest = _load("split_manifest", MANIFEST_REL)
    if manifest is None:
        pytest.skip("the split manifest is mono-only; nothing to scan here")
    _, rewriter = _rewriter()
    paths = _r0_paths(manifest)
    r0 = set(paths)
    view: dict[str, str] = {}
    for p in paths:
        try:
            data = (REPO / p).read_bytes()
        except OSError:
            continue
        staged = rewriter.content(p, data, r0)
        try:
            text = staged.decode("utf-8")
        except UnicodeDecodeError:
            text = ""  # binary: no docstring to leak
        view[rewriter.path(p)] = text
    return view, len(paths)


def test_the_export_carries_no_personal_identifier() -> None:
    """Item 1: no real-person name, handle or address survives the rewrite."""
    patterns = _patterns()
    view, scanned = _export_view()
    assert scanned >= MIN_SCANNED, f"only {scanned} path(s) scanned; matcher broke"

    hits: list[str] = []
    for staged_path, text in sorted(view.items()):
        if any(rx.search(staged_path) for rx in patterns):
            hits.append(f"{staged_path}:1 (path)")
        for lineno, line in enumerate(text.splitlines(), start=1):
            if any(rx.search(line) for rx in patterns):
                hits.append(f"{staged_path}:{lineno}")
    assert not hits, (
        f"{len(hits)} personal-identifier line(s) in the export across "
        f"{len({h.split(':')[0] for h in hits})} path(s):\n  " + "\n  ".join(hits[:40])
    )


def test_the_public_docs_describe_only_the_github_workflow() -> None:
    """Item 2: the exported docs carry the public workflow, not the mirror setup."""
    patterns = _patterns()
    _, rewriter = _rewriter()
    for rel in MIRROR_DOCS:
        mono = (REPO / rel).read_bytes()
        staged = rewriter.content(rel, mono, None)
        assert staged != mono, f"{rel} was exported verbatim; the override did not fire"
        text = staged.decode("utf-8")
        for rx in patterns:
            assert not rx.search(text), f"{rel}: a private identifier survived the override"

    agents = rewriter.content("AGENTS.md", (REPO / "AGENTS.md").read_bytes(), None).decode()
    assert "## GitHub promotion" in agents
    assert "## Origin iteration" not in agents


def test_the_identifier_list_is_mono_only_and_never_ships() -> None:
    """The list names real people, so by construction it cannot be public."""
    manifest = _load("split_manifest", MANIFEST_REL)
    if manifest is None:
        pytest.skip("the split manifest is mono-only")
    hit = manifest.match_rule(PII_REL)
    assert hit is not None and hit[0] != "R0", f"{PII_REL} maps into R0"

    listed = subprocess.run(
        ["git", "ls-files"], cwd=REPO, capture_output=True, text=True, check=True
    ).stdout.split()
    assert PII_REL in listed, f"{PII_REL} is not tracked"
