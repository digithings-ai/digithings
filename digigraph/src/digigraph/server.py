"""DigiGraph HTTP API. Phase 0: run_digigraph_workflow. Phase 1+: LangGraph + MCP."""

from __future__ import annotations

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from digigraph.llm import chat_completion, get_model_for_mode
from digigraph.models import WorkflowRequest, WorkflowResult
from digigraph.workflow import run_digigraph_workflow

app = FastAPI(
    title="DigiGraph",
    description="Orchestration brain: run_digigraph_workflow (DigiClaw custom skill)",
    version="0.1.0",
)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/health")
def health() -> dict[str, str]:
    """Health check for Docker and DigiClaw."""
    return {"status": "ok", "service": "digigraph"}


@app.get("/test_llm")
def test_llm() -> dict[str, str | bool]:
    """
    Test DigiGraph → LiteLLM → Ollama (or configured provider).
    Same code path as workflow research node; no backtest.
    """
    try:
        model = get_model_for_mode()
        reply = chat_completion(
            model,
            [{"role": "user", "content": "Reply with exactly: OK"}],
        )
        return {"ok": True, "model": model, "reply": reply or "(empty)"}
    except Exception as e:  # noqa: BLE001
        return {"ok": False, "model": "", "reply": "", "error": str(e)}


@app.post("/workflow", response_model=WorkflowResult)
def api_run_digigraph_workflow(req: WorkflowRequest) -> WorkflowResult:
    """
    DigiClaw custom skill: run_digigraph_workflow.
    Phase 0: user idea → backtest via DigiQuant → result in < 10s.
    """
    return run_digigraph_workflow(req)
