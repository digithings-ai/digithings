# tests/provider_review/test_bootstrap.py
"""Unit tests for scripts/provider_review/bootstrap.py."""
from __future__ import annotations

from unittest.mock import patch

import pytest

from scripts.provider_review.bootstrap import extract_decision_comments, load_snapshots


@pytest.mark.unit
def test_extract_finds_tagged_entry(tmp_path):
    """Finds a # llm-decision: tag and captures tags, prose, and model."""
    cfg = tmp_path / "model_modes.yaml"
    cfg.write_text(
        "phase_models:\n"
        "  # llm-decision: reasoning free-preferred\n"
        "  # DeepSeek chosen for math benchmark strength on free tier\n"
        "  master-digest: \"ollama-cloud/deepseek-v3.1:671b\"\n"
    )
    decisions = extract_decision_comments([str(cfg)])
    assert len(decisions) == 1
    d = decisions[0]
    assert d["tags"] == ["reasoning", "free-preferred"]
    assert "DeepSeek" in d["prose"]
    assert d["model"] == "ollama-cloud/deepseek-v3.1:671b"
    assert d["line"] == 2


@pytest.mark.unit
def test_extract_empty_when_no_tags(tmp_path):
    """Returns empty list when no # llm-decision: tags are present."""
    cfg = tmp_path / "config.yaml"
    cfg.write_text("model: gemini/gemini-2.5-flash\n")
    assert extract_decision_comments([str(cfg)]) == []


@pytest.mark.unit
def test_extract_skips_missing_paths(tmp_path):
    """Silently skips paths that do not exist."""
    assert extract_decision_comments([str(tmp_path / "ghost.yaml")]) == []


@pytest.mark.unit
def test_extract_scans_directory_recursively(tmp_path):
    """When given a directory path, finds tags in all nested YAML files."""
    sub = tmp_path / "sub"
    sub.mkdir()
    (sub / "a.yaml").write_text(
        "# llm-decision: extraction free-preferred\n"
        "model: gemini/gemini-2.5-flash\n"
    )
    (sub / "b.yaml").write_text("model: gemini/gemini-2.5-flash\n")
    decisions = extract_decision_comments([str(tmp_path)])
    assert len(decisions) == 1
    assert decisions[0]["tags"] == ["extraction", "free-preferred"]
    assert decisions[0]["prose"] == ""


@pytest.mark.unit
def test_extract_model_none_when_assignment_beyond_lookahead(tmp_path):
    """model is None when the YAML value is more than 5 lines below the tag."""
    cfg = tmp_path / "config.yaml"
    lines = ["# llm-decision: reasoning free-preferred"] + ["# comment"] * 5 + ["model: gemini/gemini-2.5-flash"]
    cfg.write_text("\n".join(lines) + "\n")
    decisions = extract_decision_comments([str(cfg)])
    assert len(decisions) == 1
    assert decisions[0]["model"] is None


@pytest.mark.unit
def test_load_snapshots_reads_all_yaml(tmp_path):
    """Loads all .yaml files from the snapshots directory."""
    (tmp_path / "gemini.yaml").write_text("provider: gemini\nlast_checked: 2026-05-01\n")
    (tmp_path / "groq.yaml").write_text("provider: groq\nlast_checked: 2026-05-01\n")
    with patch("scripts.provider_review.bootstrap.SNAPSHOTS_DIR", tmp_path):
        snapshots = load_snapshots()
    assert set(snapshots.keys()) == {"gemini", "groq"}
    assert snapshots["gemini"]["provider"] == "gemini"
