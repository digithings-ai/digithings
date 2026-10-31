"""Unit tests for the ADR-0036 OTel span contract (DIG-2656)."""

from __future__ import annotations

import re
import sys
import types
from typing import Any

import pytest

from digitrace import config as config_mod
from digitrace import trace as trace_mod

_OTEL_ENVS = (
    "LANGSMITH_API_KEY",
    "DIGI_OTEL_ENDPOINT",
    "OTEL_EXPORTER_OTLP_ENDPOINT",
    "DIGITRACE_LANGFUSE_OTLP_ENDPOINT",
    "LANGFUSE_OTLP_ENDPOINT",
    "LANGFUSE_HOST",
    "LANGFUSE_URL",
    "DIGI_TRACE_CONTENT_PREVIEW",
    "DIGITRACE_CONTENT_PREVIEW",
    "DIGI_TRACE_PREVIEW_CHARS",
)

_SHA256_RE = re.compile(r"[0-9a-f]{64}")


@pytest.fixture(autouse=True)
def _clear_otel_env(monkeypatch: pytest.MonkeyPatch) -> None:
    for key in _OTEL_ENVS:
        monkeypatch.delenv(key, raising=False)
    monkeypatch.setattr(trace_mod, "LANGSMITH_SDK_AVAILABLE", False)


def _install_fake_otel(monkeypatch: pytest.MonkeyPatch) -> list[dict[str, Any]]:
    """Install a minimal OTel API that records every closed span."""
    spans: list[dict[str, Any]] = []
    pkg = types.ModuleType("opentelemetry")
    trace_api = types.ModuleType("opentelemetry.trace")

    class _StatusCode:
        UNSET = "UNSET"
        OK = "OK"
        ERROR = "ERROR"

    class _FakeSpan:
        def __init__(self, name: str, attributes: dict[str, Any] | None) -> None:
            self.name = name
            self.attributes: dict[str, Any] = dict(attributes or {})
            self.status: str = _StatusCode.UNSET

        def set_attribute(self, key: str, value: Any) -> None:
            self.attributes[key] = value

        def set_status(self, status: str) -> None:
            self.status = status

    class _FakeSpanCM:
        def __init__(self, span: _FakeSpan) -> None:
            self._span = span

        def __enter__(self) -> _FakeSpan:
            return self._span

        def __exit__(self, *args: object) -> bool:
            spans.append(
                {
                    "name": self._span.name,
                    "attributes": self._span.attributes,
                    "status": self._span.status,
                }
            )
            return False

    class _FakeTracer:
        def start_as_current_span(
            self, name: str, attributes: dict[str, Any] | None = None
        ) -> _FakeSpanCM:
            return _FakeSpanCM(_FakeSpan(name, attributes))

    trace_api.StatusCode = _StatusCode  # type: ignore[attr-defined]
    trace_api.get_tracer = lambda name: _FakeTracer()  # type: ignore[attr-defined]
    pkg.trace = trace_api  # type: ignore[attr-defined]
    monkeypatch.setitem(sys.modules, "opentelemetry", pkg)
    monkeypatch.setitem(sys.modules, "opentelemetry.trace", trace_api)
    return spans


def _enable_otel(monkeypatch: pytest.MonkeyPatch) -> list[dict[str, Any]]:
    monkeypatch.setenv("DIGI_OTEL_ENDPOINT", "http://otel:4318")
    return _install_fake_otel(monkeypatch)


class _Usage:
    prompt_tokens = 11
    completion_tokens = 7
    total_tokens = 18


class _CompletionResult:
    usage = _Usage()


@pytest.mark.unit
def test_config_has_no_duplicate_otlp_endpoint_chain() -> None:
    """ADR-0036 §6: the endpoint chain lives in digibase.otel only."""
    assert not hasattr(config_mod, "_OTLP_ENDPOINT_ENVS")


@pytest.mark.unit
def test_span_attribute_allowlist_drops_unknown_and_non_scalars() -> None:
    cleaned = trace_mod.apply_span_allowlist(
        {
            "gen_ai.request.model": "openai/gpt-4o",
            "prompt": "secret",
            "api_key": "sk-abcdefghij1234567",
            "digi.input.preview": "",
            "gen_ai.usage.input_tokens": 3,
            "not.allowed": {"nested": "payload"},
        }
    )
    assert cleaned == {
        "gen_ai.request.model": "openai/gpt-4o",
        "gen_ai.usage.input_tokens": 3,
    }


