"""Commercial-license guard for LuxAlgo indicator source code (#4845).

``library_get_source_code`` serves LuxAlgo indicator Pine source, which is
CC BY-NC-SA 4.0: no source payload may be persisted (Chroma / Supabase /
``documents`` rows) or rendered into paid digiquant surfaces (tearsheets,
briefs, chat answers) without a commercial Library license.

The license is an explicit opt-in flag, default OFF::

    LUXALGO_COMMERCIAL_LICENSE=1   # only 1/true/yes/on (case-insensitive)

Two enforcement layers live here (stdlib only, so the CI-adjacent check
script can import this module without the MCP extra):

* exposure (:func:`source_code_violations`): fails when the 9th tool appears
  on any surface while the flag is OFF. When the flag is ON the dispatcher
  alone may carry it (MCP, manifest, entitlements, and read scope stay at
  8) — procurement is owner-side and nothing is wired yet.
* payload (:func:`payload_contains_source_code`,
  :func:`assert_payload_has_no_source_code`): spots source-code-shaped
  payloads so persist/render sinks can refuse them.

:func:`scan_source_code_references` is the repo-wide backstop: any code
outside the boundary package + allowlist that references the upstream tool
fails the guard (``tests/dq/test_luxalgo_license_guard.py`` and
``scripts/check_luxalgo_license_boundary.py``).
"""

from __future__ import annotations

import os
from collections.abc import Iterable, Mapping
from pathlib import Path
from typing import Any  # score:allow untyped any — heterogeneous wire payloads

__all__ = [
    "LUXALGO_COMMERCIAL_LICENSE_ENV",
    "SOURCE_CODE_UPSTREAM_TOOL",
    "SOURCE_CODE_TOOL_NAME",
    "SOURCE_CODE_TOOL_NAMES",
    "PERSIST_SINKS",
    "PAID_RENDER_SURFACES",
    "SOURCE_CODE_PAYLOAD_KEYS",
    "LicenseBoundaryError",
    "luxalgo_commercial_license_enabled",
    "LUXALGO_LICENSE_STATE_NOTE_ENABLED",
    "LUXALGO_LICENSE_STATE_NOTE_DISABLED",
    "commercial_license_note",
    "is_source_code_tool",
    "source_code_refusal_message",
    "payload_contains_source_code",
    "assert_payload_has_no_source_code",
    "source_code_violations",
    "SCAN_ALLOWLIST",
    "scan_source_code_references",
    "run_boundary_checks",
]

#: Opt-in env flag for the commercial Library license. Default OFF: unset,
#: blank, or any non-truthy value keeps source code out of every surface.
LUXALGO_COMMERCIAL_LICENSE_ENV = "LUXALGO_COMMERCIAL_LICENSE"

_TRUTHY_ENV_VALUES = frozenset({"1", "true", "yes", "on"})

#: The 9th hosted LuxAlgo MCP tool (upstream name) — deliberately unwrapped.
SOURCE_CODE_UPSTREAM_TOOL = "library_get_source_code"

#: The digiquant-side name the 9th tool would take if ever wrapped.
SOURCE_CODE_TOOL_NAME = "luxalgo_library_get_source_code"

#: Either spelling marks a source-code tool (the digiquant name contains the
#: upstream literal, so one scan literal covers both).
SOURCE_CODE_TOOL_NAMES = frozenset({SOURCE_CODE_UPSTREAM_TOOL, SOURCE_CODE_TOOL_NAME})

#: Persistence sinks a source payload must never reach without the license.
PERSIST_SINKS = ("chroma", "supabase", "documents")

#: Paid digiquant surfaces a source payload must never be rendered into
#: without the license.
PAID_RENDER_SURFACES = ("tearsheets", "briefs", "chat answers")

#: Payload keys whose non-empty value marks a source-code-shaped payload.
SOURCE_CODE_PAYLOAD_KEYS = frozenset(
    {
        "source_code",
        "pine_script",
        "pine_source",
        "script_source",
        "pinescript",
    }
)


class LicenseBoundaryError(ValueError):
    """A source-code payload crossed (or would cross) the license boundary."""


