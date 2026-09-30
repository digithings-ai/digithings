"""In-process ``luxalgo_*`` tool surface for pipeline agents (#4779 P0).

The 8 LuxAlgo Library tools are MCP-registration + orchestrator manifest
schemas only; this module gives pipeline agents the same in-process surface
the digifetch family has:

* :data:`LUXALGO_TOOLS` — the OpenAI function schemas, *generated* from
  :func:`digiquant.orchestrator_tools.build_orchestrator_tool_manifest`
  (filtered to the names declared in the luxalgo :data:`TOOL_ENTITLEMENTS`),
  so the MCP, manifest, and in-process surfaces cannot drift.
* :data:`RESEARCH_TOOLS` — the curated research subset (all 8; Library reads
  are research-only by scope §P0).
* :func:`available_luxalgo_tools` — subset -> schemas, dropping the whole
  family when ``LUXALGO_ENABLED`` disables it.
* :func:`build_luxalgo_tool_dispatcher` — ``(name, args) -> {"content": <json
  str>, "ok": bool}`` routed through the shared :class:`LuxAlgoClient` and
  serialized with the LuxAlgo attribution envelope.

The client factory (:func:`build_luxalgo_client`) and envelope serializer
(:func:`luxalgo_envelope_json`) live here too, so the MCP surface and the
pipeline dispatcher share one env-keyed cached client (``mcp_server`` imports
them).

LuxAlgo Library reads are **research references, not pipeline primaries** —
and the tools are read-scope. Every payload keeps the "Sourced from LuxAlgo
Library" attribution + the upstream canonical URL where one page is addressed.
Indicator source code is never exposed (CC BY-NC-SA license boundary).
"""

from __future__ import annotations

import json
import logging
import os
import threading
from collections.abc import Mapping
from typing import (  # score:allow untyped any — duck-typed client + heterogeneous tool payloads
    Any,
    Callable,
    NamedTuple,
)

from pydantic import BaseModel, ValidationError

from .client import LUXALGO_ENABLED_ENV, luxalgo_enabled
from .entitlements import TOOL_ENTITLEMENTS
from .models import (
    LibraryGetConceptInput,
    LibraryGetFamilyInput,
    LibraryGetIndicatorInput,
    LibraryListConceptsInput,
    LibraryListFamiliesInput,
    LibraryListIndicatorsInput,
    LibraryListTagsInput,
    LibrarySearchInput,
    LuxalgoEnvelope,
    LuxalgoError,
)

logger = logging.getLogger(__name__)

__all__ = [
    "LUXALGO_TOOLS",
    "RESEARCH_TOOLS",
    "LuxalgoDispatch",
    "LUXALGO_DISPATCH",
    "available_luxalgo_tools",
    "build_luxalgo_tool_dispatcher",
    "build_luxalgo_client",
    "close_luxalgo_client",
    "luxalgo_envelope_json",
]

# ── shared client factory + envelope serializer ──
#
# One lazily-built ``LuxAlgoClient`` per kill-switch env value. Keyed by the
# raw env value so an operator/test env change gets a fresh client without a
# process restart. Only one client is kept alive: when the env value changes,
# the replaced client is closed so its transport is not leaked. The lock
# serializes the read/close/replace dance.

_luxalgo_clients: dict[str, Any] = {}
_luxalgo_clients_lock = threading.Lock()


def close_luxalgo_client(client: Any) -> None:
    """Best-effort close for a client being replaced (never mask the new one)."""
    close = getattr(client, "close", None)
    if not callable(close):
        return
    try:
        close()
    except Exception:  # closing is cleanup; an error must not break a tool call
        pass


def build_luxalgo_client() -> Any:
    """Build/cache the LuxAlgo client from env (patchable seam for tests)."""
    from digiquant.data.luxalgo import LuxAlgoClient

    key = os.environ.get(LUXALGO_ENABLED_ENV, "")
    with _luxalgo_clients_lock:
        client = _luxalgo_clients.get(key)
        if client is not None:
            return client
        client = LuxAlgoClient()
        for stale in _luxalgo_clients.values():
            close_luxalgo_client(stale)
        _luxalgo_clients.clear()
        _luxalgo_clients[key] = client
        return client


