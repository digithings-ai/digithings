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
            # Rewritten for #2306. Dropped the digithings module roster ("digigraph,
            # digiquant, digisearch, …") that used to sit inside the backend-precedence
            # clause: this manifest also serves an OCC compliance corpus, and naming one
            # tenant's internal modules frames the corpus wrongly for the other — the
            # same failure the ex-mailbox text caused in digisearch's description. What
            # the model actually needs, and was never told, is what it receives back.
            "Keyword search (BM25 over an FTS5 index) across vault note titles and "
            "bodies. It matches literal wording, so it is the right sink for an exact "
            "term, a filename, a code, a clause number or a quoted phrase; digisearch is "
            "the semantic sink over the same corpus and is better for a concept stated "
            "in other words. Run both when either comes back thin. Each hit's doc_id IS "
            "the note's vault_path — pass it straight to digivault_get_note; this tool's "
            "metadata carries only title and tags, never vault_path. Called through "
            "digigraph you do NOT receive whole notes: you are shown the first 5 hits "
            "only, each body clipped to 300 characters, and a clipped row is labelled "
            "truncated: true. A clipped excerpt is never sufficient evidence for a "
            "table, a list, a procedure, a count, a date, or an all/every/none claim — "
            "call digivault_get_note with that row's doc_id and answer from the note it "
            "returns. Backed by Cloudflare D1 (FTS5), else a local filesystem vault "
            "(DIGIVAULT_ROOT), else Supabase FTS, in that order.",
            {
                "type": "object",
                "properties": {
                    "query": {
                        "type": "string",
                        "description": "Natural-language search query.",
                    },
                    "limit": {
                        "type": "integer",
                        "description": (
                            f"Hits to return, 1-50 (default {DEFAULT_SEARCH_NOTES_LIMIT}; "
                            "out-of-range values are clamped, not rejected). Called "
                            "through digigraph this changes the citation list, but you "
                            "still read only the first 5 hits, each clipped — raising it "
                            "gives you no extra text. To read more, call "
                            "digivault_get_note."
                        ),
                    },
                    "path_prefix": {
                        "type": "string",
                        "description": (
                            # Two independent layers now cover this argument, not one.
                            # Layer 1 (digigraph, #2265 closed by #2240):
                            # _handle_digivault_search overwrites this argument
                            # unconditionally with the caller's own session tenant
                            # scope (context.vault_path_prefix) before the request
                            # ever reaches here — whatever the model supplies is
                            # discarded, not merely filled in when absent. Layer 2
                            # (digivault itself, tenant_scope.py, #2298): once
                            # DIGI_TENANT_CORPUS_MAP is configured, this service's own
                            # server independently rejects any path_prefix that
                            # doesn't match the caller's authenticated tenant,
                            # regardless of whether Layer 1 already ran — a caller
                            # bypassing digigraph entirely is still covered. Listed
                            # as an optional schema property, but on a Cloudflare D1
                            # deployment it is functionally required: D1 has no
                            # unscoped-search mode, so a resolved prefix (from the
                            # session's own tenant context) must exist or the call
                            # fails.
                            "Vault_path prefix that scopes the search to one corpus "
                            "(e.g. clients/online-compliance-center). When called "
                            "through digigraph, not actually under your control: "
                            "digigraph replaces whatever you pass here with the "
                            "caller's own session tenant scope before this tool ever "
                            "sees it, whether you supply a value or not. Omit it; on "
                            "a Cloudflare D1 deployment the search fails outright if "
                            "no tenant scope is resolved (D1 has no unscoped mode). "
                            "On a multi-tenant deployment, digivault's own server "
                            "independently rejects a mismatched prefix outright too, "
                            "regardless of what digigraph does."
                        ),
                    },
                },
                "required": ["query"],
            },
        ),
        _fn(
            TOOL_VAULT_GET_NOTE,
            # Rewritten for #2306. The old text's only trigger was "use it after a
            # search returns a promising hit", a judgment call the model lost: it read a
            # 300-char excerpt clipped before the table it was asked about, decided the
            # excerpt was enough, never called this tool, and answered wrong. The trigger
            # is now the question's shape, which the model can evaluate, plus an explicit
            # instruction not to assess excerpt completeness at all.
            "Load one whole vault note by vault_path. Call this before answering, for "
            "every hit you intend to quote, cite, count or reason from. Search returns "
            "only a short excerpt of a note, and an excerpt is never sufficient "
            "evidence for a table, a list, a procedure, a number, a date, or any "
            "all/every/none/no-other claim. Do not assess whether an excerpt looks "
            "complete — if the answer depends on the note's content, load the note. "
            "You may issue several digivault_get_note calls in the same turn, one per "
            "note; they all execute before your next reply, so loading three notes "
            "costs one round, not three. vault_path always comes from a prior search "
            "hit and is never invented: from a digivault_search_notes hit read doc_id "
            "(its metadata holds only title/tags); from a digisearch hit read "
            "metadata.vault_path (a digisearch hit's own doc_id is a repo path, not a "
            "vault path). Most notes are one page or section of a larger source and "
            "come back with parent_doc and segment_label set — if the answer runs past "
            "the end of the page you loaded, search for the neighbouring page rather "
            "than assuming the content stops there. Very long notes are cut at about "
            "12,000 characters and marked '[truncated for LLM context...]'; there is no "
            "offset or paging argument to fetch the rest, so if you see that marker, "
            "answer only from what you received and say the note continues. D1-only: "
            "unlike digivault_search_notes this tool has no filesystem or Supabase "
            "fallback, so on a deployment without Cloudflare D1 every call fails.",
            {
                "type": "object",
                "properties": {
                    "vault_path": {
                        "type": "string",
                        "description": (
                            "Canonical note path copied from a prior search hit — never "
                            "invented. From a digivault_search_notes hit read doc_id; "
                            "from a digisearch hit read metadata.vault_path (that "
                            "tool's own doc_id is a repo path and will not resolve). "
                            "E.g. clients/digithings/security__p003. No .md suffix. A "
                            "path ending __pNNN is one page of a larger document."
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
                            # stopped a model from supplying one anyway; it only left
                            # the requirement undiscoverable, which made every call
                            # fail once nothing else injects this argument (#2239
                            # review). Same two independent layers as
                            # digivault_search_notes above: digigraph's builtin.py
                            # _handle_digivault_get_note overwrites this argument
                            # unconditionally with the caller's own session tenant
                            # scope before the request ever reaches here (#2265,
                            # closed by #2240) — and, regardless of that, digivault's
                            # own server (tenant_scope.py, #2298) independently
                            # rejects a path_prefix that doesn't match the caller's
                            # authenticated tenant once DIGI_TENANT_CORPUS_MAP is
                            # configured.
                            "Corpus prefix to fetch from (e.g. "
                            "clients/online-compliance-center). Required — this "
                            "tool has no unscoped mode; a call without it always "
                            "fails. The server rejects a vault_path outside this "
                            "prefix. When called through digigraph, not actually "
                            "under your control: digigraph replaces whatever you "
                            "pass here with the caller's own session tenant scope "
                            "before this tool ever sees it, whether you supply a "
                            "value or not. Omit it, or pass any placeholder — it "
                            "makes no difference to the outcome. On a multi-tenant "
                            "deployment, digivault's own server independently "
                            "rejects a mismatched prefix outright too, regardless "
                            "of what digigraph does."
                        ),
                    },
                },
                "required": ["vault_path", "path_prefix"],
            },
        ),
    ]
