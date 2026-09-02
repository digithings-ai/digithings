"""Durable provider-telemetry writer (#1979, Task 1.5).

Migration 067's own shape — privacy, grants, append-only triggers, absent payload columns — is
already covered by ``test_migration_067.py``. These tests cover *writer behaviour*: what is
submitted, what is held back, in what order, and what the run is told about the difference.

The recurring theme is that this ledger has no correction path. ``UPDATE``, ``DELETE`` and
``TRUNCATE`` all raise unconditionally, so every assertion about "not inserted" is an assertion
about a permanent outcome, not a retryable one.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from decimal import Decimal
from typing import Any  # score:allow untyped any — scored-lint: duck-typed fake Supabase client
from uuid import UUID, uuid4

import pytest
from digiquant.olympus.atlas import provider_telemetry as pt

from digillm import (
    ArtifactRef,
    CacheStatus,
    CallPurpose,
    NoArtifactReason,
    NodeRunOutcome,
    NodeRunRecord,
    ProviderAttemptOutcome,
    ProviderAttemptRecord,
    ProviderCallOutcome,
    ProviderCallRecord,
    RetryReason,
)

pytestmark = pytest.mark.unit

START = datetime(2026, 8, 7, 12, 0, tzinfo=timezone.utc)
END = START + timedelta(seconds=3)


# ─── a Supabase client that refuses every verb the ledger forbids ────────────


class _Table:
    def __init__(self, name: str, log: list[tuple[str, list[dict[str, Any]]]], failing: set[str]):
        self._name = name
        self._log = log
        self._failing = failing
        self._rows: list[dict[str, Any]] = []

    def insert(self, rows: list[dict[str, Any]]) -> _Table:
        self._rows = rows
        return self

    def execute(self) -> Any:
        if self._name in self._failing:
            raise RuntimeError(f"simulated {self._name} outage")
        self._log.append((self._name, self._rows))
        return object()

    # The ledger grants service_role SELECT and INSERT only, and rejects mutation by trigger for
    # every role. A writer that reached for any of these would not fail a test somewhere later —
    # it would raise in production against a table it cannot repair. Fail loudly, here.
    def _forbidden(self, verb: str) -> Any:
        raise AssertionError(f"{verb} is forbidden on the append-only ledger {self._name}")

    def upsert(self, *_a: Any, **_k: Any) -> Any:
        return self._forbidden("upsert")

    def update(self, *_a: Any, **_k: Any) -> Any:
        return self._forbidden("update")

    def delete(self, *_a: Any, **_k: Any) -> Any:
        return self._forbidden("delete")


class _Client:
    """Records every insert in call order so FK ordering is directly assertable."""

    def __init__(self, failing: set[str] | None = None):
        self.log: list[tuple[str, list[dict[str, Any]]]] = []
        self.failing = failing or set()

    def table(self, name: str) -> _Table:
        return _Table(name, self.log, self.failing)

    def rows(self, table: str) -> list[dict[str, Any]]:
        return [row for name, rows in self.log if name == table for row in rows]

    def tables_written(self) -> list[str]:
        return [name for name, _ in self.log]


@pytest.fixture(autouse=True)
def _clear_guard() -> Any:
    """The double-flush guard is process-global; a leak would silently skip a later test."""
    pt.reset_flush_guard()
    yield
    pt.reset_flush_guard()


# ─── record factories ────────────────────────────────────────────────────────


def _node(run_id: str = "gha-1", **over: Any) -> NodeRunRecord:
    return NodeRunRecord(
        **{
            "node_run_id": uuid4(),
            "run_id": run_id,
            "node_name": "hermes/analyst",
            "outcome": NodeRunOutcome.SUCCEEDED,
            "started_at": START,
            "finished_at": END,
            **over,
        }
    )


def _call(node_run_id: UUID, **over: Any) -> ProviderCallRecord:
    return ProviderCallRecord(
        **{
            "call_id": uuid4(),
            "node_run_id": node_run_id,
            "purpose": CallPurpose.CHAT_COMPLETION,
            "requested_model": "openai/gpt-5",
            "cache_status": CacheStatus.MISS,
            "outcome": ProviderCallOutcome.SUCCEEDED,
            "attempt_count": 1,
            "no_artifact_reason": NoArtifactReason.CONSUMED_INLINE,
            "started_at": START,
            "finished_at": END,
            **over,
        }
    )


def _attempt(call_id: UUID, number: int = 1, **over: Any) -> ProviderAttemptRecord:
    return ProviderAttemptRecord(
        **{
            "attempt_id": uuid4(),
            "call_id": call_id,
            "attempt_number": number,
            "provider": "openrouter",
            "requested_model": "openai/gpt-5",
            "served_model": "openai/gpt-5-2026-07",
            "outcome": ProviderAttemptOutcome.SUCCEEDED,
            "retry_reason": (RetryReason.NOT_APPLICABLE if number == 1 else RetryReason.RATE_LIMIT),
            "prompt_tokens": 100,
            "completion_tokens": 20,
            "cost_usd": Decimal("0.0125"),
            "started_at": START,
            "finished_at": END,
            **over,
        }
    )


def _flush(client: _Client, **over: Any) -> pt.FlushResult:
    return pt.flush_run_telemetry(client, **{"run_id": "gha-1", **over})


# ─── flush on the happy path ─────────────────────────────────────────────────


def test_a_normal_run_inserts_every_buffered_record_exactly_once() -> None:
    node = _node()
    call = _call(node.node_run_id)
    attempt = _attempt(call.call_id)
    client = _Client()

    result = _flush(client, node_runs=[node], provider_calls=[call], provider_attempts=[attempt])

    assert result.complete
    assert (result.node_runs.inserted, result.provider_calls.inserted) == (1, 1)
    assert result.provider_attempts.inserted == 1
    assert result.withheld_total == 0
    # "exactly once" is the load-bearing half — a duplicate cannot be deleted.
    assert len(client.rows(pt.NODE_RUNS_TABLE)) == 1
    assert len(client.rows(pt.PROVIDER_ATTEMPTS_TABLE)) == 1


def test_tiers_are_written_in_foreign_key_order() -> None:
    node = _node()
    call = _call(node.node_run_id)
    client = _Client()

    _flush(
        client, node_runs=[node], provider_calls=[call], provider_attempts=[_attempt(call.call_id)]
    )

    assert client.tables_written() == [
        pt.NODE_RUNS_TABLE,
        pt.PROVIDER_CALLS_TABLE,
        pt.PROVIDER_ATTEMPTS_TABLE,
    ]


def test_parent_calls_are_ordered_ahead_of_their_children() -> None:
    """fk_olympus_provider_calls_parent self-references, so order inside the batch matters."""
    node = _node()
    parent = _call(node.node_run_id, purpose=CallPurpose.TOOL_SELECTION)
    child = _call(node.node_run_id, parent_call_id=parent.call_id)
    grandchild = _call(node.node_run_id, parent_call_id=child.call_id)
    client = _Client()

    # Offered in reverse lineage order — the writer, not the caller, owns the ordering.
    result = _flush(client, node_runs=[node], provider_calls=[grandchild, child, parent])

    assert result.provider_calls.inserted == 3
    written = [row["call_id"] for row in client.rows(pt.PROVIDER_CALLS_TABLE)]
    assert written == [str(parent.call_id), str(child.call_id), str(grandchild.call_id)]


def test_a_cache_hit_call_persists_with_no_attempts() -> None:
    """067's chk_..._attempts allows attempt_count=0 only for a cache hit; the writer must not
    treat the missing attempt as a broken lineage."""
    node = _node()
    call = _call(
        node.node_run_id,
        cache_status=CacheStatus.HIT,
        attempt_count=0,
        artifacts=(ArtifactRef(artifact_type="brief", artifact_id="b1", version="1"),),
        no_artifact_reason=None,
    )
    client = _Client()

    result = _flush(client, node_runs=[node], provider_calls=[call])

    assert result.complete
    assert client.rows(pt.PROVIDER_CALLS_TABLE)[0]["attempt_count"] == 0


# ─── quarantine: the real production shape ───────────────────────────────────


def test_an_attempt_with_no_logical_call_is_quarantined_not_inserted() -> None:
    """Today's beliefs-distillation fold runs outside any graph node, so it emits exactly this."""
    client = _Client()

    result = _flush(client, provider_attempts=[_attempt(uuid4())])

    assert result.provider_attempts.quarantined == 1
    assert result.provider_attempts.inserted == 0
    assert client.rows(pt.PROVIDER_ATTEMPTS_TABLE) == []
    assert not result.complete, "quarantined coverage is incomplete, not success"