def _canonical_url_for(envelope: Any) -> str | None:
    """Best-effort upstream canonical URL from an envelope's data payload."""
    data = getattr(envelope, "data", None)
    if isinstance(data, Mapping):
        for field in ("url", "md_url", "mdUrl"):
            value = data.get(field)
            if isinstance(value, str) and value.strip():
                return value.strip()
    return None


def luxalgo_envelope_json(envelope: Any, *, canonical_url: str | None = None) -> str:
    """Serialize a ``LuxalgoEnvelope`` with attribution + canonical link."""
    payload = envelope.model_dump(mode="json")
    from digiquant.data.luxalgo import attribution_fields

    url = canonical_url or _canonical_url_for(envelope)
    payload.update(attribution_fields(url))
    return json.dumps(payload, indent=2, default=str)


# ── curated research subset (#4779 P0) ───────────────────────────────────────
#
# Library reads are research-only: every wrapped tool belongs to the research
# subset. No deliberation/PM wiring in this phase (deliberation is
# research-tools-only by policy #2908 and consumes the evidence bundle, not a
# new Library family).

RESEARCH_TOOLS: tuple[str, ...] = (
    "luxalgo_library_search",
    "luxalgo_library_get_concept",
    "luxalgo_library_get_indicator",
    "luxalgo_library_list_concepts",
    "luxalgo_library_list_indicators",
    "luxalgo_library_list_tags",
    "luxalgo_library_list_families",
    "luxalgo_library_get_family",
)


# ── schemas, generated from the orchestrator manifest builders ────────────────


def _luxalgo_manifest_tools() -> list[dict[str, Any]]:
    """The manifest entries whose names carry a luxalgo entitlement.

    Generated rather than hand-copied so the MCP, manifest, and in-process
    schemas are the same dicts (descriptions carry the entitlement note, and
    the top-level ``entitlement`` key is preserved as on the manifest surface).
    """
    from digiquant.orchestrator_tools import build_orchestrator_tool_manifest

    return [
        tool
        for tool in build_orchestrator_tool_manifest()
        if tool["function"]["name"] in TOOL_ENTITLEMENTS
    ]


#: Every luxalgo tool schema, in manifest order (names = TOOL_ENTITLEMENTS keys).
LUXALGO_TOOLS: list[dict[str, Any]] = _luxalgo_manifest_tools()

_SCHEMA_BY_NAME: dict[str, dict[str, Any]] = {
    tool["function"]["name"]: tool for tool in LUXALGO_TOOLS
}

_DEFAULT_TOOL_NAMES: tuple[str, ...] = tuple(t["function"]["name"] for t in LUXALGO_TOOLS)


def available_luxalgo_tools(subset: tuple[str, ...] | None = None) -> list[dict[str, Any]]:
    """Schemas for *subset* (default: every luxalgo tool), runtime-gated.

    The whole family is dropped when ``LUXALGO_ENABLED`` disables it (default
    ON; an explicit non-truthy value fails closed), because every call would
    return the typed "disabled by kill switch" ``upstream_error``. Every
    wrapped tool is keyless (``free``), so there is no session filter.

    An unknown name is a wiring bug and raises ``KeyError``.
    """
    if not luxalgo_enabled():
        return []
    names = _DEFAULT_TOOL_NAMES if subset is None else subset
    return [_SCHEMA_BY_NAME[name] for name in names]


# ── dispatcher ────────────────────────────────────────────────────────────────


class LuxalgoDispatch(NamedTuple):
    """One tool's dispatch row: args model + client method."""

    input_model: type[BaseModel]
    client_method: str


