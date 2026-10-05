"""Egress records: one reconstructable record per outbound call that leaves digillm.

The point of this file is that the audit trail has to exist without anyone
registering anything, has to say *where* the call went, and has to be able to
prove *what* went without ever making the value recoverable. A record that
cannot be read is not evidence, and a record that leaks is a liability.
"""

from __future__ import annotations

import datetime as dt
import hashlib
import hmac
import json
import re
import uuid
from pathlib import Path
from typing import Any
from unittest.mock import MagicMock, patch

import pytest
from openai import APITimeoutError
from openai.types.chat import ChatCompletion, ChatCompletionMessage
from openai.types.chat.chat_completion import Choice
from pydantic import ValidationError

import digillm
from digillm import client as client_mod
from digillm import egress_record as egress_mod
from digillm.egress_record import (
    DIGEST_KEY_ENV,
    EGRESS_LOG_PATH_ENV,
    EgressDecision,
    EgressRecord,
    compute_payload_digest,
    set_egress_observer,
)

pytestmark = pytest.mark.unit

# Any 64-hex run is the signature of a sha256 (keyed or not). Absence of one is
# therefore a meaningful assertion, not a cosmetic one.
_HEX64 = re.compile(r"[0-9a-f]{64}")

_PEPPER = "pepper-" + "0123456789abcdef0123456789abcdef"
_OTHER_PEPPER = "other-" + "fedcba9876543210fedcba9876543210"
_CANARY = "canary-e4f1b0c7-2a55-4d3e-9b6a-DO-NOT-LOG"


def _canonical(payload: Any) -> bytes:
    return json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode("utf-8")


def _digest_of(payload: Any, pepper: str) -> str:
    return hmac.new(pepper.encode("utf-8"), _canonical(payload), hashlib.sha256).hexdigest()


def _serialised(record: EgressRecord) -> str:
    return record.model_dump_json()