def test_attributed_and_orphaned_records_flush_together() -> None:
    """The post-#1982 steady state: graph nodes are attributed, the beliefs fold is not.

    A writer that decided quarantine per FLUSH rather than per RECORD would either drop the good
    rows or submit the orphan and take an FK error on the whole batch.
    """
    node = _node()
    call = _call(node.node_run_id)
    attributed = _attempt(call.call_id)
    orphan = _attempt(uuid4())
    client = _Client()

    result = _flush(
        client,
        node_runs=[node],
        provider_calls=[call],
        provider_attempts=[attributed, orphan],
    )

    assert result.provider_attempts.inserted == 1
    assert result.provider_attempts.quarantined == 1
    written = client.rows(pt.PROVIDER_ATTEMPTS_TABLE)
    assert [row["attempt_id"] for row in written] == [str(attributed.attempt_id)]


def test_a_call_whose_node_run_is_absent_is_quarantined_with_its_attempts() -> None:
    call = _call(uuid4())  # node run never buffered
    client = _Client()

    result = _flush(client, provider_calls=[call], provider_attempts=[_attempt(call.call_id)])

    assert result.provider_calls.quarantined == 1
    # The cascade matters: inserting the attempt would violate fk_..._attempts_call.
    assert result.provider_attempts.quarantined == 1
    assert client.log == []


