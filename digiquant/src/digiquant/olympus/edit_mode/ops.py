"""JSON Pointer patch ops — canonical merge primitive for Olympus edit-mode.

Logic mirrors ``digiquant/scripts/atlas/materialize_snapshot.py:apply_ops``.
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


def _get_parent_and_key(doc: Any, path: str) -> tuple[Any, str]:
    toks = _json_pointer_tokens(path)
    if not toks:
        msg = "Path refers to document root; not allowed for ops"
        raise ValueError(msg)
    cur = doc
    for token in toks[:-1]:
        if isinstance(cur, list):
            cur = cur[int(token)]
        else:
            if token not in cur or cur[token] is None:
                cur[token] = {}
            cur = cur[token]
    return cur, toks[-1]


def apply_ops(base: dict[str, Any], ops: list[dict[str, Any]]) -> dict[str, Any]:
    """Apply JSON Pointer ops to *base* and return a new document."""
    doc: Any = deepcopy(base)
    for op in ops:
        op_type = op.get("op")
        path = op.get("path")
        if not op_type or not path:
            msg = f"Invalid op (missing op/path): {op}"
            raise ValueError(msg)

        parent, key = _get_parent_and_key(doc, path)
        if op_type == "set":
            value = op.get("value")
            if isinstance(parent, list):
                parent[int(key)] = value
            else:
                parent[key] = value
        elif op_type == "append":
            value = op.get("value")
            target: Any
            if isinstance(parent, list):
                target = parent[int(key)]
            else:
                target = parent.get(key)
            if target is None:
                target = []
                if isinstance(parent, list):
                    parent[int(key)] = target
                else:
                    parent[key] = target
            if not isinstance(target, list):
                msg = f"append op requires list at {path}"
                raise ValueError(msg)
            target.append(value)
        elif op_type == "remove":
            if isinstance(parent, list):
                parent.pop(int(key))
            else:
                parent.pop(key, None)
        else:
            msg = f"Unknown op type: {op_type}"
            raise ValueError(msg)
    return doc
