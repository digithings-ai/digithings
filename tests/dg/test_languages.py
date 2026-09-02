"""Unit tests for the response-language directive builder."""

from __future__ import annotations

import re
from pathlib import Path
from types import SimpleNamespace

import pytest
from digigraph.graph.research import research_node
from digigraph.graph.state import WorkflowState
from digigraph.languages import LANGUAGE_NAMES, resolve_language_directive
from digigraph.models import WorkflowRequest
from digigraph.server import _digi_fields_from_request
from digigraph.workflow import _initial_graph_state

pytestmark = pytest.mark.unit


def test_language_names_covers_the_curated_list() -> None:
    assert LANGUAGE_NAMES == {
        "en": "English",
        "de": "German",
        "it": "Italian",
        "es": "Spanish",
        "fr": "French",
    }


def test_resolve_language_directive_for_known_non_english_code() -> None:
    directive = resolve_language_directive("de")
    assert directive is not None
    assert "German" in directive
    # #3417: answering in German must not rewrite retrieval queries into German.
    assert "retriev" in directive.lower()
    assert "do not translate" in directive.lower()


def test_resolve_language_directive_is_case_insensitive() -> None:
    assert resolve_language_directive("DE") == resolve_language_directive("de")


def test_resolve_language_directive_none_for_english() -> None:
    assert resolve_language_directive("en") is None


@pytest.mark.parametrize("bad", [None, "", "  ", "xx", "klingon", "<script>"])
def test_resolve_language_directive_none_for_unknown_or_missing(bad: str | None) -> None:
    assert resolve_language_directive(bad) is None


def test_workflow_state_declares_response_language() -> None:
    """LangGraph drops undeclared TypedDict keys — see #2097."""
    assert "response_language" in WorkflowState.__annotations__


def test_initial_graph_state_carries_response_language() -> None:
    state = _initial_graph_state(
        WorkflowRequest(prompt="hi", response_language="de"),
        "wf-lang",
    )
    assert state["response_language"] == "de"


def test_initial_graph_state_sets_response_language_to_none_when_unset() -> None:
    """response_language must be written unconditionally (even as explicit None)

    so a later turn with no language header clears a prior non-English value from
    checkpointed state instead of leaving it sticky (see #2103 final review,
    Fix 2). Corpus overrides and digi_subject use the same unconditional-None
    pattern so DIGI_TENANT_CORPUS_MAP clears reach the checkpoint.
    """
    state = _initial_graph_state(WorkflowRequest(prompt="hi"), "wf-lang-2")
    assert "response_language" in state
    assert state["response_language"] is None


def test_initial_graph_state_clears_response_language_on_next_turn() -> None:
    """Two sequential per-turn calls: 'de' then unset must produce an explicit

    None key on the second call, not merely an absent key — that's what lets
    LangGraph's per-key last-write-wins checkpoint merge actually clear a
    previously-persisted non-English value.
    """
    first = _initial_graph_state(
        WorkflowRequest(prompt="hallo", response_language="de"), "wf-lang-3"
    )
    assert first["response_language"] == "de"

    second = _initial_graph_state(WorkflowRequest(prompt="hi"), "wf-lang-3")
    assert "response_language" in second
    assert second["response_language"] is None


def test_digi_fields_from_request_reads_language_header() -> None:
    """The single header->WorkflowRequest bridge must populate response_language

    from X-Digi-Language (see #2103 final review, Fix 1) — without this, the
    header is read nowhere in production and the whole directive path is
    unreachable.
    """
    request = SimpleNamespace(state=SimpleNamespace(), headers={"x-digi-language": "de"})
    updates = _digi_fields_from_request(request)
    assert updates["response_language"] == "de"


def test_digi_fields_from_request_omits_language_when_header_absent() -> None:
    request = SimpleNamespace(state=SimpleNamespace(), headers={})
    updates = _digi_fields_from_request(request)
    assert "response_language" not in updates


def test_digi_fields_from_request_caps_an_overlong_language_header() -> None:
    """Defense-in-depth: an arbitrarily long X-Digi-Language header must not

    sit in WorkflowRequest/checkpointed state verbatim (see #2103 final
    review, Minor finding A). It's never interpolated into a prompt
    (resolve_language_directive only ever emits mapped display names), but a
    length cap keeps an oversized value out of checkpoint storage. Curated
    codes are 2 characters, so the cap is generous headroom, not a functional
    constraint.
    """
    request = SimpleNamespace(state=SimpleNamespace(), headers={"x-digi-language": "x" * 5000})
    updates = _digi_fields_from_request(request)
    assert len(updates["response_language"]) <= 16


def test_language_lists_stay_in_sync_with_frontend() -> None:
    """Cross-check digigraph.languages.LANGUAGE_NAMES against the TS curated

    list so a language added to one side without the other is caught here,
    rather than silently returning None from resolve_language_directive (see
    #2103 final review, Fix 3).

    Only a MISSING frontend file skips — that's a legitimate "the file moved"
    case. Once the file exists, failing to locate/parse the LANGUAGES array
    literal is a hard FAILURE, not a skip (see #2103 final review, Minor
    finding B): that outcome means the sync check itself has silently stopped
    working (e.g. the regex drifted from the source's actual shape), which
    must never read as green in CI.
    """
    frontend_path = (
        Path(__file__).resolve().parents[2]
        / "frontend"
        / "digichat"
        / "src"
        / "lib"
        / "languages.ts"
    )
    if not frontend_path.exists():
        pytest.skip(f"frontend languages.ts not found at {frontend_path} — skipping sync check")

    source = frontend_path.read_text(encoding="utf-8")
    match = re.search(
        r"LANGUAGES:\s*\{\s*code:\s*string;\s*label:\s*string\s*\}\[\]\s*=\s*\[(.*?)\];",
        source,
        re.DOTALL,
    )
    if not match:
        pytest.fail(
            f"could not locate LANGUAGES array literal in {frontend_path} — "
            "the sync check regex no longer matches the frontend source (file "
            "exists, so this is not a legitimate skip)"
        )

    pairs = re.findall(
        r'\{\s*code:\s*"([^"]+)",\s*label:\s*"([^"]+)"\s*\}',
        match.group(1),
    )
    if not pairs:
        pytest.fail(
            f"LANGUAGES array literal matched in {frontend_path} but no "
            "{code, label} pairs were parsed — the sync check regex no longer "
            "matches the frontend source (file exists, so this is not a "
            "legitimate skip)"
        )

    frontend_languages = {code: label for code, label in pairs}
    assert frontend_languages == LANGUAGE_NAMES


