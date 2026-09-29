# Files

- [digisearch Architecture](architecture.md) - RAG design of digisearch — ingest-to-query pipeline, pluggable index backends, web_search subsystem, scheduled monitors, websets verify-and-enrich, and vertical role under digigraph.
- [digisearch Ingest and Index](ingest-and-index.md) - Ingest pipeline — parsing, chunker selection, embeddings with cache, index writes, and backend routing — plus the SSRF-guarded URL ingest path.
- [digisearch Query and Operations](query-and-operations.md) - digisearch query paths — retrieval, hybrid RRF fusion, reranker backends, web search integration, monitors API, websets API, rate limiting, MCP binding, and operations env vars.
- [digisearch Quickstart](quickstart.md) - Start digisearch, run a stub ingest and query, verify the service, use web search, exercise monitors, and run unit gates.
