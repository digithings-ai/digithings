from __future__ import annotations

from digisearch.demos.audit_rag_demo import (
    _assertions,
    _render_summary,
    _seed_stub_if_enabled,
    evaluate_assertion,
)


def test_audit_demo_stub_covers_all_verdicts(monkeypatch) -> None:
    monkeypatch.setenv("DIGISEARCH_ALLOW_STUB", "1")
    index_name = "audit-rag-demo-test"
    _seed_stub_if_enabled(index_name)

    findings = [evaluate_assertion(assertion, index_name=index_name) for assertion in _assertions()]

    verdicts = {finding.verdict.value for finding in findings}
    assert verdicts == {"CONFIRMED", "INCONCLUSIVE", "UNCONFIRMED"}


def test_summary_only_lists_action_required_rows(monkeypatch, capsys) -> None:
    monkeypatch.setenv("DIGISEARCH_ALLOW_STUB", "1")
    index_name = "audit-rag-demo-test-summary"
    _seed_stub_if_enabled(index_name)

    findings = [evaluate_assertion(assertion, index_name=index_name) for assertion in _assertions()]
    _render_summary(findings)

    out = capsys.readouterr().out
    assert "A-01" not in out
    assert "A-02" in out
    assert "A-03" in out