def luxalgo_commercial_license_enabled(*, raw: str | None = None) -> bool:
    """Whether the commercial Library license flag is enabled (default OFF).

    Only ``1``/``true``/``yes``/``on`` (case-insensitive) enable it; unset,
    blank, or any other value — a typo included — keeps the boundary closed.
    No environment variables are read at import time.
    """
    value = os.environ.get(LUXALGO_COMMERCIAL_LICENSE_ENV) if raw is None else raw
    if value is None or not value.strip():
        return False
    return value.strip().lower() in _TRUTHY_ENV_VALUES


#: Attribution-chain note for payloads produced with the license enabled.
LUXALGO_LICENSE_STATE_NOTE_ENABLED = (
    "Commercial Library license: enabled — indicator source-code reads are "
    "licensed for this deployment."
)

#: Attribution-chain note for payloads produced without the license (default).
LUXALGO_LICENSE_STATE_NOTE_DISABLED = (
    "Commercial Library license: not enabled (default) — indicator source code "
    "(CC BY-NC-SA) is excluded from these tools; metadata only, never embedded "
    "in paid surfaces."
)


def commercial_license_note(commercial: bool | None = None) -> str:
    """The per-state license sentence for the attribution chain.

    ``None`` (default) resolves the live flag so payloads always state the
    state they were produced under; an explicit bool pins the sentence.
    """
    enabled = luxalgo_commercial_license_enabled() if commercial is None else commercial
    if enabled:
        return LUXALGO_LICENSE_STATE_NOTE_ENABLED
    return LUXALGO_LICENSE_STATE_NOTE_DISABLED


def is_source_code_tool(name: str) -> bool:
    """Whether *name* addresses indicator source code (either spelling)."""
    return name in SOURCE_CODE_TOOL_NAMES


def source_code_refusal_message(name: str) -> str:
    """Refusal text for a source-code tool call made without the license."""
    return (
        f"{name} serves LuxAlgo indicator Pine source (CC BY-NC-SA) and "
        "requires a commercial Library license: set "
        f"{LUXALGO_COMMERCIAL_LICENSE_ENV}=1 after procurement. No request made; "
        "no source payload was persisted or rendered."
    )


def payload_contains_source_code(payload: Any, *, _depth: int = 0) -> bool:
    """Whether *payload* is source-code-shaped (recursive, depth-bounded)."""
    if _depth > 6:
        return False
    if isinstance(payload, Mapping):
        for key, value in payload.items():
            if isinstance(key, str) and key.strip().lower() in SOURCE_CODE_PAYLOAD_KEYS:
                if isinstance(value, str):
                    if value.strip():
                        return True
                elif value not in (None, "", [], {}):
                    return True
            if payload_contains_source_code(value, _depth=_depth + 1):
                return True
        return False
    if isinstance(payload, (list, tuple)):
        return any(payload_contains_source_code(item, _depth=_depth + 1) for item in payload)
    return False


def assert_payload_has_no_source_code(payload: Any, *, surface: str) -> None:
    """Raise :class:`LicenseBoundaryError` if *payload* is source-code-shaped.

    Persist/render sinks call this before writing *payload* to *surface*
    (one of :data:`PERSIST_SINKS` / :data:`PAID_RENDER_SURFACES`). Fail-closed:
    a licensed deployment that legitimately holds source code must bypass
    this helper explicitly, never silently.
    """
    if payload_contains_source_code(payload):
        raise LicenseBoundaryError(
            f"refusing to send LuxAlgo indicator source code to {surface}: "
            f"CC BY-NC-SA (see {LUXALGO_COMMERCIAL_LICENSE_ENV})."
        )


#: Surfaces that must never carry the 9th tool, flag or not — everything but
#: the dispatcher. MCP, manifest, entitlements, schemas, and the research
#: subset stay at the 8 metadata tools; only the dispatcher may add the 9th,
#: and only with the license.
_ALWAYS_FREE_SURFACES = (
    "mcp_full",
    "mcp_read",
    "read_scope",
    "manifest",
    "entitlements",
    "agent_schemas",
    "research_subset",
)


