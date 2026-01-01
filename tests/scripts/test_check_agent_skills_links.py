"""Pins the agent-skills link check: it must catch a dangling skill alias, and it must not repair it.

WHAT WENT WRONG. Agent seats load skills from a skills home that pairs a plain slug with
a content-hashed runtime alias (`product-management` -> `product-management--dce17287c0`
-> a materialised source directory). The materialised directory is garbage-collected; the
two symlinks pointing at it are not. The seat then keeps a skill name that resolves to
nothing, so the skill silently stops loading — no error, no run failure. On the company
host that left 8 permanently dangling aliases across a 59-seat org, one of which had
taken `ceo-front-door` offline for the CEO seat.

TWO BROKEN SHAPES, BOTH COVERED HERE. The hashed entry is sometimes gone entirely
(garbage-collected), and sometimes still present as a link whose own target is gone. The
first shape only shows up in a directory listing as the surviving slug alias, so the
report has to read the link to name the hashed path someone has to re-create — otherwise
the finding says "broken" and not "broken this way".

WHY THE NO-REPAIR TEST IS THE LOAD-BEARING ONE. The tempting fix is to `unlink` the broken
symlink. That converts a visible defect into an invisible permanent loss: the seat no
longer names the skill at all, so nothing reports it and nothing ever repairs it. This
file asserts the check leaves the exact tree it found — dangling links, hashed targets and
all — so the bug stays loud and someone re-materialises the target instead.

Deleting links is also the fix the reporting agent was explicitly told not to ship. Pinning
it here means a later "helpful" refactor cannot quietly reintroduce it.
"""

from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path
from types import ModuleType

import pytest

pytestmark = pytest.mark.unit

REPO_ROOT = Path(__file__).resolve().parents[2]
SCRIPT = REPO_ROOT / "scripts" / "check_agent_skills_links.py"

HASH = "dce17287c0"
ALIAS = f"product-management--{HASH}"


def _load_check() -> ModuleType:
    """Import the gate script by path; `scripts/` is not a package."""
    spec = importlib.util.spec_from_file_location("check_agent_skills_links", SCRIPT)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


check = _load_check()


def _make_skill(root: Path, name: str) -> Path:
    """Create a real, loadable skill directory at `root / name`."""
    skill = root / name
    skill.mkdir(parents=True)
    (skill / "SKILL.md").write_text(f"# {name}\n", encoding="utf-8")
    return skill


def _make_healthy_alias(root: Path, slug: str) -> str:
    """`slug -> slug--<hash> -> <real dir>`, the shape a healthy seat loads."""
    hashed = f"{slug}--{HASH}"
    _make_skill(root, hashed)
    (root / slug).symlink_to(hashed)
    return hashed


def _make_orphaned_alias(root: Path, slug: str) -> str:
    """`slug -> slug--<hash>` with the hashed entry itself gone. What GC leaves behind."""
    hashed = f"{slug}--{HASH}"
    (root / slug).symlink_to(hashed)
    return hashed


def _make_dangling_alias(root: Path, slug: str) -> str:
    """`slug -> slug--<hash> -> <gone>`. The hashed link survived, its target did not."""
    hashed = f"{slug}--{HASH}"
    (root / hashed).symlink_to(root / "gc-removed" / slug)
    (root / slug).symlink_to(hashed)
    return hashed


def _snapshot(home: Path) -> dict[str, tuple[bool, bool, Path | None]]:
    """Record every entry's shape, so a mutation is visible as a diff, not a listing."""
    return {
        entry.name: (
            entry.is_symlink(),
            entry.is_dir(),
            entry.readlink() if entry.is_symlink() else None,
        )
        for entry in sorted(home.iterdir())
    }


@pytest.fixture
def clean_home(tmp_path: Path) -> Path:
    """A skills home with one healthy alias pair and one plain bundled skill."""
    home = tmp_path / "skills"
    home.mkdir()
    _make_healthy_alias(home, "product-management")
    _make_skill(home, "paperclip")
    return home