def test_a_call_whose_parent_is_unresolvable_is_quarantined() -> None:
    node = _node()
    orphaned_child = _call(node.node_run_id, parent_call_id=uuid4())
    sibling = _call(node.node_run_id)
    client = _Client()

    result = _flush(client, node_runs=[node], provider_calls=[orphaned_child, sibling])

    assert result.provider_calls.inserted == 1
    assert result.provider_calls.quarantined == 1
    assert [r["call_id"] for r in client.rows(pt.PROVIDER_CALLS_TABLE)] == [str(sibling.call_id)]


def test_a_parent_cycle_terminates_as_quarantine() -> None:
    """Impossible from the current producer and permanent if it ever happened."""
    node = _node()
    left_id, right_id = uuid4(), uuid4()
    left = _call(node.node_run_id, call_id=left_id, parent_call_id=right_id)
    right = _call(node.node_run_id, call_id=right_id, parent_call_id=left_id)
    client = _Client()

    result = _flush(client, node_runs=[node], provider_calls=[left, right])

    assert result.provider_calls.quarantined == 2
    assert client.rows(pt.PROVIDER_CALLS_TABLE) == []


# ─── retries ─────────────────────────────────────────────────────────────────


def test_retries_insert_one_row_per_attempt_under_one_call() -> None:
    node = _node()
    call = _call(node.node_run_id, attempt_count=3)
    attempts = [_attempt(call.call_id, n) for n in (1, 2, 3)]
    client = _Client()

    result = _flush(client, node_runs=[node], provider_calls=[call], provider_attempts=attempts)

    assert result.provider_attempts.inserted == 3
    rows = client.rows(pt.PROVIDER_ATTEMPTS_TABLE)
    assert sorted(row["attempt_number"] for row in rows) == [1, 2, 3]
    # uq_olympus_provider_attempts_sequence is (call_id, attempt_number).
    assert {row["call_id"] for row in rows} == {str(call.call_id)}
    assert len({(r["call_id"], r["attempt_number"]) for r in rows}) == 3