def source_code_violations(
    tool_names_by_surface: Mapping[str, Iterable[str]],
    *,
    commercial: bool,
) -> list[str]:
    """Exposure violations for the 9th tool across named surfaces.

    *tool_names_by_surface* maps surface name to its tool names (``"mcp_full"``,
    ``"mcp_read"``, ``"read_scope"``, ``"manifest"``, ``"entitlements"``,
    ``"agent_schemas"``, ``"research_subset"``, ``"dispatcher"``). Any
    source-code name on an always-free surface is a violation whether or not
    the license is held; on ``"dispatcher"`` it is a violation only while the
    flag is OFF (``commercial=False``) — when ON the 9th tool may be added
    there. Unknown surface names carrying the tool fail closed too.
    """
    violations: list[str] = []
    for surface, names in tool_names_by_surface.items():
        found = sorted(SOURCE_CODE_TOOL_NAMES & set(names))
        if not found:
            continue
        if surface == "dispatcher" and commercial:
            continue
        state = "licensed" if commercial else f"{LUXALGO_COMMERCIAL_LICENSE_ENV} is OFF"
        violations.append(
            f"{surface} exposes source-code tool(s) {found} ({state}): "
            "indicator Pine source is CC BY-NC-SA — no persist to "
            f"{'/'.join(PERSIST_SINKS)}, no render into "
            f"{'/'.join(PAID_RENDER_SURFACES)} without a commercial license."
        )
    return violations


#: Code suffixes the repo scan inspects (docs stay free to explain the boundary).
SCANNED_SUFFIXES = frozenset({".py", ".ts", ".tsx", ".js"})

#: Directories the repo scan never descends into.
PRUNE_DIRS = frozenset(
    {
        ".git",
        ".venv",
        ".worktrees",
        "__pycache__",
        "node_modules",
        "dist",
        "build",
        ".next",
        ".pytest_cache",
        ".ruff_cache",
    }
)

#: Repo-relative code paths allowed to reference the upstream tool: the
#: boundary package itself (governed by the surface assertions + dispatcher
#: gate) and the guard's own tests.
SCAN_ALLOWLIST = frozenset(
    {
        "digiquant/src/digiquant/data/luxalgo/license_guard.py",
        "digiquant/src/digiquant/data/luxalgo/attribution.py",
        "digiquant/src/digiquant/data/luxalgo/entitlements.py",
        "tests/dq/test_mcp_luxalgo_tools.py",
        "tests/dq/test_luxalgo_license_guard.py",
    }
)


def scan_source_code_references(repo_root: Path | str) -> list[str]:
    """Repo-wide backstop: code references to the source-code tool.

    Walks *repo_root* (pruning :data:`PRUNE_DIRS`, inspecting
    :data:`SCANNED_SUFFIXES`) and returns ``"<relpath>:<lineno>"`` hits for
    the upstream literal outside :data:`SCAN_ALLOWLIST`. Any hit means a
    persist sink or paid renderer started touching source payloads — or a new
    file needs an explicit allowlist decision. Sorted for stable output.
    """
    root = Path(repo_root)
    hits: list[str] = []
    for dirpath, dirnames, filenames in os.walk(root):
        dirnames[:] = sorted(d for d in dirnames if d not in PRUNE_DIRS and not d.startswith("."))
        for filename in sorted(filenames):
            if Path(filename).suffix not in SCANNED_SUFFIXES:
                continue
            path = Path(dirpath) / filename
            try:
                rel = path.relative_to(root).as_posix()
            except ValueError:
                continue
            if rel in SCAN_ALLOWLIST:
                continue
            try:
                text = path.read_text(encoding="utf-8", errors="replace")
            except OSError:
                continue
            for lineno, line in enumerate(text.splitlines(), start=1):
                if SOURCE_CODE_UPSTREAM_TOOL in line:
                    hits.append(f"{rel}:{lineno}")
    return sorted(hits)


def run_boundary_checks(
    repo_root: Path | str,
    tool_names_by_surface: Mapping[str, Iterable[str]],
    *,
    commercial: bool,
) -> list[str]:
    """Full guard: exposure violations plus repo-scan hits (for CI + tests)."""
    violations = source_code_violations(tool_names_by_surface, commercial=commercial)
    violations.extend(f"code reference: {hit}" for hit in scan_source_code_references(repo_root))
    return violations
