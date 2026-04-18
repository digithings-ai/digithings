"""Skills library: named tool bundles for the research node. Use get_tools_for_skills with project config."""

from __future__ import annotations

from digigraph.skills import builtin  # noqa: F401 - register built-in skill metadata
from digigraph.skills.registry import Skill, get_tools_for_skills, register_skill

__all__ = ["Skill", "get_tools_for_skills", "register_skill"]
