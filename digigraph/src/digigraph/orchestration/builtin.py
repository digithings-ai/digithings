"""Register built-in orchestrator tools and skills. Import this module to populate the registry."""

from __future__ import annotations

# Agent runners re-exported for test patches on builtin.run_*_agent
from digigraph.agents.analysis.runner import run_analysis_agent  # noqa: F401
from digigraph.agents.analysis.schema import ANALYSIS_AGENT_TOOL
from digigraph.agents.data_engineer.runner import run_data_engineer_agent  # noqa: F401
from digigraph.agents.data_engineer.schema import DATA_ENGINEER_AGENT_TOOL
from digigraph.agents.data_manipulation.runner import run_data_manipulation_agent  # noqa: F401
from digigraph.agents.data_manipulation.schema import DATA_MANIPULATION_AGENT_TOOL
from digigraph.agents.data_prep.runner import run_data_prep_agent  # noqa: F401
from digigraph.agents.data_prep.schema import DATA_PREP_AGENT_TOOL
from digigraph.agents.visualization.runner import run_visualization_agent  # noqa: F401
from digigraph.agents.visualization.schema import VISUALIZATION_AGENT_TOOL
from digigraph.orchestration.agent_tools import (
    _handle_analysis,
    _handle_data_engineer,
    _handle_data_manipulation,
    _handle_data_prep,
    _handle_visualization,
)
from digigraph.orchestration.digisearch_tools import (
    _handle_digisearch,
    _handle_digisearch_fetch_all,
    _handle_digisearch_research_delegate,
    _schema_digisearch_research_delegate,
    _schema_from_digisearch_manifest,
)
from digigraph.orchestration.digistore_tools import (
    DIGISTORE_LIST_TOOL,
    DIGISTORE_PROFILE_TOOL,
    _handle_digistore_list,
    _handle_digistore_profile,
)
from digigraph.orchestration.digivault_tools import (  # noqa: F401
    _DIGIVAULT_GET_NOTE_NO_PREFIX_ERROR,
    _DIGIVAULT_SEARCH_NO_PREFIX_ERROR,
    _handle_digivault_get_note,
    _handle_digivault_search,
    _note_to_result_and_payload,
    _schema_from_digivault_manifest,
)
from digigraph.orchestration.federated_tools import (
    _handle_digiquant_pipeline_delegate,
    _schema_digiquant_pipeline_delegate,
)
from digigraph.orchestration.planning_tools import (
    CREATE_PLAN_TOOL,
    TODO_TOOL,
    _handle_create_plan,
    _handle_todo,
)
from digigraph.orchestration.plugins import load_entrypoint_tools
from digigraph.orchestration.registry import register_skill, register_tool
from digigraph.orchestration.tool_common import (  # noqa: F401
    _LLM_SEARCH_PREVIEW_CHARS,
    _LLM_SEARCH_PREVIEW_ROWS,
    _digisearch_available,
    _digivault_available,
    _mark_truncated_excerpts,
    _merged_digisearch_filters,
    _preview_field,
    _search_payload_for_llm,
)
from digigraph.orchestration.web_search_tools import (
    WEB_SEARCH_TOOL,
    WEB_SEARCH_TOOL_NAME,
    _handle_web_search,
    _web_search_available,
)
from digigraph.policy import code_execution_allowed, federated_hub_enabled

# Re-export hub invoke helpers so existing tests can patch
# ``digigraph.orchestration.builtin.invoke_*`` — handlers themselves call through
# their own modules, so prefer patching digisearch_tools / digivault_tools /
# federated_tools. These aliases keep older import paths working.
from digigraph.vertical_orchestrator import (  # noqa: F401
    fetch_digiquant_tool_dicts,
    fetch_digisearch_tool_dicts,
    fetch_digivault_tool_dicts,
    invoke_digiquant_tool,
    invoke_digisearch_tool,
    invoke_digivault_tool,
)

DELEGATE_TAGS = {"delegate", "parallel_safe"}


def _federated_delegate_tool_names() -> list[str]:
    if not federated_hub_enabled():
        return []
    return ["digisearch_research_delegate", "digiquant_pipeline_delegate"]


