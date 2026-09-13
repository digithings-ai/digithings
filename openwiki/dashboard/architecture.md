---
type: frontend-architecture
title: Dashboard Architecture
description: Design of the digiquant operator dashboard — static-exported Next.js app at /dashboard/ on the shared design system.
tags: [dashboard, digiquant, nextjs, frontend]
verified:
  - by: openwiki/0.5.0
    at: 2026-09-09T14:37:17.158Z
sources:
  - id: openwiki-source-85317e6ee50bd801c6c5f886
    resource: repo://frontend/dashboard/app/layout.tsx
  - id: openwiki-source-de8bcce4f9a34c49cbeb2389
    resource: repo://frontend/dashboard/app/page.tsx
  - id: openwiki-source-49a5c74467bc0cebc9b514df
    resource: repo://frontend/dashboard/lib/book-reconciliation.ts
  - id: openwiki-source-d549d83122810923e6749df8
    resource: repo://frontend/dashboard/next.config.mjs
  - id: openwiki-source-b58aa34d88875ec609bc8cbe
    resource: repo://frontend/dashboard/package.json
  - id: openwiki-source-4b479ed8d11ca62135d6071d
    resource: repo://frontend/dashboard/README.md
generated: { by: "opencode", at: "2026-09-07T22:38:58.074Z" }
---

# Dashboard Architecture

The dashboard (`frontend/dashboard`, npm package `dashboard`) is the
digiquant operator surface: research, portfolio, and execution in one
investment-intelligence UI. It is a Next.js 16 + React 19 app that builds to
a **static export** (`output: 'export'`) served under the **`/dashboard/`
base path** — the only public path (ADR-0026); the old `/olympus/` path is
retired with no redirect alias.

## Hosting and routing

`basePath` is fixed to `/dashboard/` in `next.config.mjs` and surfaced to
client code as `NEXT_PUBLIC_DASHBOARD_BASE_PATH` (a static export has no
runtime config). Images are unoptimized, `trailingSlash` is on, and the
build runs a `check:static-export` step after `next build`. Top-level route
groups under `app/` include `research`, `portfolio`, `performance`,
`library`, `pipeline`, `strategy`, `house`, `auth`/`login`, `settings`,
`system`, and `observability`.

## Design system

Styling joins the root npm workspace and consumes the shared system via
`@digithings/design` (canon tokens, quant-native and finance-tearsheet
grammars) plus the Tailwind v4 bridge from `@digithings/web` (compiled via
`transpilePackages`). `app/globals.css` layers Tailwind, the typography
plugin, tokens, the theme bridge, and the quant-native/tearsheet styles.
The root layout scopes pages to the digiquant accent and blueprint
background, with a thin monospaced header strip carrying route crumbs and a
version/env label (`NEXT_PUBLIC_DASHBOARD_VERSION`, fallback `v0.1 · dev`).
Fonts are self-hosted at build time (`next/font`) to satisfy the dashboard
CSP — no `fonts.googleapis.com`.

## Data and auth

The dashboard reads persisted research/portfolio state (Supabase-backed book
tables) rather than calling the digiquant HTTP service per render; its
`lib/` layer owns book reconciliation, benchmark tickers, auth context, and
an auth gate, with fail-closed accounting helpers covered by unit tests.
Charts use `lightweight-charts` and `recharts`; markdown renders via
`react-markdown` with GFM + sanitize.

## Representative tests

Vitest (`npm run test` from `frontend/dashboard/`): `globals.test.ts`,
route `page.test.ts` files, and `lib/` unit tests including
`book-reconciliation`, `accounting-views`, and `accounting-nav-fail-closed`
— the fail-closed P&L contract (missing basis or mark renders `—`, never an
invented number).

## Plan tiers + Desk+ digichat (#3664 / #3670)

Effective ladder: **Observer** (free) → **Brief** → **Desk** → **Studio** /
Enterprise. Do not document Baseline/Custom as Stripe products.

- **Billing** (dashboard Settings): Brief / Desk / Studio checkout; annual is the
  default interval. Display catalog and tab visibility by effective tier live in
  `frontend/dashboard/README.md` and `docs/agent-backlog/kairos-tenancy/PRICING.md`.
- **Desk+ digichat popup:** Desk / Studio / enterprise get full chat; Brief /
  Observer see the upgrade CTA. The embed mints HMAC `X-Embed-Plan-Proof` via
  `POST /api/plan-proof` from JWT `app_metadata.plan_tier` — never a raw
  `X-Embed-Plan-Tier` header. Shared secret: `DIGICHAT_PLAN_PROOF_SECRET`.

