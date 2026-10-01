# digiquant canvas

This folder is the review tree for the digiquant operator desk. Static HTML, one stylesheet (`mock.css`), and a small `mock-nav.js` for rail resize, digichat right rail, desk expand, and pane fullscreen. No React, no build. `apps/dashboard` is unchanged. House Corpus, Book, and Profile pages are removed on purpose. house is a desk name only.

## Serve

From the repo root, this makes the index the site root:

```bash
cd docs/dashboard-mocks/canvas && python3 -m http.server 3920
```

Open [http://127.0.0.1:3920/](http://127.0.0.1:3920/).

## Frame inventory

36 HTML frames, plus `mock.css` and this README.

| Group | File |
|---|---|
| Index | `index.html` |
| Shell | `desk-picker.html` |
| Brief and charts | `brief.html` (overview), `brief-book.html`, `brief-markets.html`, `brief-chart.html`, `ticker-dossier.html`, `gloomberg.html`, `luxalgo.html` |
| Portfolio | `holdings.html`, `theses.html`, `tearsheet.html`, `ledger.html`, `attribution.html` |
| Pipeline and chat | `pipeline.html`, `chat.html` |
| Strategies and Tools (product vision, WIP / coming soon) | `strategies.html`, `strategy-detail.html`, `strategy-deploy.html`, `gloomberg.html` (Terminal), `luxalgo.html`, `charts.html`, `chat-fullscreen.html`, `fx-hub.html` |
| Settings | `settings.html`, `settings-paper.html` |
| FX Hub | `fx-hub.html`, `fx-ideas.html`, `fx-watch.html`, `fx-settings.html` |
| Rates watch | `rates-digest.html`, `rates-watchlist.html` |
| Empty / loading / error | `brief-empty.html`, `brief-loading.html`, `brief-error.html`, `holdings-empty.html`, `ledger-error.html`, `pipeline-loading.html`, `pipeline-error.html`, `fx-empty.html`, `fx-loading.html`, `fx-error.html` |
| Stylesheet | `mock.css` |

## IA

Choosing a desk replaces the whole sidebar. The picker lists three desks:

- **house** (desk name, not a page): Brief, Portfolio, Pipeline, then the product block below. Settings sits at the foot.
- **rates watch** (its own desk): Digest, Watchlist, Theses, Run, Config, Settings. Canvas redraws Digest and Watchlist. Theses, Run, and Config on that spine still open the matching skeleton frames.
- **FX Hub** (first-class desk): Hub, Ideas, Watch, Settings.

**Product block.** Every desk spine also lists Strategies, a Tools group (Terminal, LuxAlgo, Charts, digichat) and FX Hub (the FX Hub desk lists the first two groups only, since it is that desk), so the product map is always visible. Unbuilt items carry a `[wip]` or `[soon]` tag in the rail and open a page with a Coming soon or WIP banner, never a blank screen. In this tree the product pages render under the house chrome even when reached from another desk; the skeleton tree draws the rates watch variants (`51` to `57`).

- **Strategies.** Every strategy lives in the dashboard. A subscribed user deploys to a paper account or a portfolio and connects a paper broker from Settings. The deploy flow is drawn but disabled.
- **Tools.** Terminal (Bloomberg Terminal / gloomberg embed), LuxAlgo charting, own Charts, and digichat. `chat-fullscreen.html` is the full-screen digichat with a sessions sidebar and history for a logged-in user; `chat.html` stays the docked transcript.

Portfolio is one spine item. Holdings, Theses, Tearsheet, Ledger, and Attribution nest under Portfolio in the left spine (no horizontal section tabs). The ticker dossier is a deep link from a Holdings row, not a spine item.

Pipeline is one screen: run health, node document, call trace, and artifact ledger.

Tearsheet is report-only (accounting, method, tables). Published tearsheets stay on the digiquant showcase. They are not this desk.

digichat is a docked static transcript on `chat.html` and a full-screen view on `chat-fullscreen.html`. Neither is an iframe.

The layout is full-bleed. No site column guides. No max-width marketing container. The stylesheet is `mock.css` in this folder.

## Placeholder versus production

Figures are layout mocks, not book data. Chips say paper or research. There is no live-trading claim, no order ticket, and no live broker control.

Intended production behavior this canvas is drawing: a desk swap remounts the spine; portfolio stays one item with nested spine children; pipeline is the glass box for a run; FX Hub is a desk of its own; rates watch stays a separate desk; tearsheet stays a report; digichat docks as a transcript.

Gloomberg and LuxAlgo panes are labeled placeholders beside tables. They are not a chart library and not a live feed.

## Production care

digiquant has a live paying user. This canvas is a design source, not a live book. No private-client names. Do not treat the placeholder figures as positions, NAV, or fills.


## Craft locks (#4911 remock)

1. **Desk picker** — compact popover (wider than the left rail); `full` expands to a fullscreen overlay; choosing a desk swaps the sidebar spine.
2. **One viewport** — each frame is one viewport tall; panes scroll inside; no document scroll.
3. **No horizontal section tabs** — subsections nest under the active left-spine item.
4. **Top chrome path only** — breadcrumb like `house / portfolio / holdings`.
5. **Narrow panes** — column-priority when narrow; pane `full` + Esc to exit.
6. **Rails** — DigiQuant left; DigiChat right rail (never replaces the left spine).
7. **Headers** — lighter-gray section headers preserved from the `051f13ec` visual baseline.

## Polish dump (#4911 remock continuation)

1. **One viewport** — Brief split into nested spine pages (overview / book / markets / chart). No document scroll.
2. **Sparse expand** — `.col` stretches panes to fill height (`grid-auto-rows: minmax(0,1fr)`).
3. **View primitives** — shared atoms: `.atom-table`, `.atom-chart`, `.atom-feed`, `.atom-pipeline`, `.atom-tearsheet`.
4. **No top KPI strip** — `.kpis` removed from frames and hidden in CSS.
5. **Pane rearrange** — drag `⋮⋮` handle on pane headers; order persists in `sessionStorage`. Pane `full` + Esc kept.
