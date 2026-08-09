# Client docs onboard (Pick 3) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Ship a reusable offline ops pipeline under `scripts/docs_onboard/` that turns a client website URL into documentation-focused vault notes and/or a digisearch index — without creating a digicorpus peer module — so Profile A digichat → digigraph → digivault (and/or digisearch) can ground answers on that client's docs.

**Architecture:** Pick 3 is an **offline ops workflow**, not a Digi peer module. Leaf scripts under `scripts/docs_onboard/` scrape (via digifetch), classify/prioritize docs pages, fetch PDFs/docs, write digivault notes, and/or POST digisearch ingest. A parent orchestrator (`run_onboard.py`) pieces leaves for “URL → docs-focused crawl → dual sink.” Module roles stay fixed: digifetch = transport; digisearch = parse/OCR/chunk/embed/index; digivault = Obsidian notes + graph + MCP. Client-specific config lives in `docs/projects/<client>/` (or private `projects/`), never as pipeline code. digivault **local** filesystem search (when `DIGIVAULT_ROOT` is set) is a digivault task required for Profile A chat grounding — not a scrape script.

**Tech Stack:** Python 3.12, Pydantic v2, digifetch (`HttpFetcher`), digivault core (`Vault`), digisearch (`POST /ingest` + in-process parsers for vault PDF text), stdlib HTML parsing, pytest under `tests/scripts/docs_onboard/`. Optional later: Profile A Compose attach; digiquant as another pipeline entry.

**Spec input:** Agreed Pick 3 product model (this plan — authoritative). Fit synthesis: [`docs/architecture/digichat-self-hosted-release.md`](../../architecture/digichat-self-hosted-release.md) §5 (Pick 3); full picks-fit rewrite lands in Task 9. Product sketches: [`digichat-modular-frontend.md`](../../architecture/digichat-modular-frontend.md) §5; [`digichat-self-hosted-release.md`](../../architecture/digichat-self-hosted-release.md). Module refs: [`digifetch/ARCHITECTURE.md`](../../../digifetch/ARCHITECTURE.md), [`digisearch/ARCHITECTURE.md`](../../../digisearch/ARCHITECTURE.md), [`digivault/ARCHITECTURE.md`](../../../digivault/ARCHITECTURE.md). Precedent scripts: [`scripts/seed_digisearch_local.py`](../../../scripts/seed_digisearch_local.py), [`scripts/reindex_digithings_guide.py`](../../../scripts/reindex_digithings_guide.py), [`scripts/provider_review/`](../../../scripts/provider_review/).

## Global Constraints

- Digi module names are always lowercase in prose (`digichat`, `digigraph`, `digikey`, `digivault`, `digisearch`, digifetch, digithings) — never DigiChat / DigiVault / DigiCorpus.
- **There is no digicorpus package.** Do not create `digicorpus/`, do not register `component:digicorpus`, do not name a Digi peer module for this work.
- Pipeline code lives under **`scripts/docs_onboard/`** (shared, multi-client). Client manifests/config live under **`docs/projects/<client>/`** or private **`projects/<client>/`**.
- digifetch = web fetch/scrape **transport only** (no site policy, no PDF parse). digisearch = document intelligence (parse, OCR, chunk, embed, index). digivault = notes + graph + agent tools over notes.
- digichat does **not** grow crawl/ingest backends. digigraph does **not** gain a live crawl tool in MVP (batch stays offline).
- digivault core hard deps stay `pydantic` + `pyyaml`. Crawl/PDF deps must not enter digivault core; OCR stays behind digisearch (`DIGISEARCH_OCR_ENABLED` / `digisearch[ocr]`).
- digisearch `POST /ingest` `source` is a **server-side filesystem path** — scripts download to a workdir first; never pass a raw URL as `source` without a sandboxed fetch path in digisearch itself.
- Polars only if tabular work appears. No pandas. Pydantic v2 on public script surfaces — no bare dicts.
- Never touch live-trading paths.
- Every shipping PR links a GitHub Issue (`task/<N>-slug` or `Fixes #<N>`).
- Pick 1 (runtime CSP) and Pick 2 (GHCR Profile A) are **orthogonal** — this plan does not change embed CSP or stack image publish.

---

## Architectural change vs prior plan

| Prior framing (superseded) | Agreed model (this plan) |
|---|---|
| New Digi peer module `digicorpus/` with pyproject, AGENTS, CLI entrypoint | **Offline ops scripts** under `scripts/docs_onboard/` |
| digisearch out of MVP; copy pdfplumber patterns into digicorpus | **digisearch owns** parse/OCR/index; scripts call it |
| Vault-only sink | **Dual sink optional:** digivault notes and/or digisearch vector index |
| Every crawled page → note | **Classify/prioritize** — docs pages first; skip noise; map metadata to source URL |
| Client logic baked into package | **Client manifests** under `docs/projects/<client>/` |

---

## Fit with picks 1–2 (orthogonal)

| Pick | Delivers | Seam with Pick 3 |
|---|---|---|
| **1 — runtime CSP** | Stock digichat GHCR allows any parent via `DIGICHAT_EMBED_HOSTS` / tenant host keys | Docs onboard does **not** touch CSP. Parent site iframes stock digichat; ingested content is what the agent retrieves. |
| **2 — GHCR Profile A** | Client pulls digikey / digigraph / digivault; Profile A without monorepo `docker compose build` | Onboard writes into the **same** `DIGIVAULT_ROOT` volume (and/or a digisearch index). Runtime remains digichat → digigraph → tools. Scripts run **beside** the stack as a job, not a chat-tier Compose service. |
| **3 — this plan** | Offline URL → docs crawl → vault and/or digisearch | E2E chat smoke wants Pick 2’s digivault up. digivault **local search** (Task 1) can land earlier. Soft benefit from Pick 1 for parent-site demos. |

