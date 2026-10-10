# Local-stack UI target inventory (measured)

**Status: measurement only.** This file records what the four surfaces named in the
self-host plan's section 7 actually are in this tree, and what a single
`DT_BASE_URL` / `--target` switch would have to replace. It is deliberately **not**
a URL-resolution implementation and **not** a config contract — the contract is
DIG-2769's deliverable (`config/contract/`), and a second source of truth for
service URLs is exactly what the plan's own CI parity check exists to catch.

Measured on branch `DIG-2776-s8-ui-and-mcp-wiring-to-self-host-stack`
(base `github/develop`), by enumerating tracked files with `git ls-files` and
searching with `git grep`. Every count below is reproducible with the command
shown beside it.

## 1. The four surfaces section 7 names, resolved

| Plan section 7 name | Path as written | Exists? | Real path in this tree |
|---|---|---|---|
| Brief desk | `apps/digiquant-web/app` | yes | `apps/digiquant-web/app` (7 routes) |
| digiquant TUI | `clients/digiquant-tui` | **no** | no `clients/` directory at repo root (0 tracked files). The nearest surface is `digiquant/src/digiquant/cli/` — 6 Python modules (`__init__ gloomberb onchain prices strategy web_search`), an argparse CLI, not a TUI |
| DigiChat web | (unnamed) | yes | `apps/digichat` (Worker + `apps/digichat/src/app`, 3 pages) |
| DigiChat TUI | (unnamed) | yes | `apps/digichat/cli/src` — Ink/React, 8 files (`app bin tools transport scripted-adapter chat-request` + `components/thread`) |
| devkit TUI/CLI | `devkit` | **no** | no `devkit` path anywhere in the tree (0 tracked files) |

Control that makes the two "no" rows real: the same `git ls-files` enumeration
returns 75 tracked `page.tsx` files, so the enumeration is finding files.

## 2. The "53-route audit" is identifiable — it is the three Next.js app-router trees

No artifact in the repo records a 53-route list: `git ls-files` matched no route
manifest (`routes.json`, `routes.ts`, `*route*audit*`, `*audit*route*`) — 0 files.

But `page.tsx` files, grouped by owning app-router root, decompose as:

| App-router root | `page.tsx` count |
|---|---|
| `apps/dashboard/app` | 25 |
| `apps/digithings-web/app` | 21 |
| `apps/digiquant-web/app` | 7 |
| **sum** | **53** |
| `apps/reference/app` (templates, not shipped) | 15 |
| `apps/digichat/src/app` | 3 |
| `apps/digichat/reference/assistant-ui-templates/*/app` | 4 |
| repo total | 75 |

The first three sum to exactly 53 and are the three deployed web surfaces.
Treat this as a **measurement, not a recovered spec**: no file names the list.
It matters because only **7 of the 53** routes belong to a surface section 7
names. The other 46 (`apps/dashboard` 25, `apps/digithings-web` 21) are not in
section 7's list at all, so "rerun the 53-route audit locally" is either
under-scoped in the plan or the plan's route list means something else.

Reproduce: `git ls-files | grep -E '/page\.tsx$' | sed -E 's#(^[^/]+/[^/]+/[^/]+/app|.*/app)/.*#\1#' | sort | uniq -c | sort -rn`

## 3. What a `--target` / `DT_BASE_URL` switch has to replace

There is no `DT_BASE_URL` and no `DT_TARGET` anywhere in tracked files
(0 hits). Every surface derives its backend independently today. The distinct
env names per surface:

**`apps/digiquant-web`** — `NEXT_PUBLIC_MARKET_DATA_URL`, `NEXT_PUBLIC_SUPABASE_URL`,
`NEXT_PUBLIC_SUPABASE_ANON_KEY`, `PUBLIC_STRATEGY_TYPES`, `PUBLIC_TYPE_LABELS`.

