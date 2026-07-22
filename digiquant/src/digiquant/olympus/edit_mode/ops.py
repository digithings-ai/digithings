"""JSON Pointer patch ops — canonical merge primitive for Olympus edit-mode.

Logic originally mirrored ``digiquant/scripts/atlas/materialize_snapshot.py:apply_ops``
(now frozen). This copy additionally implements the RFC 6901 ``-`` append token and
fail-soft list-index handling (#1641): the patch-emitting models routinely write
``set /material_findings/-`` meaning "append" and past-end indices, and a merge
crash used to cost the whole segment (``int('-')`` ValueError, IndexError).
"""

from __future__ import annotations

from copy import deepcopy
from typing import Any  # noqa  # scored-lint suppression: heterogeneous graph / dict shapes


def _json_pointer_tokens(ptr: str) -> list[str]:
    if not ptr.startswith("/"):
        msg = f"Invalid path (must start with '/'): {ptr}"
        raise ValueError(msg)
    parts = ptr.lstrip("/").split("/")
    return [p.replace("~1", "/").replace("~0", "~") for p in parts if p != ""]


def _list_index(token: str, size: int) -> int:
    """Resolve a JSON Pointer list token to an index; ``-`` → *size* (append position)."""
    if token == "-":
        return size
    try:
        return int(token)
    except ValueError as exc:
        msg = f"invalid list index {token!r}"
        raise ValueError(msg) from exc


def _get_parent_and_key(doc: Any, path: str) -> tuple[Any, str]:
    toks = _json_pointer_tokens(path)
    if not toks:
        msg = "Path refers to document root; not allowed for ops"
        raise ValueError(msg)
    cur = doc
    for token in toks[:-1]:
        if isinstance(cur, list):
            if not cur:
                msg = f"cannot traverse empty list at token {token!r} in {path}"
                raise ValueError(msg)
            idx = _list_index(token, len(cur))
            # A mid-path ``-``/past-end index addresses the last element: the model
            # means "the item I just appended", and a hard IndexError costs the segment.
            if idx >= len(cur):
                idx = len(cur) - 1
            cur = cur[idx]
        else:
            if token not in cur or cur[token] is None:
                cur[token] = {}
            cur = cur[token]
    return cur, toks[-1]


def _apply_set(parent: Any, key: str, path: str, value: Any) -> None:
    if isinstance(parent, list):
        idx = _list_index(key, len(parent))
        if -len(parent) <= idx < len(parent):
            parent[idx] = value
        else:
            # ``-`` or a past-end index is an append, per RFC 6902 "add" semantics.
            parent.append(value)
    else:
        parent[key] = value


def _apply_append(parent: Any, key: str, path: str, value: Any) -> None:
    target: Any
    if isinstance(parent, list):
        if key == "-":
            # The path addressed the append slot of the list itself.
            parent.append(value)
            return
        idx = _list_index(key, len(parent))
        if -len(parent) <= idx < len(parent):
            target = parent[idx]
            if target is None:
                target = []
                parent[idx] = target
        else:
            target = []
            parent.append(target)
    else:
        target = parent.get(key)
        if target is None:
            target = []
            parent[key] = target
    if not isinstance(target, list):
        msg = f"append op requires list at {path}"
        raise ValueError(msg)
    target.append(value)


def _apply_remove(parent: Any, key: str) -> None:
    if isinstance(parent, list):
        if not parent:
            return
        idx = len(parent) - 1 if key == "-" else _list_index(key, len(parent))
        if -len(parent) <= idx < len(parent):
            parent.pop(idx)
        # An out-of-range index is a no-op — parity with the dict branch's
        # ``pop(key, None)``; the element the model wanted gone isn't there.
    else:
        parent.pop(key, None)


def apply_ops(base: dict[str, Any], ops: list[dict[str, Any]]) -> dict[str, Any]:
    """Apply JSON Pointer ops to *base* and return a new document."""
    doc: Any = deepcopy(base)
    for op in ops:
        op_type = op.get("op")
        path = op.get("path")
        if not op_type or not path:
            msg = f"Invalid op (missing op/path): {op}"
            raise ValueError(msg)
        try:
            parent, key = _get_parent_and_key(doc, path)
            if op_type == "set":
                _apply_set(parent, key, path, op.get("value"))
            elif op_type == "append":
                _apply_append(parent, key, path, op.get("value"))
            elif op_type == "remove":
                _apply_remove(parent, key)
            else:
                msg = f"Unknown op type: {op_type}"
                raise ValueError(msg)
        except (IndexError, KeyError, TypeError) as exc:
            # Deterministic MergeError instead of a raw crash — merge failures are
            # per-segment fail-soft upstream, never run-fatal (#1641).
            msg = f"op {op_type!r} at {path!r} failed: {type(exc).__name__}: {exc}"
            raise ValueError(msg) from exc
    return doc
