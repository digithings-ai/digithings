# Corpus / ingest → digivault Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Ship a client-side corpus ingest path that turns a website crawl and PDF text into page-level digivault notes, so a self-hosted Profile A digichat → digigraph → digivault_search_notes stack can answer from **that client's** documentation — without forking digichat or growing digithings-hosted per-client backends.

**Architecture:** Ingest is a **separate offline/job package** (`digicorpus`) that writes markdown notes into the client's `DIGIVAULT_ROOT` via digivault's core `Vault` (preferred) or `POST /v1/notes` (remote). Runtime chat stays unchanged: digichat BFF → digigraph → `digivault_hub` → `digivault_search_notes`. digivault today searches Supabase FTS only; MVP therefore includes a **local filesystem search fallback** so Profile A clients without digithings' core Supabase still ground answers on ingested notes. OCR, images, and base64 embeds are Phase 2.

**Tech Stack:** Python 3.12, Pydantic v2, digivault core (`Vault.create_note`), digifetch (HTTP crawl transport), html-to-markdown (or stdlib + selective parser), pdfplumber (PDF text), digigraph `digivault_hub`, Profile A Compose (`DIGIVAULT_ROOT` volume). Optional later: pdf2image + pytesseract (OCR), image assets under vault `_assets/`.

**Spec input:** [`docs/architecture/digichat-modular-frontend.md`](../../architecture/digichat-modular-frontend.md) §5; [`docs/architecture/digichat-self-hosted-release.md`](../../architecture/digichat-self-hosted-release.md) (corpus listed as open Follow-up). digivault reference: [`digivault/ARCHITECTURE.md`](../../../digivault/ARCHITECTURE.md), [`digivault/AGENTS.md`](../../../digivault/AGENTS.md). digigraph hub: `digigraph/src/digigraph/vertical_orchestrator/digivault_hub.py`.

## Global Constraints

- Digi module names are always lowercase in prose (`digichat`, `digigraph`, `digikey`, `digivault`, `digicorpus`, `digifetch`, `digithings`) — never DigiChat / DigiVault.
- **Do not design or ship a digichat fork.** digichat stays the modular frontend + BFF; corpus work never lands under `frontend/digichat/` as a second app.
- digichat does **not** grow per-client backends. Ingest runs in the **client's** environment (or as a one-shot job digithings helps them run against **their** vault).
- digivault / digisearch are **not** digichat HTTP backends — they are digigraph tools (`digivault_hub` → digivault `:8004`).
- digivault core hard deps stay `pydantic` + `pyyaml` only. Crawl/PDF/OCR deps must **not** enter digivault core; they live in `digicorpus` (and digivault `[service]` only if a thin local-search helper needs nothing heavier than stdlib).
- Polars only if tabular work appears (unlikely for MVP). No pandas.
- Pydantic v2 models everywhere — no bare dicts on public surfaces.
- Never touch live-trading paths.
- Every shipping PR links a GitHub Issue (`task/<N>-slug` or `Fixes #<N>`).
- Human gate if adding new network-capable hard deps to digivault core (prefer extras / new package).

---

## Fit with picks 1–2

| Pick | What it delivers | Seam with this plan (corpus) |
|---|---|---|
| **Pick 1 — embed any parent** | Stock digichat GHCR works for arbitrary parent hosts (runtime CSP `frame-ancestors` / tenant-driven hosts) so a client's product site can iframe the same digichat release. | Corpus does **not** change embed CSP or `DIGICHAT_EMBED_TENANTS`. Client wires parent host + token + `backend.type: digigraph`; ingested vault content is what the agent retrieves. No digichat code required for ingest. |
| **Pick 2 — GHCR / Profile A stack** | Client pulls digichat (+ eventually digikey/digigraph/digivault images) and runs Profile A: digichat → digigraph → digivault. | Corpus writes into the **same** `DIGIVAULT_ROOT` volume Profile A mounts. Runtime path is already `digivault_search_notes` via `digivault_hub`. digicorpus is a **job/CLI beside** the stack, not a new digichat service and not a Compose service that must scale with chat RPS. |
| **Pick 3 — this plan** | Crawl / PDF → page notes in **their** digivault; same digichat release. | Depends on Pick 2's Profile A having digivault reachable and `DIGIVAULT_URL` set on digigraph. Benefits from Pick 1 so the parent site can embed that install. |

