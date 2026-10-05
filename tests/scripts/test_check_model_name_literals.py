#!/usr/bin/env python3
"""Tests for `scripts/check_model_name_literals.py` (#5029 phase 3).

The guard's whole value is that it cannot be satisfied by accident, so most of
these tests are about the ways it could pass for the wrong reason: an empty
marker set, an allowlist entry with nothing left in it, a comment that looks
like code, a production file mistaken for a fixture.
"""

from __future__ import annotations

import importlib.util
import json
from pathlib import Path

import pytest

_MODULE_PATH = (
    Path(__file__).resolve().parent.parent.parent / "scripts" / "check_model_name_literals.py"
)
_spec = importlib.util.spec_from_file_location("check_model_name_literals", _MODULE_PATH)
assert _spec and _spec.loader
guard = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(guard)


def _fake_root(tmp_path: Path, *, markers: dict[str, object] | None = None) -> Path:
    """A minimal repo root the guard can be pointed at.

    The policy file is written because `configured_markers()` refuses to return
    an empty set — a guard whose configured vocabulary has emptied out is a
    guard that passes on everything.
    """
    policy = (
        markers
        if markers is not None
        else {
            "flagship_model_id_markers": ["gpt-5"],
            "balanced_flagship_markers": [],
            "fallback_model": "gpt-4o-mini",
        }
    )
    (tmp_path / "config").mkdir(parents=True, exist_ok=True)
    (tmp_path / "config" / "model-policy.json").write_text(json.dumps(policy), encoding="utf-8")
    return tmp_path


@pytest.mark.parametrize(
    ("rel", "exempt"),
    [
        # The one that matters: a Pages Function named after its route. Exempting
        # a bare `test` stem would have hidden this file, which ships.
        ("apps/digithings-web/functions/api/byok/test.ts", False),
        ("apps/digichat/src/app/api/byok/test/route.ts", True),
        # Real tests, three conventions.
        ("tests/dg/test_model_config.py", True),
        ("apps/digichat/src/lib/deploy-config/deploy-models.test.ts", True),
        ("apps/digichat/src/thing.spec.ts", True),
        ("digillm/src/digillm/client_test.py", True),
        # Ordinary production files.
        ("digillm/src/digillm/client.py", False),
        ("scripts/validate_model_routing.py", False),
        # Structural exemptions.
        ("packages/ui/src/components/chat/skins/grok.tsx", True),
        ("packages/ui/src/components/chat/skins/base/model.ts", True),
        ("apps/digichat/src/lib/model-catalog.generated.ts", True),
        ("apps/digichat/reference/base/lib/model.ts", True),
        ("scripts/check_model_name_literals.py", True),
    ],
)
def test_path_classification(tmp_path: Path, rel: str, exempt: bool) -> None:
    root = _fake_root(tmp_path)
    path = root / rel
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("", encoding="utf-8")
    monkey = pytest.MonkeyPatch()
    monkey.setattr(guard, "REPO_ROOT", root)
    try:
        assert (guard._is_exempt(path) or guard._is_test_path(path)) is exempt
    finally:
        monkey.undo()


