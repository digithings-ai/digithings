# Optimization Rubric (10-point)

**Target: ≥ 7/10 to merge. < 6 blocks merge.**

Score one point per criterion you fully satisfy. This rubric has a lower bar than Security/Quality because some optimizations are context-dependent — note exceptions inline.

---

## Criteria

| # | Criterion | Points | How to Check | How to Fix |
|---|-----------|--------|-------------|-----------|
| 1 | **LiteLLM caching used** — All new LLM calls go through `digigraph/llm.py` `chat_completion()` which routes through LiteLLM; no direct `openai.chat.completions.create()` calls | 1 | Search diff for `openai.chat`, `anthropic.messages`, direct provider SDK calls | Route through `get_client()` / `chat_completion()` in `llm.py` |
| 2 | **Model mode respected** — New LLM calls use `get_model_for_mode()` to select model tier (`test`/`medium`/`best`); no hardcoded model strings (e.g. `"gpt-4o"`) except in config files | 1 | Search diff for hardcoded model strings like `"gpt-4o"`, `"claude-"`, `"qwen"` | Replace with `get_model_for_mode(mode)` lookup |
| 3 | **Polars lazy evaluation** — DataFrames created from CSV or large collections use `pl.scan_csv` / `LazyFrame`; `.collect()` only called once at the end of a pipeline | 1 | Search diff for `pl.read_csv` in hot paths; check `.collect()` call frequency | Convert to `pl.scan_csv(...).filter(...).collect()` pattern |
| 4 | **No N+1 patterns** — No loop that issues one HTTP request, one DB query, or one embedding per item; use bulk/batch endpoints where available | 1 | Look for `for item in items: requests.post(...)` or embedding per chunk | Use `BatchEmbedder`, bulk ingest endpoints, or vectorized Polars operations |
| 5 | **Embedding cache used** — New embedding calls go through `EmbeddingCache` (SQLite/Redis-backed) or `BatchEmbedder` which wraps the cache; no direct `provider.embed()` in ingestion loops | 1 | Check that new embedding calls use `batch.py` or `cache.py` wrappers | Wrap with `BatchEmbedder(provider, cache=EmbeddingCache(...))` |
| 6 | **Parallel safe tools tagged** — New orchestrator tools that are stateless and idempotent are tagged `parallel_safe` in `register_tool()`; tools with side effects are not | 1 | Check `register_tool` call for `tags={"parallel_safe"}` on new tools | Add the tag if the tool has no shared mutable state; omit it otherwise |
| 7 | **No synchronous blocking in async routes** — FastAPI route handlers do not call `time.sleep()`, synchronous file I/O, or synchronous DB operations; use `asyncio.sleep`, `aiofiles`, async DB clients | 1 | Search diff for `time.sleep`, `open(` in `async def` route handlers | Use `asyncio.to_thread()` for unavoidable blocking calls |
| 8 | **Token efficiency** — New prompt templates use the minimum context needed; no raw document bodies in prompts (use `ResearchBrief` summaries, chunk previews, or tool results); avoids repeating system prompt on every turn | 1 | Estimate token count of any new prompt vs the content's actual information density | Summarize or filter before injection; use structured outputs to reduce round trips |
| 9 | **Result caching where stable** — Expensive deterministic operations (e.g. strategy manifest fetch, JWKS fetch) are cached in-process or via LiteLLM; cache invalidation is explicit | 1 | Look for repeated `requests.get(DIGIKEY_JWKS_URL)` or `POST /v1/orchestrator_tools` in loops | Cache with `functools.lru_cache` or a TTL dict; existing JWKS caching is the pattern |
| 10 | **Backtest performance target maintained** — Changes to DigiQuant data loading or strategy execution do not degrade the 10M-row < 2s backtest target; if uncertain, run a benchmark | 1 | Run `digiquant backtest -s ema_cross -S BTC-USD -d data/BTC-USD.csv` and check elapsed time | Profile with `py-spy` or `cProfile`; revert Polars to lazy mode; avoid Python loops over rows |

---

## Examples

### Passing (Score: 9)

```python
# Lazy Polars, single collect, batch embedding
frames = [pl.scan_csv(p) for p in paths]
combined = pl.concat(frames).filter(pl.col("volume") > 0).collect()

embedder = BatchEmbedder(OpenAIEmbedder(), cache=EmbeddingCache())
vecs = embedder.embed([c.content for c in chunks])
```

### Failing (Score: 5 — criteria 3, 4, 5 fail)

```python
results = []
for chunk in chunks:
    df = pl.read_csv(chunk.source)   # eager, per chunk
    vec = embedder.embed([chunk.content])  # one embedding per chunk, no cache
    results.append((df, vec))
```

---

## Notes

- Criterion 10 only applies to DigiQuant changes. For other components, score it 1 automatically.
- Criterion 8 is subjective — use judgment. "Minimum context needed" means no full 50-page document in a prompt when a 500-char summary suffices.
