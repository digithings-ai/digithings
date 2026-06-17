# digillm v2 — LiteLLM-faithful API + decommission `digigraph.llm`

Status: **in progress** (P1). Supersedes the original #632 "thin re-export" plan.
Approved 2026-06-08. **Human-gated** (auth/credential funneling) — PRs stop at human review.

## Goal
Expose digillm's LLM client with **industry-standard (LiteLLM/OpenAI) names, params, and
return types**; migrate every `digigraph.llm` consumer to digillm; **delete
`digigraph/llm.py`**; update + re-pin twelve-x.

## Decisions
1. **Mirror LiteLLM's *interface*; keep digillm's OpenAI-SDK backend** (do NOT depend on the
   `litellm` library — digillm stays provider-agnostic via the OpenAI-compatible client +
   its own provider registry). `completion()` returns the OpenAI **`ChatCompletion`** object
   (LiteLLM-compatible shape).
2. **Renames:** `chat_completion` → **`completion`**; `chat_completion_with_tools` →
   **`run_tools`** (agentic loop — NOT a LiteLLM endpoint, deliberately kept separate, since
   OpenAI/LiteLLM also keep tool execution out of the completion endpoint).
3. **`structured_completion`** stays as a helper (calls `completion(response_format=…)`,
   parses `.choices[0].message.content`).
4. **Clean break, no compat aliases** — twelve-x is insulated (pins old SHA) until P3.
5. **Phased, each its own PR.**

## Return-type contract
- `completion(...)` → `openai.types.chat.ChatCompletion` (or a stream when `stream=True`).
  Callers read `resp.choices[0].message.content` and `.tool_calls`. This is the breaking
  change that touches every call site.
- `run_tools(...)` → **final answer `str`** (it's a loop, not an endpoint; the streamed final
  turn can't cleanly reconstruct a `ChatCompletion`). Keeps its current str contract.

## P1 — digillm v2 API  (branch: task/632; folds in the Part A streaming already committed)
`digillm/src/digillm/client.py`:
- Add `completion(model, messages, *, tools=None, tool_choice="auto", temperature=0.2,
  max_tokens=None, response_format=None, stream=False)` → `ChatCompletion`. Same internals
  as today's `chat_completion` (provider routing via `get_client_for_model`, `_create_with_retry`,
  cache) but **returns the response object** instead of extracting str/tuple. Cache stores the
  response content keyed as today (tool-free, non-BYOK only).
- Rename loop → `run_tools(...)`; internally adapt to `completion`'s object return
  (`resp.choices[0].message`), preserving `parallel_safe_tools` + `stream_deltas` (Part A).
- Keep: proxy/BYOK contextvars (`set/reset/get_proxy_key`, `set/reset/get_byok`),
  `register_provider`, `clear_caches`, `get_client`/`get_client_for_model`, `resolve_model`,
  typed dicts, `_create_with_retry`, `_normalize_tool_arguments`, `_compact_tool_message_content`,
  `_stream_completion_one_turn`.
- `structured.py`: `structured_completion` over `completion(response_format=…)`.
- `__init__.py`: export `completion`, `run_tools`, `structured_completion`, `resolve_model`,
  contextvars, `register_provider`, `clear_caches`, types. (Remove `chat_completion`,
  `chat_completion_with_tools`.)
- Rewrite `digillm/tests/test_digillm.py` to the new names + object return.

## P2 — digigraph migrate + delete `llm.py`  (own PR)
- New `digigraph/model_config.py`: `ModelModesConfig`, `_load_model_modes`, `_get_llm_mode`,
  `get_model_for_mode`, `get_model_for_phase`, `resolve_effective_model`,
  `_openai_base_looks_like_direct_ollama`, `_EXTERNAL_PROVIDERS`, and the **request-model
  routing** helper (provider-key→ollama fallback, `ollama-cloud/` strip) that yields the model
  string handed to `digillm.completion`.
- New `digigraph/llm_auth.py`: `push/pop_lite_llm_proxy`, `push/pop_byok`, `get_byok_override`
  → feed digillm contextvars (`set_proxy_key`, `set_byok` for openai BYOK; anthropic → env).
- Migrate ~10 consumers (server, filter_hints, research, research_brief, research_agent,
  agents/*/runner) to `from digillm import completion, run_tools` + mode-resolution from
  `digigraph.model_config`; update call sites to the object return.
- Add `digillm>=0.1.0` to `digigraph/pyproject.toml` dependencies.
- **Delete** `digigraph/src/digigraph/llm.py`.
- Split `tests/dg/test_llm.py` → `test_model_config.py` + `test_llm_auth.py` (keep mode-resolution
  + auth/BYOK tests; drop client/retry/completion tests now covered by digillm).

## P3 — twelve-x  (own PR, coordinated)
- Update twelve-x's digillm call sites to the new API (object return) + tests; re-pin digillm
  to the P1 merge SHA.

## Risks
- **Breaking return type** → every call site (digigraph + twelve-x + tests). Mechanical but broad.
- **Auth** (human gate): verify the credential funnel (contextvars fed by digigraph middleware)
  is behavior-preserved; digigraph's `tests/dg` BYOK/proxy tests are the safety net.
- **twelve-x** breaks until P3 (insulated by SHA pin until then).