def test_langgraph_preserves_response_language_through_invoke() -> None:
    """Regression: StateGraph(WorkflowState) must not strip response_language."""
    from langgraph.graph import END, START, StateGraph

    seen: dict[str, str | None] = {}

    def _capture(state: WorkflowState) -> dict:
        seen["response_language"] = state.get("response_language")
        return {}

    builder: StateGraph[WorkflowState] = StateGraph(WorkflowState)
    builder.add_node("capture", _capture)
    builder.add_edge(START, "capture")
    builder.add_edge("capture", END)
    graph = builder.compile()
    graph.invoke({"prompt": "x", "response_language": "de"})
    assert seen["response_language"] == "de"


def test_research_node_appends_directive_for_known_language(monkeypatch) -> None:
    monkeypatch.setenv("DIGISEARCH_URL", "http://digisearch:8002")
    captured: dict = {}

    def fake_document_rag_path(*, system_prompt, **_kwargs):
        captured["system_prompt"] = system_prompt
        return {"research_note": "ok"}

    monkeypatch.setattr(
        "digigraph.graph.research._run_document_rag_path",
        lambda **kwargs: fake_document_rag_path(**kwargs),
    )
    monkeypatch.setattr(
        "digigraph.graph.research._load_research_settings",
        lambda: (None, "default", "default", "You are a helpful assistant."),
    )
    research_node({"prompt": "hallo", "response_language": "de"})
    assert "You are a helpful assistant." in captured["system_prompt"]
    assert "German" in captured["system_prompt"]


def test_research_node_leaves_prompt_unchanged_for_english_or_unset(monkeypatch) -> None:
    monkeypatch.setenv("DIGISEARCH_URL", "http://digisearch:8002")
    captured: dict = {}

    monkeypatch.setattr(
        "digigraph.graph.research._run_document_rag_path",
        lambda **kwargs: (
            captured.update(system_prompt=kwargs["system_prompt"]) or {"research_note": "ok"}
        ),
    )
    monkeypatch.setattr(
        "digigraph.graph.research._load_research_settings",
        lambda: (None, "default", "default", "You are a helpful assistant."),
    )
    research_node({"prompt": "hi", "response_language": "en"})
    assert captured["system_prompt"] == "You are a helpful assistant."


def test_research_node_takes_quant_path_when_system_prompt_is_default(monkeypatch) -> None:
    """Regression guard for the append-after-is_document_mode placement.

    With no ``research_system_prompt_override`` and no tenant custom prompt,
    ``_load_research_settings`` returns the real ``RESEARCH_SYSTEM`` constant, so
    ``is_document_mode`` must be computed (and be False) BEFORE the language
    directive is appended. If the append were moved before that comparison, the
    appended directive text alone would make ``system_prompt != RESEARCH_SYSTEM``
    and misroute this plain quant-strategy request into the document-RAG path.
    """
    from digigraph.graph.research import RESEARCH_SYSTEM

    captured: dict = {}

    monkeypatch.setattr(
        "digigraph.graph.research._run_document_rag_path",
        lambda **kwargs: captured.update(document_rag_called=True) or {"research_note": "ok"},
    )
    monkeypatch.setattr(
        "digigraph.graph.research._run_quant_or_augmented_path",
        lambda **kwargs: (
            captured.update(quant_path_called=True, is_document_mode=kwargs.get("is_document_mode"))
            or {"research_note": "LLM-extracted"}
        ),
    )
    monkeypatch.setattr(
        "digigraph.graph.research._load_research_settings",
        lambda: (None, "default", "default", RESEARCH_SYSTEM),
    )

    research_node({"prompt": "build me a mean-reversion strategy", "response_language": "de"})

    assert "document_rag_called" not in captured
    assert captured.get("quant_path_called") is True
    assert captured.get("is_document_mode") is False


def test_research_node_appends_directive_to_tenant_override_prompt(monkeypatch) -> None:
    monkeypatch.setenv("DIGISEARCH_URL", "http://digisearch:8002")
    captured: dict = {}

    monkeypatch.setattr(
        "digigraph.graph.research._run_document_rag_path",
        lambda **kwargs: (
            captured.update(system_prompt=kwargs["system_prompt"]) or {"research_note": "ok"}
        ),
    )
    monkeypatch.setattr(
        "digigraph.graph.research._load_research_settings",
        lambda: (None, "occ_help", "occ_help", "You are a helpful assistant."),
    )
    research_node(
        {
            "prompt": "hallo",
            "response_language": "de",
            "research_system_prompt_override": "You are the OCC help assistant.",
        }
    )
    assert captured["system_prompt"].startswith("You are the OCC help assistant.")
    assert "German" in captured["system_prompt"]
