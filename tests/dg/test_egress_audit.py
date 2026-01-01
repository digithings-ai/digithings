"""Leaf B: a real digigraph outbound call reaches the fleet audit stream (DIG-1140).

Leaf A (DIG-1089) gives digillm an :class:`~digillm.egress_record.EgressRecord` for every
outbound attempt, but persists it only to its own process-local JSONL file, which no
fleet-wide reader consumes. These tests pin the bridge from that record into
``digibase.audit.emit_event`` -- the fleet's documented sole emitter -- and prove the
record is *evidence*: reconstructable after the fact, stable across identical calls,
discriminating between calls that differ, and free of any Art. 9 value.

The reconstruction tests drive the real digigraph ``completion`` wrapper against a stubbed
provider instead of mocking digillm's entry points, because the claim under test is that a
real outbound call lands in the audit stream; a mocked ``_digillm_completion`` would prove
only that our own glue calls our own glue.
"""

from __future__ import annotations

import importlib
import json
import re
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import MagicMock, patch
from uuid import uuid4

import pytest
from digibase.audit import redact_mapping
from digigraph.llm_client import _EGRESS_AUDIT_EVENT_TYPE, _record_egress_to_audit_stream
from digillm.egress_record import (
    DIGEST_KEY_ENV,
    EGRESS_LOG_PATH_ENV,
    EgressDecision,
    EgressRecord,
    record_egress,
    set_egress_observer,
)
from openai.types.chat import ChatCompletion, ChatCompletionMessage
from openai.types.chat.chat_completion import Choice

from digigraph import llm_client
from digillm import clear_caches

pytestmark = pytest.mark.unit

# Any 64-hex run is an HMAC-SHA256 signature, so its presence or absence is meaningful.
_HEX64 = re.compile(r"[0-9a-f]{64}")

# A distinctive Art. 9 value. It must never appear anywhere in the audit stream.
_CANARY = "canary-e4f1b0c7-2a55-4d3e-9b6a-DO-NOT-LOG"

_PEPPER = "pepper-" + "0123456789abcdef0123456789abcdef"

_DIGILLM_CLIENT = "digillm.client"

_FAKE_BASE_URL = "https://llm.internal.example/v1"