```text
Pick 1: parent site ──iframe──► digichat (stock release)          [orthogonal]
Pick 2: digichat ──► digigraph ──► digivault / digisearch tools   [orthogonal stack]
Pick 3: scripts/docs_onboard ──writes──► DIGIVAULT_ROOT and/or digisearch index
```

**Non-seams:** scripts must not import digichat Node/TS; digichat must not call docs_onboard; digigraph must not grow crawl tools in MVP.

---

## Module roles (do not blur)

| Module | Owns | Does not own |
|---|---|---|
| **digifetch** | HTTP fetch/download, retry, rate limit, optional browser session | URL allowlists, docs-vs-skip policy, HTML→note shaping, PDF OCR |
| **digisearch** | Parse, OCR, chunk, embed, vector index (`POST /ingest`, parsers) | Site crawl BFS, vault note graph, client manifest schema |
| **digivault** | Markdown notes, frontmatter, wikilinks, MCP/orchestrator tools, **local search** when `DIGIVAULT_ROOT` set | Scraping, PDF libraries in core |
| **scripts/docs_onboard** | Ops orchestration + classification + workdir layout + sink writers | New Digi service / peer module |
| **docs/projects/\<client\>** | Seed URL, allow hosts, sink flags, index name, path prefixes | Pipeline implementation |

---

## Proposed script tree

```text
scripts/docs_onboard/
  __init__.py
  models.py              # Pydantic: OnboardManifest, DiscoveredPage, PageClass, WorkItem, OnboardResult
  workspace.py           # Workdir layout: pages.jsonl, assets/, notes meta map
  scrape_site.py         # Leaf: URL → discovered pages/assets (digifetch transport)
  classify_pages.py      # Leaf: prioritize docs vs skip; attach class + score
  fetch_docs.py          # Leaf: download PDFs/other docs into workdir/assets
  write_vault_notes.py   # Leaf: classified docs → digivault notes (+ source_url metadata)
  write_search_index.py  # Leaf: workdir files → digisearch POST /ingest (+ source_url metadata)
  run_onboard.py         # Parent: load manifest → scrape → classify → fetch → sinks

docs/ops/CLIENT_PIPELINES.md          # Index of offline client ops workflows
docs/digichat/CLIENT-DOCS-ONBOARD.md  # Operator runbook for this pipeline
docs/projects/<client>/onboard.yaml   # Per-client manifest (example + real clients)
```

CLI invocation convention (match existing scripts):

```bash
python scripts/docs_onboard/run_onboard.py \
  --manifest docs/projects/acme/onboard.yaml \
  --workdir /tmp/acme-onboard \
  --vault-root /data/vault \
  --sinks vault,search
```

Leaf scripts are also runnable alone for debugging (same flags subset).

---

## File structure

| File | Responsibility |
|---|---|
| `scripts/docs_onboard/models.py` | Shared Pydantic models + manifest load |
| `scripts/docs_onboard/workspace.py` | Atomic JSONL write helpers; workdir paths |
| `scripts/docs_onboard/scrape_site.py` | BFS crawl via digifetch; emit `pages.jsonl` |
| `scripts/docs_onboard/classify_pages.py` | Heuristic docs priority; rewrite JSONL with `page_class` |
| `scripts/docs_onboard/fetch_docs.py` | Download PDF/doc URLs into `assets/` |
| `scripts/docs_onboard/write_vault_notes.py` | HTML/PDF → vault notes with source metadata |
| `scripts/docs_onboard/write_search_index.py` | Assets + HTML exports → digisearch ingest |
| `scripts/docs_onboard/run_onboard.py` | Parent orchestrator |
| `tests/scripts/docs_onboard/test_*.py` | Unit tests (no network) |
| `digivault/src/digivault/local_search.py` | Filesystem keyword search for `digivault_search_notes` |
| `digivault/src/digivault/server.py` | Search precedence: local root → else Supabase |
| `digivault/ARCHITECTURE.md` | Document search precedence |
| `docs/ops/CLIENT_PIPELINES.md` | Ops workflow index |
| `docs/digichat/CLIENT-DOCS-ONBOARD.md` | Client operator runbook |
| `docs/projects/example-docs-client/onboard.yaml` | Example manifest (public dogfood shape) |
| `docs/architecture/digichat-self-host-picks-fit.md` | Pick 3 section rewritten off digicorpus |
| `docs/architecture/digichat-self-hosted-release.md` | Mark corpus follow-up → this plan |

---

### Task 1: digivault local search for `digivault_search_notes`

**Why in this plan:** Profile A clients write notes to a volume. Today `digivault_search_notes` ignores `DIGIVAULT_ROOT` and queries Supabase FTS only — ingest would succeed and chat would miss it. This is a **digivault** change, not a scrape script.

**Files:**
- Create: `digivault/src/digivault/local_search.py`
- Create: `tests/dv/test_local_search.py`
- Modify: `digivault/src/digivault/server.py` (`TOOL_VAULT_SEARCH_NOTES` branch)
- Modify: `digivault/src/digivault/orchestrator_tools.py` (tool description)
- Modify: `digivault/ARCHITECTURE.md` (search precedence)
- Modify: `tests/dv/test_server.py` (local-root path; keep Supabase fakes)