def test_a_repeated_flush_of_one_run_writes_nothing_the_second_time() -> None:
    node = _node()
    call = _call(node.node_run_id)
    attempts = [_attempt(call.call_id, n) for n in (1, 2)]
    client = _Client()
    kwargs = {"node_runs": [node], "provider_calls": [call], "provider_attempts": attempts}

    first = _flush(client, **kwargs)
    second = _flush(client, **kwargs)

    assert first.inserted_total == 4
    assert second.skipped == "already_flushed"
    assert second.inserted_total == 0
    # Guarded in-process rather than left to the UNIQUE constraint: a constraint violation would
    # abort the batch and is indistinguishable from a real integrity failure in the logs.
    assert len(client.rows(pt.PROVIDER_ATTEMPTS_TABLE)) == 2


def test_the_flush_guard_is_keyed_by_attempt_not_run_id_alone() -> None:
    """pipeline-olympus.yml retries the chain up to three times inside ONE job, so run_id is
    identical across attempts — exactly why atlas_run_diagnostics keys on (run_id, attempt)."""
    node = _node()
    client = _Client()

    first = _flush(client, attempt=1, node_runs=[node])
    second = _flush(client, attempt=2, node_runs=[_node()])

    assert first.inserted_total == 1
    assert second.skipped is None
    assert second.inserted_total == 1


# ─── validation is the gate, because the ledger admits no repair ─────────────


def test_a_record_that_fails_revalidation_is_counted_and_never_submitted() -> None:
    node = _node()
    # model_construct bypasses every validator — the exact way a bad record reaches a writer.
    bogus = NodeRunRecord.model_construct(
        node_run_id=uuid4(),
        run_id="",  # violates both min_length=1 and CHECK (length(run_id) > 0)
        node_name="n",
        fanout_key=None,
        outcome=NodeRunOutcome.SUCCEEDED,
        artifacts=(),
        started_at=START,
        finished_at=END,
    )
    client = _Client()

    result = _flush(client, node_runs=[node, bogus])

    assert result.node_runs.rejected == 1
    assert result.node_runs.inserted == 1
    assert [row["run_id"] for row in client.rows(pt.NODE_RUNS_TABLE)] == ["gha-1"]


def test_a_record_whose_enum_field_holds_a_raw_string_still_serializes() -> None:
    """Serialize the REVALIDATED instance, not the one handed in.

    Found by review. `model_construct` can seat a plain `str` in a `StrEnum` field. That dumps to
    something `model_validate` accepts, so the record passes the gate — but the original object
    has no `.value` for the row builder to read, and the resulting `AttributeError` would abort
    the flush *after* an earlier tier had already landed, leaving a permanently partial batch in
    a ledger that admits no repair.
    """
    node = _node()
    sneaky = ProviderCallRecord.model_construct(
        call_id=uuid4(),
        node_run_id=node.node_run_id,
        parent_call_id=None,
        purpose="chat_completion",  # a str, not CallPurpose — no `.value`
        requested_model="openai/gpt-5",
        cache_status="miss",
        outcome="succeeded",
        attempt_count=1,
        artifacts=(),
        no_artifact_reason="consumed_inline",
        error_type=None,
        started_at=START,
        finished_at=END,
    )
    client = _Client()

    result = _flush(client, node_runs=[node], provider_calls=[sneaky])

    assert result.provider_calls.inserted == 1
    row = client.rows(pt.PROVIDER_CALLS_TABLE)[0]
    assert row["purpose"] == "chat_completion"
    assert row["cache_status"] == "miss"
    assert row["outcome"] == "succeeded"


def test_a_call_referencing_a_rejected_node_run_is_quarantined() -> None:
    """A dropped record is not a resolvable referent — eligibility follows what LANDED."""
    bogus_node = NodeRunRecord.model_construct(
        node_run_id=uuid4(),
        run_id="",
        node_name="n",
        fanout_key=None,
        outcome=NodeRunOutcome.SUCCEEDED,
        artifacts=(),
        started_at=START,
        finished_at=END,
    )
    call = _call(bogus_node.node_run_id)
    client = _Client()

    result = _flush(client, node_runs=[bogus_node], provider_calls=[call])

    assert result.node_runs.rejected == 1
    assert result.provider_calls.quarantined == 1
    assert client.rows(pt.PROVIDER_CALLS_TABLE) == []