```text
Pick 1: parent site ──iframe──► digichat (stock release)
Pick 2: digichat ──► digigraph ──digivault_hub──► digivault :8004
Pick 3: digicorpus job ──writes──► DIGIVAULT_ROOT ──(search)──► digivault_search_notes
```

**Non-seams (do not couple):** digicorpus must not import digichat Node/TS; digichat must not call digicorpus; digigraph must not grow crawl tools in MVP (ingest stays offline).

---

## Component ownership

| Piece | Owner | Rationale |
|---|---|---|
| Crawl / PDF extract / note shaping / CLI | **New package `digicorpus/`** | Heavy optional deps; client-run job; keeps digivault core FastAPI-free and dep-light. Mirrors digifetch / digiskills library shape. |
| Note persistence semantics | **digivault core** (`Vault.create_note`, frontmatter, `_safe_path`) | Already owns vault layout; ingest must not invent a second note format. |
| HTTP note API (optional remote write) | **digivault service** `POST /v1/notes` (`digivault:write`) | When vault is only reachable over the stack network. |
| Chat-time retrieval | **digivault** `digivault_search_notes` + **digigraph** `digivault_hub` | Unchanged tool name; add **local FTS/keyword fallback** so client vaults work without digithings Supabase. |
| digichat | **No changes for MVP** | Activity mapper for `digivault_search_notes` already exists under `adapters/digithings/activity/`. |
| digisearch | **Out of MVP path** | Do not require digisearch for doc chatbots. May **copy patterns** from `digisearch/ingestion/parsers/pdf.py` (pdfplumber → OCR) into digicorpus — do **not** import digisearch from digicorpus. |
| digifetch | **Transport only** | digicorpus composes digifetch HTTP fetch/retry/ratelimit for crawl; site-specific URL policy stays in digicorpus. |

**Rejected alternatives**

- ❌ Scripts dumped only under `digivault/scripts/` with pdfplumber/OCR deps — pollutes digivault packaging and AGENTS import-cost rules.
- ❌ digichat API route that crawls on demand — grows digichat backends; violates §5 hard rule.
- ❌ digigraph tool `corpus_ingest` in MVP — mixes online orchestration with long batch jobs; rate limits and timeouts fight crawls.

---

## Critical gap (must fix for end-to-end MVP)

Today `digivault_search_notes` **bypasses `DIGIVAULT_ROOT`** and queries Supabase FTS (`SupabaseStore.search` / `search_architecture_notes`). Profile A clients writing notes to a local volume would **ingest successfully but chat would not see them** unless they also run digithings' core Supabase mirror.

**MVP fix:** When `DIGIVAULT_ROOT` is set, `digivault_search_notes` searches the local vault (simple ranked keyword / title+body scan is enough for v1). Prefer local when root is configured; keep Supabase path when root is unset and Supabase creds exist (digithings.ai reference install). Document the precedence in `digivault/ARCHITECTURE.md`.

---

## MVP vs later split

### MVP (ship first — working client doc chatbot)

1. Local filesystem backend for `digivault_search_notes` (gap above).
2. `digicorpus` package scaffold + note writer (idempotent upsert by stable note name).
3. Website crawl (same-origin allowlist, depth/limit caps) → one markdown note per HTML page.
4. PDF text extract (pdfplumber / pymupdf) → one note per PDF **page** (or per doc with page markers if page count is huge — default **per page**).
5. Frontmatter contract: `title`, `tags`, `source_url` / `source_path`, `ingested_at`, `content_type`.
6. CLI: `digicorpus crawl …` and `digicorpus pdf …` writing into `--vault-root` (or `DIGIVAULT_ROOT`).
7. Operator runbook: run ingest against Profile A volume; smoke digigraph tool search.
8. Unit tests with `tmp_path` fixtures — no live network in CI.

### Later (Phase 2 — images / OCR / richness)