class TestScriptScanning:
    """A literal in real code is found; the same word in prose is not."""

    def test_python_literal_is_found(self, tmp_path: Path) -> None:
        path = tmp_path / "m.py"
        path.write_text('MODEL = "gpt-4o-mini"\n', encoding="utf-8")
        assert guard.scan(path) == [(1, "gpt-4o-mini")]

    def test_python_docstring_is_not_a_literal(self, tmp_path: Path) -> None:
        # Prose is allowed to describe what a configured value looks like.
        path = tmp_path / "m.py"
        path.write_text('"""Ship gpt-4o-mini or gpt-4o by default."""\nX = 1\n', encoding="utf-8")
        assert guard.scan(path) == []

    def test_python_comment_is_not_a_literal(self, tmp_path: Path) -> None:
        path = tmp_path / "m.py"
        path.write_text("# TODO: drop gpt-4o-mini\nX = 1\n", encoding="utf-8")
        assert guard.scan(path) == []

    def test_ts_string_literal_is_found(self, tmp_path: Path) -> None:
        path = tmp_path / "m.ts"
        path.write_text('const m = "claude-sonnet-4-6";\n', encoding="utf-8")
        assert guard.scan(path) == [(1, "claude-sonnet-4-6")]

    def test_ts_line_comment_is_masked(self, tmp_path: Path) -> None:
        path = tmp_path / "m.ts"
        path.write_text("// const m = 'grok-4.3';\nconst x = 1;\n", encoding="utf-8")
        assert guard.scan(path) == []

    def test_ts_block_comment_is_masked(self, tmp_path: Path) -> None:
        path = tmp_path / "m.ts"
        path.write_text("/*\n * gemini-3.5-flash\n */\nconst x = 1;\n", encoding="utf-8")
        assert guard.scan(path) == []

    def test_url_in_a_string_does_not_start_a_comment(self, tmp_path: Path) -> None:
        """The naive stripper blanks from `//` to end of line, losing real code.

        A URL is the everyday case, and losing the tail of a line would hide a
        literal sitting after it — a false negative created by the tool meant
        to find them.
        """
        path = tmp_path / "m.ts"
        path.write_text(
            'const u = "https://api.example/v1"; const m = "gpt-4o-mini";\n', encoding="utf-8"
        )
        assert guard.scan(path) == [(1, "gpt-4o-mini")]

    def test_masker_preserves_offsets_and_length(self) -> None:
        src = 'const a = "x"; // note\nconst b = "gpt-4o";\n'
        masked = guard._mask_js_comments(src)
        assert len(masked) == len(src)
        assert masked.count("\n") == src.count("\n")
        assert "note" not in masked
        assert "gpt-4o" in masked


class TestGuardOutcomes:
    """The three ways this guard must fail, and the one way it must pass."""

    def test_passes_on_a_clean_tree(self, tmp_path: Path, capsys: pytest.CaptureFixture) -> None:
        root = _fake_root(tmp_path)
        (root / "app").mkdir()
        (root / "app" / "m.py").write_text('X = "anthropic"\n', encoding="utf-8")
        monkey = pytest.MonkeyPatch()
        monkey.setattr(guard, "REPO_ROOT", root)
        monkey.setattr(guard, "KNOWN_REMAINING", {})
        try:
            assert guard.main() == 0
        finally:
            monkey.undo()
        assert "OK" in capsys.readouterr().out

    def test_fails_on_a_planted_literal(
        self, tmp_path: Path, capsys: pytest.CaptureFixture
    ) -> None:
        root = _fake_root(tmp_path)
        (root / "app").mkdir()
        (root / "app" / "m.py").write_text('X = "gpt-4o-mini"\n', encoding="utf-8")
        monkey = pytest.MonkeyPatch()
        monkey.setattr(guard, "REPO_ROOT", root)
        monkey.setattr(guard, "KNOWN_REMAINING", {})
        try:
            assert guard.main() == 1
        finally:
            monkey.undo()
        assert "app/m.py" in capsys.readouterr().err

    def test_allowlisted_file_passes_at_its_recorded_count(self, tmp_path: Path) -> None:
        root = _fake_root(tmp_path)
        (root / "app").mkdir()
        (root / "app" / "m.py").write_text('A = "gpt-4o-mini"\nB = "gpt-4o"\n', encoding="utf-8")
        monkey = pytest.MonkeyPatch()
        monkey.setattr(guard, "REPO_ROOT", root)
        monkey.setattr(guard, "KNOWN_REMAINING", {"app/m.py": 2})
        try:
            assert guard.main() == 0
        finally:
            monkey.undo()

    def test_stale_allowlist_entry_is_reported(
        self, tmp_path: Path, capsys: pytest.CaptureFixture
    ) -> None:
        """The anti-rot property: the list shrinks and says so.

        Without this the allowlist is a permanent exemption wearing a comment,
        which is the failure mode #5029 was opened about.
        """
        root = _fake_root(tmp_path)
        (root / "app").mkdir()
        (root / "app" / "m.py").write_text('A = "gpt-4o-mini"\n', encoding="utf-8")
        monkey = pytest.MonkeyPatch()
        monkey.setattr(guard, "REPO_ROOT", root)
        monkey.setattr(guard, "KNOWN_REMAINING", {"app/m.py": 3})
        try:
            assert guard.main() == 1
        finally:
            monkey.undo()
        assert "allowlist expects 3" in capsys.readouterr().err

    def test_allowlist_entry_for_a_vanished_file_is_reported(
        self, tmp_path: Path, capsys: pytest.CaptureFixture
    ) -> None:
        root = _fake_root(tmp_path)
        (root / "app").mkdir()
        (root / "app" / "m.py").write_text("X = 1\n", encoding="utf-8")
        monkey = pytest.MonkeyPatch()
        monkey.setattr(guard, "REPO_ROOT", root)
        monkey.setattr(guard, "KNOWN_REMAINING", {"app/gone.py": 4})
        try:
            assert guard.main() == 1
        finally:
            monkey.undo()
        assert "found 0" in capsys.readouterr().err


