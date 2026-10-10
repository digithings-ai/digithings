"""The two skill-document tools — list_skills and get_skill (DIG-2637).

Same trust model as the session preference tools: the model asks, and the
result it gets back is data it must act on. Nothing here is baked into a system
prompt — the point of the feature is that a document reaches the agent's
context only when the agent asks for it by id.

Deliberately dumb handlers. A skill document is instructions, not a decision:
this layer resolves an id to text and refuses an unknown id with a corrective
message naming what does exist. What to do with the instructions is the
document's business, not this file's.
"""

from __future__ import annotations

from typing import Any

from digigraph.orchestration.registry import ToolContext
from digigraph.skill_library.loader import (
    SkillDocumentError,
    list_skill_documents,
    load_skill_document,
)

LIST_SKILLS = "list_skills"
GET_SKILL = "get_skill"

# The always-on bundle id research.py appends to the skill ids, exactly as it
# does for "session".
SKILL_LIBRARY_SKILL_ID = "skill_library"

SKILL_LIBRARY_TOOL_NAMES = frozenset({LIST_SKILLS, GET_SKILL})

_SKILL_ID_PROPERTY = {
    "type": "string",
    "description": "Skill id, kebab-case, exactly as list_skills reported it.",
}


def _fn(name: str, description: str, properties: dict[str, Any], required: list[str]) -> dict:
    return {
        "type": "function",
        "function": {
            "name": name,
            "description": description,
            "parameters": {"type": "object", "properties": properties, "required": required},
        },
    }


SKILL_LIBRARY_TOOL_SCHEMAS: list[tuple[str, dict]] = [
    (
        LIST_SKILLS,
        _fn(
            LIST_SKILLS,
            "List the skill documents available, with a one-line description each. "
            "Call get_skill with an id to read the instructions before doing the work.",
            {},
            [],
        ),
    ),
    (
        GET_SKILL,
        _fn(
            GET_SKILL,
            "Read one skill document: its instructions, by id from list_skills.",
            {"name": _SKILL_ID_PROPERTY},
            ["name"],
        ),
    ),
]


def _handle_list_skills(_args: dict[str, Any], _context: ToolContext) -> dict[str, Any]:
    documents = list_skill_documents()
    return {
        "ok": True,
        "count": len(documents),
        "skills": [doc.as_summary() for doc in documents],
    }


def _handle_get_skill(args: dict[str, Any], _context: ToolContext) -> dict[str, Any]:
    raw = (args or {}).get("name")
    try:
        document = load_skill_document(raw if isinstance(raw, str) else "")
    except SkillDocumentError as exc:
        # Corrective, not fatal: naming the ids that do exist is what lets the
        # agent retry without another round trip.
        try:
            known = [doc.name for doc in list_skill_documents()]
        except SkillDocumentError:
            known = []
        return {
            "ok": False,
            "error": str(exc),
            "known_skills": known,
        }
    return {
        "ok": True,
        "name": document.name,
        "description": document.description,
        "version": document.version,
        "source": document.source,
        "content": document.body,
    }


def skill_library_tool_handler(name: str):
    """Build the registry handler for one skill-library tool."""

    def handler(args: dict[str, Any], context: ToolContext) -> dict[str, Any]:
        if name == LIST_SKILLS:
            return _handle_list_skills(args, context)
        if name == GET_SKILL:
            return _handle_get_skill(args, context)
        return {"ok": False, "error": f"unknown skill-library tool: {name}"}

    return handler
