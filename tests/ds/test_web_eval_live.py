"""Research-turn eval harness (#4064, Task 6).

Offline by default: the Task 1 retrieval seam (``retrieve._live`` /
``retrieve._fetch``) and the rerank stage (``answer._rank`` /
``structured._rank``) are patched, and ``digillm.client.completion`` is faked,
so every research case runs with no network, no model weights, and no digillm
key while the real ``grounded_answer`` / ``structured_synthesis`` assembly,
``verify_grounding``, ``_numbered_sources``, and accounting code still run.

Live mode is opt-in behind ``DIGISEARCH_WEB_SEARCH_LIVE=1`` (the landed gate):
it runs one sampled case per category against the real search backends
(searxng sidecar → ddgs failover) + digillm and prints p50 stage ms +
citation coverage per effort. Those numbers are single-key, single-day
SCAFFOLDING anchors — never SLO constants; re-measure per environment and
record date/key tier in ``digisearch/ARCHITECTURE.md`` before quoting them
(Phase B spec, Goal).
"""

from __future__ import annotations

import json
import os
import re
import statistics
import sys
from collections.abc import Callable
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest
from digisearch.web.grounding_models import EFFORT_PRESETS, EffortMode, TurnUsage
from digisearch.web.retrieve import FetchedPage
from digisearch.web_search.models import WebSearchResponse, WebSearchResult

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "digisearch" / "tests"))

from web_search_eval_cases import CASES, RESEARCH_CASES

pytestmark = pytest.mark.unit

LIVE = os.environ.get("DIGISEARCH_WEB_SEARCH_LIVE") == "1"

_CITATION_RE = re.compile(r"\[(\d+)\]")

#: Model id the offline fakes report; the real call resolves
#: ``DIGISEARCH_SYNTHESIS_MODEL`` (set per case by ``_patch_offline``).
_SYNTHESIS_MODEL = "test/web-research-eval"

#: The one structured shape every research case exercises: ``summary`` plus
#: one ``drivers[i]`` leaf per ``must_contain`` word.
STRUCTURED_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {
        "summary": {"type": "string"},
        "drivers": {"type": "array", "items": {"type": "string"}},
    },
    "required": ["summary", "drivers"],
}


def test_eval_harness_runs_offline():
    assert len(CASES) >= 20  # landed provider cases, untouched
    assert len(RESEARCH_CASES) >= 10  # Phase B research-turn additions
    assert all(c.get("must_cite", True) for c in RESEARCH_CASES)


# ── offline world ─────────────────────────────────────────────────────────────


def _case_slug(case: dict[str, Any]) -> str:
    return re.sub(r"[^a-z0-9]+", "-", str(case["query"]).lower()).strip("-")


def _hits_pages(case: dict[str, Any]) -> tuple[list[WebSearchResult], list[FetchedPage]]:
    """Deterministic pseudo-retrieval embedding the query + ``must_contain`` words."""
    query = str(case["query"])
    keywords = [str(word) for word in case["must_contain"]]
    slug = _case_slug(case)
    hits = [
        WebSearchResult(
            url=f"https://example.com/{slug}/{index}",
            title=f"{query} — source {index}",
            snippet=f"{query} ({', '.join(keywords)}) snippet {index}",
            score=1.0 - index / 10,
            engine="searxng",
        )
        for index in (1, 2)
    ]
    pages = [
        FetchedPage(
            url=hit.url,
            title=hit.title,
            markdown=f"{query} {' '.join(keywords)} body {index}",
        )
        for index, hit in enumerate(hits, start=1)
    ]
    return hits, pages


def _patch_offline(monkeypatch: pytest.MonkeyPatch, case: dict[str, Any]) -> list[FetchedPage]:
    """Patch the retrieval seam + rerank for one case; real synthesis still runs."""
    from digisearch.web import answer as answer_mod
    from digisearch.web import retrieve as retrieve_mod
    from digisearch.web import structured as structured_mod

    hits, pages = _hits_pages(case)

    def fake_live(query: str, top_n: int) -> WebSearchResponse:
        return WebSearchResponse(query=query, provider="searxng", results=hits[:top_n])

    def fake_fetch(ranked_hits: list[WebSearchResult], top_n: int) -> list[FetchedPage]:
        return pages[:top_n]

    def fake_rank(question: str, ranked: list[FetchedPage], top_n: int) -> list[FetchedPage]:
        return list(ranked)[:top_n]

    monkeypatch.setattr(retrieve_mod, "_live", fake_live)
    monkeypatch.setattr(retrieve_mod, "_fetch", fake_fetch)
    monkeypatch.setattr(answer_mod, "_rank", fake_rank)
    monkeypatch.setattr(structured_mod, "_rank", fake_rank)
    monkeypatch.setenv(answer_mod.SYNTHESIS_MODEL_ENV, _SYNTHESIS_MODEL)
    return pages