1. OCR fallback for scanned PDFs (`digicorpus[ocr]` → pdf2image + pytesseract), patterned after digisearch's gated OCR.
2. Image extraction from HTML/PDF → vault `_assets/<note>/…` plus markdown image links; base64 embeds only when asset files are impractical (size-capped).
3. Incremental re-crawl (etag / content-hash skip), sitemap.xml seed, robots.txt respect hardening.
4. Optional `POST /v1/notes` batch writer with digikey JWT for remote vaults.
5. Optional sync job to Supabase for digithings' own mirrored vault (not required for clients).
6. Helm/k8s CronJob example beside Compose.

---

## File structure

| File | Responsibility |
|---|---|
| `digicorpus/pyproject.toml` | Package metadata; deps: pydantic, digivault (path/editable), digifetch; extras: `pdf`, `ocr`, `dev` |
| `digicorpus/ARCHITECTURE.md` | Module map, note frontmatter contract, CLI, non-goals |
| `digicorpus/AGENTS.md` | Pre-flight, anti-patterns (no digichat imports, no digisearch imports) |
| `digicorpus/src/digicorpus/models.py` | Pydantic: `IngestSource`, `PageDocument`, `IngestResult`, `IngestConfig` |
| `digicorpus/src/digicorpus/note_writer.py` | Map `PageDocument` → vault note name + frontmatter + body; create/overwrite via `Vault` |
| `digicorpus/src/digicorpus/naming.py` | Stable slug from URL or PDF path+page (filesystem-safe, unique) |
| `digicorpus/src/digicorpus/html_extract.py` | HTML bytes → title + main text markdown (boilerplate strip) |
| `digicorpus/src/digicorpus/crawl.py` | BFS crawl using digifetch; allowlist host; depth/page caps |
| `digicorpus/src/digicorpus/pdf_text.py` | PDF bytes → list of page texts (pdfplumber; optional pymupdf) |
| `digicorpus/src/digicorpus/cli.py` | Typer CLI entrypoints |
| `digicorpus/tests/` | Unit tests (`tmp_path`, fake HTML/PDF fixtures) |
| `digivault/src/digivault/local_search.py` | Ranked keyword search over filesystem vault notes |
| `digivault/src/digivault/server.py` | `digivault_search_notes` precedence: local root → else Supabase |
| `digivault/src/digivault/orchestrator_tools.py` | Update tool description (local vault and/or Supabase) |
| `digivault/ARCHITECTURE.md` | Document search precedence |
| `docs/digichat/CORPUS-INGEST.md` | Client operator runbook (Profile A volume + digicorpus CLI) |
| `docs/architecture/digichat-self-hosted-release.md` | Mark corpus Follow-up addressed / link plan |
| `tests/dv/test_local_search.py` | digivault local search unit tests |
| `scripts/project_routing.json` / `scripts/ci_paths.yaml` | Register `digicorpus` when package lands (follow digifetch precedent) |

---

### Task 1: digivault local search for `digivault_search_notes`

**Files:**
- Create: `digivault/src/digivault/local_search.py`
- Create: `tests/dv/test_local_search.py`
- Modify: `digivault/src/digivault/server.py` (orchestrator_invoke branch for `TOOL_VAULT_SEARCH_NOTES`)
- Modify: `digivault/src/digivault/orchestrator_tools.py` (tool description)
- Modify: `digivault/ARCHITECTURE.md` (search precedence)
- Modify: `tests/dv/test_server.py` (keep Supabase tests; add local-root path)

