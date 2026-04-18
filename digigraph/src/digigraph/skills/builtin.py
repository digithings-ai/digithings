"""Register built-in skill metadata (search, sitaas_rag). Tool and skill registration is in orchestration.builtin."""

from __future__ import annotations

from digigraph.orchestration import builtin  # noqa: F401 - ensure tools and skills are registered
from digigraph.skills.registry import Skill, register_skill


def _register_builtin_skills() -> None:
    register_skill(
        Skill(
            id="search",
            name="Search",
            description="DigiSearch: digisearch and digisearch_fetch_all. Available when DigiSearch URL is set.",
            tool_names=["digisearch", "digisearch_fetch_all"],
            when=None,  # gating is in orchestration.builtin
        )
    )
    register_skill(
        Skill(
            id="sitaas_rag",
            name="Sitaas RAG",
            description="Search plus delegate agents (visualization, analysis, data_prep, data_manipulation, data_engineer) and todo (plan) tool. When run_data_dir is set.",
            tool_names=[
                "digisearch",
                "digisearch_fetch_all",
                "digistore_list",
                "digistore_profile",
                "visualization_agent",
                "analysis_agent",
                "data_prep_agent",
                "data_manipulation_agent",
                "data_engineer_agent",
                "todo",
                "create_plan",
            ],
            when=None,
        )
    )


_register_builtin_skills()