**`apps/dashboard`** — 29 distinct names including `NEXT_PUBLIC_DASHBOARD_API_URL`,
`NEXT_PUBLIC_MARKET_DATA_URL`, `NEXT_PUBLIC_DIGIQUANT_BASE_URL`,
`NEXT_PUBLIC_SUPABASE_URL` / `_ANON_KEY`, `NEXT_PUBLIC_BASE_PATH`,
`NEXT_PUBLIC_DIGICHAT_EMBED_ORIGIN` / `_HOST` / `_EMBED_TOKEN`, and a
`DIGICHAT_*` CSP/tenant block (`DIGICHAT_FRAME_SRC`, `DIGICHAT_POPUP_FRAME_ORIGINS`,
`DIGICHAT_EMBED_TENANTS`, `DIGICHAT_EMBED_HOST`, `DIGICHAT_EMBED_ORIGIN`, …).

**`apps/digithings-web`** — `NEXT_PUBLIC_MARKET_DATA_URL`, `NEXT_PUBLIC_SUPABASE_URL`,
`NEXT_PUBLIC_SUPABASE_ANON_KEY`, `DIGICHAT_URL`, `DIGICHAT_EMBED_ORIGIN`,
`DIGICHAT_EMBED_HOSTS`, `DIGICHAT_EMBED_TENANTS`, `DIGICHAT_VERSION`,
`DIGICHAT_REVISION`, `DIGICHAT_IMAGE_TAG`.

**`apps/digichat`** — 25+ `DIGICHAT_*` names (`DIGICHAT_BASE_PATH`,
`DIGICHAT_API_KEY`, `DIGICHAT_BOOTSTRAP_API_KEY`, `DIGICHAT_CONFIG`,
`DIGICHAT_APP_CSP`, `DIGICHAT_ALLOW_LOCAL_EMBED_PARENTS`,
`DIGICHAT_ALLOW_PRIVATE_ENDPOINTS`, `DIGICHAT_CHROME_SKIN`, …).

Hardcoded `https://*.digithings.ai` occurrences per surface — the literal strings
a target switch would have to make overridable:

| Surface | occurrences |
|---|---|
| `apps/digiquant-web` | 7 |
| `apps/dashboard` | 29 |
| `apps/digithings-web` | 26 |
| `apps/digichat` | 151 |

## 4. What is deliberately absent from this file

- **No URL resolver, no `--target` flag, no `DT_TARGET`.** These read
  `config/contract/`, which DIG-2769 has not created. Writing a second resolver
  now creates a parallel source of truth that the plan's own drift check would
  have to reconcile.
- **No `dt ui-audit`.** No such tool exists in `kit/bin/` and no audit harness
  exists in the repo, so "rerun" has nothing to rerun and its route list is not
  recorded anywhere (section 2).
- **No generated `opencode.json` / `mcp.json` snippets.** Those must embed local
  digikey tokens minted by DIG-2775's bring-up; generating them before that
  means inventing a token source.

## 5. Open questions for the owning seats

1. **DIG-2769 (Repo, CI & Release Engineer)** — does the contract's `env` section
   own the per-surface names in section 3, or only the service-URL half? If only
   the service URLs, the tenant/CSP/key names stay surface-local and `--target`
   only has to override ~6 of the ~50.
2. **DIG-2775 (Host & Runtime Engineer)** — will `dt up` print the resolved
   per-service URLs in the form section 7 assumes (`api.`, `graph.`, `key.`,
   `search.`, `mcp.`, `chat.` subdomains of `digithings.localhost`)?
3. **Epic DIG-2758** — is the "53-route audit" the dashboard + digithings-web +
   digiquant-web set (section 2), and if so, do the 46 dashboard /
   digithings-web routes belong in this slice's scope?
4. **DIG-2766 (Backend Engineer, Core Services)** is a live duplicate of this
   issue (same S8, same epic, `todo`). One of the two should be closed to avoid
   two seats writing the same UI wiring.
