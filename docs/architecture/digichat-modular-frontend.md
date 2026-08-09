# digichat as a modular frontend

> Scope and design — digichat is a backend-agnostic translation UI. digithings
> tenants talk to digigraph (digillm + digivault hub). Client embeds may use
> Foundry. Adapters only translate provider streams into shared digichat visuals.

**Status:** Living architecture note (2026-08-09)
**Related:** [ADR-0018](../adr/0018-digichat-path-routing.md), [activity protocol](../superpowers/specs/2026-08-01-digichat-activity-protocol-design.md), [`frontend/digichat/ARCHITECTURE.md`](../../frontend/digichat/ARCHITECTURE.md)
**Naming:** Digi module names are always lowercase in prose ([PR #2007](https://github.com/digithings-ai/digithings/pull/2007)).

---

## 1. Adapter contract

digichat is a **modular frontend + BFF**:

1. **Shared UI** — `@digithings/digichat-ui` (`DigiChatSession`, `ChatActivities`)
2. **Activity contract** — `ActivitySpan` → `DigiChatActivity`; server-side `activityDetail` gate
3. **Tenant registry** — `DIGICHAT_EMBED_TENANTS` (hostname → branding + policy + backend)
4. **Provider adapters** — translate backend wire formats into the activity vocabulary

**Rules**

- digichat UI never speaks digigraph / Foundry / OpenAI wire formats.
- Each adapter’s job is **translation only** into `ActivitySpan` / `data-digichatActivity` + text stream.
- digithings tenants must use `backend.type: digigraph`. digigraph owns digivault, digisearch, and digillm.
- digivault / digisearch are **not** digichat HTTP backends — they are digigraph tools; digichat only has activity mappers under `adapters/digithings/activity/`.
- Client (non-digithings) embeds use `backend.type: foundry`.
- digichat Node accepts only `digigraph` | `foundry`. Unused `external-relay` and digichat-Node `digivault` backends are removed.

```mermaid
flowchart LR
  UI["digichat UI"]
  Adapters["Adapter translation layer"]
  UI --> Adapters
  Adapters --> DG["digigraph"]
  Adapters --> Foundry["Foundry client"]
  DG --> digillmNode["digillm / LiteLLM"]
  DG --> VaultHub["digivault_hub"]
  VaultHub --> digivaultNode["digivault service"]
```

**digithings path**

```text
Browser → digichat BFF → digigraph → digillm → LiteLLM
                              └─ digivault_search_notes (digivault_hub → digivault :8004)
```

**Layout**

```text
frontend/digichat/src/lib/adapters/
  digithings/
    stream.ts
    activity/{digivault.ts,digisearch.ts,index.ts}
  foundry/stream.ts
  shared/messages.ts
```

---

## 2. Current vs target (digithings.ai/chat)

| | Current (until cutover complete) | Target |
|---|---|---|
| Host | Cloudflare Pages Function | digichat Node behind Cloudflare Tunnel |
| LLM | OpenRouter direct from Pages | digigraph → digillm → LiteLLM |
| Vault | Direct Supabase digivault search in Function | digigraph `digivault_hub` → digivault :8004 |
| digichat backend | n/a (bypasses digichat Node) | `backend.type: digigraph` |

Cutover runbook: [`infra/digichat-digithings/README.md`](../../infra/digichat-digithings/README.md).

---

## 3. Client onboarding checklist

```text
[ ] digichat Node reachable; DIGICHAT_EMBED_HOSTS at build; DIGICHAT_EMBED_TENANTS at runtime
[ ] backend.type: digigraph (digithings) or foundry (Azure client)
[ ] activityDetail set explicitly (off|labels|full)
[ ] digithings stack: DIGIGRAPH_INTERNAL_URL, digikey auth, DIGIVAULT_URL on digigraph
[ ] Smoke: tool rows + answer via digigraph (no direct OpenRouter from digichat)
```

---

## 4. Foundry

Foundry remains the client Azure adapter. Behavior polish (reasoning summary, activity parity) is tracked separately — not required for digithings digigraph cutover.
