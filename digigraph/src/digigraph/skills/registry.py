"""Skills registry: named bundles of tools with optional when(context). Delegates to orchestration registry."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable

# Import to ensure tools and skills are registered when skills are used.
from digigraph.orchestration import builtin as _  # noqa: F401
from digigraph.orchestration.registry import ToolContext, get_tools


@dataclass
class Skill:
    """A skill is a named bundle of tool names, with optional metadata and when predicate."""

    id: str
    name: str
    description: str
    tool_names: list[str]
    when: Callable[[ToolContext], bool] | None = None


_skill_meta: dict[str, Skill] = {}


def register_skill(skill: Skill) -> None:
    """Register skill metadata (id, name, description). Tool registration is in orchestration.builtin."""
    _skill_meta[skill.id] = skill


def get_tools_for_skills(skill_ids: list[str], context: ToolContext) -> list[dict[str, Any]]:
    """Return OpenAI tool dicts for the given skill ids and context. Uses orchestration registry."""
    return get_tools(skill_ids, context)