**Interfaces:**
- Consumes: `Vault` under `DIGIVAULT_ROOT`; existing `VaultSearchHit` from `digivault.supabase_store`.
- Produces: `search_local_vault(vault: Vault, query: str, *, limit: int) -> list[VaultSearchHit]`. Precedence: if `DIGIVAULT_ROOT` set → local; else Supabase.

- [ ] **Step 1: Write the failing test**

```python
# tests/dv/test_local_search.py
from __future__ import annotations

from pathlib import Path

import pytest

from digivault.local_search import search_local_vault
from digivault.vault import Vault


@pytest.mark.unit
def test_search_local_vault_ranks_title_and_body(tmp_path: Path) -> None:
    root = tmp_path / "vault"
    root.mkdir()
    v = Vault(root)
    v.create_note(
        "alpha-guide",
        frontmatter={"title": "Alpha onboarding", "tags": ["docs"]},
        body="Welcome to Alpha. Reset your password here.",
    )
    v.create_note(
        "beta-pricing",
        frontmatter={"title": "Beta pricing", "tags": ["sales"]},
        body="Unrelated commercial terms.",
    )
    hits = search_local_vault(v, "alpha password", limit=5)
    assert hits
    assert hits[0].vault_path.endswith("alpha-guide.md")
    assert hits[0].rank > 0
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/dv/test_local_search.py::test_search_local_vault_ranks_title_and_body -v`  
Expected: FAIL with `ModuleNotFoundError: No module named 'digivault.local_search'`.

- [ ] **Step 3: Implement `local_search.py`**

```python
# digivault/src/digivault/local_search.py
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


def search_local_vault(vault: Vault, query: str, *, limit: int = 7) -> list[VaultSearchHit]:
    """Rank notes by token overlap in title + body. Deterministic; no network."""
    q = [t for t in _tokens(query) if t]
    if not q or vault.root is None:
        return []
    scored: list[VaultSearchHit] = []
    for note in vault.list_notes():
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
```

- [ ] **Step 4: Wire `orchestrator_invoke` precedence**

In `digivault/src/digivault/server.py`, replace the Supabase-only branch for `TOOL_VAULT_SEARCH_NOTES` with:

```python
    if tool == TOOL_VAULT_SEARCH_NOTES:
        query = str(args.get("query") or "").strip()
        if not query:
            return OrchestratorInvokeResponse(ok=False, tool=tool, error="query is required")
        try:
            limit = int(args["limit"]) if args.get("limit") else DEFAULT_SEARCH_NOTES_LIMIT
        except (TypeError, ValueError):
            limit = DEFAULT_SEARCH_NOTES_LIMIT
        limit = max(1, min(limit, _MAX_SEARCH_NOTES_LIMIT))

        root = (os.environ.get("DIGIVAULT_ROOT") or "").strip()
        if root:
            from digivault.local_search import search_local_vault

            hits = search_local_vault(_open_vault(), query, limit=limit)
        else:
            hits = _open_supabase_store().search(query, limit=limit)
        data = {"hits": [h.model_dump(mode="json") for h in hits]}
        return OrchestratorInvokeResponse(ok=True, tool=tool, data=data)
```

Update `orchestrator_tools.py` description: searches the configured local vault (`DIGIVAULT_ROOT`) when set; otherwise Supabase FTS when credentials exist. Document precedence in `digivault/ARCHITECTURE.md`.

> Note: prefer a top-of-module import for `search_local_vault` if that does not create a cycle; the inline import above is only acceptable if a cycle is documented — follow repo no-inline-imports rule when implementing.

- [ ] **Step 5: Run tests**

```bash
pytest tests/dv/test_local_search.py tests/dv/test_server.py -m unit -v
ruff check digivault/src/digivault/local_search.py digivault/src/digivault/server.py
```

Expected: PASS; Supabase path still works when `DIGIVAULT_ROOT` unset.

- [ ] **Step 6: Commit**

```bash
git add digivault/src/digivault/local_search.py digivault/src/digivault/server.py \
  digivault/src/digivault/orchestrator_tools.py digivault/ARCHITECTURE.md \
  tests/dv/test_local_search.py tests/dv/test_server.py
git commit -m "$(cat <<'EOF'
feat(digivault): local filesystem search for digivault_search_notes

Profile A client vaults under DIGIVAULT_ROOT become searchable without
digithings core Supabase, unblocking docs onboard → chat grounding.
EOF
)"
```

---

### Task 2: Shared models, workspace, example manifest

**Files:**
- Create: `scripts/docs_onboard/__init__.py`
- Create: `scripts/docs_onboard/models.py`
- Create: `scripts/docs_onboard/workspace.py`
- Create: `docs/projects/example-docs-client/onboard.yaml`
- Create: `tests/scripts/docs_onboard/test_models.py`
- Create: `tests/scripts/docs_onboard/test_workspace.py`

**Interfaces:**
- Consumes: YAML manifest path.
- Produces:
  - `OnboardManifest` (seed_url, allowed_hosts, max_pages, max_depth, sinks, digisearch_index, vault_subdir, docs_path_prefixes, skip_path_prefixes)
  - `DiscoveredPage` (url, final_url, content_type, title, depth, link_text, discovered_from)
  - `PageClass` enum: `docs` | `pdf` | `asset` | `skip`
  - `ClassifiedPage` (page + page_class + score + reasons)
  - `OnboardResult` (pages_seen, docs_kept, skipped, vault_notes, search_docs, errors)
  - `Workspace` paths: `pages.jsonl`, `classified.jsonl`, `assets/`, `html/`, `meta/source_map.jsonl`

- [ ] **Step 1: Write failing tests**