@pytest.mark.unit
def test_otel_leg_emits_model_provider_tokens_and_ids(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    spans = _enable_otel(monkeypatch)

    @trace_mod.traceable("completion")
    def fn(
        model: str,
        messages: list[dict[str, str]],
        *,
        tenant_id: str = "",
        pipeline_run_id: str = "",
        session_id: str = "",
    ) -> _CompletionResult:
        return _CompletionResult()

    fn(
        "openai/gpt-4o",
        [{"role": "user", "content": "hello"}],
        tenant_id="tenant-a",
        pipeline_run_id="run-9",
        session_id="sess-3",
    )

    assert len(spans) == 1
    attrs = spans[0]["attributes"]
    assert spans[0]["name"] == "digitrace.completion"
    assert attrs["openinference.span.kind"] == "LLM"
    assert attrs["gen_ai.operation.name"] == "chat"
    assert attrs["gen_ai.request.model"] == "openai/gpt-4o"
    assert attrs["llm.model_name"] == "openai/gpt-4o"
    assert attrs["gen_ai.system"] == "openai"
    assert attrs["gen_ai.provider.name"] == "openai"
    assert attrs["llm.provider"] == "openai"
    assert attrs["gen_ai.usage.input_tokens"] == 11
    assert attrs["gen_ai.usage.output_tokens"] == 7
    assert attrs["gen_ai.usage.total_tokens"] == 18
    assert attrs["llm.token_count.prompt"] == 11
    assert attrs["llm.token_count.completion"] == 7
    assert attrs["llm.token_count.total"] == 18
    assert attrs["tenant.id"] == "tenant-a"
    assert attrs["pipeline.run_id"] == "run-9"
    assert attrs["session.id"] == "sess-3"
    # Every emitted key is on the allowlist.
    assert set(attrs) <= trace_mod.SPAN_ATTRIBUTE_ALLOWLIST


@pytest.mark.unit
def test_otel_leg_sends_hash_and_length_not_prompt_text(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    spans = _enable_otel(monkeypatch)
    prompt = "email jane@example.com or call +1-415-555-0199 key sk-abcdefghij1234567"
    completion = "reply to jane@example.com please"

    @trace_mod.traceable("completion")
    def fn(model: str, messages: list[dict[str, str]]) -> str:
        return completion

    fn("openai/gpt-4o", [{"role": "user", "content": prompt}])

    attrs = spans[0]["attributes"]
    rendered = " ".join(str(value) for value in attrs.values())
    for secret in ("jane@example.com", "+1-415-555-0199", "sk-abcdefghij1234567", "reply to"):
        assert secret not in rendered
    assert _SHA256_RE.fullmatch(attrs["digi.input.sha256"])
    assert _SHA256_RE.fullmatch(attrs["digi.output.sha256"])
    assert attrs["digi.input.length"] > 0
    assert attrs["digi.output.length"] > 0
    # The preview is off by default.
    assert "digi.input.preview" not in attrs
    assert "digi.output.preview" not in attrs


@pytest.mark.unit
def test_otel_leg_preview_is_opt_in_and_redacted(monkeypatch: pytest.MonkeyPatch) -> None:
    spans = _enable_otel(monkeypatch)
    monkeypatch.setenv("DIGI_TRACE_CONTENT_PREVIEW", "1")
    monkeypatch.setenv("DIGI_TRACE_PREVIEW_CHARS", "80")

    @trace_mod.traceable("completion")
    def fn(model: str, messages: list[dict[str, str]]) -> str:
        return "ok"

    fn("openai/gpt-4o", [{"role": "user", "content": "write to jane@example.com"}])

    attrs = spans[0]["attributes"]
    assert "digi.input.preview" in attrs
    preview = attrs["digi.input.preview"]
    assert "[REDACTED_EMAIL]" in preview
    assert "jane@example.com" not in preview
    assert len(preview) <= 81  # 80 chars plus the ellipsis


@pytest.mark.unit
def test_otel_leg_error_has_no_message_or_stacktrace(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    spans = _enable_otel(monkeypatch)

    @trace_mod.traceable("boom")
    def fn() -> None:
        raise ValueError("secret jane@example.com")

    with pytest.raises(ValueError, match="secret"):
        fn()

    attrs = spans[0]["attributes"]
    assert spans[0]["status"] == "ERROR"
    assert attrs["error.type"] == "ValueError"
    rendered = " ".join(str(value) for value in attrs.values())
    assert "secret" not in rendered
    assert "jane@example.com" not in rendered
    assert "Traceback" not in rendered


@pytest.mark.unit
def test_otel_leg_ignores_arbitrary_kwargs(monkeypatch: pytest.MonkeyPatch) -> None:
    spans = _enable_otel(monkeypatch)

    @trace_mod.traceable("completion")
    def fn(
        model: str,
        messages: list[dict[str, str]],
        *,
        prompt: str = "",
        api_key: str = "",
    ) -> str:
        return "done"

    fn(
        "openai/gpt-4o",
        [],
        prompt="private prompt text",
        api_key="sk-abcdefghij1234567",
    )

    attrs = spans[0]["attributes"]
    assert "prompt" not in attrs
    assert "api_key" not in attrs
    rendered = " ".join(str(value) for value in attrs.values())
    assert "private prompt text" not in rendered
    assert "sk-abcdefghij1234567" not in rendered


@pytest.mark.unit
def test_span_kind_override_and_validation(monkeypatch: pytest.MonkeyPatch) -> None:
    spans = _enable_otel(monkeypatch)

    @trace_mod.traceable("lookup", span_kind="RETRIEVER")
    def fn(query: str) -> str:
        return "hit"

    fn("docs")

    assert spans[0]["attributes"]["openinference.span.kind"] == "RETRIEVER"
    with pytest.raises(ValueError, match="unknown span kind"):
        trace_mod.traceable("x", span_kind="NOT_A_KIND")