**Interfaces:**
- Consumes: `Vault` note index + note file bodies under `DIGIVAULT_ROOT`; existing `VaultSearchHit` shape from `supabase_store.py` (reuse so digigraph/tool callers see the same hit schema).
- Produces: `search_local_vault(vault: Vault, query: str, *, limit: int) -> list[VaultSearchHit]` used by `orchestrator_invoke` when `DIGIVAULT_ROOT` is set.

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
Expected: FAIL with `ModuleNotFoundError: digivault.local_search` (or import error).

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
        tags = tuple(note.tags)
        scored.append(
            VaultSearchHit(
                vault_path=note.rel_path,
                title=title,
                note_type="local",
                summary=(body.strip().split("\n") or [""])[0][:240],
                body_markdown=body,
                tags=tags,
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
            hits = search_local_vault(_open_vault(), query, limit=limit)
        else:
            hits = _open_supabase_store().search(query, limit=limit)
        data = {"hits": [h.model_dump(mode="json") for h in hits]}
        return OrchestratorInvokeResponse(ok=True, tool=tool, data=data)
```

Update `orchestrator_tools.py` description to say: searches the configured local vault (`DIGIVAULT_ROOT`) when set; otherwise Supabase FTS when credentials exist.

- [ ] **Step 5: Run tests**

Run:

```bash
pytest tests/dv/test_local_search.py tests/dv/test_server.py -m unit -v
ruff check digivault/src/digivault/local_search.py digivault/src/digivault/server.py
```

Expected: PASS; existing Supabase fakes still pass when `DIGIVAULT_ROOT` unset.

- [ ] **Step 6: Commit**

```bash
git add digivault/src/digivault/local_search.py digivault/src/digivault/server.py \
  digivault/src/digivault/orchestrator_tools.py digivault/ARCHITECTURE.md \
  tests/dv/test_local_search.py tests/dv/test_server.py
git commit -m "$(cat <<'EOF'
feat(digivault): local filesystem search for digivault_search_notes

Profile A client vaults under DIGIVAULT_ROOT become searchable without
digithings core Supabase, unblocking corpus ingest → chat grounding.
EOF
)"
```

---

### Task 2: `digicorpus` package scaffold + note writer

**Files:**
- Create: `digicorpus/pyproject.toml`
- Create: `digicorpus/ARCHITECTURE.md`
- Create: `digicorpus/AGENTS.md`
- Create: `digicorpus/src/digicorpus/__init__.py`
- Create: `digicorpus/src/digicorpus/models.py`
- Create: `digicorpus/src/digicorpus/naming.py`
- Create: `digicorpus/src/digicorpus/note_writer.py`
- Create: `digicorpus/tests/test_note_writer.py`

**Interfaces:**
- Consumes: `digivault.Vault.create_note` / overwrite path (see Step 3 — upsert).
- Produces: `write_page(vault: Vault, doc: PageDocument, *, subdir: str = "corpus") -> Note` and `slug_for_url(url: str) -> str`.

- [ ] **Step 1: Write failing tests for naming + writer**

```python
# digicorpus/tests/test_note_writer.py
from __future__ import annotations

from pathlib import Path

import pytest
from digivault.vault import Vault

from digicorpus.models import PageDocument
from digicorpus.naming import slug_for_url
from digicorpus.note_writer import write_page


@pytest.mark.unit
def test_slug_for_url_stable() -> None:
    assert slug_for_url("https://docs.example.com/guides/Start/") == slug_for_url(
        "https://docs.example.com/guides/Start"
    )
    assert "/" not in slug_for_url("https://docs.example.com/a/b")


@pytest.mark.unit
def test_write_page_creates_markdown_note(tmp_path: Path) -> None:
    vault = Vault(tmp_path)
    doc = PageDocument(
        source_url="https://docs.example.com/guides/start",
        title="Getting started",
        body_markdown="Install the agent.\n\nSee next steps.",
        content_type="text/html",
        tags=("corpus", "web"),
    )
    note = write_page(vault, doc, subdir="corpus")
    assert note.name
    path = tmp_path / note.rel_path
    text = path.read_text(encoding="utf-8")
    assert "Getting started" in text
    assert "source_url: https://docs.example.com/guides/start" in text
    assert "Install the agent" in text
```

- [ ] **Step 2: Run to verify fail**

Run: `pytest digicorpus/tests/test_note_writer.py -v`  
Expected: FAIL (package missing).

- [ ] **Step 3: Implement models, naming, writer**

`PageDocument` fields (Pydantic v2): `source_url: str | None`, `source_path: str | None`, `title: str`, `body_markdown: str`, `content_type: str`, `tags: tuple[str, ...] = ()`, `page_number: int | None = None`.

`slug_for_url`: lowercase host+path, strip trailing slash, replace non-alnum with `-`, collapse dashes, max length ~80, prefix `web-`.

`slug_for_pdf(path: str, page: int) -> str`: `pdf-<stem>-p{page:04d}` sanitized.

`write_page`: build frontmatter `title`, `tags`, `source_url`/`source_path`, `content_type`, `ingested_at` (UTC ISO), optional `page`; body = markdown. If note exists, overwrite file via safe path + `reindex` (add `Vault.upsert_note` **or** delete+create in digicorpus using path write through a small helper that still goes through `_safe_path` — prefer adding `Vault.write_note(name, *, frontmatter, body, subdir, overwrite=True)` in digivault if missing; keep sandbox guarantees).

If digivault lacks overwrite, add a focused digivault helper in the same PR:

```python
def write_note(
    self,
    name: str,
    *,
    frontmatter: dict[str, Any] | None = None,
    body: str = "",
    subdir: str = "",
    overwrite: bool = False,
) -> Note:
    ...
```

- [ ] **Step 4: Scaffold `pyproject.toml`**

```toml
[project]
name = "digicorpus"
version = "0.1.0"
description = "digicorpus – crawl/PDF ingest into digivault notes for client documentation chatbots"
requires-python = ">=3.12"
dependencies = [
  "pydantic>=2",
  # digivault + digifetch installed editable from monorepo in CI / workspace
]

[project.optional-dependencies]
pdf = ["pdfplumber>=0.11"]
ocr = ["pdfplumber>=0.11", "pdf2image>=1.17", "pytesseract>=0.3"]
dev = ["pytest>=8,<10", "ruff>=0.16,<0.17"]

[project.scripts]
digicorpus = "digicorpus.cli:app"
```

Document in ARCHITECTURE: install via `pip install -e ./digicorpus -e ./digivault -e ./digifetch`.

- [ ] **Step 5: Run tests + commit**

```bash
pip install -e ./digivault -e ./digicorpus
pytest digicorpus/tests/test_note_writer.py -v
git add digicorpus digivault/src/digivault/vault.py  # if write_note added
git commit -m "$(cat <<'EOF'
feat(digicorpus): scaffold package and vault note writer

Client documentation ingest writes page-level digivault notes without
touching digichat.
EOF
)"
```

---

### Task 3: HTML crawl → page notes (MVP)

**Files:**
- Create: `digicorpus/src/digicorpus/html_extract.py`
- Create: `digicorpus/src/digicorpus/crawl.py`
- Create: `digicorpus/src/digicorpus/cli.py` (crawl command)
- Create: `digicorpus/tests/test_html_extract.py`
- Create: `digicorpus/tests/test_crawl.py`
- Create: `digicorpus/tests/fixtures/sample.html`

**Interfaces:**
- Consumes: digifetch HTTP fetch (sync); `write_page`; `IngestConfig(max_pages: int, max_depth: int, allowed_hosts: tuple[str, ...])`.
- Produces: `crawl_site(start_url: str, vault: Vault, config: IngestConfig) -> IngestResult` with `notes_written: int`, `urls_seen: int`, `errors: list[str]`.

- [ ] **Step 1: Failing extract test**

```python
# digicorpus/tests/test_html_extract.py
from digicorpus.html_extract import html_to_page

