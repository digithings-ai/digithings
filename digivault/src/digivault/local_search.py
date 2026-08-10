"""Filesystem keyword search for digivault_search_notes (Profile A / client vaults)."""

from __future__ import annotations

import re
from collections import Counter
from pathlib import Path

from digivault.frontmatter import split_frontmatter
from digivault.supabase_store import VaultSearchHit
from digivault.vault import Vault

_TOKEN = re.compile(r"[a-z0-9]+", re.IGNORECASE)


def _tokens(text: str) -> list[str]:
    return [t.lower() for t in _TOKEN.findall(text)]


def _path_under_prefix(path_for_prefix: str, rel: str, prefix: str) -> bool:
    """True when *path_for_prefix* or *rel* is *prefix* or a child path under it.

    Requires a path-segment boundary so ``clients/occ`` does not match
    ``clients/occasion/...`` (corpus isolation for multi-tenant vault roots).
    """
    if path_for_prefix == prefix or rel == prefix or rel == f"{prefix}.md":
        return True
    return path_for_prefix.startswith(prefix + "/") or rel.startswith(prefix + "/")


def search_local_vault(
    vault: Vault,
    query: str,
    *,
    limit: int = 7,
    path_prefix: str | None = None,
) -> list[VaultSearchHit]:
    """Rank notes by token overlap in title + body. Deterministic; no network."""
    q = [t for t in _tokens(query) if t]
    if not q or vault.root is None:
        return []
    prefix = (path_prefix or "").strip().strip("/")
    scored: list[VaultSearchHit] = []
    for note in vault.list_notes():
        rel = note.rel_path.replace("\\", "/")
        # note.rel_path often includes .md; vault_path in hits historically used rel_path
        path_for_prefix = rel[:-3] if rel.endswith(".md") else rel
        if prefix and not _path_under_prefix(path_for_prefix, rel, prefix):
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