def _real_completion(content: str) -> ChatCompletion:
    return ChatCompletion(
        id="cmpl-egress",
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
    client.base_url = "https://llm.internal.example/v1"
    client.api_key = "sk-egress-must-never-appear"
    return client


class _Collector:
    def __init__(self) -> None:
        self.records: list[EgressRecord] = []

    def __call__(self, record: EgressRecord) -> None:
        self.records.append(record)

    @property
    def last(self) -> EgressRecord:
        assert self.records, "no egress record was emitted"
        return self.records[-1]

    def lines(self) -> list[str]:
        return [_serialised(record) for record in self.records]


@pytest.fixture(autouse=True)
def _clean_state(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> Any:
    """Isolate the observer, the digest key and the sink path per test."""
    monkeypatch.delenv(DIGEST_KEY_ENV, raising=False)
    monkeypatch.delenv(EGRESS_LOG_PATH_ENV, raising=False)
    monkeypatch.setenv(EGRESS_LOG_PATH_ENV, str(tmp_path / "egress" / "records.jsonl"))
    monkeypatch.delenv("DIGI_TOOL_MESSAGE_MAX_CHARS", raising=False)
    digillm.clear_caches()
    digillm.set_usage_observer(None)
    set_egress_observer(None)
    yield
    set_egress_observer(None)
    digillm.clear_caches()


def _sink_lines(path: Path) -> list[str]:
    if not path.exists():
        return []
    return [line for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


# --- 1. exactly one record per physical attempt that reached the wire ---------


def test_every_provider_call_emits_exactly_one_record() -> None:
    collector = _Collector()
    set_egress_observer(collector)

    fake_client = _fake_client()
    fake_client.chat.completions.create.side_effect = [_real_completion("first")]
    with patch.object(client_mod, "get_client_for_model", return_value=fake_client):
        digillm.completion("gpt-4o-mini", [{"role": "user", "content": "one"}])
    assert len(collector.records) == 1, "a completions call emitted other than one record"

    collector.records.clear()
    digillm.clear_caches()
    fake_client.chat.completions.create.side_effect = [_real_completion("streamed")]
    with patch.object(client_mod, "get_client_for_model", return_value=fake_client):
        digillm.run_tools(
            "gpt-4o-mini",
            [{"role": "user", "content": "two"}],
            [],
            execute_tool=lambda *_: "",
            stream_deltas=True,
        )
    assert len(collector.records) == 1, "a streaming call emitted other than one record"

    collector.records.clear()
    digillm.clear_caches()
    fake_client.chat.completions.create.side_effect = [
        APITimeoutError(request=MagicMock()),
        _real_completion("recovered"),
    ]
    with (
        patch.object(client_mod, "get_client_for_model", return_value=fake_client),
        patch.object(client_mod, "_sleep_transient_retry", return_value=0.0),
    ):
        digillm.completion("gpt-4o-mini", [{"role": "user", "content": "three"}])
    assert len(collector.records) == 2, "one record per physical attempt on the wire is required"
    attempts = [record.attempt_id for record in collector.records]
    assert len(set(attempts)) == 2, "retried attempts must be distinguishable by attempt_id"
    assert len({record.call_id for record in collector.records}) == 1, "attempts share one call_id"


# --- 2. the no-egress path is still a record ---------------------------------


def test_cache_hit_is_recorded_as_a_distinct_decision() -> None:
    collector = _Collector()
    set_egress_observer(collector)

    fake_client = _fake_client()
    fake_client.chat.completions.create.side_effect = [
        _real_completion("warm the cache"),
        _real_completion("warm the cache"),
    ]
    messages = [{"role": "user", "content": "cache me"}]
    with patch.object(client_mod, "get_client_for_model", return_value=fake_client):
        digillm.completion("gpt-4o-mini", messages)
        digillm.completion("gpt-4o-mini", messages)

    assert fake_client.chat.completions.create.call_count == 1, "the second call must hit the cache"
    assert len(collector.records) == 2, "a cache hit leaves the log spotty if it emits nothing"
    hit = collector.last
    assert hit.decision == EgressDecision.CACHE_HIT == "cache_hit"
    assert hit.destination == "none", "nothing left the process, so the destination must say so"


# --- 3. the digest is keyed --------------------------------------------------


def test_digest_is_keyed_not_a_plain_hash(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv(DIGEST_KEY_ENV, _PEPPER)
    collector = _Collector()
    set_egress_observer(collector)

    fake_client = _fake_client()
    fake_client.chat.completions.create.side_effect = [_real_completion("ok")]
    with patch.object(client_mod, "get_client_for_model", return_value=fake_client):
        digillm.completion("gpt-4o-mini", [{"role": "user", "content": "digest me"}])

    outbound = fake_client.chat.completions.create.call_args.kwargs["messages"]
    record = collector.last
    assert record.digest_algorithm == "hmac-sha256"
    assert record.payload_digest == _digest_of(outbound, _PEPPER)

    unkeyed = hashlib.sha256(_canonical(outbound)).hexdigest()
    assert unkeyed not in _serialised(record), "an unkeyed hash of the payload is a lookup table"
    assert unkeyed not in "\n".join(collector.lines())


# --- 4. low-entropy payloads stay unrecoverable ------------------------------


def test_digest_is_not_reversible_for_low_entropy_values() -> None:
    male = {"content": "male"}
    female = {"content": "female"}

    digest_a, algorithm_a = compute_payload_digest(male, key=_PEPPER)
    digest_b, algorithm_b = compute_payload_digest(female, key=_PEPPER)
    other_a, _ = compute_payload_digest(male, key=_OTHER_PEPPER)
    other_b, _ = compute_payload_digest(female, key=_OTHER_PEPPER)

    assert algorithm_a == algorithm_b == "hmac-sha256"
    assert digest_a and digest_b and other_a and other_b
    assert digest_a != digest_b
    assert other_a != other_b
    # A reader holding one digest and a short candidate list cannot rank
    # candidates, because the pepper is not in their hands.
    assert len({digest_a, digest_b, other_a, other_b}) == 4

    # "A truncated or structured digest of a short value is the value."
    assert digest_a is not None and len(digest_a) == 64
    unkeyed_male = hashlib.sha256(_canonical(male)).hexdigest()
    unkeyed_female = hashlib.sha256(_canonical(female)).hexdigest()
    assert digest_a not in (unkeyed_male, unkeyed_female)
    assert digest_b not in (unkeyed_male, unkeyed_female)

    def _record_for(digest: str, algorithm: str) -> EgressRecord:
        return EgressRecord(
            ts=dt.datetime(2026, 10, 5, 12, 0, tzinfo=dt.UTC),
            call_id=uuid.UUID(int=1),
            attempt_id=uuid.UUID(int=2),
            destination="https://llm.internal.example/v1",
            provider="openai",
            model="gpt-4o-mini",
            purpose="chat_completion",
            decision=EgressDecision.UNSCREENED,
            payload_digest=digest,
            digest_algorithm=algorithm,
            cache_status="miss",
            outcome="succeeded",
        )

    short = _record_for(digest_a, algorithm_a)
    long_payload = "male" + "x" * 4000
    long_digest, long_algorithm = compute_payload_digest({"content": long_payload}, key=_PEPPER)
    long_record = _record_for(long_digest, long_algorithm)

    assert "male" not in _serialised(short).lower()
    # No field but the digest may move when the input length changes, so
    # nothing leaks how long the payload was.
    short_fields = short.model_dump()
    long_fields = long_record.model_dump()
    differing = {key for key in short_fields if short_fields[key] != long_fields[key]}
    assert differing == {"payload_digest"}


# --- 5. no pepper means no digest, and the record says so --------------------


@pytest.mark.parametrize("bad_key", [None, "", "short-pepper", "x" * 31])
def test_missing_pepper_emits_no_digest_and_says_so(
    monkeypatch: pytest.MonkeyPatch, bad_key: str | None
) -> None:
    if bad_key is None:
        monkeypatch.delenv(DIGEST_KEY_ENV, raising=False)
    else:
        monkeypatch.setenv(DIGEST_KEY_ENV, bad_key)

    collector = _Collector()
    set_egress_observer(collector)
    fake_client = _fake_client()
    fake_client.chat.completions.create.side_effect = [_real_completion("ok")]
    with patch.object(client_mod, "get_client_for_model", return_value=fake_client):
        digillm.completion("gpt-4o-mini", [{"role": "user", "content": "no pepper"}])

    record = collector.last
    assert record.digest_algorithm == "absent"
    assert record.payload_digest is None
    line = _serialised(record)
    assert not _HEX64.search(line), "a missing pepper must not fall back to an unkeyed hash"


# --- 6. the payload is never in the record -----------------------------------


def test_record_never_carries_the_payload(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv(DIGEST_KEY_ENV, _PEPPER)
    collector = _Collector()
    set_egress_observer(collector)

    fake_client = _fake_client()
    fake_client.chat.completions.create.side_effect = [_real_completion("ok")]
    with patch.object(client_mod, "get_client_for_model", return_value=fake_client):
        digillm.completion("gpt-4o-mini", [{"role": "user", "content": _CANARY}])

    line = _serialised(collector.last)
    assert _CANARY not in line
    assert "canary" not in line.lower()
    allowed = {category.value for category in egress_mod.ART9_CATEGORY_IDS}
    assert set(collector.last.category_ids) <= allowed
    # The eight closed ids are the whole vocabulary: no free-text slot that a
    # matched value could hide in.
    assert allowed == {
        "health",
        "genetic",
        "biometric",
        "racial_or_ethnic_origin",
        "political_opinions",
        "religious_or_philosophical_beliefs",
        "trade_union_membership",
        "sex_life_or_sexual_orientation",
    }


# --- 7. destination is recorded, credentials never are -----------------------


def test_destination_is_recorded_and_never_the_api_key() -> None:
    collector = _Collector()
    set_egress_observer(collector)

    fake_client = _fake_client()
    fake_client.chat.completions.create.side_effect = [_real_completion("ok")]
    with patch.object(client_mod, "get_client_for_model", return_value=fake_client):
        digillm.completion("gpt-4o-mini", [{"role": "user", "content": "where did this go"}])

    record = collector.last
    assert record.destination == "https://llm.internal.example/v1"
    assert record.model
    assert record.provider
    line = _serialised(record)
    assert "sk-egress-must-never-appear" not in line
    assert "sk-" not in line
    assert "api_key" not in line


# --- 8. the digest covers what actually went on the wire ---------------------


def test_digest_covers_the_truncated_outbound_payload(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv(DIGEST_KEY_ENV, _PEPPER)
    monkeypatch.setattr(client_mod, "_MAX_TOOL_MESSAGE_CHARS", 200)
    collector = _Collector()
    set_egress_observer(collector)

    full_payload = "S" * 5000
    compacted = client_mod._compact_tool_message_content(full_payload)
    outbound_messages = [{"role": "tool", "content": compacted}]

    fake_client = _fake_client()
    fake_client.chat.completions.create.side_effect = [_real_completion("ok")]
    with patch.object(client_mod, "get_client_for_model", return_value=fake_client):
        digillm.completion("gpt-4o-mini", outbound_messages)

    sent = fake_client.chat.completions.create.call_args.kwargs["messages"]
    assert sent == outbound_messages
    assert len(sent[0]["content"]) < len(full_payload), "the test must actually exercise compaction"

    record = collector.last
    assert record.payload_digest == _digest_of(sent, _PEPPER)
    # Digesting the pre-truncation input would describe something that did not
    # leave, and comparing the two digests reconstructs the omitted tail.
    assert record.payload_digest != _digest_of([{"role": "tool", "content": full_payload}], _PEPPER)


# --- 9. observers are fail-soft ----------------------------------------------


def test_observer_failure_never_breaks_the_llm_call() -> None:
    def exploding_observer(record: EgressRecord) -> None:
        raise RuntimeError("observer is broken")

    set_egress_observer(exploding_observer)
    fake_client = _fake_client()
    fake_client.chat.completions.create.side_effect = [_real_completion("still fine")]
    with patch.object(client_mod, "get_client_for_model", return_value=fake_client):
        completion = digillm.completion("gpt-4o-mini", [{"role": "user", "content": "boom"}])

    assert completion.choices[0].message.content == "still fine"


# --- 10. the default sink writes, it does not no-op ---------------------------


def test_unregistered_default_is_a_local_sink_not_a_no_op(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.setenv(EGRESS_LOG_PATH_ENV, str(tmp_path / "nested" / "egress.jsonl"))
    set_egress_observer(None)

    fake_client = _fake_client()
    fake_client.chat.completions.create.side_effect = [_real_completion("ok")]
    with patch.object(client_mod, "get_client_for_model", return_value=fake_client):
        digillm.completion("gpt-4o-mini", [{"role": "user", "content": "write it down"}])

    path = tmp_path / "nested" / "egress.jsonl"
    lines = _sink_lines(path)
    assert lines, "with no observer registered the record still has to land on disk"
    payload = json.loads(lines[-1])
    assert payload["decision"] == "unscreened"
    assert payload["destination"] == "https://llm.internal.example/v1"
    assert EgressRecord.model_validate(payload) is not None


# --- contract of the record itself -------------------------------------------


def test_decision_enum_is_closed_and_only_honest_values_are_reachable() -> None:
    assert {decision.value for decision in EgressDecision} == {
        "unscreened",
        "pass",
        "masked",
        "refused",
        "cache_hit",
    }


def test_record_is_frozen_and_forbids_payload_shaped_fields() -> None:
    fields = set(EgressRecord.model_fields)
    for banned in ("prompt", "messages", "response", "content", "api_key", "raw_exception", "text"):
        assert banned not in fields, f"{banned} must not be a record field"

    with pytest.raises(ValidationError):
        EgressRecord(
            ts="2026-10-05T12:00:00Z",
            call_id="00000000-0000-0000-0000-000000000001",
            attempt_id="00000000-0000-0000-0000-000000000002",
            destination="https://llm.internal.example/v1",
            provider="openai",
            model="gpt-4o-mini",
            purpose="chat_completion",
            decision="unscreened",
            payload_digest=None,
            digest_algorithm="absent",
            cache_status="miss",
            outcome="succeeded",
            prompt="leak",
        )

    with pytest.raises(ValidationError):
        EgressRecord(
            ts="2026-10-05T12:00:00Z",
            call_id="00000000-0000-0000-0000-000000000001",
            attempt_id="00000000-0000-0000-0000-000000000002",
            destination="https://llm.internal.example/v1",
            provider="openai",
            model="gpt-4o-mini",
            purpose="chat_completion",
            decision="screen_it_later_maybe",
            payload_digest=None,
            digest_algorithm="absent",
            cache_status="miss",
            outcome="succeeded",
        )


def test_observer_is_exported_and_never_breaks_the_call() -> None:
    assert digillm.set_egress_observer is egress_mod.set_egress_observer