#: ``name -> dispatch`` for every luxalgo tool. The row mirrors the MCP
#: wrapper for that tool (same Pydantic input model, same client method); the
#: parity test pins both directions.
LUXALGO_DISPATCH: dict[str, LuxalgoDispatch] = {
    "luxalgo_library_search": LuxalgoDispatch(LibrarySearchInput, "library_search"),
    "luxalgo_library_get_concept": LuxalgoDispatch(LibraryGetConceptInput, "library_get_concept"),
    "luxalgo_library_get_indicator": LuxalgoDispatch(
        LibraryGetIndicatorInput, "library_get_indicator"
    ),
    "luxalgo_library_list_concepts": LuxalgoDispatch(
        LibraryListConceptsInput, "library_list_concepts"
    ),
    "luxalgo_library_list_indicators": LuxalgoDispatch(
        LibraryListIndicatorsInput, "library_list_indicators"
    ),
    "luxalgo_library_list_tags": LuxalgoDispatch(LibraryListTagsInput, "library_list_tags"),
    "luxalgo_library_list_families": LuxalgoDispatch(
        LibraryListFamiliesInput, "library_list_families"
    ),
    "luxalgo_library_get_family": LuxalgoDispatch(LibraryGetFamilyInput, "library_get_family"),
}


def build_luxalgo_tool_dispatcher(
    client: Any | None = None,
) -> Callable[[str, dict[str, Any]], str | dict[str, Any]]:
    """Return an ``execute_tool(name, args) -> result`` bound to a client.

    Each result is ``{"content": <attribution-enveloped JSON string>, "ok": bool}``:
    ``content`` is what the model reads, and ``ok`` is the honest success flag
    the tool-call telemetry records.

    ``client`` is the patchable seam tests inject (MockTransport-backed); when
    omitted, the shared env-keyed :func:`build_luxalgo_client` is resolved on
    each call so the cache is shared with the MCP tools and an env change is
    picked up without rebuilding the dispatcher.

    Args are validated through the tool's Pydantic input model; invalid args
    are answered with a typed ``invalid_input`` envelope with no request (the
    same contract as the MCP wrappers) — except a non-mapping args payload,
    which is answered directly. The ``content`` half of every result is
    attribution-enveloped JSON and the dispatcher never raises.
    """

    def _resolve_client() -> Any:
        return client if client is not None else build_luxalgo_client()

    def execute_tool(name: str, args: dict[str, Any]) -> str | dict[str, Any]:
        spec = LUXALGO_DISPATCH.get(name)
        if spec is None:
            return {"content": f"Error: unknown luxalgo tool {name!r}", "ok": False}
        try:
            payload = dict(args or {})
            request: Any = spec.input_model.model_validate(payload)
        except ValidationError as exc:
            # Typed invalid_input with no request (the single validation/error
            # contract for both surfaces).
            logger.warning("luxalgo tool %s got invalid args: %s", name, exc)
            return {
                "content": luxalgo_envelope_json(
                    LuxalgoEnvelope(
                        data=LuxalgoError(
                            code="invalid_input",
                            message=f"invalid args for {name}: {exc.errors(include_url=False)}",
                            retryable=False,
                        )
                    )
                ),
                "ok": False,
            }
        except (TypeError, ValueError) as exc:
            # A non-mapping args payload (list/str/number) never reaches the
            # client: answer with the same typed invalid_input shape instead
            # of raising out of the tool loop.
            logger.warning("luxalgo tool %s got non-mapping args: %s", name, exc)
            return {
                "content": luxalgo_envelope_json(
                    LuxalgoEnvelope(
                        data=LuxalgoError(
                            code="invalid_input",
                            message=(
                                f"tool args must be an object; got {type(args).__name__}: {exc}"
                            ),
                            retryable=False,
                        )
                    )
                ),
                "ok": False,
            }
        try:
            envelope = getattr(_resolve_client(), spec.client_method)(request)
        except Exception as exc:  # mirror the MCP wrappers: never raise to the loop
            logger.warning("luxalgo tool %s failed: %s", name, exc)
            return {
                "content": json.dumps({"error": f"{type(exc).__name__}: {exc}"}),
                "ok": False,
            }
        return {
            "content": luxalgo_envelope_json(envelope),
            # An envelope whose ``data`` slot is a typed error is still a failed
            # call: the model gets the error text, telemetry records ok=False.
            "ok": not isinstance(envelope.data, LuxalgoError),
        }

    return execute_tool
