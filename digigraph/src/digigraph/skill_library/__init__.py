"""Skill documents for digigraph.

Instructions the agent fetches with the ``get_skill`` tool call, one folder per
skill. Packs are read from ``DIGIGRAPH_SKILLS_DIR/<pack>/<name>/SKILL.md`` when
that variable is set, and from the in-package library otherwise. Not to be
confused with ``digigraph.skills.registry``, which bundles tool names rather
than prose.
"""

from digigraph.skill_library.loader import (
    SKILL_LIBRARY_DIR,
    SKILL_NAME_RE,
    SKILL_PACK_RE,
    SKILLS_DIR_ENV,
    SkillDocument,
    SkillDocumentError,
    known_skill_names,
    list_skill_documents,
    load_skill_document,
    pack_dir,
    skills_dir,
)

__all__ = [
    "SKILL_LIBRARY_DIR",
    "SKILL_NAME_RE",
    "SKILL_PACK_RE",
    "SKILLS_DIR_ENV",
    "SkillDocument",
    "SkillDocumentError",
    "known_skill_names",
    "list_skill_documents",
    "load_skill_document",
    "pack_dir",
    "skills_dir",
]
