"""Writes a :class:`SkillPackage` to disk as an installable Agent Skill.

Layout matches the Anthropic Agent Skills format::

    <out_dir>/<manifest.name>/
        SKILL.md
        references/
            ...

Copy or symlink ``<out_dir>/<manifest.name>/`` into any coding agent's skills
directory (e.g. a project's ``.claude/skills/``) to install it — no server,
no extra tooling.
"""

from __future__ import annotations

import zipfile
from pathlib import Path

from digiskills.frontmatter import render_skill_md
from digiskills.models import SkillPackage


def write_skill_package(package: SkillPackage, out_dir: Path) -> Path:
    """Write ``package`` under ``out_dir/<manifest.name>/`` and return that path.

    Raises:
        ValueError: a reference's resolved path would escape the package root
            (defense in depth — ``SkillReference`` already rejects traversal
            segments at construction time; this re-checks the resolved path).
    """
    package_dir = Path(out_dir) / package.manifest.name
    package_dir.mkdir(parents=True, exist_ok=True)

    skill_md = render_skill_md(package.manifest, package.body)
    (package_dir / "SKILL.md").write_text(skill_md, encoding="utf-8")

    resolved_root = package_dir.resolve()
    for ref in package.references:
        dest = (package_dir / ref.relative_path).resolve()
        if resolved_root != dest and resolved_root not in dest.parents:
            raise ValueError(f"reference path escapes package root: {ref.relative_path!r}")
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_text(ref.content, encoding="utf-8")

    return package_dir


def write_skill_zip(package: SkillPackage, zip_path: Path) -> Path:
    """Write ``package`` as a zip archive at ``zip_path`` and return that path.

    The archive root is ``<manifest.name>/`` — the same layout
    :func:`write_skill_package` writes to disk — so extracting the zip in
    place produces an identical installable directory.
    """
    zip_path = Path(zip_path)
    zip_path.parent.mkdir(parents=True, exist_ok=True)
    root = package.manifest.name
    with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as zf:
        zf.writestr(f"{root}/SKILL.md", render_skill_md(package.manifest, package.body))
        for ref in package.references:
            zf.writestr(f"{root}/{ref.relative_path}", ref.content)
    return zip_path
