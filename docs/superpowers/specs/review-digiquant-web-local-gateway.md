# Review — digiquant-web local gateway + LuxAlgo workflow

| Field | Value |
| --- | --- |
| Reviewer | Fresh-context Cursor subagent `bc-df8fb024-2d1a-59be-99d5-041cfe9173e3` |
| Subject | `47d5d6f4c..3daa7b2e0` |
| Re-review commit | `3daa7b2e0` |
| Final verdict | Approve |
| Final findings | Critical 0 · Important 0 · Minor 2 |

## Findings and resolution

1. **Important — public integration status overstated the local-only wire.**
   `apps/digiquant-web/app/_products.ts` used `integrated` even though the browser
   client refuses non-loopback pages. Resolved by changing LuxAlgo to `local only`.
2. **Important — production guidance covered only the dedicated gateway variable.**
   `NEXT_PUBLIC_MARKET_DATA_URL` has no loopback guard. Resolved in
   `apps/digiquant-web/gateway/README.md` and `.env.local.example`: production and
   staging keep the deployed R2-backed market worker URL and never use `:8792`.
3. **Minor — runbook did not name the intended operator.** Resolved by making the
   `:3910` + `:8792` two-terminal steps explicit for Chris.
4. **Minor — search completion could update state after unmount.** Resolved with a
   mounted ref guarding both health and search completions.

## Non-blocking observations

- Component render tests cover the static handoff and gateway-client tests cover
  the policy states, but no DOM test drives every badge transition.
- The removed root `ts-1440.png` was an earlier ad-hoc screenshot; deleting it
  restores the repository rule that walkthrough screenshots are not committed.

## Evidence checked

- Gateway URL and page-host loopback validation, fixed probe route, origin
  validation, scrubbed stdio child, and local-only documentation.
- LuxAlgo UI exposes Library metadata and attribution only, retains LuxAlgo as
  chart/journal handoff, and renders no competing chart.
- Re-review found no regression in the local-only security boundary.