@pytest.fixture
def orphaned_alias_home(tmp_path: Path) -> Path:
    """The DIG-2284 fingerprint: the slug alias survived, its hashed entry did not."""
    home = tmp_path / "skills"
    home.mkdir()
    assert not (home / ALIAS).exists()
    _make_orphaned_alias(home, "product-management")
    _make_healthy_alias(home, "ceo-front-door")
    _make_skill(home, "paperclip")
    return home


def test_clean_home_passes(clean_home: Path) -> None:
    findings, count = check.scan_skills_home(clean_home)
    assert findings == []
    assert count == 3
    assert check.main(["--skills-home", str(clean_home)]) == 0


def test_orphaned_alias_is_reported_with_its_hashed_target_name(orphaned_alias_home: Path) -> None:
    """The hashed entry is absent from the listing, so only the link can name it."""
    findings, _ = check.scan_skills_home(orphaned_alias_home)
    assert len(findings) == 1
    finding = findings[0]
    assert (finding.kind, finding.name) == ("dangling-link", "product-management")
    # Without the hashed name in the report, the reader has to guess what to re-create.
    assert ALIAS in finding.detail
    assert finding.is_failure


def test_dangling_alias_fails_loudly(
    orphaned_alias_home: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    exit_code = check.main(["--skills-home", str(orphaned_alias_home)])
    assert exit_code == 1
    stderr = capsys.readouterr().err
    assert "FAIL dangling-link: product-management" in stderr
    assert ALIAS in stderr
    # The repair instruction must be in the failure text, not only in the docstring:
    # this is what stops the reader reaching for `rm` on the link.
    assert "never repairs anything" in stderr
    assert "do not delete the link" in stderr


def test_broken_link_layers_are_each_reported(tmp_path: Path) -> None:
    """When the hashed link survives, both layers name themselves in the report."""
    home = tmp_path / "skills"
    home.mkdir()
    _make_dangling_alias(home, "product-management")
    _make_skill(home, "paperclip")

    findings, count = check.scan_skills_home(home)
    assert count == 3
    assert sorted((f.kind, f.name) for f in findings) == [
        ("dangling-link", "product-management"),
        ("dangling-link", ALIAS),
    ]
    assert check.main(["--skills-home", str(home)]) == 1


def test_check_never_mutates_the_tree(orphaned_alias_home: Path) -> None:
    """The load-bearing guarantee: a failure leaves the tree exactly as found."""
    before = _snapshot(orphaned_alias_home)

    assert check.main(["--skills-home", str(orphaned_alias_home), "--strict"]) == 1

    assert _snapshot(orphaned_alias_home) == before
    # Explicit, so a refactor that deletes the dangling alias cannot pass by returning
    # the same directory listing.
    assert (orphaned_alias_home / "product-management").is_symlink()
    assert (orphaned_alias_home / "product-management").readlink().name == ALIAS
    assert not (orphaned_alias_home / ALIAS).exists()


def test_missing_manifest_is_a_failure(clean_home: Path) -> None:
    (clean_home / "empty-skill").mkdir()
    findings, _ = check.scan_skills_home(clean_home)
    missing = [f for f in findings if f.kind == "missing-manifest"]
    assert [f.name for f in missing] == ["empty-skill"]
    assert check.main(["--skills-home", str(clean_home)]) == 1


def test_a_skill_dir_that_lost_its_manifest_is_still_caught(clean_home: Path) -> None:
    """`SKILL.md` gone but the rest of the skill present: markdown present, so it counts."""
    (clean_home / "paperclip" / "SKILL.md").unlink()
    (clean_home / "paperclip" / "reference.md").write_text("# ref\n", encoding="utf-8")
    findings, _ = check.scan_skills_home(clean_home)
    assert [(f.kind, f.name) for f in findings] == [("missing-manifest", "paperclip")]


def test_a_bookkeeping_container_is_not_a_skill(clean_home: Path) -> None:
    """`synced/` on the real host: opaque sync buckets, no manifest by design.

    Reporting it would make the gate cry wolf on every run, which is how a loud check
    gets ignored.
    """
    container = clean_home / "synced"
    bucket = container / "d36e81fc-3318-46e7-b842-cfe834aedf85"
    bucket.mkdir(parents=True)
    (container / ".bucket-d36e81fc").write_text("", encoding="utf-8")
    findings, _ = check.scan_skills_home(clean_home)
    assert findings == []
    assert check.main(["--skills-home", str(clean_home), "--strict"]) == 0


def test_expect_fails_when_a_required_skill_does_not_resolve(clean_home: Path) -> None:
    assert check.main(["--skills-home", str(clean_home), "--expect", "ceo-front-door"]) == 1
    findings = check.check_expected(clean_home, ["ceo-front-door"])
    assert [f.kind for f in findings] == ["unresolvable"]
    assert "re-sync the seat" in findings[0].detail


def test_expect_passes_for_a_desired_skill_that_resolves(clean_home: Path) -> None:
    assert check.check_expected(clean_home, ["product-management", "paperclip"]) == []
    assert check.main(["--skills-home", str(clean_home), "--expect", "product-management"]) == 0


def test_expect_flags_a_dangling_desired_skill(orphaned_alias_home: Path) -> None:
    """The seat-level signal: a skill a seat is supposed to load does not load."""
    assert (
        check.main(["--skills-home", str(orphaned_alias_home), "--expect", "product-management"])
        == 1
    )
    findings = check.check_expected(orphaned_alias_home, ["ceo-front-door", "product-management"])
    assert [(f.kind, f.name) for f in findings] == [("unresolvable", "product-management")]


def test_expect_flags_a_skill_that_resolves_without_a_manifest(clean_home: Path) -> None:
    (clean_home / "product-management").unlink()
    (clean_home / "product-management").mkdir()
    findings = check.check_expected(clean_home, ["product-management"])
    assert [f.kind for f in findings] == ["unresolvable"]


def test_orphaned_hashed_alias_warns_but_does_not_fail(clean_home: Path) -> None:
    _make_skill(clean_home, "summarize-status--61a9e96dc6")
    findings, _ = check.scan_skills_home(clean_home)
    assert [f.kind for f in findings] == ["orphaned-alias"]
    assert check.main(["--skills-home", str(clean_home)]) == 0
    assert check.main(["--skills-home", str(clean_home), "--strict"]) == 1


def test_absent_skills_home_is_not_a_failure(clean_home: Path) -> None:
    """A CI checkout has no `.claude/skills` until `make agents-init` runs."""
    missing = clean_home.parent / "not-built"
    assert check.main(["--skills-home", str(missing)]) == 0
    assert check.main(["--skills-home", str(missing), "--require-skills-home"]) == 1


def test_hidden_entries_are_not_skills(clean_home: Path) -> None:
    (clean_home / ".staging").mkdir()
    (clean_home / ".DS_Store").write_text("", encoding="utf-8")
    findings, count = check.scan_skills_home(clean_home)
    assert findings == []
    assert count == 3


def test_json_report_names_every_failure(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    home = tmp_path / "skills"
    home.mkdir()
    _make_dangling_alias(home, "product-management")
    _make_skill(home, "paperclip")

    assert check.main(["--skills-home", str(home), "--json"]) == 1
    report = json.loads(capsys.readouterr().out)
    assert report["skillsHome"] == str(home)
    assert report["entries"] == 3
    # Both link layers named, so the reader knows which path to re-materialise.
    assert sorted(line.split(": ")[1] for line in report["failures"]) == [
        "product-management",
        ALIAS,
    ]
    assert report["warnings"] == []


def test_hashed_alias_slug_recognition() -> None:
    assert check.hashed_alias_slug("product-management--dce17287c0") == "product-management"
    assert check.hashed_alias_slug("ask-an-expert--dc02ecb490") == "ask-an-expert"
    # Not a 10-hex suffix, so not a runtime alias.
    assert check.hashed_alias_slug("paperclip") is None
    assert check.hashed_alias_slug("summarize-status--61a9e96dc6x") is None
