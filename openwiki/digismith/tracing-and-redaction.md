---
type: behavior-guide
title: Tracing and Redaction
description: How digismith traceable() activates, what tracing_enabled() reports, and how PiiRedactor scrubs span payloads before LangSmith submission.
tags: [digismith, tracing, langsmith, pii-redaction]
verified:
  - by: openwiki/0.5.0
    at: 2026-09-07T22:31:53.755Z
sources:
  - id: openwiki-source-4b364849947e51d0e3e08109
    resource: repo://digismith/ARCHITECTURE.md
  - id: openwiki-source-e502a2c67cf187dc015ba472
    resource: repo://digismith/src/digismith/config.py
  - id: openwiki-source-9fad818d57858b73e94fed57
    resource: repo://digismith/src/digismith/redaction.py
  - id: openwiki-source-c00fdd1354f900a1d45b111a
    resource: repo://digismith/src/digismith/trace.py
  - id: openwiki-source-42c8be06536f30eafbc5f1c8
    resource: repo://tests/dsm/test_redaction.py
  - id: openwiki-source-ecab72add51be212920aacbe
    resource: repo://tests/dsm/test_trace.py
generated: { by: "opencode", at: "2026-09-07T22:31:53.755Z" }
---

# Tracing and Redaction

Tracing in digismith is a conditional decorator plus a value-pattern
redactor attached to the LangSmith SDK's native input/output hooks. The
rule of thumb: **no key or no SDK means the decorator does not exist at
runtime** — the function object passes through untouched.

## `traceable(name)` activation semantics

```python
from digismith.trace import traceable

@traceable("chat_completion")
def chat_completion(...): ...
```

The returned decorator checks two conditions at decoration (import) time:

1. The `langsmith` package is importable (module-level guard sets
   `LANGSMITH_SDK_AVAILABLE`).
2. `LANGSMITH_API_KEY` is set in the environment.

Both present → the function is wrapped with
`langsmith.traceable(name=name, process_inputs=…, process_outputs=…)`,
where the process hooks are the active redactor's methods. Either absent →
the original function is returned unchanged: same identity, same
`__name__`, zero per-call overhead (no closure, no wrapper, no branch).

An optional `redactor=` argument overrides the default redactor built from
the current environment. When tracing is inactive, the override is never
constructed.

## SDK-skew fallback

If the installed SDK version does not accept the `process_inputs` /
`process_outputs` kwargs, `langsmith.traceable(...)` setup raises
(`TypeError`, `ValueError`, `RuntimeError`, or `OSError` are caught), a
debug message is logged naming the span, and the original function is
returned. Tracing is skipped for that function rather than crashing the
host. Operators hitting this path should upgrade the SDK — without the
hooks, spans would flow unredacted.

## `tracing_enabled()` and helpers

`digismith.config` provides the runtime introspection used by both the
decorator path and `/v1/status`:

- `tracing_enabled()` — true when the API key is non-empty **and** the SDK
  imports. Re-reads the environment on every call, so tests can
  `monkeypatch` env vars freely.
- `langsmith_sdk_importable()` — bare import probe, no side effects.
- `default_langsmith_endpoint()` — `LANGSMITH_ENDPOINT` or
  `https://api.smith.langchain.com`.
- `langsmith_host_sanitized()` — hostname only (no path, credentials, or
  query); prefixes `https://` when the value has no scheme so bare
  hostnames still parse.

## `PiiRedactor`: what gets scrubbed

The redactor walks `dict` / `list` / `tuple` structures recursively and
replaces PII-looking substrings inside string values. Non-string scalars
(`int`, `bool`, `None`, floats) pass through untouched. Key names are
irrelevant — matching is by value pattern.

| Pattern | Sentinel | Notes |
|---------|----------|-------|
| Email (RFC-5321-lite) | `[REDACTED_EMAIL]` | `user@example.com` |
| API-key prefixes (`sk-`, `sk_`, `dgk_live_`, `dgk_test_`, `lsv2_`) + 8+ key chars | `[REDACTED_KEY]` | Keys checked first — they can contain digit runs a phone pattern would otherwise match |
| E.164 / North-American phone | `[REDACTED_PHONE]` | `+1-415-555-0199`, `(415) 555-0199`, `415.555.0199` |
| Extra regexes from `DIGI_PII_PATTERNS` | `[REDACTED]` | Comma-separated; invalid regexes are skipped, never fatal |

`DIGI_PII_PATTERNS` is read at redactor construction
(`PiiRedactor.from_env()` / `default_redactor()`), so tests rebuild the
redactor after mutating the environment. Example:

```bash
DIGI_PII_PATTERNS='TOP_SECRET_\w+,BADGE-\d{4}'
```

`process_inputs` accepts the SDK's inputs dict and always returns a dict;
`process_outputs` accepts anything and returns the redacted value. The
module has no dependency on `langsmith` — it operates on plain Python
structures.

## Span attribute contract (advisory, unenforced)

digismith documents which span attributes traces *should* carry
(`workflow_id`, `request_id`, `session_id`, `job_id`, tool/run name) and
which they *must not* (`raw prompts/completions`, API keys/tokens,
unapproved file paths, full document bodies). No runtime validator enforces
this: no Pydantic span model, no ingestion check. Enforcement today is the
redactor (value patterns) plus developer discipline. Key-name-based
redaction is the complement in `digibase.audit.redact_mapping`; length-based
document summarization and key-name deny-lists remain follow-ups.

## Failure and edge behavior

- No key / no SDK → pure no-op; tests run green without configuration.
- SDK present but old → debug-logged fallback to no-op (see above).
- Invalid `DIGI_PII_PATTERNS` entry → skipped silently; valid entries and
  all defaults still apply.
- Empty `LANGSMITH_ENDPOINT` → sanitized host is `None`, and the default
  host appears in `/v1/status` when the variable is unset entirely.
- LangSmith export itself is async-batched inside the SDK: negligible call
  latency, ~1s visibility lag, and spans can be lost on abrupt process exit
  with no backpressure signal to the application.