def _completion_response(text: str) -> Any:
    """Minimal duck-typed ChatCompletion (only choices[0].message.content is read)."""
    return SimpleNamespace(choices=[SimpleNamespace(message=SimpleNamespace(content=text))])


def _patch_completion(
    monkeypatch: pytest.MonkeyPatch,
    respond: Callable[[list[dict[str, Any]], dict[str, Any]], str],
) -> list[dict[str, Any]]:
    """Fake ``digillm.client.completion``; returns the recorded calls."""
    calls: list[dict[str, Any]] = []

    def completion(model: str, messages: list[dict[str, Any]], **kwargs: Any) -> Any:
        calls.append({"model": model, "messages": messages, **kwargs})
        return _completion_response(respond(messages, kwargs))

    monkeypatch.setattr("digillm.client.completion", completion)
    return calls


def _grounded_completion(case: dict[str, Any]) -> Callable[..., str]:
    """One cited line per ``must_contain`` word, alternating [1]/[2]."""
    query = str(case["query"])
    keywords = [str(word) for word in case["must_contain"]]

    def respond(messages: list[dict[str, Any]], kwargs: dict[str, Any]) -> str:
        lines = []
        for index, keyword in enumerate(keywords, start=1):
            cite = 1 if index % 2 else 2
            lines.append(f"{query} — {keyword} is supported by desks [{cite}]")
        return "\n".join(lines)

    return respond


def _structured_completion(case: dict[str, Any], source_urls: list[str]) -> Callable[..., str]:
    """Wrapper payload with one cited grounding entry per content leaf."""
    keywords = [str(word) for word in case["must_contain"]]
    content = {"summary": f"{case['query']} coverage", "drivers": keywords}

    def citation(index: int) -> dict[str, str]:
        return {
            "url": source_urls[index % len(source_urls)],
            "title": f"source {index}",
            "excerpt": f"excerpt {index}",
        }

    grounding = [
        {"field": "summary", "citations": [citation(0)], "confidence": "high"},
        *[
            {
                "field": f"drivers[{index}]",
                "citations": [citation(index + 1)],
                "confidence": "high",
            }
            for index in range(len(keywords))
        ],
    ]
    return lambda messages, kwargs: json.dumps({"content": content, "grounding": grounding})


def _answer_lines(answer: str) -> list[str]:
    return [line.strip() for line in answer.splitlines() if line.strip()]


def _cited_line(line: str, source_count: int) -> bool:
    """True when the line carries a ``[n]`` that points at a rendered source."""
    return any(1 <= int(match) <= source_count for match in _CITATION_RE.findall(line))


def _citation_coverage(answer: str, source_count: int) -> float:
    """Fraction of non-empty answer lines carrying a valid ``[n]`` citation."""
    lines = _answer_lines(answer)
    if not lines:
        return 0.0
    return sum(1 for line in lines if _cited_line(line, source_count)) / len(lines)


def _leaf_paths(value: Any, prefix: str = "") -> list[str]:
    """Dotted leaf paths for dict/list content (``summary``, ``drivers[0]``)."""
    if isinstance(value, dict):
        paths: list[str] = []
        for key, child in value.items():
            child_prefix = f"{prefix}.{key}" if prefix else str(key)
            paths.extend(_leaf_paths(child, child_prefix))
        return paths
    if isinstance(value, list):
        paths = []
        for index, child in enumerate(value):
            paths.extend(_leaf_paths(child, f"{prefix}[{index}]"))
        return paths
    return [prefix] if prefix else []


def _expected_cost(pages_fetched: int, llm_calls: int) -> dict[str, Any]:
    """The landed advisory-only cost envelope (``total`` never gates alone)."""
    return {
        "total": 0.0,
        "provider": "web-oss",
        "breakdown": {"searches": 1, "pages_fetched": pages_fetched, "llm_calls": llm_calls},
        "note": "oss-synthesis; llm spend metered in digillm telemetry, not here",
    }