```python
# tests/scripts/docs_onboard/test_models.py
from __future__ import annotations

from pathlib import Path

import pytest

from scripts.docs_onboard.models import OnboardManifest, PageClass, load_manifest


@pytest.mark.unit
def test_load_manifest_roundtrip(tmp_path: Path) -> None:
    path = tmp_path / "onboard.yaml"
    path.write_text(
        """
client: example-docs-client
seed_url: https://docs.example.com/
allowed_hosts:
  - docs.example.com
max_pages: 50
max_depth: 3
sinks: [vault, search]
digisearch_index: example_docs
vault_subdir: clients/example
docs_path_prefixes: ["/docs", "/guide", "/api"]
skip_path_prefixes: ["/blog", "/careers"]
""".strip()
        + "\n",
        encoding="utf-8",
    )
    m = load_manifest(path)
    assert m.client == "example-docs-client"
    assert m.seed_url.startswith("https://")
    assert "vault" in m.sinks and "search" in m.sinks
    assert m.digisearch_index == "example_docs"
```

```python
# tests/scripts/docs_onboard/test_workspace.py
from __future__ import annotations

from pathlib import Path

import pytest

from scripts.docs_onboard.models import DiscoveredPage
from scripts.docs_onboard.workspace import Workspace


@pytest.mark.unit
def test_workspace_append_pages(tmp_path: Path) -> None:
    ws = Workspace.create(tmp_path / "work")
    page = DiscoveredPage(
        url="https://docs.example.com/guide",
        final_url="https://docs.example.com/guide",
        content_type="text/html",
        title="Guide",
        depth=1,
    )
    ws.append_page(page)
    loaded = list(ws.iter_pages())
    assert len(loaded) == 1
    assert loaded[0].url.endswith("/guide")
```

- [ ] **Step 2: Run to verify fail**

Run: `pytest tests/scripts/docs_onboard/test_models.py tests/scripts/docs_onboard/test_workspace.py -v`  
Expected: FAIL (import / module missing).

- [ ] **Step 3: Implement models + workspace**

```python
# scripts/docs_onboard/models.py (essential surface)
from __future__ import annotations

from enum import Enum
from pathlib import Path

import yaml
from pydantic import BaseModel, ConfigDict, Field, HttpUrl


class PageClass(str, Enum):
    docs = "docs"
    pdf = "pdf"
    asset = "asset"
    skip = "skip"


class OnboardManifest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    client: str
    seed_url: str
    allowed_hosts: tuple[str, ...] = ()
    max_pages: int = Field(default=100, ge=1, le=5000)
    max_depth: int = Field(default=3, ge=0, le=20)
    sinks: tuple[str, ...] = ("vault",)  # vault | search
    digisearch_index: str = "default"
    vault_subdir: str = "corpus"
    docs_path_prefixes: tuple[str, ...] = ()
    skip_path_prefixes: tuple[str, ...] = ()


def load_manifest(path: Path) -> OnboardManifest:
    data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    return OnboardManifest.model_validate(data)


class DiscoveredPage(BaseModel):
    model_config = ConfigDict(extra="forbid")

    url: str
    final_url: str
    content_type: str = ""
    title: str = ""
    depth: int = 0
    link_text: str = ""
    discovered_from: str | None = None


class ClassifiedPage(BaseModel):
    model_config = ConfigDict(extra="forbid")

    page: DiscoveredPage
    page_class: PageClass
    score: float = 0.0
    reasons: tuple[str, ...] = ()


class OnboardResult(BaseModel):
    model_config = ConfigDict(extra="forbid")

    pages_seen: int = 0
    docs_kept: int = 0
    skipped: int = 0
    vault_notes: int = 0
    search_docs: int = 0
    errors: tuple[str, ...] = ()
```

`Workspace.create(root)` makes `assets/`, `html/`, `meta/`; `append_page` / `iter_pages` read-write `pages.jsonl` as one JSON object per line via `model_dump(mode="json")`.

Ship example manifest:

```yaml
# docs/projects/example-docs-client/onboard.yaml
client: example-docs-client
seed_url: https://docs.example.com/
allowed_hosts:
  - docs.example.com
max_pages: 100
max_depth: 3
sinks: [vault, search]
digisearch_index: example_docs
vault_subdir: clients/example-docs-client
docs_path_prefixes: ["/docs", "/guide", "/api", "/reference"]
skip_path_prefixes: ["/blog", "/careers", "/pricing"]
```

- [ ] **Step 4: Run tests + commit**

```bash
pytest tests/scripts/docs_onboard/test_models.py tests/scripts/docs_onboard/test_workspace.py -v
git add scripts/docs_onboard docs/projects/example-docs-client tests/scripts/docs_onboard
git commit -m "$(cat <<'EOF'
feat(scripts): docs_onboard models and workspace scaffold

Shared Pydantic manifest/page types for the offline client docs
onboard pipeline (no digicorpus module).
EOF
)"
```

---

### Task 3: `scrape_site.py` — discover pages/assets

**Files:**
- Create: `scripts/docs_onboard/scrape_site.py`
- Create: `scripts/docs_onboard/html_links.py` (link extraction helper)
- Create: `tests/scripts/docs_onboard/test_scrape_site.py`
- Create: `tests/scripts/docs_onboard/fixtures/sample_docs_index.html`

**Interfaces:**
- Consumes: `OnboardManifest`; injectable `fetch_html: Callable[[str], tuple[str, str, str]]` returning `(final_url, content_type, text)` (tests never hit network; production wraps digifetch `HttpFetcher.fetch`).
- Produces: `scrape_site(manifest, workspace, *, fetch_html=...) -> int` pages written; discovers HTML + linked `.pdf`/doc URLs.

