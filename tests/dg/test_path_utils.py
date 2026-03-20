"""Unit tests for digigraph.path_utils — resolve-first path traversal prevention."""

from __future__ import annotations

import os
import sys
from pathlib import Path

import pytest

from digigraph.path_utils import assert_safe_path


# ---------------------------------------------------------------------------
# Happy path — valid sub-paths
# ---------------------------------------------------------------------------

@pytest.mark.unit
class TestAssertSafePathValid:
    def test_direct_child_file(self, tmp_path: Path) -> None:
        (tmp_path / "data.json").touch()
        result = assert_safe_path(tmp_path, "data.json")
        assert result == (tmp_path / "data.json").resolve()

    def test_nested_subdirectory(self, tmp_path: Path) -> None:
        (tmp_path / "sub").mkdir()
        (tmp_path / "sub" / "file.txt").touch()
        result = assert_safe_path(tmp_path, "sub/file.txt")
        assert result == (tmp_path / "sub" / "file.txt").resolve()

    def test_deep_nested_path(self, tmp_path: Path) -> None:
        deep = tmp_path / "a" / "b" / "c"
        deep.mkdir(parents=True)
        (deep / "x.py").touch()
        result = assert_safe_path(tmp_path, "a/b/c/x.py")
        assert result == (deep / "x.py").resolve()

    def test_returns_path_object(self, tmp_path: Path) -> None:
        (tmp_path / "f.txt").touch()
        result = assert_safe_path(tmp_path, "f.txt")
        assert isinstance(result, Path)

    def test_absolute_path_within_base(self, tmp_path: Path) -> None:
        (tmp_path / "inside.txt").touch()
        abs_ref = str(tmp_path / "inside.txt")
        result = assert_safe_path(tmp_path, abs_ref)
        assert result.is_relative_to(tmp_path)

    def test_custom_label_in_error_message(self, tmp_path: Path) -> None:
        with pytest.raises(ValueError, match="my_label"):
            assert_safe_path(tmp_path, "", label="my_label")


# ---------------------------------------------------------------------------
# Path traversal — must be rejected
# ---------------------------------------------------------------------------

@pytest.mark.unit
class TestAssertSafePathTraversal:
    def test_dotdot_parent_escape(self, tmp_path: Path) -> None:
        with pytest.raises(ValueError, match="escapes"):
            assert_safe_path(tmp_path, "../outside.txt")

    def test_dotdot_in_middle_of_path(self, tmp_path: Path) -> None:
        with pytest.raises(ValueError, match="escapes"):
            assert_safe_path(tmp_path, "sub/../../etc/passwd")

    def test_absolute_path_outside_base(self, tmp_path: Path) -> None:
        with pytest.raises(ValueError, match="escapes"):
            assert_safe_path(tmp_path, "/etc/passwd")

    def test_multiple_dotdot_segments(self, tmp_path: Path) -> None:
        with pytest.raises(ValueError, match="escapes"):
            assert_safe_path(tmp_path, "../../../../etc/hosts")

    def test_sibling_directory_with_same_prefix(self, tmp_path: Path) -> None:
        # /tmp/abc123 and /tmp/abc123extra are siblings; second should be rejected
        base = tmp_path / "abc"
        base.mkdir()
        sibling = tmp_path / "abc_extra"
        sibling.mkdir()
        # Attempt to reach the sibling via absolute path
        with pytest.raises(ValueError, match="escapes"):
            assert_safe_path(base, str(sibling / "file.txt"))

    @pytest.mark.skipif(
        sys.platform == "win32",
        reason="Symlink creation may require elevated privileges on Windows",
    )
    def test_symlink_to_parent_rejected(self, tmp_path: Path) -> None:
        link = tmp_path / "link_to_parent"
        link.symlink_to(tmp_path.parent)
        with pytest.raises(ValueError, match="escapes"):
            assert_safe_path(tmp_path, "link_to_parent/secret.txt")


# ---------------------------------------------------------------------------
# Empty / whitespace ref
# ---------------------------------------------------------------------------

@pytest.mark.unit
class TestAssertSafePathEmpty:
    def test_empty_string_raises(self, tmp_path: Path) -> None:
        with pytest.raises(ValueError):
            assert_safe_path(tmp_path, "")

    def test_whitespace_only_raises(self, tmp_path: Path) -> None:
        with pytest.raises(ValueError):
            assert_safe_path(tmp_path, "   ")

    def test_error_message_includes_label(self, tmp_path: Path) -> None:
        with pytest.raises(ValueError, match="dataset_ref"):
            assert_safe_path(tmp_path, "", label="dataset_ref")
