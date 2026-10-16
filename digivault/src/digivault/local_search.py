"""Filesystem keyword search for digivault_search_notes (Profile A / client vaults)."""

from __future__ import annotations

import re
from collections import Counter
from pathlib import Path

from digivault.d1_store import resolve_path_prefix
from digivault.frontmatter import split_frontmatter
from digivault.supabase_store import VaultSearchHit
from digivault.vault import Vault

_TOKEN = re.compile(r"[a-z0-9]+", re.IGNORECASE)

# Common English function words — a model-written query can still be a full,
# question-shaped sentence (e.g. "what is page 13?"), so without filtering
# "what/is/how/the" would score every note in the corpus.
_STOPWORDS: frozenset[str] = frozenset(
    {
        "a",
        "an",
        "and",
        "are",
        "as",
        "at",
        "be",
        "by",
        "can",
        "do",
        "does",
        "for",
        "from",
        "how",
        "i",
        "in",
        "is",
        "it",
        "me",
        "my",
        "of",
        "on",
        "or",
        "our",
        "please",
        "tell",
        "that",
        "the",
        "their",
        "this",
        "to",
        "us",
        "we",
        "what",
        "when",
        "where",
        "which",
        "who",
        "why",
        "with",
        "you",
        "your",
    }
)


def _tokens(text: str) -> list[str]:
    return [t.lower() for t in _TOKEN.findall(text)]


def _query_tokens(query: str) -> list[str]:
    """Tokenize query and drop stopwords; fall back to raw tokens if all were stopped."""
    raw = [t for t in _tokens(query) if t]
    content = [t for t in raw if t not in _STOPWORDS and len(t) > 1]
    return content or raw


def search_local_vault(
    vault: Vault,
    query: str,
    *,
    limit: int = 7,
    path_prefix: str | None = None,
) -> list[VaultSearchHit]:
    """Rank notes by token overlap in title + body. Deterministic; no network."""
    q = _query_tokens(query)
    if not q or vault.root is None:
        return []
    # Route through the shared helper rather than normalizing inline. A bare
    # `(path_prefix or "").strip().strip("/")` makes a non-None prefix that
    # normalizes to empty ("/", "   ", "///") falsy, which skips the `if prefix:`
    # guard below and returns every note in the root -- the exact fail-open
    # `resolve_path_prefix` exists to prevent. `enforce_tenant_path_prefix` only
    # covers this when DIGI_TENANT_CORPUS_MAP is set; with the map unset the
    # request reaches here unscoped. None still means "no scoping requested".
    prefix = resolve_path_prefix(path_prefix)
    scored: list[VaultSearchHit] = []
    for note in vault.list_notes():
        rel = note.rel_path.replace("\\", "/")
        # note.rel_path often includes .md; vault_path in hits historically used rel_path
        path_for_prefix = rel[:-3] if rel.endswith(".md") else rel
        if prefix:
            # Every clause must respect the "/" boundary — a bare `rel.startswith(prefix)`
            # would also match a sibling path that merely shares the same characters
            # (path_prefix="clients/acme" matching "clients/acme-evil/..."), leaking one
            # tenant's notes into another's search results (#2358). d1_store.py and
            # supabase_store.py already enforce the boundary the same way; keep this in
            # sync with those.
            if not (
                path_for_prefix == prefix
                or path_for_prefix.startswith(prefix + "/")
                or rel.startswith(prefix + "/")
            ):
                continue
        path = Path(vault.root) / note.rel_path
        raw = path.read_text(encoding="utf-8")
        _fm, body = split_frontmatter(raw)
        title = note.title or note.name
        blob_tokens = _tokens(f"{title}\n{body}")
        if not blob_tokens:
            continue
        title_tokens = set(_tokens(title))
        counts = Counter(blob_tokens)
        score = 0.0
        for t in q:
            score += 3.0 * (1.0 if t in title_tokens else 0.0)
            score += float(counts.get(t, 0))
        if score <= 0:
            continue
        scored.append(
            VaultSearchHit(
                vault_path=note.rel_path,
                title=title,
                note_type="local",
                summary=(body.strip().split("\n") or [""])[0][:240],
                body_markdown=body,
                tags=tuple(note.tags),
                wikilinks=tuple(link.target for link in note.outlinks),
                rank=score,
            )
        )
    scored.sort(key=lambda h: (-h.rank, h.vault_path))
    return scored[: max(1, limit)]
