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
                            # digigraph's own corpus-routing context (`context.vault_
                            # path_prefix`, populated by `resolve_corpus_override`, which
                            # defaults to None) fills this in only when it has a corpus
                            # context AND the model omits this key — with no corpus
                            # context, omitting this argument fills in nothing. Listed as
                            # an optional schema property, but on a Cloudflare D1
                            # deployment it is functionally required: D1 has no
                            # unscoped-search mode, so a resolved prefix (from either
                            # source) must exist or the call fails.
                            #
                            # A model-supplied value is no longer trusted unchecked: once
                            # DIGI_TENANT_CORPUS_MAP is configured, digivault's own server
                            # (tenant_scope.py, #2298) rejects any path_prefix that does
                            # not match the caller's authenticated tenant, regardless of
                            # what digigraph's own builtin.py does or doesn't overwrite
                            # (#2265) — that fix, where merged, is a second, independent
                            # layer, not the only one.
                            "Vault_path prefix that scopes the search to one corpus "
                            "(e.g. clients/online-compliance-center). If the caller has "
                            "a corpus context, omitting this argument lets that context "
                            "fill it in for you; with no such context, omitting it "
                            "fills in nothing, and on a Cloudflare D1 deployment the "
                            "search then fails outright (D1 has no unscoped mode). Do "
                            "not supply a different corpus's prefix on the caller's "
                            "behalf — on a multi-tenant deployment the server will "
                            "reject a mismatched prefix outright, not just ignore this "
                            "instruction."
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
                            # argument (#2239 review). Once DIGI_TENANT_CORPUS_MAP is
                            # configured, digivault's own server (tenant_scope.py,
                            # #2298) now also rejects a path_prefix that doesn't match
                            # the caller's authenticated tenant.
                            "Corpus prefix to fetch from (e.g. "
                            "clients/online-compliance-center). Required — this "
                            "tool has no unscoped mode; a call without it always "
                            "fails. The server rejects a vault_path outside this "
                            "prefix, and on a multi-tenant deployment rejects a "
                            "path_prefix that isn't the caller's own corpus outright "
                            "— use the same prefix the prior search was scoped to, "
                            "never a different corpus's."
                        ),
                    },
                },
                "required": ["vault_path", "path_prefix"],
            },
        ),
    ]
