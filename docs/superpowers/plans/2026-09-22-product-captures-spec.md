# Product captures — spec (v13, stage 12, #4429)

**Status: spec only.** No capture is built, embedded, or faked by this stage. The
landing page carries no product screenshot today because there is none that is
honest to show: a mocked dashboard or an invented terminal would be exactly the
"unmarked projection" the site's honesty rule forbids. This document is the
brief for producing the real artefacts later, and the contract for how they may
be placed when they exist.

Owner direction (2026-09-22, verbatim intent): throughout the UI, "like we see in
the opencode website or Bloomberg website", there could be screenshots or
animated videos of the product itself — the digiquant section could have the
digiquant dashboard screenshot or the tier sheets animated; digichat could have
a screenshot of the chat animated as it answers, calling tools, a full tool
chain; a graph of how you could deploy it in your stack on Azure or anywhere via
the Docker/containerised release; digichat embedded in your website and how
that embed looks. "Mainly digiquant and digichat at the moment and what they're
capable of."

## What may be shown, and what may not

Every capture is a **recording of a real run of the real software**, taken
against data that is either public or synthetic-but-labelled. Rules, in the same
voice as the rest of the site:

- **No performance figures** — no return, no Sharpe, no P&L, no win rate, in any
  capture placed on a marketing page. The digiquant dashboard capture must be
  taken with real positions masked or with the demo/synthetic book, and the
  frame must carry the same "illustrative view" label the `QuantSection` uses.
  (The product itself shows figures; the marketing page does not. That is the
  line the owner drew and it does not move because a screenshot makes it
  tempting.)
- **No invented tool calls.** The digichat capture shows a real question against
  a real, running stack, with real MCP/tool invocations. If a tool call in the
  frame is staged, the frame is captioned as staged.
- **No customer data.** DataTap's name is already used in the quotes section
  under their documented self-hosted integration; their instance, tenants or
  data never appear in a capture.
- **No live-trading promise.** A capture may show the research→portfolio
  pipeline; it may not imply an order was placed or that live trading runs.
- **Version-stamped.** Each capture records the commit/tag it was taken at, in
  the asset filename or a sidecar, so it can be re-shot when the UI moves.

## Assets to produce

Each row is one capture: what it shows, where it would go, and the exact source
tree it must be shot from so it stays reproducible.

| # | Asset | Shows | Page slot | Source / how to shoot |
|---|-------|-------|-----------|------------------------|
| 1 | `digiquant-dashboard` | The operator surface: positions, attention queue, overlay graph | Stage-9 `#digiquant` (right column, replacing or beside `<Pipeline/>`) | `digiquant/src/digiquant/dashboard/` served via the dashboard route; demo book, real figures masked |
| 2 | `digiquant-tearsheet` | A **tear sheet** (the owner said "tier sheets") — the per-strategy equity/regime summary, animated as it draws | Stage-9 `#digiquant`, as a small looping clip beside the prose | Same dashboard surface; synthetic/demo strategy, labelled |
| 3 | `digichat-toolchain` | A question answered *with a full tool chain*: retrieve → tool call → answer, tool cards visible | Stage-11 `#faq` (replacing the static `QuickAsk` pane once shot) and/or Stage-3 boot area | `digichat` `/embed` against a locally running stack with digisearch + an MCP server up; `GROQ_API_KEY` in `.env` |
| 4 | `deploy-anywhere` | The deployment graph: laptop → VM → Azure Container Apps → Kubernetes, all from the same image | New small band under Stage-4 (module grid) or the Stage-10 pricing area | Diagram from `docker-compose.yml` + `Dockerfile*` (real services, real ports); drawn, not photographed. It is a *diagram*, so it may be authored — but every node is a real compose service or a real documented target |
| 5 | `embed-widget` | digichat embedded in a host page, composer + first paint | Stage-10 free tier (the "embed it" claim) | `digichat` embed against `widget.js` / `/embed`; the documented path in `docs/architecture/digichat-modular-frontend.md` |

**Priority:** 3 (digichat tool chain) and 4 (deploy diagram) first — they carry
the most claim for the least risk (no figures). Then 1, then 2, then 5.

## Format contract

- **Static where motion adds nothing.** Dashboard and tear sheet get a still
  first; an animated version only if the motion is the point (the tear sheet
  drawing, the tool chain stepping).
- **Short, silent, looping, small.** Video: MP4/H.264 + WebM, ≤ 6 s, ≤ 800 px
  wide, no audio, no UI chrome from the recording host, `loop muted autoplay
  playsinline`. A poster frame is mandatory so nothing shifts before it plays.
- **Reduced motion is a hard requirement.** Every animated asset ships a static
  poster and only plays when `prefers-reduced-motion: no-preference`. There must
  be no autoplaying motion for a visitor who asked for none — the same rule the
  `Terminal` primitive already follows.
- **Dark and light.** Shoot in the theme the page ships by default (dark); a
  light-theme variant is optional and, if made, must be the same frame, not a
  re-layout.
- **Placement is opt-in.** These land as `<Figure>`-wrapped assets with a real
  caption and a source line ("shot at `digichat v2.3.x`, demo book"), never as a
  bare decorative background.

## Where they live

`apps/digithings-web/public/captures/` (the dir does not exist yet — create it
when the first real asset exists, not before), served with the app's normal
static headers. Filenames carry the date and source tag, e.g.
`digichat-toolchain-2026-09-22-digichat-v2.3.1.webm`. Because this is a static
export on Cloudflare Pages, no build-time processing is needed; the assets are
copied as-is from `public/`.

## Out of scope

- Building any capture in this stage.
- Any change to the digichat container, the `/embed` postMessage contract, or
  `widget.js` — that surface is frozen for this work (owner decision, plan §7).
- Any capture that would require a running broker or a live trading path.
- Placeholder images. If an asset is not shot, the slot is simply absent; the
  page must read as complete without it.

## Follow-up issue

When the first asset is shot, open a task that (a) adds it under
`public/captures/`, (b) wires the reduced-motion poster pattern, and (c) updates
`{component}/ARCHITECTURE.md` for whichever surface was captured. This spec is
the acceptance criteria for that task.
