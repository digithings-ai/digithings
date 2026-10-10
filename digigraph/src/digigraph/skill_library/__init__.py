"""Skill documents for digigraph (DIG-2637).

Instructions the agent fetches with the ``get_skill`` tool call, one folder per
skill under ``skill_library/<name>/SKILL.md``. Not to be confused with
``digigraph.skills.registry``, which bundles tool names rather than prose.
"""

from digigraph.skill_library.loader import (
    SKILL_LIBRARY_DIR,
    SKILL_NAME_RE,
    SkillDocument,
    SkillDocumentError,
    known_skill_names,
    list_skill_documents,
    load_skill_document,
)

__all__ = [
    "SKILL_LIBRARY_DIR",
    "SKILL_NAME_RE",
    "SkillDocument",
    "SkillDocumentError",
    "known_skill_names",
    "list_skill_documents",
    "load_skill_document",
]
