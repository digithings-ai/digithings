"""Path validation utilities. Shared by server.py, run_storage.py, and digistore.py."""

from __future__ import annotations

from pathlib import Path


def assert_safe_path(base: Path, ref: str, label: str = "path") -> Path:
    """Resolve *ref* under *base* and assert it stays within *base*.

    Uses ``Path.is_relative_to()`` after resolving both sides — immune to
    ``..`` segments, URL-encoded separators, and symlink-based escapes.

    Parameters
    ----------
    base:
        Trusted root directory (must already be resolved).
    ref:
        User-supplied path fragment (relative or absolute).
    label:
        Name used in error messages (e.g. "dataset_ref", "file path").

    Returns
    -------
    Path
        Fully resolved path guaranteed to be under *base*.

    Raises
    ------
    ValueError
        If *ref* resolves outside *base* or is empty.
    """
    if not ref or not ref.strip():
        raise ValueError(f"{label} must not be empty")
    base_resolved = base.resolve()
    candidate = Path(ref)
    # If relative, join under base first so relative refs stay scoped
    if not candidate.is_absolute():
        candidate = base_resolved / candidate
    resolved = candidate.resolve()
    if not resolved.is_relative_to(base_resolved):
        raise ValueError(
            f"{label} escapes allowed root: {ref!r} resolves to {resolved}, "
            f"which is outside {base_resolved}"
        )
    return resolved