- [ ] **Step 1: Failing test (injectable fetch)**

```python
# tests/scripts/docs_onboard/test_scrape_site.py
from __future__ import annotations

from pathlib import Path

import pytest

from scripts.docs_onboard.models import OnboardManifest
from scripts.docs_onboard.scrape_site import scrape_site
from scripts.docs_onboard.workspace import Workspace

FIXTURE = Path(__file__).parent / "fixtures" / "sample_docs_index.html"


@pytest.mark.unit
def test_scrape_site_bfs_respects_caps(tmp_path: Path) -> None:
    html = FIXTURE.read_text(encoding="utf-8")
    pages = {
        "https://docs.example.com/": html,
        "https://docs.example.com/guide/start": "<html><title>Start</title><body><main>Hello</main></body></html>",
        "https://docs.example.com/blog/news": "<html><title>News</title><body>skip me</body></html>",
    }

    def fetch_html(url: str) -> tuple[str, str, str]:
        return url, "text/html", pages[url]

    manifest = OnboardManifest(
        client="example",
        seed_url="https://docs.example.com/",
        allowed_hosts=("docs.example.com",),
        max_pages=10,
        max_depth=2,
    )
    ws = Workspace.create(tmp_path / "work")
    n = scrape_site(manifest, ws, fetch_html=fetch_html)
    urls = {p.url for p in ws.iter_pages()}
    assert n >= 2
    assert "https://docs.example.com/guide/start" in urls
```

Fixture `sample_docs_index.html` must include links to `/guide/start`, `/blog/news`, and `/files/manual.pdf`.

- [ ] **Step 2: Run to verify fail**

Run: `pytest tests/scripts/docs_onboard/test_scrape_site.py -v`  
Expected: FAIL (module missing).

- [ ] **Step 3: Implement scrape**

Rules:
- BFS from `seed_url`; only enqueue hosts in `allowed_hosts` (default: seed host if empty).
- Cap `max_pages` / `max_depth`.
- Record PDF/doc hrefs as discovered pages with `content_type` hint `application/pdf` when extension matches (do not download yet — Task 5).
- Persist raw HTML for HTML pages under `workspace.html_dir / <slug>.html` for later sinks.
- Production default `fetch_html` uses digifetch:

```python
from digifetch.http import HttpFetcher

def default_fetch_html(url: str) -> tuple[str, str, str]:
    fetcher = HttpFetcher()
    result = fetcher.fetch(url)
    return result.url, result.content_type or "text/html", result.text
```

- [ ] **Step 4: CLI entry for leaf**

```bash
python scripts/docs_onboard/scrape_site.py \
  --manifest docs/projects/example-docs-client/onboard.yaml \
  --workdir /tmp/example-onboard
```

- [ ] **Step 5: Tests + commit**

```bash
pytest tests/scripts/docs_onboard/test_scrape_site.py -v
git add scripts/docs_onboard tests/scripts/docs_onboard
git commit -m "$(cat <<'EOF'
feat(scripts): docs_onboard scrape_site leaf via digifetch

Discover same-host HTML and PDF URLs into a workdir for classify/fetch.
EOF
)"
```

---

### Task 4: `classify_pages.py` — docs priority vs skip

**Files:**
- Create: `scripts/docs_onboard/classify_pages.py`
- Create: `tests/scripts/docs_onboard/test_classify_pages.py`

**Interfaces:**
- Consumes: `Workspace` pages + `OnboardManifest` prefixes.
- Produces: `classify_pages(manifest, workspace) -> int` writing `classified.jsonl`; every page gets `PageClass` + score + reasons.

Intelligence rules (v1 heuristics — explicit, testable):

1. URL path starts with any `skip_path_prefixes` → `skip`.
2. URL ends with `.pdf` (or content_type pdf) → `pdf` (always keep; high score).
3. Path starts with any `docs_path_prefixes` → `docs` (boost).
4. Path contains `/docs`, `/guide`, `/api`, `/reference`, `/manual` → `docs`.
5. Otherwise HTML → `skip` by default (YAGNI: do not vault the marketing homepage unless prefixes match). Optional: if path is `/` and host looks like `docs.*`, classify as `docs` with low score.

- [ ] **Step 1: Failing test**

```python
# tests/scripts/docs_onboard/test_classify_pages.py
from __future__ import annotations

from pathlib import Path

import pytest

from scripts.docs_onboard.classify_pages import classify_pages
from scripts.docs_onboard.models import DiscoveredPage, OnboardManifest, PageClass
from scripts.docs_onboard.workspace import Workspace


@pytest.mark.unit
def test_classify_prefers_docs_and_pdfs(tmp_path: Path) -> None:
    manifest = OnboardManifest(
        client="example",
        seed_url="https://docs.example.com/",
        docs_path_prefixes=("/guide",),
        skip_path_prefixes=("/blog",),
    )
    ws = Workspace.create(tmp_path / "work")
    for url, _ in [
        ("https://docs.example.com/guide/start", "text/html"),
        ("https://docs.example.com/blog/news", "text/html"),
        ("https://docs.example.com/files/manual.pdf", "application/pdf"),
    ]:
        ws.append_page(
            DiscoveredPage(url=url, final_url=url, content_type="text/html" if not url.endswith(".pdf") else "application/pdf", depth=1)
        )
    classify_pages(manifest, ws)
    by_url = {c.page.url: c for c in ws.iter_classified()}
    assert by_url["https://docs.example.com/guide/start"].page_class == PageClass.docs
    assert by_url["https://docs.example.com/blog/news"].page_class == PageClass.skip
    assert by_url["https://docs.example.com/files/manual.pdf"].page_class == PageClass.pdf
```

