# ADR-0016 — Structured outputs for the research agent

- **Status:** Accepted
- **Date:** 2026-04-29
- **Related issue:** [#492](https://github.com/digithings-ai/digithings/issues/492)
- **Related fix:** [#490](https://github.com/digithings-ai/digithings/issues/490) (bias Literal failures that motivated this ADR)

## Context

The Atlas research pipeline ([ADR-0014](0014-atlas-in-digiquant.md)) calls `run_research_agent`
for every phase node. The agent instructs the LLM to return a single JSON object matching a
Pydantic schema embedded in the prompt (`OUTPUT_SCHEMA` block). This is prompt-engineering only —
the model is free to produce any token sequence.

In April 2026 a 14-day pipeline outage was traced to two Pydantic `literal_error` failures:

- `SegmentReport.bias` received `"positive"` (not in `["bullish", "bearish", ...]`).
- `CtaPositioningReport.cta_flow_bias` received `"mixed"` (not in the then-three-value set).

Both are cases where Gemini Flash paraphrased an allowed value instead of emitting the exact
string. The immediate fix (PR #491) adds `field_validator(mode="before")` synonym normalisation
and expands the `cta_flow_bias` Literal. This ADR records the second layer: native structured
output at the API level.

## Decision

Pass `response_format={"type": "json_schema", "json_schema": {"name": ..., "schema": ...}}`
to `chat_completion` for every `run_research_agent` call.

`chat_completion` adds `response_format` to the API request when:
1. The caller supplies it **and**
2. `tools` is not set — `tools` and `response_format` are mutually exclusive in the OpenAI API.

`response_format` is included in the LLM cache key so that different schemas never collide.

## Provider compatibility

| Provider | Endpoint | json_schema support | Notes |
|----------|----------|--------------------|----|
| Gemini Flash | `generativelanguage.googleapis.com/v1beta/openai/` | ✓ | `$defs`, `anyOf`, `enum` all handled natively; no schema pre-processing needed |
| OpenAI | `api.openai.com/v1` | ✓ (non-strict) | Strict mode not used — see below |
| Ollama (local) | port 11434 | ⚠ silently ignored | Falls back to prompt-embedded schema |
| Ollama Cloud | `ollama.com/v1` | ⚠ silently ignored | Same as local |
| LiteLLM proxy | configured `OPENAI_API_BASE` | varies | Passes through to backend; Gemini/OpenAI backends work |

## Why not `strict: true`

OpenAI strict mode requires every property to be listed in `required` with no defaults, and
forbids `anyOf` with `null`. Pydantic models used in Atlas have many optional fields with
`default_factory`, `None` defaults, and nullable types (`Bias | None`, `float | None`).
Generating a strict-compatible schema would require pre-processing every model schema, adding
fragility for no reliability gain over non-strict json_schema (which still produces valid JSON
matching the schema for all fields the model emits).

## Why `field_validator` stays

Defense-in-depth. Three independent layers:

1. **`response_format` json_schema** — prevents the model from generating non-conforming tokens
   on providers that support it (Gemini, OpenAI).
2. **Prompt-embedded `OUTPUT_SCHEMA`** — instructs the model on providers that silently ignore
   `response_format` (Ollama, some LiteLLM backends).
3. **`field_validator(mode="before")`** on `SegmentReport.bias` — normalises LLM synonyms
   (`"positive"` → `"bullish"`) regardless of which path was taken.

Removing the validator would couple correctness to provider support for `response_format`. The
validator is cheap and has no downside.

## Why `response_format` is not in `_stream_completion_one_turn`

The streaming path (`chat_completion_with_tools` / DigiChat) is a tool-calling loop. Tools and
`response_format` are mutually exclusive, so the streaming path never sends `response_format`.
The research agent uses the non-streaming `chat_completion` path with no tools.

## Consequences

- Gemini Flash (the production model for all Atlas phases) now enforces the output schema at
  token-generation time, eliminating the class of `literal_error` failures seen in April 2026.
- OpenAI-backend deployments get the same guarantee.
- Ollama / LiteLLM-only deployments are unchanged — they already relied on the prompt schema.
- The LLM cache is correctly partitioned by schema: two different segment models will never
  share a cached response.
- `BadRequestError` from schema rejection is not caught — it propagates immediately so the
  caller sees the real error (a schema that a provider rejects should be fixed, not retried).
