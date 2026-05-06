# Optimization rubric

Default minimum: **7/10**

Score one point per criterion satisfied. This is the most project-specific rubric — some criteria apply to all projects, others only to specific stacks. Criteria that genuinely don't apply count as satisfied.

---

## Criteria

1. **No N+1 patterns** — Loops that make one HTTP call, database query, or embedding request per item are replaced with bulk/batch operations. An `O(n)` call in a loop is a red flag.

2. **No blocking I/O in async paths** — Any operation that blocks the event loop (synchronous file I/O, `requests.get`, CPU-intensive computation) is wrapped in `asyncio.to_thread` or moved to a worker queue.

3. **Caching for stable results** — Results that are expensive to compute and stable over time (auth tokens, JWKS endpoints, embedding lookups, model manifests) are cached with an appropriate TTL.

4. **Lazy evaluation for large datasets** — Data pipelines process records lazily (generators, streaming, lazy DataFrames) rather than loading everything into memory. A single `.collect()` at the end of a pipeline, not in the middle.

5. **Token / payload efficiency** — LLM prompt inputs use summaries or briefs rather than full document bodies where the full body isn't needed. Prompts are as short as they can be while still providing necessary context.

6. **Parallel-safe operations tagged** — Stateless tools and functions that can safely run in parallel are marked as such (decorator, tag, or comment). Stateful or side-effecting operations are explicitly sequential.

7. **No redundant computation** — Values that are computed once and used multiple times are stored in a variable, not recomputed. No repeated identical API calls in the same request lifecycle.

8. **Batch over sequential** — Where the downstream API or database supports batch operations, they are used. No per-item HTTP requests where a batch endpoint exists.

9. **Connection pooling used** — HTTP clients and database connections use pooling (not creating a new connection per request). Connections are not left open after use.

10. **Performance targets maintained** — If this component has defined performance targets (response time, throughput, memory), the change does not regress them. A benchmark or load test confirms this where applicable.

---

## Common fixes

| Failure | Fix |
|---|---|
| N+1 query | Use bulk insert/fetch; collect IDs and query once |
| Blocking in async | Wrap with `asyncio.to_thread`; use `aiohttp`/`httpx` async client |
| Missing cache | Add a TTL cache with `functools.lru_cache`, Redis, or equivalent |
| Full payload in prompt | Summarise or truncate before insertion; use RAG retrieval |
| Per-item API calls | Use batch endpoint; collect results and process together |
