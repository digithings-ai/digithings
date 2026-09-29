# Review — PR #4540: add the anthropic and google-vertex AI-SDK backends

- **Subject:** PR [#4540](https://github.com/digithings-ai/digithings/pull/4540) (`task/4539-digichat-anthropic-vertex` → `module/digichat`), issue [#4539](https://github.com/digithings-ai/digithings/issues/4539)
- **Reviewed revision:** `4c337710e`; fixes in `25a914b0f`
- **Reviewer:** independent fresh-context read-only subagent (`general`, delegation `keen-jade-lynx`, 2026-09-23T01:32:58Z → 01:36:18Z). The author session did not review its own work.
- **Verdict:** APPROVE WITH NITS — blocker 0 / major 0 / minor 3 / nit 5

The reviewer had **no shell tool**, so it could not run test/lint/build; its
conclusions are from the diff, on-disk files and `node_modules`. The PR body's
verification numbers were re-run independently by the author session (below).

## Findings

| # | Severity | Finding | Resolution |
|---|---|---|---|
| 1 | minor | `webSearch` / `sources` are `true` on both new `BACKEND_ADAPTERS` entries, but the shared mapper passes no provider search tool to `streamText`, so no grounding citations flow. Consistent with the OpenAI pair. | Fixed — explicit "declared for the matrix, not wired yet (#4539)" comments on both entries; values kept `true` (the parity test asserts `sources === true` for every type). Gap recorded in the program plan. |
| 2 | minor | `google-vertex` has no credential pre-check: `readBackendApiKey` throws a clean 502 for the env-key backends, but ADC resolves lazily inside `streamText`, so an absent credential surfaces as an opaque upstream error. | Fixed — documented in `adapters/ai-sdk/stream.ts` next to the 502 mapping. |
| 3 | minor | `project` / `location` are unvalidated non-empty strings and select which GCP project the BFF's ambient (cloud-platform scoped) credential is spent against. Not tenant-exploitable (config sources are operator-controlled). | Fixed — comment on `GoogleVertexBackendSchema`; allowlist noted as the follow-up if tenant-authored config is ever accepted. |
| 4 | nit | `createAnthropic({ apiKey, name: "anthropic" })` hardcodes the name while the OpenAI arm uses `backend.type`. | Fixed — now `name: backend.type`. |
| 5 | nit | `apps/digichat/ARCHITECTURE.md` still listed only `digigraph \| foundry` for `backend.type`. | Fixed — now lists all six types. |
| 6 | nit | `@ai-sdk/google-vertex` is imported eagerly, so `google-auth-library` loads for every AI-SDK request; would break on the Edge runtime. | Deferred — a dynamic import would make `resolveAiSdkModel` async (signature + call site + 3 test assertions). The route is Node-only today, so no runtime impact. Recorded in the program plan. |
| 7 | nit | Tenant validator is not `.strict()`; a stray `backend` key is silently dropped (safe — nothing is forwarded). | Documented only — benign, and the tenant path is the safer one. |
| 8 | nit | `z.string().min(1)` accepts whitespace-only values while the validator's `.trim()` rejects them, so the tenant path is stricter. | Documented only — the security-critical `apiKeyEnv` regex is byte-for-byte identical on both sides. |

**Out of scope (flagged, not touched):** `apps/digichat/cli/package-lock.json`
still pins `ai@7.0.93` + `@ai-sdk/provider@4.0.10`. It is not a workspace member,
so the root dedupe holds, but an `npm ci` there would reintroduce a second
provider copy. This is not "resolved repo-wide".

## Verified clean

- **Schema:** `AnthropicBackendSchema` has no `baseUrl` and `GoogleVertexBackendSchema` has no credential field; both `.strict()`; `BackendSchema` has exactly six members.
- **Tenant registry:** the union and both `validateEntry` branches match the schema's rules, and the final error enumerates all six types.
- **Registry:** both `Extract` types, the four-way `AiSdkBackendConfig`, both adapter entries (protocol / auth / capability flags) and the extended `isAiSdkConfig` are correct; `AI_SDK_PROTOCOLS` needed no change.
- **Provider factory:** four-arm exhaustive switch; the OpenAI arm is behaviour-identical; credentials are read only from `process.env[apiKeyEnv]` and never logged or returned; `createVertex`'s ADC path is confirmed and Node-safe.
- **Route:** untouched — the existing `AI_SDK_PROTOCOLS.has(...) && isAiSdkConfig(...)` branch covers both new protocols; no `backend.type` comparison was introduced.
- **Dedupe:** exactly one `@ai-sdk/provider` (`4.0.17`) and one `ai` (`7.0.111`); the four `libc` selectors survive; no non-AI-SDK package was bumped.
- **Tests:** non-vacuous, though the provider tests mock the providers (they validate the wrapper's call shape, not real provider behaviour).
- **Security:** no new secret-to-config-controlled-host path; the `DIGICHAT_BACKEND_` guard is enforced in both the schema and the validator; `toDigichatClientConfig` still projects only the `backendType` discriminator.

## Could not verify (reviewer)

Test/lint/build results; the "packages approved by the owner" human-gate claim;
live Anthropic/Vertex behaviour and real ADC resolution in the deployment
environment.

## Post-fix verification (author session, revision `25a914b0f`)

- `apps/digichat` `npm run test` → 130 files / 1300 tests passed
- `apps/digichat` `npm run lint` → 30 problems, 0 errors
- `apps/digichat` `npm run build` → exit 0, type-checks clean
- `python3 scripts/check_frontend_canon.py` → clean
- `python3 scripts/check_doc_links.py` → OK (418 markdown files)