- [ ] **Step 2: Implement + run tests + commit**

```bash
pytest tests/scripts/docs_onboard/test_classify_pages.py -v
git commit -m "$(cat <<'EOF'
feat(scripts): docs_onboard classify_pages prioritizes docs and PDFs

Not every crawled page belongs in digivault; skip noise via manifest prefixes.
EOF
)"
```

---

### Task 5: `fetch_docs.py` — download PDFs and doc assets

**Files:**
- Create: `scripts/docs_onboard/fetch_docs.py`
- Create: `tests/scripts/docs_onboard/test_fetch_docs.py`

**Interfaces:**
- Consumes: classified `pdf` (and optional `asset`) pages; injectable `download: Callable[[str], bytes]`.
- Produces: files under `workspace.assets_dir`; append `meta/source_map.jsonl` rows `{local_path, source_url, content_type}`.

- [ ] **Step 1: Failing test**

```python
@pytest.mark.unit
def test_fetch_docs_writes_asset_and_source_map(tmp_path: Path) -> None:
    # seed workspace with one ClassifiedPage pdf; inject download returning b"%PDF-1.4..."
    # assert asset file exists and source_map maps it back to URL
    ...
```

(Implement the full test body in-repo — assert `source_url` preserved.)

- [ ] **Step 2: Implement with digifetch `HttpFetcher.download` as default**

Respect digifetch `DEFAULT_MAX_BYTES`. Skip pages already present (same URL hash) for idempotent re-runs.

- [ ] **Step 3: Tests + commit**

```bash
pytest tests/scripts/docs_onboard/test_fetch_docs.py -v
git commit -m "$(cat <<'EOF'
feat(scripts): docs_onboard fetch_docs downloads PDFs with source map

Assets land in the workdir; metadata maps local files back to source URLs.
EOF
)"
```

---

### Task 6: `write_vault_notes.py` — digivault sink

**Files:**
- Create: `scripts/docs_onboard/write_vault_notes.py`
- Create: `scripts/docs_onboard/naming.py`
- Create: `scripts/docs_onboard/html_to_markdown.py`
- Create: `tests/scripts/docs_onboard/test_write_vault_notes.py`
- Modify if needed: `digivault/src/digivault/vault.py` — add `write_note(..., overwrite=True)` if create-only blocks idempotent re-runs (keep `_safe_path` guarantees).

**Interfaces:**
- Consumes: classified `docs` HTML (from `html/`) + fetched PDFs; `Vault` / `--vault-root` / `DIGIVAULT_ROOT`.
- Produces: `write_vault_notes(manifest, workspace, vault) -> int` notes written.
- Frontmatter contract: `title`, `tags`, `source_url`, `content_type`, `ingested_at` (UTC ISO), optional `page`, `client`.
- PDF text: use digisearch parsers in-process (`ParserRegistry` / PDF parser) — **do not** vendor pdfplumber into the script package. If digisearch not installed, skip PDFs with a clear error listing `pip install -e ./digisearch`.

- [ ] **Step 1: Failing tests for naming + HTML note**

```python
@pytest.mark.unit
def test_slug_for_url_stable() -> None:
    from scripts.docs_onboard.naming import slug_for_url

    assert slug_for_url("https://docs.example.com/guides/Start/") == slug_for_url(
        "https://docs.example.com/guides/Start"
    )
    assert "/" not in slug_for_url("https://docs.example.com/a/b")


@pytest.mark.unit
def test_write_vault_notes_html_includes_source_url(tmp_path: Path) -> None:
    # workspace with one docs ClassifiedPage + saved HTML containing "Ship agents safely"
    # Vault(tmp_path); write_vault_notes(...); assert frontmatter source_url + body phrase
    ...
```

- [ ] **Step 2: Implement writer**

Idempotent upsert by stable slug. Tags include `onboard`, `docs` or `pdf`, and `client:<name>`.

- [ ] **Step 3: Tests + commit**

```bash
pytest tests/scripts/docs_onboard/test_write_vault_notes.py -v
git commit -m "$(cat <<'EOF'
feat(scripts): docs_onboard write_vault_notes sink with source_url

Docs-priority HTML/PDF content becomes digivault notes mapped to origin URLs.
EOF
)"
```

---

### Task 7: `write_search_index.py` — digisearch sink

**Files:**
- Create: `scripts/docs_onboard/write_search_index.py`
- Create: `tests/scripts/docs_onboard/test_write_search_index.py`

**Interfaces:**
- Consumes: workdir HTML exports + `assets/` PDFs; digisearch URL + digikey token (same pattern as `scripts/seed_digisearch_local.py`).
- Produces: `write_search_index(manifest, workspace, *, digisearch_url, token, post_ingest=...) -> int`.
- Each `POST /ingest` body:

```python
{
  "source": str(local_path),           # server-visible path
  "index_name": manifest.digisearch_index,
  "doc_type": "html" | "pdf",
  "metadata": {
    "source_url": "...",
    "client": manifest.client,
    "page_class": "docs" | "pdf",
  },
}
```

**Path constraint:** When digisearch runs in Docker, local host paths are not visible. MVP documents two operator modes:

1. **Host digisearch** (`make stack-local`): workdir on host; `source` is host path.
2. **Compose digisearch:** mount workdir into the digisearch container (e.g. `/data/onboard`) and pass `--source-prefix /data/onboard` so posted paths match the container filesystem (mirror `DIGISEARCH_SEED_REMOTE_PREFIX` pattern).