def test_the_writer_never_reaches_for_a_mutating_verb() -> None:
    """_Table raises on upsert/update/delete; reaching one would fail this test, not production."""
    node = _node()
    call = _call(node.node_run_id)
    client = _Client()

    _flush(
        client, node_runs=[node], provider_calls=[call], provider_attempts=[_attempt(call.call_id)]
    )

    assert client.tables_written()  # something was written, so the assertion above is live


def test_no_payload_secret_or_raw_exception_column_is_ever_submitted() -> None:
    node = _node()
    call = _call(
        node.node_run_id,
        outcome=ProviderCallOutcome.FAILED,
        error_type="RateLimitError",
        no_artifact_reason=NoArtifactReason.CALL_FAILED,
    )
    client = _Client()

    _flush(client, node_runs=[node], provider_calls=[call])

    forbidden = {"prompt", "response", "messages", "content", "api_key", "search_text", "traceback"}
    for _table, rows in client.log:
        for row in rows:
            assert not (forbidden & set(row)), f"payload-bearing key in {sorted(row)}"
            assert len(str(row.get("error_type") or "")) <= 200


def test_a_failing_insert_is_sanitized_to_an_exception_type() -> None:
    """A driver message can carry a URL, a row payload, or a credential fragment."""
    client = _Client(failing={pt.NODE_RUNS_TABLE})

    result = _flush(client, node_runs=[_node()])

    assert result.node_runs.error_type == "RuntimeError"
    assert "simulated" not in str(result.node_runs.error_type)


# ─── failure is fail-soft, and partial writes are reported as permanent ──────


def test_a_failed_insert_never_raises_and_reports_the_shortfall() -> None:
    node = _node()
    call = _call(node.node_run_id)
    client = _Client(failing={pt.PROVIDER_CALLS_TABLE})

    result = _flush(
        client, node_runs=[node], provider_calls=[call], provider_attempts=[_attempt(call.call_id)]
    )

    assert result.node_runs.inserted == 1
    assert result.provider_calls.inserted == 0
    assert result.provider_calls.error_type == "RuntimeError"
    # The cascade is the point: submitting the attempt would violate fk_..._attempts_call.
    assert result.provider_attempts.quarantined == 1
    assert result.provider_attempts.inserted == 0
    assert not result.complete


def test_a_partially_landed_batch_is_flagged_as_permanently_inconsistent() -> None:
    """Tier 1 landed, tier 2 did not, and no UPDATE/DELETE/TRUNCATE can reconcile them."""
    node = _node()
    client = _Client(failing={pt.PROVIDER_CALLS_TABLE})

    result = _flush(client, node_runs=[node], provider_calls=[_call(node.node_run_id)])

    assert result.partially_written
    assert result.inserted_total == 1


def test_a_wholly_failed_flush_is_not_reported_as_partial() -> None:
    client = _Client(failing={pt.NODE_RUNS_TABLE})

    result = _flush(client, node_runs=[_node()])

    assert not result.complete
    assert not result.partially_written, "nothing landed, so nothing is inconsistent"


# ─── reconciliation ──────────────────────────────────────────────────────────


def test_full_provider_evidence_reconciles_on_the_five_shared_keys() -> None:
    detailed = {
        "llm_calls": 2,
        "prompt_tokens": 200,
        "completion_tokens": 40,
        "cost_usd": 0.025,
        "search_calls": 1,
    }
    result = _flush(
        _Client(), aggregate_snapshot=dict(detailed), detailed_projection=dict(detailed)
    )

    assert result.reconciliation.status == "reconciled"
    assert result.reconciliation.billing_exact
    assert result.reconciliation.unavailable_keys == ()