SAMPLE = b"""<!doctype html><html><head><title>Acme Docs</title></head>
<body><nav>Ignore</nav><main><h1>Acme Docs</h1><p>Ship agents safely.</p></main></body></html>"""


def test_html_to_page_prefers_main() -> None:
    doc = html_to_page(SAMPLE, source_url="https://docs.acme.test/index")
    assert "Ship agents safely" in doc.body_markdown
    assert "Acme" in doc.title
```

- [ ] **Step 2: Implement extract (stdlib `html.parser` first; avoid BeautifulSoup unless needed)**

Keep MVP extraction simple: title from `<title>` / first `h1`; body text from `<main>` else `<article>` else `<body>`; strip `script`/`style`/`nav`; emit paragraphs as markdown lines.

- [ ] **Step 3: Crawl with caps + allowlist**

BFS from `start_url`; only enqueue links whose host is in `allowed_hosts` (default: start URL host); skip non-http(s); stop at `max_pages` / `max_depth`; use digifetch fetcher with injectable transport in tests (pass `fetch: Callable[[str], bytes]`).

- [ ] **Step 4: CLI**

```bash
digicorpus crawl https://docs.example.com \
  --vault-root /data/vault \
  --max-pages 200 \
  --max-depth 3 \
  --subdir corpus/web