Tests inject `post_ingest(payload) -> dict` — no network.

- [ ] **Step 1: Failing test**

```python
@pytest.mark.unit
def test_write_search_index_posts_metadata(tmp_path: Path) -> None:
    posted: list[dict] = []

    def post_ingest(payload: dict) -> dict:
        posted.append(payload)
        return {"doc_id": "x", "chunks_created": 1, "index_name": payload["index_name"], "status": "ok"}

    # seed workspace with one docs html file + source_map; call write_search_index
    assert posted[0]["metadata"]["source_url"].startswith("https://")
    assert posted[0]["index_name"] == "example_docs"
```

- [ ] **Step 2: Implement + commit**

```bash
pytest tests/scripts/docs_onboard/test_write_search_index.py -v
git commit -m "$(cat <<'EOF'
feat(scripts): docs_onboard write_search_index digisearch sink

Optional vector index sink posts local paths with source_url metadata.
EOF
)"
```

OCR: scanned PDFs are handled **inside digisearch** when `DIGISEARCH_OCR_ENABLED=true` and `digisearch[ocr]` is installed — do not reimplement OCR in scripts.

---

### Task 8: `run_onboard.py` — parent orchestrator

**Files:**
- Create: `scripts/docs_onboard/run_onboard.py`
- Create: `tests/scripts/docs_onboard/test_run_onboard.py`

**Interfaces:**
- Consumes: `--manifest`, `--workdir`, `--vault-root`, `--sinks` (override), digisearch auth env.
- Produces: `OnboardResult` printed as JSON; exit `0` on success, `2` if any sink errors.

Pipeline order:

```text
scrape_site → classify_pages → fetch_docs → [write_vault_notes?] → [write_search_index?]
```

- [ ] **Step 1: Failing integration-style unit test with all leaves injected / monkeypatched**

Assert order of calls and that `skip` pages never reach vault writer.

- [ ] **Step 2: Implement argparse CLI**

```bash
python scripts/docs_onboard/run_onboard.py \
  --manifest docs/projects/example-docs-client/onboard.yaml \
  --workdir /tmp/example-onboard \
  --vault-root "${DIGIVAULT_ROOT:-/tmp/demo-vault}" \
  --sinks vault,search \
  --digisearch-url "${DIGISEARCH_URL:-http://127.0.0.1:8002}" \
  --digikey-url "${DIGIKEY_URL:-http://127.0.0.1:8005}" \
  --api-key "${DIGISEARCH_SEED_API_KEY}"
```

- [ ] **Step 3: Tests + commit**

```bash
pytest tests/scripts/docs_onboard/ -v
git commit -m "$(cat <<'EOF'
feat(scripts): docs_onboard run_onboard parent orchestrator

URL → docs-focused crawl → optional digivault and digisearch sinks.
EOF
)"
```

---

### Task 9: Ops index, runbook, fit-doc Pick 3 rewrite

**Files:**
- Create: `docs/ops/CLIENT_PIPELINES.md`
- Create: `docs/digichat/CLIENT-DOCS-ONBOARD.md`
- Modify: `docs/architecture/digichat-self-host-picks-fit.md` (Pick 3 rows/sections — remove digicorpus framing)
- Modify: `docs/architecture/digichat-self-hosted-release.md` (§5 follow-up → link this plan + CLIENT-DOCS-ONBOARD)
- Modify: `docs/digichat/INSTALL.md` (short “Populate client docs” pointer)
- Modify: `docs/architecture/digichat-modular-frontend.md` §5 Later bullet — link CLIENT-DOCS-ONBOARD

**Interfaces:**
- Consumes: Tasks 1–8 behaviors.
- Produces: Operator-discoverable docs index + corrected fit synthesis.

- [x] **Step 1: Write `docs/ops/CLIENT_PIPELINES.md`**

```markdown
# Client ops pipelines

Offline, multi-client workflows that live under `scripts/` with per-client
manifests under `docs/projects/<client>/` (or private `projects/`). These are
**not** Digi peer modules.

| Pipeline | Parent script | Purpose | Sinks |
|---|---|---|---|
| **Client docs onboard** | `scripts/docs_onboard/run_onboard.py` | Website URL → docs-focused crawl → PDFs → store | digivault and/or digisearch |
| *(later)* digiquant research ingest | TBD | Separate entry for quant research corpora | digisearch / vault as designed |

## Module roles

- **digifetch** — fetch/scrape transport
- **digisearch** — parse, OCR, chunk, embed, index
- **digivault** — notes, graph, MCP/agent over notes (local search when `DIGIVAULT_ROOT` set)

## Related

- Runbook: [`docs/digichat/CLIENT-DOCS-ONBOARD.md`](../digichat/CLIENT-DOCS-ONBOARD.md)
- Plan: [`docs/superpowers/plans/2026-08-09-digichat-corpus-ingest.md`](../superpowers/plans/2026-08-09-digichat-corpus-ingest.md)
- Fit: [`docs/architecture/digichat-self-host-picks-fit.md`](../architecture/digichat-self-host-picks-fit.md)
```

- [x] **Step 2: Write `docs/digichat/CLIENT-DOCS-ONBOARD.md`**

Cover: prerequisites; install editable digifetch/digivault/digisearch; example `run_onboard.py`; Profile A volume path; smoke via `digivault_search_notes` / digisearch query; explicit **not** a digichat fork; Pick 1/2 orthogonal; OCR via digisearch env.

- [x] **Step 3: Rewrite fit doc Pick 3 seams**

