# DigiSearch

> RAG and retrieval for the DigiThings ecosystem — semantic search, hybrid retrieval, and pluggable vector backends.

**What it is:** DigiSearch is the centralized RAG (Retrieval-Augmented Generation) and document search layer. It handles the complete retrieval pipeline: ingestion, parsing, chunking, embedding, vector indexing, hybrid search, reranking, and result normalization. It is backend-agnostic — the same API works whether the vector store is pgvector, Chroma, Azure AI Search, Qdrant, or any other supported backend.

**The problem:** Every AI application that needs to search over documents reinvents the parsing, chunking, embedding, and retrieval stack. DigiSearch provides this as a service that any DigiThings module or client application can call, with a consistent interface regardless of the underlying vector technology.

**Key architectural insight — retrieval mode matches query type:**
Not every query needs vector search. DigiSearch selects the retrieval strategy based on what's being asked:
- "All macro research for 2026-04-19" → direct document selection (SQL query to DigiStore)
- "Macro + sector research, last 2 weeks" → metadata filter → fetch documents directly
- "Find research mentioning oil supply disruption" → filter by document type → vector search on filtered set
- "What themes appear across Q1?" → pure semantic vector search

This distinction matters: vector search is expensive and noisy when metadata filtering is sufficient. DigiSearch applies the cheapest effective strategy for each query type.

**Selective indexing (what gets indexed and what doesn't):**
Not everything in DigiStore gets indexed by DigiSearch. Specifically:
- Index: finalized research documents, strategy summaries, thesis documents, monthly rollups, Digest archives
- Do not index: raw delta patches, in-progress drafts, intermediate agent outputs
- Re-index trigger: document transitions from draft → final state in DigiStore
- Rationale: delta documents (daily patches to existing files) are not semantically distinct documents — indexing them pollutes the search space and degrades quality

**Current state (shipped):**
Parser registry (PDF, DOCX, HTML, Markdown, CSV, text with OCR fallback). 5+ chunking strategies (fixed, recursive, sentence, sliding, semantic). Azure AI Search backend (primary) + Chroma (fallback) + stub for tests. Multi-backend strategy — same code serves Azure enterprise deployments and local Chroma instances via environment config. Hybrid search with RRF (Reciprocal Rank Fusion) fusion for keyword + vector. Optional HybridSearcher for reranking.

**Pluggable backend registry:**
- pgvector: Supabase/Postgres — no extra service, good default for Supabase users
- Chroma: local, existing client deployments
- Azure AI Search: enterprise clients on Microsoft infrastructure
- Qdrant: high-performance, self-hostable, production-grade
- Weaviate: strong built-in hybrid search
- LanceDB: columnar + vector, excellent for local and embedded deployments
- Pinecone: managed serverless
- Extensible: new backends added via registry pattern — no core changes required

**Backend selection:** Config-driven. A client on Azure uses Azure AI Search. A local dev instance uses Chroma or pgvector. Same DigiSearch API regardless.

**12-month roadmap:**
- Expand backend registry to include Qdrant, Weaviate, LanceDB
- Selective indexing rules enforcement (draft/final state tracking via DigiStore)
- Index access control: read DigiKey JWT scopes and filter results by user permissions
- DigiQuant research library indexing (finalized Atlas documents)
- digithings-guide index live on digithings.ai (powers the site's chat demo)

**Open source vs. proprietary:** Entirely open. The retrieval infrastructure is commodity. Client-specific index configurations and the documents within them are private.
