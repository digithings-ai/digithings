# digiquant dashboard skeleton: phase B static mocks

Static HTML and one shared stylesheet at `../canvas/mock.css`. No React, no build step, no JavaScript, no chart library. Nothing under `apps/dashboard` changes. Open `index.html` in a browser, or run `python3 -m http.server` in this folder. House content pages are removed. The layout is full-bleed.

Plan: the [dashboard skeleton plan in PR #4908](https://github.com/digithings-ai/digithings/pull/4908). Issue: [#4895](https://github.com/digithings-ai/digithings/issues/4895). Phase letters here are the plan's A/B/C, not [#4761](https://github.com/digithings-ai/digithings/issues/4761) phases.

## The IA these frames draw

A **desk** is a swappable research configuration. Choosing a desk replaces the **entire sidebar**, not a page inside a fixed one.

- The **desk picker** sits at the top of the sidebar, under the wordmark. It is the only control that changes the desk. It is not a paper/live switch and not a book switcher. Each option previews its own spine, so the remount is obvious before you click.
- **house** (baseline research desk name, always-on, read-only) defines: Brief, Portfolio, Pipeline, Settings. Settings is pinned at the foot. House content pages are removed. There is no House destination.
- The desk layout is full-bleed: the operator surface is the viewport width, with no site column guides and no centered marketing wrap.
- **rates watch** (custom, research only) defines: Digest, Watchlist, Theses, Run, Config, Settings. Different items, labels, order and surfaces. Same chrome shell, so it reads as one product.
- There is no "Desks" destination. Desks are the picker.

Auth sits outside the frame. The ticker dossier is a deep link from a Holdings row, with no sidebar item and no sixth tab.

## Frames

Start at `index.html`. Frames are grouped there the same way.

| Group | Frames |
|---|---|
| Auth | `00-sign-in` |
| house desk | `01` Brief, `02` Holdings, `03` Theses, `04` thesis detail, `05` Tearsheet, `06` Ledger, `07` Ledger empty, `08` Attribution, `09` ticker dossier, `10` Pipeline. House content pages (Corpus, Book, Profile) are removed. |
| house desk, Settings by plan | `14` Profile, `15` Keys, `16` Brokers, `17` Notifications, `18` Billing (not configured), `19` About, `20` Desk plan, `21` Brief plan |
| desk picker | `30` open on house, `31` open on rates watch, `32` both spines side by side (review aid) |
| rates watch desk | `40` Digest, `41` Watchlist, `42` Theses, `43` Run, `44` Config, `45` to `50` Settings tabs |

Omission by plan is shown, not greyed. Frame `20` (Desk plan) has four Settings tabs and a picker that lists house only. Frame `21` (Brief plan) has three tabs and no Pipeline in the sidebar. Observer matches Brief.

## Locks applied

All twelve Human Gate defaults, with the desk correction on top.

- One Portfolio item with sticky tabs Holdings, Theses, Tearsheet, Ledger, Attribution. House content pages are removed.
- FX Hub, journal, builder, tools, calendars, integrations hub, embedded digichat, command line: not drawn, no chips.
- Paper brokers live in Settings, Brokers. Live execution is one disabled control with a `Paper` chip. No header paper/live switch.
- `/why` and `/pipeline` are redirects in the plan; `/why` is not drawn. In the house desk `/pipeline` is a real item again, because "Desks" is now the picker and not a page.
- Tearsheet is a report: accounting NAV, method, tables. No curve and no second chart library. The LuxAlgo and Gloomberg panes are labeled placeholders, and the LuxAlgo one appears on the ticker dossier only.
- Published strategy tearsheets stay on the digiquant-web showcase.
- Missing marks are an em dash with an `unavailable` badge. Alpha and information ratio show an em dash until 20 daily pairs exist (the window has 16).
- Job words only. digi* names are lowercase.

## Trading and setups engine: future slot, off nav

A future surface that suggests trade setups (paper-first, never live by default) is **omitted from every spine**. No nav row, no chip, no frame. When it exists it is another surface a desk config can include, and it does not gain an order action. This follows the plan's coming-soon rule: omit, or one disabled chip on a page that already shipped.

## Decisions to confirm in review

1. **Pipeline label.** The earlier Pipeline-to-Desks rename is superseded by the correction. The glass-box page is named Pipeline again and belongs to the house desk spine only.
2. **Settings tabs.** The plan's Settings, Pipeline tab (watchlist, themes, budget, schedule) moved into the custom desk's **Config** surface, since those knobs are a desk's configuration. Settings now has six tabs at Studio: Profile, Keys, Brokers, Notifications, Billing, About. This departs from the plan's seven-tab matrix.
3. **Custom desks at Studio.** The plan has overlay work at Studio and above, so the picker lists custom desks from Studio. Below that it lists house only.
4. **rates watch surfaces.** Digest, Watchlist, Run and Config are proposed compositions of data the overlay already carries (watchlist, themes, budget, schedule, run status). The desk is research only and holds no paper book, so it has no NAV. Watchlist and Config are not in the plan's surface catalog.
5. **Settings in every spine.** Settings is account-level but is listed inside each desk's spine so the whole sidebar swaps. Its tabs are identical across desks.
6. **Tier word.** "Desk" is also a plan tier name. Frames use the word `plan` in annotations and never use the tier as a nav label.
7. **Routes for custom desks** are not decided. Annotation strips show `/watchlist (desk: rates watch)` as a placeholder.
8. **Figures.** The plan says phase B draws no sample positions, but a Holdings row is needed to reach the dossier. Figures are layout placeholders, labeled in every frame's annotation strip, and internally consistent: 17 book events replay to 11 open positions, NAV points reproduce the headline figures, and contribution sums to +118 bp. They are not book data.
9. **Command palette** is not drawn. It would list the active desk's spine plus deep links.

## Craft

A dense operator desk, not a site. The layout is full-bleed. Digiquant-web tokens and type are the only thing carried over. Its landing patterns (hero bands, centered column, vertical site guides, one-viewport sections, big lede copy, closing wordmark) are not used.

- **Shell.** Full-bleed, edge to edge: no max-width, no outer page or column guide lines (those belong to the website); only internal panel hairlines. A 40px top bar (pixel wordmark, dated close marks for a handful of names, posture and run status), a 192px numbered rail (desk picker above the spine), a one-line page band (path, title, job, posture), one sticky tab row, and a thin footer line.
- **Content.** Panels tile on a 12-column grid and share hairlines. Brief is a scoreboard strip of eight figures, then Decision and Signals, then allocation, movers and break conditions, then run health. Holdings is grouped by sleeve with weight bars, thesis links and mark source, beside a symbol pane and sleeve exposure. Pipeline is the run canvas, node document, call trace and artifact ledger on one screen.
- **Tokens.** One solid black canvas, hairlines only, radius 0, Inter for prose and JetBrains Mono for chrome and figures at 10.5 to 15px, tabular figures, full-bleed canvas, `NN / label` eyebrows, bracketed micro-labels (`[paper]`, `[close]`), one accent (teal) used for the active rail tick and `[live]` only. Green and red only on signed P&L and mark change.
- **Charts.** The locked plan (decisions 9, section 7) allows no drawn curves in these mocks, no chart library, and LuxAlgo as the only chart backbone. So charts appear as labeled, display-only LuxAlgo and Gloomberg panes beside tables (Holdings, dossier, Watchlist), not as drawn series. Tearsheet stays a report. Weight bars inside table cells are the only drawn data marks.
- No icons, no JS. At most one primary action per page. The dashed strip above every frame is annotation, not product chrome.

## Reviewing locally

The frames are plain files. Serve this folder and open `index.html`:

```bash
cd docs/dashboard-mocks/skeleton && python3 -m http.server 3920
```

After pulling the branch tip, hard refresh (Cmd+Shift+R). Each page links `../canvas/mock.css`.