def _register_tools() -> None:
    register_tool(
        "digisearch",
        None,
        _handle_digisearch,
        schema_factory=lambda ctx: _schema_from_digisearch_manifest(ctx, "digisearch"),
    )
    register_tool(
        "digisearch_fetch_all",
        None,
        _handle_digisearch_fetch_all,
        schema_factory=lambda ctx: _schema_from_digisearch_manifest(ctx, "digisearch_fetch_all"),
    )
    register_tool(
        "digivault_search_notes",
        None,
        _handle_digivault_search,
        schema_factory=lambda ctx: _schema_from_digivault_manifest(ctx, "digivault_search_notes"),
    )
    register_tool(
        "digivault_get_note",
        None,
        _handle_digivault_get_note,
        schema_factory=lambda ctx: _schema_from_digivault_manifest(ctx, "digivault_get_note"),
    )
    register_tool(
        "visualization_agent",
        VISUALIZATION_AGENT_TOOL,
        _handle_visualization,
        tags=DELEGATE_TAGS,
    )
    register_tool(
        "analysis_agent",
        ANALYSIS_AGENT_TOOL,
        _handle_analysis,
        tags=DELEGATE_TAGS,
    )
    register_tool(
        "data_prep_agent",
        DATA_PREP_AGENT_TOOL,
        _handle_data_prep,
        tags=DELEGATE_TAGS,
    )
    register_tool(
        "data_manipulation_agent",
        DATA_MANIPULATION_AGENT_TOOL,
        _handle_data_manipulation,
        tags=DELEGATE_TAGS,
    )
    if code_execution_allowed():
        register_tool(
            "data_engineer_agent",
            DATA_ENGINEER_AGENT_TOOL,
            _handle_data_engineer,
            tags=DELEGATE_TAGS,
        )
    register_tool(
        "digistore_list",
        DIGISTORE_LIST_TOOL,
        _handle_digistore_list,
    )
    register_tool(
        "digistore_profile",
        DIGISTORE_PROFILE_TOOL,
        _handle_digistore_profile,
    )
    register_tool(
        "todo",
        TODO_TOOL,
        _handle_todo,
    )
    register_tool(
        "create_plan",
        CREATE_PLAN_TOOL,
        _handle_create_plan,
    )
    register_tool(
        WEB_SEARCH_TOOL_NAME,
        WEB_SEARCH_TOOL,
        _handle_web_search,
    )
    if federated_hub_enabled():
        register_tool(
            "digisearch_research_delegate",
            None,
            _handle_digisearch_research_delegate,
            tags=DELEGATE_TAGS,
            schema_factory=_schema_digisearch_research_delegate,
        )
        register_tool(
            "digiquant_pipeline_delegate",
            None,
            _handle_digiquant_pipeline_delegate,
            tags=DELEGATE_TAGS,
            schema_factory=_schema_digiquant_pipeline_delegate,
        )


def _project_rag_tool_names() -> list[str]:
    names = [
        "digisearch",
        "digisearch_fetch_all",
        "digistore_list",
        "digistore_profile",
        "visualization_agent",
        "analysis_agent",
        "data_prep_agent",
        "data_manipulation_agent",
    ]
    if code_execution_allowed():
        names.append("data_engineer_agent")
    names.extend(["todo", "create_plan", *_federated_delegate_tool_names()])
    return names


def _register_skills() -> None:
    search_bundle = ["digisearch", "digisearch_fetch_all", *_federated_delegate_tool_names()[:1]]
    register_skill(
        "search",
        search_bundle,
        when=lambda ctx: _digisearch_available(ctx),
    )
    register_skill(
        "project_rag",
        _project_rag_tool_names(),
        when=lambda ctx: ctx.has_run_data_dir,
    )
    register_skill(
        "digivault",
        ["digivault_search_notes", "digivault_get_note"],
        when=lambda ctx: _digivault_available(ctx),
    )
    register_skill(
        "web",
        [WEB_SEARCH_TOOL_NAME],
        when=_web_search_available,
    )


_register_tools()
_register_skills()
load_entrypoint_tools()
