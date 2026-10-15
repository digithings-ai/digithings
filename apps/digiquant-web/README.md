# digiquant-web

Next.js served desk for **digiquant** — research, portfolio, and execution in
one operator surface. Served at `/app` (`apps/dashboard` redirects
`/dashboard/` here).

## Dev

```bash
npm run dev:local --workspace digiquant-web   # 127.0.0.1:3910
```

Live data comes from `dashboard-api` (contract: `apps/dashboard-api/CONTRACT.md`).
Point at a local worker (see `apps/dashboard-api/README.md`):

```bash
# .env.local
NEXT_PUBLIC_DASHBOARD_API_URL=http://127.0.0.1:8788
```

Unset, loopback previews use the `/official-api` dev proxy and every other
host uses the production dashboard-api URL (see
`.env.local.example`). Market panels stay empty rather than falling back to
anything else — live prices come from the deployed R2-backed market worker.

## Gates

```bash
npm run lint --workspace digiquant-web
npm run test --workspace digiquant-web
```