def test_missing_provider_cost_reports_unavailable_rather_than_zero() -> None:
    """_nullable_sum returns None when any contributor is None; that must not become 0."""
    detailed = {
        "llm_calls": 1,
        "prompt_tokens": 100,
        "completion_tokens": 20,
        "cost_usd": None,
        "search_calls": 0,
    }
    aggregate = {**detailed, "cost_usd": 0.0}
    attempts = [_attempt(uuid4(), cost_usd=None)]

    result = _flush(
        _Client(),
        provider_attempts=attempts,
        aggregate_snapshot=aggregate,
        detailed_projection=detailed,
    )

    assert result.reconciliation.status == "unavailable"
    assert result.reconciliation.unavailable_keys == ("cost_usd",)
    assert not result.reconciliation.billing_exact
    assert result.reconciliation.detailed["cost_usd"] is None, "never coerced to 0"
    # The shortfall is quantified, not merely flagged.
    assert result.reconciliation.attempts_missing_cost == 1


def test_missing_token_usage_is_quantified_too() -> None:
    attempts = [
        _attempt(uuid4(), prompt_tokens=None, completion_tokens=None),
        _attempt(uuid4()),
    ]
    result = _flush(
        _Client(),
        provider_attempts=attempts,
        aggregate_snapshot={"llm_calls": 2},
        detailed_projection={"llm_calls": 2, "prompt_tokens": None},
    )

    assert result.reconciliation.attempts_missing_usage == 1
    assert result.reconciliation.status == "unavailable"


def test_a_genuine_disagreement_is_mismatched_not_unavailable() -> None:
    """Unavailable means unknown. Mismatched means known and wrong. Collapsing them hides a bug."""
    detailed = {
        "llm_calls": 1,
        "prompt_tokens": 100,
        "completion_tokens": 20,
        "cost_usd": 0.01,
        "search_calls": 0,
    }
    aggregate = {**detailed, "llm_calls": 4}

    result = _flush(_Client(), aggregate_snapshot=aggregate, detailed_projection=detailed)

    assert result.reconciliation.status == "mismatched"
    assert result.reconciliation.mismatched_keys == ("llm_calls",)
    assert not result.reconciliation.billing_exact


def test_an_unknown_key_does_not_suppress_a_mismatch_on_a_different_key(
    caplog: pytest.LogCaptureFixture,
) -> None:
    """The two facts are orthogonal and must both be reported.

    Found by review: `_log_result` chained these as `if unavailable / elif mismatched`, and
    `cost_usd` is unknown whenever any contributing attempt omits cost — so on the common path a
    real disagreement was computed into `mismatched_keys` and then never logged anywhere. The
    suite exercised the two states only in isolation, which is exactly why it passed.
    """
    detailed = {
        "llm_calls": 2,
        "prompt_tokens": 100,
        "completion_tokens": 20,
        "cost_usd": None,  # a provider omitted cost — unknown
        "search_calls": 0,
    }
    aggregate = {**detailed, "llm_calls": 9, "cost_usd": 0.5}  # and the counts disagree

    with caplog.at_level("INFO", logger=pt.logger.name):
        result = _flush(_Client(), aggregate_snapshot=aggregate, detailed_projection=detailed)

    assert result.reconciliation.unavailable_keys == ("cost_usd",)
    assert result.reconciliation.mismatched_keys == ("llm_calls",)
    # `status` answers one question — may an exact-billing claim be made — and unknown wins it.
    assert result.reconciliation.status == "unavailable"
    assert not result.reconciliation.billing_exact
    messages = "\n".join(record.getMessage() for record in caplog.records)
    assert "unavailable for cost_usd" in messages
    assert "disagree with the aggregate on llm_calls" in messages, (
        "a detected mismatch must never be computed and then silently dropped"
    )