Replace digicorpus language in `digichat-self-host-picks-fit.md`:

| Location | New wording |
|---|---|
| §1 Pick 3 purpose | Offline `scripts/docs_onboard` crawl → digivault and/or digisearch for that client's docs |
| §2 diagram | `local search → docs_onboard scripts → runbook` (not digicorpus) |
| §3 `DIGIVAULT_ROOT` owner | digivault (+ docs_onboard scripts) |
| §3 volumes row | docs_onboard writes volume / notes API — offline job beside stack |
| Stage D checklist | digivault local search; scripts/docs_onboard leaves + parent; CLIENT-DOCS-ONBOARD + CLIENT_PIPELINES; Profile A smoke |

- [x] **Step 4: Commit**

```bash
git add docs/ops/CLIENT_PIPELINES.md docs/digichat/CLIENT-DOCS-ONBOARD.md \
  docs/architecture/digichat-self-host-picks-fit.md \
  docs/architecture/digichat-self-hosted-release.md \
  docs/digichat/INSTALL.md docs/architecture/digichat-modular-frontend.md
git commit -m "$(cat <<'EOF'
docs: client docs onboard runbook and ops pipeline index

Replace digicorpus-as-module framing with scripts/docs_onboard ops workflow.
EOF
)"
```

---

### Task 10 (Later — out of MVP core)

Do **not** start until Tasks 1–9 have a green client smoke.

1. **Profile A attach** — document env/Compose mounts so onboard workdir + `DIGIVAULT_ROOT` share a volume; optional one-shot service profile (not a chat-tier replica). Soft-depends Pick 2.
2. **digiquant entry** — second parent under `scripts/` (or docs_onboard sibling) for research corpora; listed in `CLIENT_PIPELINES.md`.
3. **Richer crawl** — sitemap.xml seed, robots.txt hardening, digifetch `[browser]` for JS apps, etag/content-hash skip.
4. **Image assets** — vault `_assets/` + markdown links; size-capped embeds.
5. **Remote vault writer** — `POST /v1/notes` with digikey JWT when filesystem root is unavailable.

---

## Acceptance criteria

### MVP done when

1. **No digicorpus module** — no `digicorpus/` package; no `component:digicorpus` routing.
2. **No digichat backend growth** — digichat still only `digigraph` | `foundry` adapters.
3. **Local search** — with `DIGIVAULT_ROOT` set and no Supabase, `digivault_search_notes` hits filesystem notes.
4. **Classify intelligence** — docs prefixes kept; skip prefixes excluded; PDFs fetched; source_url in vault frontmatter and digisearch metadata.
5. **Dual sink** — `--sinks vault`, `--sinks search`, and `--sinks vault,search` all work in unit tests with fakes.
6. **Parent CLI** — `run_onboard.py --manifest … --workdir …` runs the leaf chain.
7. **Docs** — `docs/ops/CLIENT_PIPELINES.md` + `docs/digichat/CLIENT-DOCS-ONBOARD.md`; fit doc Pick 3 no longer describes digicorpus-as-module.
8. **Tests** — `pytest tests/dv/test_local_search.py tests/scripts/docs_onboard -m unit` green without network.

### Explicitly out of MVP

- digicorpus peer module / PyPI package / GHCR job image named digicorpus
- digigraph live crawl tool
- digiquant pipeline entry (Task 10)
- Perfect SPA crawl / robots perfection
- Multi-tenant vault routing inside one digivault process

---

## Test plan (operator)

```bash
# 1. Unit
pip install -e ./digivault -e ./digifetch -e "./digisearch[dev]"
pytest tests/dv/test_local_search.py tests/scripts/docs_onboard -m unit -v

# 2. Local vault smoke
export DIGIVAULT_ROOT=/tmp/demo-vault
mkdir -p "$DIGIVAULT_ROOT"
python scripts/docs_onboard/run_onboard.py \
  --manifest docs/projects/example-docs-client/onboard.yaml \
  --workdir /tmp/example-onboard \
  --vault-root "$DIGIVAULT_ROOT" \
  --sinks vault \
  # use a real docs host allowlisted in a private manifest for live smoke
# start digivault with DIGIVAULT_ROOT; invoke digivault_search_notes

# 3. digisearch sink smoke (host stack)
# DIGISEARCH_SEED_API_KEY=… python scripts/docs_onboard/run_onboard.py … --sinks search

# 4. Profile A (after Pick 2) — mount same volume; ask digichat a doc question
```

---

## Self-review checklist

| Agreed requirement | Task |
|---|---|
| Offline ops workflow, not digicorpus module | Goal, Global Constraints, Tasks 2–8 |
| digifetch / digisearch / digivault role split | Module roles + Tasks 3, 5–7 |
| Code under `scripts/`; manifests under `docs/projects/` | Script tree, Task 2, Task 9 |
| Leaf scripts + parent orchestrator | Tasks 3–8 |
| Docs priority / skip / PDF scan / source URL metadata | Tasks 4–7 |
| Dual sink optional | Tasks 6–8 |
| `docs/ops/CLIENT_PIPELINES.md` | Task 9 |
| digivault local search as digivault task | Task 1 |
| Fit doc Pick 3 seams | Task 9 |
| Cross-link picks 1–2 orthogonal | Fit section + Task 9 |
| Profile A / digiquant later | Task 10 |

Placeholder scan: Task 10 is explicitly deferred with gates — not TBD inside MVP steps. Test stubs marked `...` in Tasks 5–6 must be expanded to full assertions when implementing (same patterns as Tasks 2–4).
