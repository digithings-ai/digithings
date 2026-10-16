"""Planning tools: todo and create_plan."""

from __future__ import annotations

from typing import Any

from digigraph.orchestration.registry import ToolContext

TODO_TOOL: dict[str, Any] = {
    "type": "function",
    "function": {
        "name": "todo",
        "description": "Emit a list of intended tasks or steps for this request. Use to make your plan explicit before executing tools (e.g. 'search all from X', 'chart by date', 'export CSV'). The list is recorded for context; execution continues with the normal tool loop.",
        "parameters": {
            "type": "object",
            "properties": {
                "tasks": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "Ordered list of task descriptions.",
                }
            },
            "required": ["tasks"],
        },
    },
}


def _handle_todo(args: dict[str, Any], context: ToolContext) -> str | dict[str, Any]:
    """Record the LLM's intended task list; return a short confirmation."""
    tasks = args.get("tasks") or []
    if not isinstance(tasks, list):
        tasks = [str(tasks)]
    tasks = [str(t) for t in tasks if t]
    if context.state is not None:
        context.state["todo_plan"] = tasks
    n = len(tasks)
    return {"content": f"Recorded {n} task(s). Proceed with your tools."}


CREATE_PLAN_TOOL: dict[str, Any] = {
    "type": "function",
    "function": {
        "name": "create_plan",
        "description": "Submit a structured execution plan: ordered steps with agent names, arguments, and optional depends_on. Use {{step_id.field}} in args to reference prior step outputs (e.g. {{1.dataset_ref}}). The executor will run steps in dependency order and in parallel when independent.",
        "parameters": {
            "type": "object",
            "properties": {
                "steps": {
                    "type": "array",
                    "items": {
                        "type": "object",
                        "properties": {
                            "id": {"type": "string", "description": "Step id (e.g. '1', '2')."},
                            "agent": {
                                "type": "string",
                                "description": "Tool/agent name (e.g. digisearch_fetch_all, visualization_agent).",
                            },
                            "args": {
                                "type": "object",
                                "description": "Arguments for the agent. Use {{step_id.field}} for placeholders.",
                            },
                            "depends_on": {
                                "type": "array",
                                "items": {"type": "string"},
                                "description": "Step ids that must complete before this step.",
                            },
                        },
                        "required": ["id", "agent"],
                    },
                    "description": "Ordered steps to execute.",
                }
            },
            "required": ["steps"],
        },
    },
}


def _handle_create_plan(args: dict[str, Any], context: ToolContext) -> str | dict[str, Any]:
    """Store the structured plan in state for the executor; return confirmation and plan."""
    steps = args.get("steps") or []
    if not isinstance(steps, list):
        return {"content": "steps must be a list."}
    normalized = []
    for s in steps:
        if not isinstance(s, dict):
            continue
        step_id = s.get("id")
        agent = s.get("agent")
        if not step_id or not agent:
            continue
        normalized.append(
            {
                "id": str(step_id),
                "agent": str(agent),
                "args": s.get("args") if isinstance(s.get("args"), dict) else {},
                "depends_on": [str(d) for d in s.get("depends_on") or []]
                if isinstance(s.get("depends_on"), list)
                else [],
            }
        )
    if context.state is not None:
        context.state["plan"] = normalized
    return {
        "content": f"Plan recorded ({len(normalized)} steps). Executor will run when planning_mode is enabled.",
        "plan": normalized,
    }
