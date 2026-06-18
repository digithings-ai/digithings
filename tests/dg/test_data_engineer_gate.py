"""REM-049: data_engineer_agent registration gate."""

from __future__ import annotations

import pytest

from digigraph.policy import code_execution_allowed


@pytest.mark.unit
def test_data_engineer_gated_off_by_default(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("DIGI_ALLOW_CODE_EXEC", raising=False)
    assert code_execution_allowed() is False


@pytest.mark.unit
def test_data_engineer_allowed_when_env_set(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("DIGI_ALLOW_CODE_EXEC", "1")
    assert code_execution_allowed() is True


@pytest.mark.unit
def test_sitaas_rag_tool_list_reflects_exec_flag(monkeypatch: pytest.MonkeyPatch) -> None:
    from digigraph.orchestration.builtin import _sitaas_rag_tool_names

    monkeypatch.delenv("DIGI_ALLOW_CODE_EXEC", raising=False)
    assert "data_engineer_agent" not in _sitaas_rag_tool_names()

    monkeypatch.setenv("DIGI_ALLOW_CODE_EXEC", "1")
    assert "data_engineer_agent" in _sitaas_rag_tool_names()