```

- [ ] **Step 5: Tests + commit**

```bash
pytest digicorpus/tests/test_html_extract.py digicorpus/tests/test_crawl.py -v
git commit -m "feat(digicorpus): crawl HTML sites into digivault page notes"
```

---

### Task 4: PDF text → page notes (MVP)

**Files:**
- Create: `digicorpus/src/digicorpus/pdf_text.py`
- Create: `digicorpus/tests/test_pdf_text.py`
- Create: `digicorpus/tests/fixtures/hello.pdf` (tiny text PDF checked in or generated in test)
- Modify: `digicorpus/src/digicorpus/cli.py` (`pdf` command)
- Modify: `digicorpus/pyproject.toml` (`[pdf]` extra)

**Interfaces:**
- Consumes: PDF bytes; `write_page` with `page_number` and `source_path`.
- Produces: `ingest_pdf(path: Path, vault: Vault, *, subdir: str = "corpus/pdf") -> IngestResult`.

- [ ] **Step 1: Failing test with generated PDF**

Prefer generating a one-page PDF in the test with a minimal writer **or** skip-if-no-pdfplumber and use a checked-in fixture. Assert page-1 note body contains known string.

- [ ] **Step 2: Implement pdfplumber extraction**

```python
def extract_pdf_pages(raw: bytes) -> list[str]:
    import pdfplumber
    import io
    pages: list[str] = []
    with pdfplumber.open(io.BytesIO(raw)) as pdf:
        for page in pdf.pages:
            pages.append(page.extract_text() or "")
    return pages
