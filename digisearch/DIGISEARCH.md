# DigiSearch

**Module:** `digisearch`
**Purpose:** All RAG, vectorization, document ingestion, and search functionality across the Digi ecosystem.
**Exposes:** `DigiSearch` client, `DigiIndex` interface, `DigiDocument`, `DigiChunk`, and MCP server tooling for use by DigiFlow and DigiGraph.

**Integration status**
- **Docker:** `digisearch` service (HTTP API on 8002) in `docker-compose.yml`. MCP server: `docker compose --profile digisearch-mcp up`.
- **DigiGraph:** Wired via `DIGISEARCH_URL`; research node optionally augments with document context when available.
- **DigiFlow:** Point Langflow at `http://digisearch:8002` (HTTP) or MCP server at `http://127.0.0.1:8765/mcp`.

---

## Table of Contents

1. [Overview](#overview)
2. [Architecture](#architecture)
3. [Folder Structure](#folder-structure)
4. [Core Models](#core-models)
5. [Ingestion & Parsing](#ingestion--parsing)
6. [OCR](#ocr)
7. [Chunking](#chunking)
8. [Embedding](#embedding)
9. [Index Backends](#index-backends)
10. [Search & Retrieval](#search--retrieval)
11. [Integrations](#integrations)
12. [Configuration](#configuration)
13. [Naming Conventions](#naming-conventions)
14. [Build Phases](#build-phases)

---

## Overview

DigiSearch is the centralized search and retrieval module for the Digi ecosystem. It handles the full RAG pipeline from raw document ingestion through chunking, embedding, indexing, and multi-modal search. It is designed to be backend-agnostic — swapping embedding providers, vector databases, or search strategies should never require changes outside of configuration.

DigiSearch is consumed primarily by:
- **DigiFlow** (Langflow-based) — via importable Python API or REST
- **DigiGraph** (LangGraph-based) — via importable Python API or MCP tools
- **CLI** — for scripting, pipelines, and local development

---

## Architecture

```
                        ┌─────────────────────────────────┐
                        │          DigiSearch              │
                        │         (public client)          │
                        └────────────────┬────────────────┘
                                         │
          ┌──────────────────────────────┼──────────────────────────────┐
          │                              │                              │
  ┌───────▼───────┐            ┌─────────▼────────┐          ┌────────▼───────┐
  │   Ingestion   │            │    Embedding     │          │     Search     │
  │  parsers/ocr/ │──►Chunks──►│   providers/     │──►Vecs──►│ keyword/vector │
  │   chunkers/   │            │   cache/batch    │          │ hybrid/rerank  │
  └───────────────┘            └──────────────────┘          └────────┬───────┘
                                                                       │
                                                              ┌────────▼───────┐
                                                              │  Index Backends│
                                                              │ chroma/azure/  │
                                                              │ opensearch/... │
                                                              └────────────────┘
                                                                       │
                              ┌────────────────────────────────────────┤
                              │                    │                   │
                     ┌────────▼──────┐   ┌─────────▼──────┐  ┌───────▼───────┐
                     │  MCP Server   │   │      CLI        │  │   REST API    │
                     │ (DigiFlow /   │   │ digisearch ...  │  │  (FastAPI)    │
                     │  DigiGraph)   │   └─────────────────┘  └───────────────┘
                     └───────────────┘
```

---

## Folder Structure

```
digisearch/
│
├── __init__.py                 # Exports DigiSearch, DigiIndex, DigiDocument, DigiChunk
│
├── core/
│   ├── models.py               # DigiDocument, DigiChunk, DigiQuery, DigiResult (shared contracts)
│   └── config.py               # DigiSearchConfig, provider config loaders, env handling
│
├── ingestion/
│   ├── base.py                 # Abstract Parser interface
│   ├── parsers/
│   │   ├── pdf.py              # PDFParser (pdfplumber / pymupdf)
│   │   ├── docx.py             # DocxParser (python-docx)
│   │   ├── html.py             # HTMLParser (beautifulsoup4)
│   │   ├── markdown.py         # MarkdownParser
│   │   ├── csv.py              # CSVParser
│   │   └── plaintext.py        # PlainTextParser
│   ├── ocr/
│   │   ├── base.py             # Abstract OCRProvider
│   │   ├── tesseract.py        # TesseractOCR
│   │   ├── azure_di.py         # AzureDocumentIntelligence
│   │   └── textract.py         # AWSTextract
│   └── chunkers/
│       ├── base.py             # Abstract Chunker
│       ├── fixed.py            # FixedSizeChunker
│       ├── sentence.py         # SentenceChunker (nltk / spacy)
│       ├── recursive.py        # RecursiveChunker (LangChain-style)
│       ├── semantic.py         # SemanticChunker (embedding-based splits)
│       └── sliding_window.py   # SlidingWindowChunker
│
├── embedding/
│   ├── base.py                 # Abstract EmbeddingProvider
│   ├── cache.py                # EmbeddingCache (sqlite or redis backed)
│   ├── batch.py                # BatchEmbedder (rate limiting, retry, concurrency)
│   └── providers/
│       ├── openai.py           # OpenAIEmbedder
│       ├── azure_openai.py     # AzureOpenAIEmbedder
│       ├── cohere.py           # CohereEmbedder
│       ├── huggingface.py      # HuggingFaceEmbedder (local sentence-transformers)
│       └── ollama.py           # OllamaEmbedder (fully local)
│
├── indexes/
│   ├── base.py                 # Abstract DigiIndex interface
│   └── backends/
│       ├── chroma.py           # ChromaBackend (local persistent + in-memory)
│       ├── faiss.py            # FAISSBackend (local)
│       ├── lancedb.py          # LanceDBBackend (local)
│       ├── azure_search.py     # AzureAISearchBackend
│       ├── opensearch.py       # OpenSearchBackend
│       ├── pinecone.py         # PineconeBackend
│       ├── weaviate.py         # WeaviateBackend
│       ├── qdrant.py           # QdrantBackend
│       ├── hipporag.py         # HippoRAGBackend (experimental)
│       └── pageindex.py        # PageIndexBackend (experimental)
│
├── search/
│   ├── keyword.py              # BM25Searcher, TFIDFSearcher
│   ├── vector.py               # VectorSearcher (ANN over embeddings)
│   ├── hybrid.py               # HybridSearcher (RRF fusion)
│   ├── reranker.py             # Reranker (cross-encoder, Cohere Rerank, BGE)
│   ├── multi_index.py          # MultiIndexSearcher (fan-out + merge)
│   └── transforms/
│       ├── query_expansion.py  # QueryExpander
│       └── hyde.py             # HyDE (Hypothetical Document Embeddings)
│
├── integrations/
│   ├── mcp_server.py           # Expose DigiIndex instances as MCP tool servers
│   ├── cli.py                  # Typer-based CLI (digisearch)
│   └── rest_api.py             # FastAPI wrapper (optional microservice mode)
│
└── tests/
    ├── test_parsers.py
    ├── test_chunkers.py
    ├── test_embedders.py
    ├── test_backends.py
    └── test_search.py
```

---

## Core Models

These are the shared data contracts. `DigiDocument` and `DigiChunk` are prefixed because they are passed between modules (DigiFlow, DigiGraph) and need to be unambiguous.

```python
# core/models.py

@dataclass
class DigiDocument:
    id: str
    content: str
    source: str                    # file path, URL, or identifier
    doc_type: str                  # "pdf", "html", "docx", etc.
    metadata: dict                 # author, timestamp, title, custom tags
    chunks: list["DigiChunk"] = field(default_factory=list)

@dataclass
class DigiChunk:
    id: str
    content: str
    doc_id: str                    # parent DigiDocument.id
    embedding: list[float] | None
    metadata: dict                 # chunk_index, page_number, section, etc.

@dataclass
class DigiQuery:
    text: str
    embedding: list[float] | None = None
    top_k: int = 10
    filters: dict = field(default_factory=dict)
    mode: str = "hybrid"           # "keyword" | "vector" | "hybrid"

@dataclass
class DigiResult:
    chunk: DigiChunk
    score: float
    source_doc: DigiDocument | None = None
    rank: int | None = None
```

---

## Ingestion & Parsing

All parsers implement the abstract `Parser` base and return a `DigiDocument`. The ingest pipeline normalizes all input formats before chunking.

**Supported input formats:**

| Parser | Library | Notes |
|---|---|---|
| `PDFParser` | `pdfplumber` / `pymupdf` | Falls back to OCR if text layer is absent |
| `DocxParser` | `python-docx` | Preserves heading structure |
| `HTMLParser` | `beautifulsoup4` | Strips nav/footer by default |
| `MarkdownParser` | `mistune` | Preserves heading metadata |
| `CSVParser` | `pandas` | Each row becomes a document or chunk |
| `PlainTextParser` | stdlib | Encoding detection via `chardet` |

```python
# Abstract interface
class Parser(ABC):
    @abstractmethod
    def parse(self, source: str | Path | bytes) -> DigiDocument:
        ...

    def can_parse(self, source: str) -> bool:
        ...
```

A `ParserRegistry` auto-selects the right parser based on file extension or MIME type.

---

## OCR

OCR runs as a preprocessing step when a parser detects a scanned or image-heavy document (e.g. a PDF with no extractable text layer). OCR providers are pluggable.

```python
class OCRProvider(ABC):
    @abstractmethod
    def extract_text(self, image: bytes | Path) -> str:
        ...
```

**Providers:**

| Class | Backend | Notes |
|---|---|---|
| `TesseractOCR` | Tesseract (local) | Good for offline/on-prem use |
| `AzureDocumentIntelligence` | Azure DI API | Best for structured/form docs |
| `AWSTextract` | AWS Textract | Good for mixed layout docs |

OCR output is passed through the normal parser pipeline — the result is still a `DigiDocument`.

---

## Chunking

All chunkers implement the abstract `Chunker` base and return a list of `DigiChunk` from a `DigiDocument`.

```python
class Chunker(ABC):
    @abstractmethod
    def chunk(self, doc: DigiDocument) -> list[DigiChunk]:
        ...
```

**Available chunkers:**

| Class | Strategy | Best For |
|---|---|---|
| `FixedSizeChunker` | Token/character count | Uniform, fast |
| `SentenceChunker` | Sentence boundaries (spacy/nltk) | Prose documents |
| `RecursiveChunker` | Hierarchical delimiter splits | Code, markdown, structured text |
| `SemanticChunker` | Embedding cosine distance splits | Dense, mixed-topic documents |
| `SlidingWindowChunker` | Overlapping fixed windows | When context continuity matters |

Chunkers are configurable via `DigiSearchConfig` (chunk size, overlap, min/max thresholds). Multiple chunkers can be composed in a pipeline.

---

## Embedding

All embedding providers implement the abstract `EmbeddingProvider` base.

```python
class EmbeddingProvider(ABC):
    @abstractmethod
    def embed(self, texts: list[str]) -> list[list[float]]:
        ...

    @property
    @abstractmethod
    def dimensions(self) -> int:
        ...
```

**Providers:**

| Class | Backend | Local? |
|---|---|---|
| `OpenAIEmbedder` | OpenAI API | No |
| `AzureOpenAIEmbedder` | Azure OpenAI API | No |
| `CohereEmbedder` | Cohere API | No |
| `HuggingFaceEmbedder` | `sentence-transformers` | Yes |
| `OllamaEmbedder` | Ollama | Yes |

**Supporting infrastructure:**

- `BatchEmbedder` — wraps any provider with batching, rate-limit handling, exponential backoff, and async concurrency
- `EmbeddingCache` — SQLite (default) or Redis-backed cache keyed on content hash. Prevents re-embedding unchanged chunks.

Multiple embedding models can be active simultaneously (e.g. one for indexing, one for query-time reranking).

---

## Index Backends

All backends implement the `DigiIndex` interface. This is the core abstraction — search code, MCP tools, and the CLI never talk to a backend directly.

```python
class DigiIndex(ABC):
    name: str
    embedding_provider: EmbeddingProvider

    @abstractmethod
    def add(self, chunks: list[DigiChunk]) -> None: ...

    @abstractmethod
    def query(self, query: DigiQuery) -> list[DigiResult]: ...

    @abstractmethod
    def delete(self, ids: list[str]) -> None: ...

    @abstractmethod
    def update(self, chunks: list[DigiChunk]) -> None: ...

    @abstractmethod
    def list_collections(self) -> list[str]: ...

    @abstractmethod
    def snapshot(self, path: str) -> None: ...
```

**Local backends:**

| Class | Backend | Notes |
|---|---|---|
| `ChromaBackend` | ChromaDB | Default local backend. Persistent or in-memory. |
| `FAISSBackend` | FAISS | Fast ANN for large local datasets |
| `LanceDBBackend` | LanceDB | Columnar storage, good for filtering |

**Cloud / hosted backends:**

| Class | Backend | Notes |
|---|---|---|
| `AzureAISearchBackend` | Azure AI Search | Supports hybrid search natively |
| `OpenSearchBackend` | OpenSearch | Self-hosted or AWS managed |
| `PineconeBackend` | Pinecone | Managed vector DB |
| `WeaviateBackend` | Weaviate | Multi-modal, graph features |
| `QdrantBackend` | Qdrant | Self-hosted or cloud, strong filtering |

**Experimental / open-source:**

| Class | Backend | Notes |
|---|---|---|
| `HippoRAGBackend` | HippoRAG | KG-augmented RAG retrieval |
| `PageIndexBackend` | PageIndex | PageRank-influenced retrieval scoring |

All backends support index lifecycle: create, upsert, delete, snapshot, and re-index.

---

## Search & Retrieval

Search is composed from modular layers. The `DigiSearch` client orchestrates them based on config and query mode.

### Keyword Search
`BM25Searcher` — BM25 scoring over an inverted index. Used standalone or as the keyword leg of hybrid search. Backed by `rank_bm25` for local indexes or delegated to native BM25 in OpenSearch/Azure.

### Vector Search
`VectorSearcher` — ANN search over embeddings via the active `DigiIndex` backend. Supports configurable `top_k`, metadata filtering, and namespace/collection scoping.

### Hybrid Search
`HybridSearcher` — Runs keyword and vector search in parallel then merges results using **Reciprocal Rank Fusion (RRF)**. Alpha weight between keyword and vector scores is configurable per query.

```
hybrid_score = (1 - alpha) * bm25_score + alpha * vector_score
```

### Re-ranking
`Reranker` — Optional second-pass cross-encoder reranker over the initial candidate set. Providers:
- `CohereReranker` — Cohere Rerank API
- `BGEReranker` — local `BAAI/bge-reranker` via HuggingFace
- `CrossEncoderReranker` — any `sentence-transformers` cross-encoder model

### Multi-Index Search
`MultiIndexSearcher` — Fans a query out to multiple `DigiIndex` instances in parallel, then merges and deduplicates results. Useful for federated search across backends or collections.

### Query Transforms (optional middleware)
Applied before the search step when configured:

- `QueryExpander` — Generates query variants to increase recall
- `HyDE` — Generates a hypothetical answer document, embeds it, and uses that embedding as the query vector. Improves semantic retrieval on sparse queries.

---

## Integrations

### MCP Server

Any configured `DigiIndex` can be exposed as an MCP tool server, making it directly callable from DigiFlow and DigiGraph agents.

```python
# integrations/mcp_server.py
from digisearch import DigiSearch

app = DigiSearch.from_config("config.yaml")
mcp = app.as_mcp_server()
mcp.run()
```

Each exposed index registers as a named MCP tool with an auto-generated JSON schema derived from `DigiQuery`. Tool names follow the pattern `digisearch_{index_name}_query`.

Multiple indexes can be exposed from a single MCP server process, or each can run as its own server for isolation.

### CLI

Built with [Typer](https://typer.tiangolo.com/). Entry point: `digisearch`.

```bash
# Ingest documents into an index
digisearch ingest --index my_index --source ./docs/ --chunker recursive

# Run a search query
digisearch query --index my_index --text "how does billing work" --mode hybrid --top-k 5

# Build or re-index from config
digisearch index build --config config.yaml

# Inspect an index
digisearch index inspect --index my_index

# Start an MCP server
digisearch serve --config config.yaml --port 8765

# Start the REST API
digisearch api --config config.yaml --port 8000
```

### REST API (optional)

FastAPI wrapper for running DigiSearch as a microservice. Useful for deployments where DigiFlow/DigiGraph are in separate processes or containers.

```
POST   /ingest
POST   /query
GET    /indexes
GET    /indexes/{name}
DELETE /indexes/{name}/documents/{id}
GET    /health
```

**POST /query** accepts optional `format: "table"`. When set, the response includes a `formatted` field with a markdown table string (Rank, Score, doc_id, metadata columns, Content) for display. Callers (e.g. DigiGraph) use this to show results without project-specific formatting logic.

**HTTP client** (`digisearch.http_client`): `query_digisearch()`, `format_results_table()`, and `search_documents()` provide a universal way to call the API and format results. All display/table logic lives here; DigiGraph and other consumers only pass base_url and query params.

---

## Configuration

DigiSearch is config-driven. Indexes, embedding providers, chunking strategies, and search behavior are all defined in a YAML or TOML file so no code changes are needed to switch backends.

```yaml
# config.yaml

embedding:
  provider: openai
  model: text-embedding-3-small
  cache: true

indexes:
  - name: docs
    backend: chroma
    persist_path: ./data/chroma
    chunker: recursive
    chunk_size: 512
    chunk_overlap: 64

  - name: contracts
    backend: azure_search
    endpoint: ${AZURE_SEARCH_ENDPOINT}
    api_key: ${AZURE_SEARCH_KEY}
    index_name: contracts-v1
    chunker: sentence

search:
  default_mode: hybrid
  hybrid_alpha: 0.6
  reranker:
    enabled: true
    provider: cohere
    top_n: 5

mcp:
  expose:
    - docs
    - contracts
  port: 8765
```

Environment variables are supported in all string values via `${VAR_NAME}` syntax. Provider credentials should always come from environment, never hardcoded.

---

## Naming Conventions

| Scope | Convention | Example |
|---|---|---|
| Public API / cross-module | `Digi` prefix | `DigiSearch`, `DigiIndex`, `DigiChunk` |
| Internal classes | Descriptive, no prefix | `ChromaBackend`, `RecursiveChunker`, `HybridSearcher` |
| CLI commands | `digisearch <verb>` | `digisearch query`, `digisearch ingest` |
| MCP tools | `digisearch_{index}_query` | `digisearch_docs_query` |
| Config keys | `snake_case` | `persist_path`, `chunk_overlap` |

The rule: if another module or end user will see the name, use the `Digi` prefix. Internal implementation details inside DigiSearch are named for what they do.

---

## Build Phases

| Phase | Scope |
|---|---|
| **1 — Core** | `DigiDocument`, `DigiChunk`, `DigiQuery`, `DigiResult` models. `ChromaBackend`. `OpenAIEmbedder`. `VectorSearcher`. End-to-end working pipeline. |
| **2 — Ingestion** | All document parsers. `RecursiveChunker` and `FixedSizeChunker`. `ParserRegistry`. Ingest pipeline. |
| **3 — Chunking & Embedding** | Remaining chunkers. `BatchEmbedder`. `EmbeddingCache`. Remaining embedding providers. |
| **4 — Hybrid Search** | `BM25Searcher`. `HybridSearcher` with RRF. `Reranker`. |
| **5 — Cloud Backends** | `AzureAISearchBackend`, `OpenSearchBackend`, `PineconeBackend`, `WeaviateBackend`, `QdrantBackend`. |
| **6 — OCR** | `TesseractOCR`, `AzureDocumentIntelligence`, `AWSTextract`. PDF fallback integration. |
| **7 — Experimental** | `HippoRAGBackend`, `PageIndexBackend`. Query transforms (`HyDE`, `QueryExpander`). `MultiIndexSearcher`. |
| **8 — MCP Server** | `as_mcp_server()`. Tool schema generation. Multi-index exposure. |
| **9 — CLI** | Full `digisearch` CLI. All verbs wired to core API. |
| **10 — REST API** | FastAPI wrapper. Health checks. Auth middleware. |

---

*DigiSearch is part of the Digi ecosystem. See also: DigiFlow (Langflow framework), DigiGraph (LangGraph framework).*