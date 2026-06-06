"""Unit tests for the agent tier-routing logic.

Tests the quota-check and priority-parse logic used by:
- .github/workflows/copilot-issue-dispatch.md  (gh-aw: quota check + assign-to-agent)
- .github/workflows/copilot-pr-lifecycle.md    (gh-aw: PR state machine)
- .github/workflows/scheduled-maintenance.yml  (duplicate-issues tokenizer)

All tests are pure-Python (no subprocess, no network) and run as part of
`pytest -m unit`.
"""

from __future__ import annotations

import json
import re
import pytest

pytestmark = pytest.mark.unit


# ── Helpers extracted verbatim from the workflow inline scripts ──────────────

def _parse_exhausted(state_labels_json: str) -> str:
    """Mirrors the quota-exhausted check in copilot-issue-dispatch.md."""
    labels = json.loads(state_labels_json)
    return "true" if "quota:copilot-exhausted" in labels else "false"


def _parse_priority(issue_labels_json: str) -> str:
    """Mirrors the priority-label parse in copilot-issue-dispatch.md."""
    labels = json.loads(issue_labels_json)
    tier = "none"
    for label in labels:
        m = re.match(r"^priority:(critical|high|medium|low)$", label["name"])
        if m:
            tier = m.group(1)
            break
    return tier


def _tokenize_title(title: str) -> set:
    """Mirrors the tokenize() function in duplicate-issues job."""
    t = re.sub(r"^\[[^\]]+\]\s*", "", title.lower())
    return set(re.findall(r"\w+", t)) - {"the", "a", "an", "and", "or", "of", "in", "for", "to"}


def _similarity(title_a: str, title_b: str) -> float:
    ta = _tokenize_title(title_a)
    tb = _tokenize_title(title_b)
    if len(ta) < 3 or len(tb) < 3:
        return 0.0
    return len(ta & tb) / max(len(ta | tb), 1)


# ── Quota state parsing ──────────────────────────────────────────────────────

class TestExhaustedParsing:
    def test_not_exhausted_when_label_absent(self):
        state = json.dumps(["housekeeping", "maintenance"])
        assert _parse_exhausted(state) == "false"

    def test_exhausted_when_label_present(self):
        state = json.dumps(["quota:copilot-exhausted", "maintenance"])
        assert _parse_exhausted(state) == "true"

    def test_empty_label_list(self):
        assert _parse_exhausted("[]") == "false"

    def test_only_exhausted_label(self):
        assert _parse_exhausted('["quota:copilot-exhausted"]') == "true"

    def test_cursor_exhausted_does_not_affect_copilot_check(self):
        state = json.dumps(["quota:cursor-exhausted"])
        assert _parse_exhausted(state) == "false"


# ── Priority label parsing ───────────────────────────────────────────────────

class TestPriorityParsing:
    def _labels(self, *names) -> str:
        return json.dumps([{"name": n} for n in names])

    def test_critical(self):
        assert _parse_priority(self._labels("priority:critical", "exec:copilot")) == "critical"

    def test_high(self):
        assert _parse_priority(self._labels("component:root", "priority:high")) == "high"

    def test_medium(self):
        assert _parse_priority(self._labels("priority:medium")) == "medium"

    def test_low(self):
        assert _parse_priority(self._labels("priority:low")) == "low"

    def test_no_priority_label(self):
        assert _parse_priority(self._labels("exec:copilot", "component:root")) == "none"

    def test_empty_labels(self):
        assert _parse_priority("[]") == "none"

    def test_first_match_wins(self):
        # Both priority:high and priority:low present — first one wins
        result = _parse_priority(self._labels("priority:high", "priority:low"))
        assert result == "high"


# ── Escalation routing matrix ────────────────────────────────────────────────

class TestEscalationMatrix:
    """Validates the routing logic described in EXECUTION_TIERS.md.

    Routing rules:
      - exhausted=false → assign Copilot (happy path)
      - exhausted=true + priority high|critical → swap to exec:claude
      - exhausted=true + priority medium|low|none → park with pending:quota
    """

    def _route(self, exhausted: str, priority: str) -> str:
        if exhausted == "false":
            return "assign_copilot"
        if priority in ("high", "critical"):
            return "escalate_claude"
        return "park"

    def test_happy_path_assigns_copilot(self):
        assert self._route("false", "none") == "assign_copilot"

    def test_happy_path_with_high_priority(self):
        assert self._route("false", "high") == "assign_copilot"

    def test_exhausted_critical_escalates(self):
        assert self._route("true", "critical") == "escalate_claude"

    def test_exhausted_high_escalates(self):
        assert self._route("true", "high") == "escalate_claude"

    def test_exhausted_medium_parks(self):
        assert self._route("true", "medium") == "park"

    def test_exhausted_low_parks(self):
        assert self._route("true", "low") == "park"

    def test_exhausted_no_priority_parks(self):
        assert self._route("true", "none") == "park"


# ── Duplicate-issue title tokenizer ──────────────────────────────────────────

class TestDuplicateTitleTokenizer:
    def test_strips_bracket_prefix(self):
        tokens = _tokenize_title("[feat] add user authentication")
        assert "feat" not in tokens
        assert "user" in tokens
        assert "authentication" in tokens

    def test_strips_fix_prefix(self):
        tokens = _tokenize_title("[fix] resolve calendar sync bug")
        assert "fix" not in tokens
        assert "calendar" in tokens

    def test_stopwords_removed(self):
        tokens = _tokenize_title("the quick brown fox")
        assert "the" not in tokens
        assert "quick" in tokens

    def test_case_insensitive(self):
        t1 = _tokenize_title("[feat] Add User Auth")
        t2 = _tokenize_title("[fix] add user auth")
        assert t1 == t2

    def test_identical_titles_max_similarity(self):
        score = _similarity("[feat] add OAuth login support", "[feat] add OAuth login support")
        assert score == 1.0

    def test_different_prefix_same_content_high_similarity(self):
        score = _similarity("[feat] add OAuth login support", "[fix] add OAuth login support")
        assert score >= 0.8

    def test_unrelated_titles_low_similarity(self):
        score = _similarity("[feat] add user authentication", "[chore] update pip dependencies")
        assert score < 0.3

    def test_short_titles_skipped(self):
        # Titles with <3 tokens after processing should not match
        score = _similarity("fix bug", "fix bug")
        assert score == 0.0

    def test_partial_overlap(self):
        score = _similarity(
            "[feat] add atlas research workflow integration",
            "[feat] add hermes analysis workflow integration",
        )
        # "add", "workflow", "integration" overlap (3 of ~7 unique) — expect moderate
        assert 0.3 < score < 0.7