class TestVacuity:
    """A guard that cannot fail is worse than no guard, so these are errors."""

    def test_empty_marker_set_is_refused(self, tmp_path: Path) -> None:
        root = _fake_root(
            tmp_path,
            markers={
                "flagship_model_id_markers": [],
                "balanced_flagship_markers": [],
                "fallback_model": None,
            },
        )
        monkey = pytest.MonkeyPatch()
        monkey.setattr(guard, "REPO_ROOT", root)
        try:
            with pytest.raises(SystemExit, match="pass vacuously"):
                guard.configured_markers()
        finally:
            monkey.undo()

    def test_missing_policy_file_is_refused(self, tmp_path: Path) -> None:
        monkey = pytest.MonkeyPatch()
        monkey.setattr(guard, "REPO_ROOT", tmp_path)
        try:
            with pytest.raises(SystemExit, match="model policy not found"):
                guard.configured_markers()
        finally:
            monkey.undo()

    def test_empty_tree_is_refused(self, tmp_path: Path) -> None:
        root = _fake_root(tmp_path)
        monkey = pytest.MonkeyPatch()
        monkey.setattr(guard, "REPO_ROOT", root)
        monkey.setattr(guard, "KNOWN_REMAINING", {})
        try:
            with pytest.raises(SystemExit, match="pass vacuously"):
                guard.main()
        finally:
            monkey.undo()

    def test_configured_markers_come_from_the_policy(self, tmp_path: Path) -> None:
        """Adding a name to config and hardcoding it must be a failure.

        If the markers were hardcoded in this script, an id promoted into
        config and then pasted into source would pass.
        """
        root = _fake_root(
            tmp_path,
            markers={
                "flagship_model_id_markers": ["brand-new-9"],
                "balanced_flagship_markers": [],
                "fallback_model": None,
            },
        )
        monkey = pytest.MonkeyPatch()
        monkey.setattr(guard, "REPO_ROOT", root)
        try:
            assert guard.configured_markers() == {"brand-new-9"}
        finally:
            monkey.undo()


@pytest.mark.unit
class TestAgainstThisRepo:
    """The committed allowlist must match the tree as committed.

    This is the test that stops the numbers in `KNOWN_REMAINING` drifting away
    from reality between runs of the guard itself, which is what makes them
    falsifiable.
    """

    def test_repo_passes_clean(self) -> None:
        assert guard.main() == 0

    def test_no_allowlist_entry_points_at_a_test_fixture(self) -> None:
        for name in guard.KNOWN_REMAINING:
            path = guard.REPO_ROOT / name
            assert path.is_file(), f"{name} in KNOWN_REMAINING does not exist"
            assert not guard._is_test_path(path), f"{name} is a test fixture; it needs no exemption"
            assert not guard._is_exempt(path), (
                f"{name} is structurally exempt; drop it from the allowlist"
            )

    def test_pattern_matches_what_it_claims(self) -> None:
        for name in (
            "gpt-4o-mini",
            "gpt-5.6-luna",
            "claude-sonnet-4-6",
            "gemini-3.7-flash",
            "grok-4.3",
            "llama-3.3-70b",
            "deepseek/deepseek-v4-pro",
            "qwen3-235b",
            "glm-4.6",
            "kimi-k2",
            "nemotron-3.5",
            "phi-4",
            "gemma-3-27b",
        ):
            assert guard.MODEL_ID_PATTERN.search(name), f"{name} should match"
        for name in ("gpt", "openai", "x-ai", "anthropic", "a model id", "TOOLCHAIN"):
            assert not guard.MODEL_ID_PATTERN.search(name), f"{name} should not match"
