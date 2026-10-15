#!/usr/bin/env python3
"""Verify and repair the two-layer ~/.claude/skills symlink tree.

The skills home is written in two layers:

    layer 1 (alias)  <slug>            -> <slug>--<hash>          (relative)
    layer 2 (target) <slug>--<hash>    -> <absolute path>          (managed root)

The alias only resolves while the layer-2 link exists. Historically the layer-2
links were unlinked on their own (a prune that treats them as disposable
scratch), which left the layer-1 aliases pointing at nothing. Nothing failed
loudly: the alias was still enumerated as a skill, it just had no content.

This script finds every alias whose layer-2 target is missing, resolves the
correct target from the managed skill root, and reports it. With --repair it
recreates the missing layer-2 links. It never deletes an alias.

Exit codes:
    0  every alias resolves (or --repair fixed them)
    1  one or more aliases are dangling and were not repaired
    2  bad environment / usage

Usage:
    check_agent_skills_links.py                 # check only, non-zero on dangling
    check_agent_skills_links.py --repair        # recreate missing layer-2 links
    check_agent_skills_links.py --skills-home X # check a different home
    check_agent_skills_links.py --json          # machine-readable report
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
from pathlib import Path

HASHED_SUFFIX = re.compile(r"^(?P<slug>.+?)--(?P<hash>[0-9a-f]{10})$")
FRONTMATTER_NAME = re.compile(r"^name:[ \t]*(?P<name>.+?)[ \t]*$", re.MULTILINE)


def eprint(*args: object) -> None:
    print(*args, file=sys.stderr)


def default_skills_home() -> Path:
    env = os.environ.get("CLAUDE_SKILLS_HOME")
    if env:
        return Path(env).expanduser()
    claude_home = os.environ.get("CLAUDE_HOME")
    base = Path(claude_home).expanduser() if claude_home else Path.home() / ".claude"
    return base / "skills"


def default_managed_roots() -> list[Path]:
    """Every managed skill root, e.g. ~/.paperclip/instances/*/skills/<uuid>."""
    roots: list[Path] = []
    for override in os.environ.get("PAPERCLIP_SKILL_ROOTS", "").split(os.pathsep):
        if override.strip():
            roots.append(Path(override.strip()).expanduser())
    if roots:
        return roots
    instances = Path.home() / ".paperclip" / "instances"
    if instances.is_dir():
        for instance in sorted(instances.iterdir()):
            skills = instance / "skills"
            if not skills.is_dir():
                continue
            for managed in sorted(skills.iterdir()):
                if managed.is_dir() and (managed / "__catalog__").is_dir():
                    roots.append(managed)
    return roots


def skill_name_of(directory: Path) -> str | None:
    """Read the `name:` out of a SKILL.md frontmatter, if there is one."""
    skill_md = directory / "SKILL.md"
    if not skill_md.is_file():
        return None
    try:
        text = skill_md.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return None
    match = FRONTMATTER_NAME.search(text)
    if not match:
        return None
    return match.group("name").strip().strip("\"'")


def is_skill_dir(path: Path) -> bool:
    return path.is_dir() and (path / "SKILL.md").is_file()


def resolve_target(slug: str, hashed_name: str, managed_roots: list[Path]) -> tuple[Path | None, str]:
    """Find the live source directory for `slug`, mirroring the server's
    resolution order: managed dir, then catalog snapshot, then runtime cache.

    Returns (target, reason). reason is "missing" when nothing was found.
    """
    ambiguous: list[tuple[str, Path]] = []
    for root in managed_roots:
        # (a) managed skill directory
        candidate = root / slug
        if is_skill_dir(candidate):
            return candidate, "managed"

        # (b) catalog snapshot, named <slug>--<hash>
        candidate = root / "__catalog__" / hashed_name
        if is_skill_dir(candidate):
            return candidate, "catalog"

        # (c) runtime skill cache, keyed by skill id + content fingerprint
        cache = root / "__runtime_cache_v1__"
        if cache.is_dir():
            for skill_id_dir in sorted(cache.iterdir()):
                if not skill_id_dir.is_dir():
                    continue
                for fingerprint_dir in sorted(skill_id_dir.iterdir()):
                    files = fingerprint_dir / "files"
                    if is_skill_dir(files) and skill_name_of(files) == slug:
                        ambiguous.append((f"cache:{skill_id_dir.name}", files))

    if len(ambiguous) == 1:
        return ambiguous[0][1], ambiguous[0][0]
    if len(ambiguous) > 1:
        paths = ", ".join(str(p) for _, p in ambiguous)
        eprint(f"  AMBIGUOUS {slug}: {len(ambiguous)} cached copies ({paths})")
        return None, f"ambiguous:{len(ambiguous)}"
    return None, "missing"


def audit(skills_home: Path, managed_roots: list[Path]) -> dict:
    report: dict = {
        "skillsHome": str(skills_home),
        "managedRoots": [str(r) for r in managed_roots],
        "aliases": 0,
        "dangling": [],
        "unknown": [],
        "orphanTarget": [],
        "repaired": [],
        "repairFailed": [],
    }
    if not skills_home.is_dir():
        eprint(f"skills home does not exist: {skills_home}")
        return report
    if not managed_roots:
        eprint("no managed skill roots found; cannot resolve targets")

    for entry in sorted(skills_home.iterdir()):
        if not entry.is_symlink():
            continue
        report["aliases"] += 1
        # An alias that resolves is fine.
        if entry.exists():
            continue
        link = os.readlink(entry)
        hashed_match = HASHED_SUFFIX.match(entry.name)
        if hashed_match:
            # A layer-2 entry whose source directory is gone. Nothing to repair:
            # recreating it would just re-dangle. An orphaned layer-1 alias will
            # show up in the `dangling` list and flag this one by name.
            report["orphanTarget"] = report.get("orphanTarget", [])
            report["orphanTarget"].append(
                {"entry": entry.name, "link": link, "slug": hashed_match.group("slug")}
            )
            continue
        if os.path.isabs(link):
            # A single-layer symlink straight at an absolute path.
            report["unknown"].append(
                {"alias": entry.name, "link": link, "reason": "absolute target missing"}
            )
            continue
        # Layer-1 alias: the hashed name lives in the link, not in the name.
        hashed_name = link
        target, reason = resolve_target(entry.name, hashed_name, managed_roots)
        if target is None:
            report["repairFailed"].append(
                {"alias": entry.name, "hashed": hashed_name, "reason": reason}
            )
        else:
            report["dangling"].append(
                {
                    "alias": entry.name,
                    "slug": entry.name,
                    "hashed": hashed_name,
                    "source": reason,
                    "target": str(target),
                }
            )
    return report


def repair(skills_home: Path, report: dict) -> None:
    """Recreate the missing layer-2 links. Aliases are never touched."""
    for item in report["dangling"]:
        hashed_path = skills_home / item["hashed"]
        if hashed_path.exists() or hashed_path.is_symlink():
            continue
        try:
            os.symlink(item["target"], hashed_path)
            report["repaired"].append(item)
            print(f"  repaired {item['hashed']} -> {item['target']} ({item['source']})")
        except OSError as exc:
            eprint(f"  FAILED {item['hashed']}: {exc}")
            report["repairFailed"].append(
                {"alias": item["alias"], "hashed": item["hashed"], "reason": str(exc)}
            )


def recheck(skills_home: Path) -> list[str]:
    """Second pass over the same home. Returns aliases still dangling."""
    still: list[str] = []
    for entry in sorted(skills_home.iterdir()):
        if entry.is_symlink() and not entry.exists():
            still.append(entry.name)
    return still


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--skills-home", default=None)
    parser.add_argument("--repair", action="store_true")
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args(argv)

    skills_home = Path(args.skills_home).expanduser() if args.skills_home else default_skills_home()
    managed_roots = default_managed_roots()

    report = audit(skills_home, managed_roots)

    if args.repair and report["dangling"]:
        print(f"repairing {len(report['dangling'])} dangling skill links in {skills_home}")
        repair(skills_home, report)

    if args.repair:
        report["stillDangling"] = recheck(skills_home)

    dangling = report["dangling"] if not args.repair else report.get("stillDangling", [])
    failed = report["repairFailed"]

    if args.json:
        print(json.dumps(report, indent=2))
    else:
        print(f"skills home: {skills_home}")
        print(f"aliases checked: {report['aliases']}")
        print(f"dangling: {len(dangling)}")
        for item in dangling:
            print(f"  DANGLING {item if isinstance(item, str) else item['alias']}")
        for item in failed:
            print(f"  UNREPAIRABLE {item['alias']} ({item['reason']})")
        for item in report["unknown"]:
            print(f"  BROKEN-LINK {item['alias']} -> {item['link']} ({item['reason']})")
        for item in report["orphanTarget"]:
            print(f"  ORPHAN-TARGET {item['entry']} -> {item['link']}")
        if args.repair:
            print(f"repaired: {len(report['repaired'])}")

    if failed:
        eprint("FAIL: some dangling skill links have no resolvable source")
        return 1
    if report["unknown"]:
        eprint(
            f"FAIL: {len(report['unknown'])} skill symlink(s) point at a missing "
            "absolute target"
        )
        return 1
    if dangling:
        eprint(
            f"FAIL: {len(dangling)} skill alias(es) resolve to nothing. "
            "Run with --repair, or check the managed skill root."
        )
        return 1
    print("OK: every skill alias resolves")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))