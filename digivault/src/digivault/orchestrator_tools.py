"""OpenAI-style orchestrator tool definitions for digivault.

Hubs (e.g. digigraph) fetch these via ``POST /v1/orchestrator_tools`` and execute
via ``POST /v1/orchestrator_invoke`` so vault tooling is owned by this service.
"""

from __future__ import annotations

from typing import Any, TypedDict  # score:allow untyped any — OpenAI tool JSON-schema property maps


class FunctionParametersSchema(TypedDict, total=False):
    type: str
    properties: dict[str, Any]
    required: list[str]


class FunctionToolSchema(TypedDict):
    name: str
    description: str
    parameters: FunctionParametersSchema


class OpenAIToolDict(TypedDict):
    type: str
    function: FunctionToolSchema


TOOL_VAULT_SEARCH_TAG = "digivault_search_tag"
TOOL_VAULT_BACKLINKS = "digivault_backlinks"
TOOL_VAULT_LINT = "digivault_lint"
TOOL_VAULT_CREATE_NOTE = "digivault_create_note"
TOOL_VAULT_SEARCH_NOTES = "digivault_search_notes"
TOOL_VAULT_GET_NOTE = "digivault_get_note"

ORCHESTRATOR_TOOL_NAMES: frozenset[str] = frozenset(
    {
        TOOL_VAULT_SEARCH_TAG,
        TOOL_VAULT_BACKLINKS,
        TOOL_VAULT_LINT,
        TOOL_VAULT_CREATE_NOTE,
        TOOL_VAULT_SEARCH_NOTES,
        TOOL_VAULT_GET_NOTE,
    }
)

DEFAULT_SEARCH_NOTES_LIMIT = 7


def _fn(name: str, description: str, params: FunctionParametersSchema) -> OpenAIToolDict:
    return {
        "type": "function",
        "function": {"name": name, "description": description, "parameters": params},
    }