def test_a_detail_shortfall_is_reported_as_explainable_but_an_excess_is_not(
    caplog: pytest.LogCaptureFixture,
) -> None:
    """`usage.record` gates only on capture being active; a `ProviderCallRecord` also needs an
    open node scope. So the aggregate legitimately counts calls the detail cannot see, and detail
    BELOW aggregate has a standing explanation. Detail ABOVE it has none — nothing can inflate the
    detailed side except double-counting, so that direction must read differently."""
    base = {"llm_calls": 5, "prompt_tokens": 10, "completion_tokens": 2, "cost_usd": 0.1}

    with caplog.at_level("INFO", logger=pt.logger.name):
        _flush(
            _Client(),
            aggregate_snapshot={**base, "search_calls": 0},
            detailed_projection={**base, "llm_calls": 2, "search_calls": 0},
        )
    assert "consistent with calls made outside a node scope" in caplog.text

    caplog.clear()
    pt.reset_flush_guard()
    with caplog.at_level("INFO", logger=pt.logger.name):
        _flush(
            _Client(),
            aggregate_snapshot={**base, "search_calls": 0},
            detailed_projection={**base, "llm_calls": 8, "search_calls": 0},
        )
    assert "un-scoped calls cannot explain" in caplog.text


def test_reconciliation_is_still_reported_when_the_flush_is_skipped() -> None:
    """A double flush writes nothing, but the run's coverage question still has an answer."""
    projection = {
        "llm_calls": 1,
        "prompt_tokens": 1,
        "completion_tokens": 1,
        "cost_usd": None,
        "search_calls": 0,
    }
    client = _Client()
    _flush(client, node_runs=[_node()])
    second = _flush(
        client, node_runs=[_node()], aggregate_snapshot=projection, detailed_projection=projection
    )

    assert second.skipped == "already_flushed"
    assert second.reconciliation.status == "unavailable"


# ─── serialization ───────────────────────────────────────────────────────────


def test_cost_is_serialized_as_a_string_to_preserve_numeric_precision() -> None:
    node = _node()
    call = _call(node.node_run_id)
    attempt = _attempt(call.call_id, cost_usd=Decimal("0.000001"))
    client = _Client()

    _flush(client, node_runs=[node], provider_calls=[call], provider_attempts=[attempt])

    cost = client.rows(pt.PROVIDER_ATTEMPTS_TABLE)[0]["cost_usd"]
    assert cost == "0.000001", "a float round-trip loses exactly the sub-cent values that matter"
    assert isinstance(cost, str)


def test_absent_usage_serializes_as_null_never_zero() -> None:
    node = _node()
    call = _call(node.node_run_id)
    attempt = _attempt(
        call.call_id, prompt_tokens=None, completion_tokens=None, cost_usd=None, served_model=None
    )
    client = _Client()

    _flush(client, node_runs=[node], provider_calls=[call], provider_attempts=[attempt])

    row = client.rows(pt.PROVIDER_ATTEMPTS_TABLE)[0]
    assert row["prompt_tokens"] is None
    assert row["completion_tokens"] is None
    assert row["cost_usd"] is None
    assert row["served_model"] is None


def test_recorded_at_is_left_to_the_database_write_clock() -> None:
    client = _Client()
    _flush(client, node_runs=[_node()])
    assert "recorded_at" not in client.rows(pt.NODE_RUNS_TABLE)[0]


def test_artifacts_serialize_as_a_jsonb_array_of_references() -> None:
    node = _node()
    call = _call(
        node.node_run_id,
        artifacts=(ArtifactRef(artifact_type="thesis", artifact_id="AAPL", version="3"),),
        no_artifact_reason=None,
    )
    client = _Client()

    _flush(client, node_runs=[node], provider_calls=[call])

    assert client.rows(pt.PROVIDER_CALLS_TABLE)[0]["artifacts"] == [
        {"artifact_type": "thesis", "artifact_id": "AAPL", "version": "3"}
    ]


def test_the_fanout_key_survives_to_the_row() -> None:
    """Task 1.4's per-ticker discriminator is the join Olympus reads cost-by-name from."""
    client = _Client()
    _flush(client, node_runs=[_node(fanout_key="NVDA")])
    assert client.rows(pt.NODE_RUNS_TABLE)[0]["fanout_key"] == "NVDA"