@pytest.fixture(autouse=True)
def _isolate_sinks(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Point both sinks at ``tmp_path`` and reset the one thing these tests mutate.

    The digillm client cache is cleared on the way in and out. That is all this fixture is
    allowed to do.

    It deliberately does NOT install the egress observer, even though it owns that global.
    An earlier version re-installed ``llm_client._record_egress_to_audit_stream`` on the way
    in, which quietly made the module-level registration unobservable: every test in this
    file then exercised the raw bridge whether or not importing ``llm_client`` had actually
    registered it. A mutant that kept the first record and discarded every later one
    (per-process dedup) passed the whole file, because the fixture handed it a working
    observer. Restoring state is not the same as forcing it -- this fixture restores
    nothing here, so ``llm_client``'s own import-time registration stays load-bearing. The
    one test that does move the global
    (``test_importing_llm_client_installs_the_bridge``) restores it by reloading the module,
    which re-runs the registration.

    The usage and telemetry observers are also deliberately untouched. They are registered
    by the same module-level block, and ``test_llm_client.py`` asserts on those globals
    directly -- clearing them here made this file fail two unrelated tests purely by running
    first (verified: ``test_llm_client.py`` passes alone, and fails when this file precedes
    it).
    """
    monkeypatch.delenv(DIGEST_KEY_ENV, raising=False)
    monkeypatch.delenv("AUDIT_SINK_URL", raising=False)
    monkeypatch.setenv(EGRESS_LOG_PATH_ENV, str(tmp_path / "egress" / "records.jsonl"))
    monkeypatch.setenv("AUDIT_LOG_PATH", str(tmp_path / "audit" / "events.jsonl"))

    yield
    clear_caches()


@pytest.fixture
def audit_path(tmp_path: Path) -> Path:
    """The fleet audit stream for this test."""
    return tmp_path / "audit" / "events.jsonl"


def _egress_events(audit_path: Path) -> list[dict]:
    """Egress events only, payload lifted to the top level for assertions."""
    if not audit_path.exists():
        return []
    rows = (
        json.loads(raw)
        for raw in audit_path.read_text(encoding="utf-8").splitlines()
        if raw.strip()
    )
    return [r["payload"] for r in rows if r.get("event_type") == _EGRESS_AUDIT_EVENT_TYPE]


def _real_completion(content: str) -> ChatCompletion:
    return ChatCompletion(
        id="cmpl-egress-audit",
        created=0,
        model="test-model",
        object="chat.completion",
        choices=[
            Choice(
                index=0,
                finish_reason="stop",
                message=ChatCompletionMessage(role="assistant", content=content),
            )
        ],
    )


def _fake_client() -> MagicMock:
    client = MagicMock()
    client.base_url = _FAKE_BASE_URL
    client.api_key = "sk-egress-must-never-appear"
    return client


def _outbound_call(messages: list[dict], *, answer: str = "ok") -> ChatCompletion:
    """Drive one real digigraph ``completion`` call against a stubbed provider.

    Only model *resolution* is mocked -- it is env/YAML substitution with no bearing on the
    egress path. Everything from ``get_client_for_model`` downwards, including record
    construction and emission, is digillm's real code.
    """
    fake = _fake_client()
    fake.chat.completions.create.return_value = _real_completion(answer)
    with (
        patch(f"{_DIGILLM_CLIENT}.get_client_for_model", return_value=fake),
        patch.object(llm_client, "resolve_request_model", return_value="gpt-4o-mini"),
    ):
        result = llm_client.completion("gpt-4o-mini", messages)
    clear_caches()
    return result


def _a_record(**overrides) -> EgressRecord:
    """Build one record directly. ``ts`` has no default, so it must be supplied here."""
    kwargs = {
        "ts": datetime.now(timezone.utc),
        "call_id": uuid4(),
        "attempt_id": uuid4(),
        "destination": _FAKE_BASE_URL,
        "provider": "openai",
        "model": "gpt-4o-mini",
        "purpose": "initial_generation",
        "cache_status": "miss",
        "outcome": "succeeded",
    }
    kwargs.update(overrides)
    return EgressRecord(**kwargs)


def _emit_directly(**overrides) -> None:
    """Emit one record through the real ``record_egress`` without a provider call."""
    kwargs = {
        "call_id": uuid4(),
        "attempt_id": uuid4(),
        "destination": _FAKE_BASE_URL,
        "provider": "openai",
        "model": "gpt-4o-mini",
        "purpose": "initial_generation",
        "cache_status": "miss",
        "outcome": "succeeded",
    }
    kwargs.update(overrides)
    record = record_egress(**kwargs)
    assert record is not None, "digillm failed to build a record; the rest of this test is void"


def test_a_real_outbound_call_is_reconstructable_from_the_audit_stream(
    monkeypatch: pytest.MonkeyPatch, audit_path: Path
) -> None:
    """One real call must answer which destination, which decision, and which categories."""
    monkeypatch.setenv(DIGEST_KEY_ENV, _PEPPER)

    result = _outbound_call([{"role": "user", "content": "one"}])
    assert result.choices[0].message.content == "ok"

    events = _egress_events(audit_path)
    assert len(events) == 1, (
        f"expected exactly one egress record in the audit stream, got {len(events)}: {events}"
    )
    record = events[0]

    # Reconstructable: every question a later auditor asks of the line is answered by it.
    assert record["destination"] == _FAKE_BASE_URL
    assert record["decision"] in tuple(EgressDecision)
    assert "category_ids" in record, "the audit line must carry category_ids even when empty"
    assert isinstance(record["category_ids"], list)
    assert record["outcome"] == "succeeded"

    # Stability: an identical call must give an identical digest, or the digest is noise.
    _outbound_call([{"role": "user", "content": "one"}])
    stable = _egress_events(audit_path)
    assert len(stable) == 2, f"expected a second egress record, got {len(stable)}"
    assert stable[1]["payload_digest"] == stable[0]["payload_digest"], (
        "two identical calls produced different payload_digests; the digest is not stable"
    )

    # Discrimination: one differing message must change it, or the digest proves nothing.
    _outbound_call([{"role": "user", "content": "two"}])
    differing = _egress_events(audit_path)
    assert len(differing) == 3, f"expected a third egress record, got {len(differing)}"
    assert differing[2]["payload_digest"] != differing[0]["payload_digest"], (
        "a one-word change produced the same payload_digest; the digest does not discriminate"
    )


def test_no_art9_value_reaches_the_audit_stream(
    monkeypatch: pytest.MonkeyPatch, audit_path: Path
) -> None:
    """A distinctive Art. 9 value is absent from the whole audit line, not merely redacted."""
    monkeypatch.setenv(DIGEST_KEY_ENV, _PEPPER)

    # Nested content, so redact_mapping's recursion over nested values is really exercised.
    _outbound_call(
        [
            {
                "role": "user",
                "content": [{"type": "text", "text": f"diagnose {_CANARY} for patient 42"}],
            }
        ]
    )

    raw = audit_path.read_text(encoding="utf-8")
    assert _CANARY not in raw, "an Art. 9 value reached the fleet audit stream"
    assert "patient 42" not in raw, "context surrounding the value leaked alongside it"

    events = _egress_events(audit_path)
    assert len(events) == 1
    # The field never carries the value at all; the keyed digest proves the payload was
    # seen without being recorded.
    assert _HEX64.search(events[0]["payload_digest"] or ""), (
        "expected a keyed payload_digest proving the payload was seen but not recorded"
    )


def test_absent_pepper_degrades_to_no_digest_not_no_record(audit_path: Path) -> None:
    """Losing the pepper must cost the digest, never the record itself."""
    _outbound_call([{"role": "user", "content": "one"}])

    events = _egress_events(audit_path)
    assert len(events) == 1, f"the record was lost when the pepper was absent: {events}"
    record = events[0]
    assert record["payload_digest"] is None, "a digest appeared with no pepper key configured"
    assert record["digest_algorithm"] == "absent"
    # Everything needed for reconstruction except the payload proof is still there.
    assert record["destination"] == _FAKE_BASE_URL
    assert record["outcome"] == "succeeded"
    assert record["call_id"]


def test_egress_observer_failure_does_not_break_the_llm_call(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, audit_path: Path
) -> None:
    """A raising observer is swallowed; the LLM call must still return its answer.

    Driven by a genuinely unwritable audit destination rather than a patched ``emit_event``,
    so the real failure path is exercised. Three controls keep each step from passing for the
    wrong reason: the same setup records when the sink works, the broken configuration is
    shown to raise before the LLM path is exercised, and digillm's own sink is shown to
    survive the failure.
    """
    # Control 1 -- with a writable sink the very same call records. Without this, the rest
    # of the test could pass simply because nothing was ever emitted.
    _outbound_call([{"role": "user", "content": "control"}])
    assert len(_egress_events(audit_path)) == 1, "control run did not record; test is void"

    # Make emit_event raise by pointing it at a path whose parent is a regular file.
    blocker = tmp_path / "blocker"
    blocker.write_text("not a directory", encoding="utf-8")
    monkeypatch.setenv("AUDIT_LOG_PATH", str(blocker / "nested" / "events.jsonl"))

    # Control 2 -- prove the configuration really breaks the emitter *through this bridge*,
    # rather than assuming it. A bridge that swallowed the error itself would still leave
    # the LLM call working below, so only asserting on emit_event directly would let such a
    # mutant survive while this test kept reporting a pass.
    with pytest.raises(OSError):
        _record_egress_to_audit_stream(_a_record())

    result = _outbound_call([{"role": "user", "content": "failing"}])
    assert result.choices[0].message.content == "ok", (
        "the LLM call failed because the audit stream could not be written"
    )

    # Control 3 -- digillm's own process-local sink is independent of the audit stream, so
    # the record still exists, just not where the fleet can read it.
    egress_sink = tmp_path / "egress" / "records.jsonl"
    assert egress_sink.exists(), "digillm's own sink should survive an audit-stream failure"


def test_the_bridge_calls_emit_event_and_invents_no_fields(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The audit payload is the record itself, so the line cannot drift from Leaf A's shape."""
    monkeypatch.setenv(DIGEST_KEY_ENV, _PEPPER)
    with patch.object(llm_client, "_emit_audit_event") as emit:
        record = record_egress(
            call_id=uuid4(),
            attempt_id=uuid4(),
            destination=_FAKE_BASE_URL,
            provider="openai",
            model="gpt-4o-mini",
            purpose="initial_generation",
            cache_status="miss",
            outcome="succeeded",
            payload=[{"role": "user", "content": "one"}],
        )
    assert record is not None, "digillm failed to build a record; this test is void"
    emit.assert_called_once()
    args, kwargs = emit.call_args
    assert args[0] == _EGRESS_AUDIT_EVENT_TYPE
    assert set(kwargs["payload"]) == set(EgressRecord.model_fields), (
        "the audit payload's keys differ from the record's fields: "
        f"{set(kwargs['payload']) ^ set(EgressRecord.model_fields)}"
    )
    assert kwargs["payload"] == record.model_dump(mode="json")


def test_category_ids_survive_the_bridge_and_discriminate(audit_path: Path) -> None:
    """Category ids land in the audit line and are discriminating between records.

    ``digillm.client._record_egress`` takes no ``category_ids`` argument, so every record
    from a real unscreened call carries ``()``. Proving the field *discriminates* therefore
    requires records that carry ids, driven through ``record_egress`` directly and labelled
    as such here rather than passed off as real outbound calls.
    """
    call_id = uuid4()
    _emit_directly(
        call_id=call_id,
        decision=EgressDecision.REFUSED,
        category_ids=("genetic", "health"),
    )
    first = _egress_events(audit_path)
    assert len(first) == 1, f"expected one egress record, got {len(first)}"
    assert sorted(first[0]["category_ids"]) == ["genetic", "health"]
    assert first[0]["decision"] == "refused"
    assert first[0]["call_id"] == str(call_id)

    # Same call id, one category fewer: the field must change, or a merged or truncated list
    # would leave an auditor unable to tell these two records apart.
    _emit_directly(call_id=call_id, decision=EgressDecision.REFUSED, category_ids=("genetic",))
    second = _egress_events(audit_path)
    assert len(second) == 2
    assert second[1]["category_ids"] == ["genetic"], (
        "category_ids does not discriminate between records differing only in that field"
    )


def test_redact_mapping_does_not_rewrite_the_egress_payload() -> None:
    """Pin the assumption test 2 rests on, using a differential and a firing control.

    If a future Leaf A field were named so ``redact_mapping``'s key-substring rule matched
    it, test 2 would still pass -- the value never reaches the payload either way -- but for
    the wrong reason. The control proves the redaction rule is live, so the no-op below is a
    measured fact and not a rule that has silently stopped matching.
    """
    payload = {
        "destination": _FAKE_BASE_URL,
        "api_key": "sk-must-be-redacted",
    }
    redacted = redact_mapping(payload)

    # Control: the rule fires on the one key it is meant to catch.
    assert redacted["api_key"] == "[REDACTED]", "the redaction control did not fire"

    # The egress fields themselves pass through untouched.
    record_payload = _a_record().model_dump(mode="json")
    assert redact_mapping(record_payload) == record_payload, (
        "redact_mapping altered the egress payload; test 2 would be proving redaction "
        "rather than absence"
    )


def test_importing_llm_client_installs_the_bridge(audit_path: Path) -> None:
    """The bridge must be installed by importing llm_client, not by a call site opting in."""
    set_egress_observer(None)
    assert _egress_events(audit_path) == []

    importlib.reload(llm_client)  # importing is what registers the observer
    _emit_directly()
    _emit_directly()

    events = _egress_events(audit_path)
    assert len(events) == 2, (
        "importing llm_client must install a bridge that records every egress record; got "
        f"{len(events)} line(s) for two records. A bridge that registers but records only "
        "the first record leaves the audit stream silently empty for the rest of the "
        "process lifetime."
    )