# ── offline eval legs ─────────────────────────────────────────────────────────


def test_research_cases_grounded_answer_offline(monkeypatch):
    from digisearch.web.answer import grounded_answer

    for case in RESEARCH_CASES:
        assert case.get("must_cite"), f"{case['query']!r} must opt into citation checks"
        pages = _patch_offline(monkeypatch, case)
        calls = _patch_completion(monkeypatch, _grounded_completion(case))
        for effort in (EffortMode.FAST, EffortMode.THOROUGH):
            context = f"{case['query']!r} ({effort.value})"
            data, usage = grounded_answer(str(case["query"]), config=EFFORT_PRESETS[effort])

            text = str(data.output.get("text") or "")
            lines = _answer_lines(text)
            assert lines, f"{context}: empty answer"
            uncited = [line for line in lines if not _cited_line(line, len(pages))]
            assert not uncited, f"{context}: uncited answer lines {uncited}"

            lowered = text.lower()
            for keyword in case["must_contain"]:
                word = str(keyword).lower()
                assert word in lowered, f"{context}: {word!r} missing from the answer"
                assert any(word in str(row["snippet"]).lower() for row in data.results), (
                    f"{context}: {word!r} missing from the cited snippets"
                )

            assert data.search_type == f"web-{effort.value}"
            assert data.cost_dollars == _expected_cost(len(pages), llm_calls=1)
            assert isinstance(usage, TurnUsage)
            assert usage.searches == 1
            assert usage.llm_calls == 1
            assert usage.pages_cited == len(pages)
            assert usage.total_ms == (
                usage.search_ms + usage.fetch_ms + usage.rerank_ms + usage.synthesis_ms
            )

        assert calls, f"{case['query']!r}: digillm completion was never called"
        assert all(call["model"] == _SYNTHESIS_MODEL for call in calls)
        assert all(call["usage_kind"] == "web_search" for call in calls)


def test_research_cases_structured_synthesis_offline(monkeypatch):
    from digisearch.web.structured import structured_synthesis

    for case in RESEARCH_CASES:
        context = f"{case['query']!r} (structured)"
        pages = _patch_offline(monkeypatch, case)
        _patch_completion(monkeypatch, _structured_completion(case, [p.url for p in pages]))
        data, usage = structured_synthesis(
            str(case["query"]),
            output_schema=STRUCTURED_SCHEMA,
            config=EFFORT_PRESETS[EffortMode.THOROUGH],
        )

        content = data.output.get("content")
        grounding = data.output.get("grounding")
        assert isinstance(content, dict), f"{context}: content is not a dict"
        assert isinstance(grounding, list) and grounding, f"{context}: no grounding entries"
        assert set(STRUCTURED_SCHEMA["required"]) <= set(content), f"{context}: required keys"

        cited_urls = {page.url for page in pages}
        by_field = {str(entry.get("field")): entry for entry in grounding}
        for path in _leaf_paths(content):
            entry = by_field.get(path)
            assert entry is not None, f"{context}: leaf {path!r} has no grounding entry"
            citations = entry.get("citations") or []
            assert citations, f"{context}: leaf {path!r} has no citation"
            assert any(str(c.get("url")) in cited_urls for c in citations), (
                f"{context}: leaf {path!r} cites nothing from the retrieved set"
            )
            assert entry.get("confidence") != "unverified", f"{context}: leaf {path!r} verifies"

        assert data.search_type == "web-thorough"
        assert data.cost_dollars == _expected_cost(len(pages), llm_calls=1)
        assert isinstance(usage, TurnUsage)
        assert usage.llm_calls == 1
        assert usage.pages_cited == len(pages)


def test_offline_oss_envelope_renders_through_format_web_results(monkeypatch):
    """OSS -> EXA interchange: the landed renderer consumes an OSS envelope."""
    from digisearch.web.answer import grounded_answer
    from digisearch.web_exa import format_web_results

    case = RESEARCH_CASES[0]
    pages = _patch_offline(monkeypatch, case)
    _patch_completion(monkeypatch, _grounded_completion(case))
    data, _ = grounded_answer(str(case["query"]), config=EFFORT_PRESETS[EffortMode.FAST])

    rendered = format_web_results(data)
    for page in pages:
        assert page.url in rendered
        assert page.title in rendered
    for line in _answer_lines(str(data.output["text"])):
        # ``output`` renders via dict repr, so embedded newlines escape but each
        # answer line stays verbatim.
        assert line in rendered
    for page in pages:
        # OSS `snippet` rows degrade to Title/URL only — never a crash, and the
        # raw page body is never re-rendered by the EXA-shaped renderer.
        assert page.markdown not in rendered