def build_orchestrator_tool_manifest() -> list[OpenAIToolDict]:
    """Return the OpenAI function-tool definitions owned by digivault."""
    return [
        _fn(
            TOOL_VAULT_SEARCH_TAG,
            "Find vault notes carrying a given tag. Use to locate documentation by topic.",
            {
                "type": "object",
                "properties": {"tag": {"type": "string", "description": "Tag without '#'"}},
                "required": ["tag"],
            },
        ),
        _fn(
            TOOL_VAULT_BACKLINKS,
            "List notes that link to a given note (its backlinks).",
            {
                "type": "object",
                "properties": {"name": {"type": "string", "description": "Note name (stem)"}},
                "required": ["name"],
            },
        ),
        _fn(
            TOOL_VAULT_LINT,
            "Validate the vault: unresolved wikilinks, missing frontmatter, orphans.",
            {"type": "object", "properties": {}},
        ),
        _fn(
            TOOL_VAULT_CREATE_NOTE,
            "Create a new markdown note in the vault with optional frontmatter and body.",
            {
                "type": "object",
                "properties": {
                    "name": {"type": "string", "description": "New note name (stem)"},
                    "title": {"type": "string"},
                    "body": {"type": "string"},
                },
                "required": ["name"],
            },
        ),
        _fn(
            TOOL_VAULT_SEARCH_NOTES,
            "Search vault notes by relevance across title and body. Backend precedence: "
            "Cloudflare D1 (FTS5) when configured, ahead of everything else; else the "
            "local filesystem vault when DIGIVAULT_ROOT is set (Profile A / client "
            "volumes); else Supabase FTS when CORE_SUPABASE_URL / CORE_SUPABASE_ANON_KEY "
            "are configured (digithings architecture vault: digigraph, digiquant, "
            "digisearch, digichat, digikey, digismith, digivault, digiclaw, digibase, "
            "and roadmap modules). Use for questions about vault contents, modules, "
            "ports, APIs, architecture, or client docs ingested into the local vault.",
            {
                "type": "object",
                "properties": {
                    "query": {
                        "type": "string",
                        "description": "Natural-language search query.",
                    },
                    "limit": {
                        "type": "integer",
                        "description": f"Max hits to return (default {DEFAULT_SEARCH_NOTES_LIMIT}).",
                    },
                    "path_prefix": {
                        "type": "string",
                        "description": (
                            # Not an enforced boundary at this server, but it is no
                            # longer a mere default-if-missing at the caller either:
                            # digigraph's builtin.py _handle_digivault_search
                            # overwrites this argument unconditionally with the
                            # caller's own session tenant scope
                            # (context.vault_path_prefix) before the request ever
                            # reaches here — whatever the model supplies is discarded,
                            # not merely filled in when absent (digigraph #2265,
                            # closed by #2240). Listed as an optional schema property,
                            # but on a Cloudflare D1 deployment it is functionally
                            # required: D1 has no unscoped-search mode, so a resolved
                            # prefix (from the session's own tenant context) must
                            # exist or the call fails.
                            "Vault_path prefix that scopes the search to one corpus "
                            "(e.g. clients/online-compliance-center). This is a search "
                            "filter, not an access-control boundary — and, when called "
                            "through digigraph, not actually under your control: "
                            "digigraph replaces whatever you pass here with the "
                            "caller's own session tenant scope before this tool ever "
                            "sees it, whether you supply a value or not. Omit it; on a "
                            "Cloudflare D1 deployment the search fails outright if no "
                            "tenant scope is resolved (D1 has no unscoped mode)."
                        ),
                    },
                },
                "required": ["query"],
            },
        ),
        _fn(
            TOOL_VAULT_GET_NOTE,
            "Load one vault note in full by its vault_path. D1-only: unlike "
            "digivault_search_notes, this tool has no filesystem or Supabase "
            "fallback, so on a deployment without Cloudflare D1 configured every "
            "call fails. Use it after a search returns a promising hit, but the "
            "vault_path lives in a different field depending on which search you "
            "used: a digisearch hit for content ingested from this vault carries it "
            "at metadata.vault_path; a digivault_search_notes hit carries it at "
            "doc_id instead — that tool's metadata holds only title/tags, never "
            "vault_path. Call this to read the whole note — a complete page or "
            "document section — instead of reasoning from the excerpt. Do not "
            "guess a vault_path; only use one copied from a prior search hit.",
            {
                "type": "object",
                "properties": {
                    "vault_path": {
                        "type": "string",
                        "description": (
                            "Canonical note path from a prior search hit. From a "
                            "digisearch hit, read hit.metadata.vault_path; from a "
                            "digivault_search_notes hit, read hit.doc_id instead "
                            "(that tool's metadata carries only title/tags, never "
                            "vault_path). E.g. clients/digithings/security__p003. No "
                            ".md suffix. Never invent this value — only pass one "
                            "copied from a prior search hit."
                        ),
                    },
                    "path_prefix": {
                        "type": "string",
                        "description": (
                            # Declared (not omitted) because the server handler
                            # requires it — `args.get("path_prefix")` normalizing to
                            # empty returns `ok=False, error="path_prefix is
                            # required for digivault_get_note"` — and
                            # `OrchestratorInvokeRequest.arguments` is
                            # `dict[str, Any]`, so omitting the schema property never
                            # stopped a model from supplying one anyway (#2265); it
                            # only left the requirement undiscoverable, which made
                            # every call fail once nothing else injects this
                            # argument (#2239 review).
                            "Corpus prefix to fetch from (e.g. "
                            "clients/online-compliance-center). Required — this "
                            "tool has no unscoped mode; a call without it always "
                            "fails. The server rejects a vault_path outside this "
                            "prefix, but path_prefix itself is not verified "
                            "against the caller's actual tenant (#2265) — use the "
                            "same prefix the prior search was scoped to, never a "
                            "different corpus's."
                        ),
                    },
                },
                "required": ["vault_path", "path_prefix"],
            },
        ),
    ]