```

One `PageDocument` per page; title `"{filename} (p. N)"`; tag `corpus`, `pdf`.

- [ ] **Step 3: CLI**

```bash
digicorpus pdf ./manual.pdf --vault-root /data/vault --subdir corpus/pdf
```

- [ ] **Step 4: Tests + commit**

```bash
pip install -e "./digicorpus[pdf]"
pytest digicorpus/tests/test_pdf_text.py -v
git commit -m "feat(digicorpus): ingest PDF text pages into digivault notes"
```

---

### Task 5: Operator runbook + architecture links (MVP acceptance docs)

**Files:**
- Create: `docs/digichat/CORPUS-INGEST.md`
- Modify: `docs/architecture/digichat-self-hosted-release.md` (§5 Follow-ups — mark corpus in progress / link this plan)
- Modify: `docs/architecture/digichat-modular-frontend.md` §5 Later bullet — link CORPUS-INGEST.md
- Modify: `docs/digichat/INSTALL.md` (short “Populate the vault” pointer)
- Modify: `infra/digichat-release/README.md` (optional one-liner: ingest is offline digicorpus)

**Interfaces:**
- Consumes: Profile A Compose `DIGIVAULT_ROOT` volume path; digikey scopes for live API writes (document only).
- Produces: Documented smoke path end-to-end.

- [ ] **Step 1: Write `docs/digichat/CORPUS-INGEST.md`** with:

1. Prerequisites: Profile A up; `DIGIVAULT_URL` on digigraph; vault volume mounted.
2. Install digicorpus editable from monorepo (or future GHCR job image — later).
3. Example crawl + PDF commands writing into the Compose volume path.
4. Smoke: `curl` digivault orchestrator_invoke `digivault_search_notes` with a known phrase from ingested page **or** digichat embed question expecting that phrase.
5. Explicit: **not** a digichat fork; digichat unchanged.
6. Explicit: OCR/images = Phase 2.

- [ ] **Step 2: Link from modular-frontend §5 and self-hosted-release Follow-ups**

- [ ] **Step 3: Commit**

```bash
git commit -m "docs(digichat): corpus ingest runbook for Profile A digivault"
```

---

### Task 6 (Later): OCR + images + base64

**Files (when started):**
- `digicorpus/src/digicorpus/pdf_ocr.py`
- `digicorpus/src/digicorpus/assets.py`
- `digicorpus/tests/test_pdf_ocr.py`
- Update `CORPUS-INGEST.md` Phase 2 section

**Acceptance for this task only when scheduled:**

- [ ] Scanned PDF with no text layer yields OCR text when `digicorpus[ocr]` installed and `DIGICORPUS_OCR=1`.
- [ ] HTML `<img>` / PDF images saved under `DIGIVAULT_ROOT/_assets/<note-slug>/` with relative markdown links.
- [ ] Base64 data-URI embeds allowed only below a documented byte cap (e.g. 100 KiB); larger assets must be files.
- [ ] digivault core still has no OCR deps.

Do **not** start Task 6 until Tasks 1–5 are merged and a client smoke has validated text-only ingest.

---

### Task 7 (Later): CI registration + optional HTTP writer

**Files:**
- `scripts/ci_paths.yaml`, `.github/workflows/test-digicorpus.yml`, `scripts/project_routing.json` (`component:digicorpus` → `develop`)
- Optional: `digicorpus/src/digicorpus/http_writer.py` posting `CreateNoteRequest` to digivault with digikey JWT

Only after MVP package is stable.

---

## Acceptance criteria

### MVP done when

1. **No digichat fork / no digichat backend growth** — diff has no new digichat HTTP backend types; digichat still only `digigraph` | `foundry`.
2. **Local search works** — with `DIGIVAULT_ROOT` set and no Supabase env, `digivault_search_notes` returns hits from filesystem notes.
3. **Crawl ingest** — `digicorpus crawl <url> --vault-root <tmp>` writes ≥1 note with `source_url` frontmatter; re-run is idempotent (same slug overwritten).
4. **PDF ingest** — `digicorpus pdf <file> --vault-root <tmp>` writes one note per text page.
5. **Runtime path unchanged** — digichat → digigraph → `digivault_hub` → `digivault_search_notes` retrieves an ingested phrase in a Profile A smoke (manual or documented curl).
6. **Ownership clean** — crawl/PDF deps live in `digicorpus`; digivault core remains pydantic+pyyaml.
7. **Docs** — `docs/digichat/CORPUS-INGEST.md` exists and is linked from modular-frontend §5 / self-hosted-release.
8. **Tests** — `pytest tests/dv/test_local_search.py digicorpus/tests -m unit` green without network.

### Explicitly out of MVP

- OCR / image assets / base64 embeds
- digisearch requirement for doc chatbots
- Publishing digicorpus to PyPI / GHCR job image
- robots.txt perfection, JS-rendered SPA crawl (Playwright crawl can follow via digifetch `[browser]` later)
- Multi-tenant vault routing inside one digivault process

---

## Test plan (operator)

```bash
# 1. Unit
pip install -e ./digivault -e ./digifetch -e "./digicorpus[pdf,dev]"
pytest tests/dv/test_local_search.py digicorpus/tests -m unit -v

# 2. Local vault search smoke
export DIGIVAULT_ROOT=/tmp/demo-vault
digivault init --root "$DIGIVAULT_ROOT"   # or mkdir + .digivault.yml
digicorpus crawl https://example.com --vault-root "$DIGIVAULT_ROOT" --max-pages 3
# start digivault with DIGIVAULT_ROOT; invoke digivault_search_notes for a known word

# 3. Profile A (Compose) — after Pick 2 overlays exist
# mount same volume digivault uses; run digicorpus against that path; ask digichat a doc question
```

---

## Self-review checklist

| Spec / product claim | Task |
|---|---|
| Ingest separate from digichat; not a digichat fork | Ownership + Tasks 2–5; acceptance #1 |
| Crawl site / PDFs → page-level digivault notes | Tasks 3–4 |
| Images + OCR + base64 later | Task 6 |
| Runtime digichat → digigraph → digivault_search | Task 1 + acceptance #5 |
| Profile A self-hosted client vault | Tasks 1, 5; Fit with picks 1–2 |
| digithings does not host multi-client digichat | Global constraints + Fit section |
| Supabase-only search gap for clients | Task 1 |

Placeholder scan: none intentional — Phase 2 tasks are explicit deferred work with acceptance gates, not TBD stubs inside MVP steps.