# ── live eval legs (opt-in scaffolding; never SLOs) ───────────────────────────


def _live_sample() -> list[dict[str, Any]]:
    """One case per category, mirroring the landed provider-suite live sample."""
    seen: set[str] = set()
    sample: list[dict[str, Any]] = []
    for case in RESEARCH_CASES:
        category = str(case.get("category") or "")
        if category and category not in seen:
            seen.add(category)
            sample.append(case)
    return sample


@pytest.mark.skipif(not LIVE, reason="live web eval needs DIGISEARCH_WEB_SEARCH_LIVE=1")
def test_live_grounded_answers_record_stage_ms_and_coverage():
    from digisearch.web.answer import INSUFFICIENT_SOURCES, grounded_answer

    sample = _live_sample()
    assert sample, "RESEARCH_CASES must carry at least one categorized case"
    record: dict[str, dict[str, float]] = {}
    for effort in (EffortMode.FAST, EffortMode.THOROUGH):
        stages: dict[str, list[float]] = {
            "search_ms": [],
            "fetch_ms": [],
            "rerank_ms": [],
            "synthesis_ms": [],
            "total_ms": [],
        }
        coverage: list[float] = []
        for case in sample:
            data, usage = grounded_answer(str(case["query"]), config=EFFORT_PRESETS[effort])
            text = str(data.output.get("text") or "")
            assert text.strip(), f"{case['query']!r}: empty live answer"
            assert not text.startswith(INSUFFICIENT_SOURCES), (
                f"{case['query']!r}: live synthesis produced no cited answer"
            )
            assert data.cost_dollars and data.cost_dollars.get("provider") == "web-oss"
            assert isinstance(usage, TurnUsage) and usage.llm_calls >= 1
            for stage in stages:
                stages[stage].append(float(getattr(usage, stage)))
            coverage.append(_citation_coverage(text, len(data.results)))
        record[effort.value] = {
            **{stage: statistics.median(values) for stage, values in stages.items()},
            "citation_coverage_p50": statistics.median(coverage),
            "n": float(len(sample)),
        }
    print(f"web-eval live record (grounded): {json.dumps(record, sort_keys=True)}")


@pytest.mark.skipif(not LIVE, reason="live web eval needs DIGISEARCH_WEB_SEARCH_LIVE=1")
def test_live_structured_synthesis_grounds_every_field():
    from digisearch.web.structured import structured_synthesis

    sample = _live_sample()
    assert sample, "RESEARCH_CASES must carry at least one categorized case"
    record: dict[str, dict[str, float]] = {}
    for effort in (EffortMode.FAST, EffortMode.THOROUGH):
        coverage: list[float] = []
        for case in sample:
            data, usage = structured_synthesis(
                str(case["query"]),
                output_schema=STRUCTURED_SCHEMA,
                config=EFFORT_PRESETS[effort],
            )
            content = data.output.get("content") or {}
            grounding = data.output.get("grounding") or []
            assert isinstance(content, dict) and content, f"{case['query']!r}: empty content"
            assert set(STRUCTURED_SCHEMA["required"]) <= set(content), (
                f"{case['query']!r}: required keys missing from live content"
            )
            cited_urls = {str(row.get("url")) for row in data.results}
            for entry in grounding:
                citations = entry.get("citations") or []
                assert citations, f"{case['query']!r}: field {entry.get('field')!r} has no citation"
                assert any(str(c.get("url")) in cited_urls for c in citations), (
                    f"{case['query']!r}: field {entry.get('field')!r} cites nothing retrieved"
                )
            leaves = _leaf_paths(content)
            assert leaves, f"{case['query']!r}: live content has no resolvable leaf fields"
            have = {str(entry.get("field")) for entry in grounding}
            coverage.append(len(set(leaves) & have) / len(leaves))
            assert data.cost_dollars and data.cost_dollars.get("provider") == "web-oss"
            assert isinstance(usage, TurnUsage) and usage.llm_calls == 1
        record[effort.value] = {
            "field_coverage_p50": statistics.median(coverage),
            "n": float(len(sample)),
        }
    print(f"web-eval live record (structured): {json.dumps(record, sort_keys=True)}")
