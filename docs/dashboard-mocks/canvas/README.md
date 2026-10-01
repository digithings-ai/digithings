# digiquant canvas

This folder is the review tree for the digiquant operator desk. Static HTML, one stylesheet (`mock.css`), no React, no build, no JavaScript. `apps/dashboard` is unchanged. House Corpus, Book, and Profile pages are removed on purpose. house is a desk name only.

## Serve

From the repo root, this makes the index the site root:

```bash
cd docs/dashboard-mocks/canvas && python3 -m http.server 3920
```

Open [http://127.0.0.1:3920/](http://127.0.0.1:3920/).

## Frame inventory

31 HTML frames, plus `mock.css` and this README.

| Group | File |
|---|---|
| Index | `index.html` |
| Shell | `desk-picker.html` |
| Brief and charts | `brief.html`, `ticker-dossier.html`, `gloomberg.html`, `luxalgo.html` |
| Portfolio | `holdings.html`, `theses.html`, `tearsheet.html`, `ledger.html`, `attribution.html` |
| Pipeline and chat | `pipeline.html`, `chat.html` |
| Settings | `settings.html`, `settings-paper.html` |
| FX Hub | `fx-hub.html`, `fx-ideas.html`, `fx-watch.html`, `fx-settings.html` |
| Rates watch | `rates-digest.html`, `rates-watchlist.html` |
| Empty / loading / error | `brief-empty.html`, `brief-loading.html`, `brief-error.html`, `holdings-empty.html`, `ledger-error.html`, `pipeline-loading.html`, `pipeline-error.html`, `fx-empty.html`, `fx-loading.html`, `fx-error.html` |
| Stylesheet | `mock.css` |

## IA

Choosing a desk replaces the whole sidebar. The picker lists three desks:

- **house** (desk name, not a page): Brief, Portfolio, Pipeline, Settings. Settings sits at the foot.
- **rates watch** (its own desk): Digest, Watchlist, Theses, Run, Config, Settings. Canvas redraws Digest and Watchlist. Theses, Run, and Config on that spine still open the matching skeleton frames.
- **FX Hub** (first-class desk): Hub, Ideas, Watch, Settings.

Portfolio is one spine item. Sticky tabs are Holdings, Theses, Tearsheet, Ledger, Attribution. The ticker dossier is a deep link from a Holdings row, not a spine item.

Pipeline is one screen: run health, node document, call trace, and artifact ledger.

Tearsheet is report-only (accounting, method, tables). Published tearsheets stay on the digiquant showcase. They are not this desk.

digichat is a docked static transcript on `chat.html`. It is not an iframe.

The layout is full-bleed. No site column guides. No max-width marketing container. The stylesheet is `mock.css` in this folder.

## Placeholder versus production

Figures are layout mocks, not book data. Chips say paper or research. There is no live-trading claim, no order ticket, and no live broker control.

Intended production behavior this canvas is drawing: a desk swap remounts the spine; portfolio stays one item with those sticky tabs; pipeline is the glass box for a run; FX Hub is a desk of its own; rates watch stays a separate desk; tearsheet stays a report; digichat docks as a transcript.

Gloomberg and LuxAlgo panes are labeled placeholders beside tables. They are not a chart library and not a live feed.

## Production care

digiquant has a live paying user. This canvas is a design source, not a live book. No private-client names. Do not treat the placeholder figures as positions, NAV, or fills.
