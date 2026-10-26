# Live UI inventory

Snapshot of every UI element the shipped surfaces carry, collected from source on
2026-10-26 at `4592153e9a` (branch `change/brand-studio`). Purpose: the list
digiweb builds from. An entry marked **add** is a candidate specimen; **present**
means digiweb already renders it; **skip** means it is vendored, product-local,
or dead.

Method: twelve read-only sweeps, one per surface or family. Each row cites the
source file; counts are per sweep.

| sweep | elements | already in digiweb |
|---|---:|---:|
| digithings.ai | 38 | 1 |
| digiquant.io marketing | 20 | 1 |
| digiquant desk `/app` | 33 | 0 |
| dashboard | 33 | 0 |
| digichat skin | 18 | 0 |
| tracing / digitrace | 17 | 0 |
| TUI clients | 43 | 4 |
| icons / glyphs / emblems | 58 | 3 |
| themes / palettes | 64 | 6 |
| toolbars / menus | 15 | 2 |
| kit coverage gap | 104 kit parts | 25 |
| motion / effects | 19 | 2 |

Totals are overlapping (the same kit part can appear on several surfaces). The
kit sweep is the canonical set: **104 parts, 67 live in at least one surface, 25
shown in digiweb, 45 live but unshown, 37 with no live consumer**.

## digithings.ai (`apps/digithings-web`)

| element | source | add? |
|---|---|---|
| DtNav (kit NavShell composition) | `components/DtNav.tsx:53` | add |
| animated nav wordmark (ScrollBanner) | `app/_nav.tsx:17` | skip — brand studio owns the wordmark |
| NavShell primitive | `packages/ui/src/components/NavShell.tsx:487` | add |
| landing hero (field + wordmark + CTA) | `components/landing/LandingPage.tsx:48` | add |
| PixelField canvas | `components/landing/PixelField.tsx:13` | add (motion) |
| PixelWordmark (kit) | `packages/ui/src/components/landing/PixelWordmark.tsx:13` | present via brand studio |
| hero cue + hero-rise | `LandingPage.tsx:99,55` | add (motion) |
| SectionHead | `components/landing/SectionHead.tsx:7` | add |
| SectionRail | `components/landing/SectionRail.tsx:15` | add |
| WhyStack / WhyPriceTable | `LandingSections.tsx`, `WhyPriceTable.tsx:68` | skip — content |
| ModuleGrid (landing + kit) | `components/landing/ModuleGrid.tsx:94`, `packages/ui/.../ModuleGrid.tsx:309` | add |
| ScrollBanner | `components/landing/ScrollBanner.tsx:16` | present via module gallery |
| QuantSection | `components/landing/QuantSection.tsx:571` | add |
| OpenSource band / OpenSourceLive | `LandingSections.tsx:154`, `OpenSourceLive.tsx:12` | skip — live data |
| Pricing / PricingMatrix | `components/landing/Pricing.tsx:150` | add |
| FaqMorph / FaqList | `FaqMorph.tsx:98`, `LandingSections.tsx:83` | add (motion) |
| LiveAsk / ContactForm | `LiveAsk.tsx:34`, `ContactForm.tsx:32` | skip — live endpoints |
| DtFooter / FooterCells | `components/DtFooter.tsx:40`, `packages/ui/.../FooterCells.tsx:52` | add |
| FooterWordmark | `components/landing/FooterWordmark.tsx:9` | add (motion) |
| SocialRow + vendor glyphs | `packages/ui/src/components/SocialRow.tsx:66`, `icons.tsx:19` | add |
| CtaLink / IconLink / CopyCommand | `packages/ui/src/components/chrome.tsx:102,137`, `docs/CopyCommand.tsx:70` | add |
| Reveal / stagger / entrance | `packages/ui/src/motion/primitives.tsx:48,77,95` | add (motion) |

## digiquant.io marketing (`apps/digiquant-web`)

| element | source | add? |
|---|---|---|
| Band frame + numbered eyebrow | `app/_chrome/Band.tsx:12,77` | add — the baseline cites it |
| LayoutRails (fixed hairlines) | `app/_chrome/LayoutRails.tsx:4` | add |
| Band pin / sticky head | `app/globals.css:331` | add |
| Step header `[ 01 ]` | `app/_bands/start.tsx:10` | add |
| Hero (TopBand + QuantField) | `app/_bands/top.tsx:18`, `_chrome/QuantField.tsx:128` | add |
| QuantWordmark | `app/_chrome/QuantWordmark.tsx:22` | add |
| Metric odometer | `components/dashboard/count-up.tsx:10` | add |
| Strategy card / tearsheet | `components/tearsheet/strategy-card.tsx:21`, `tearsheet-view.tsx:141` | add |
| Chart set (7) | `components/tearsheet/tearsheet-view.tsx:629` | add |
| CTA set / copy commands | `app/_bands/top.tsx:47` | add |
| Nav + footer | `components/site-chrome.tsx:18`, `_chrome/Footer.tsx:11` | add |
| Integration grid | `app/_bands/integrations.tsx:38` | skip — live data |
| Pricing strip | `components/start/pricing-strip.tsx:28` | add |
| Market bar | `app/_chrome/MarketBarShell.tsx:18` | skip — live data |
| TabStrip rail | `components/tearsheet/rail/strategy-rail-live.tsx:19` | add |

## digiquant desk `/app` (`apps/digiquant-web`)

| element | source | add? |
|---|---|---|
| Pane grid 12×12 / mosaic | `components/desk/pages/pane.tsx:21,25` | add — the baseline tile |
| Pane chrome + age badge | `pane.tsx:226,138` | add |
| Pane table / stat row | `pane.tsx:146,119` | add |
| Desk shell / frame / rail | `desk-shell.tsx:23`, `desk-frame.tsx:59`, `desk-nav.tsx:78` | add |
| Panel toolbar (table/chart, chart picker) | `panel-view.tsx:80,96` | add |
| Panel chart + unavailable fallback | `panel-chart.tsx:56,8` | add |
| Desk command (`/`, ⌘K) / shortcuts (`?`) | `desk-command.tsx:12`, `desk-shortcuts.tsx:6` | add |
| Chat thread rows (▸) | `chat-threads.tsx:8` | add |
| Desk picker | `desk-picker.tsx:11` | add |
| Kit DataTable / KpiGrid / Sparkline / StateBlock | `packages/ui/src/components/desk/*` | add |
| OrderBook / SortableTable / MarketBar / StockTicker / PerformanceDashboard / SyncedTearsheet | `packages/ui/src/components/finance-composites/*` | add |
| Command palette | `packages/ui/src/components/command-palette/CommandPalette.tsx:128` | add |
| LiveBadge | `packages/ui/src/components/finance-tearsheet/LiveBadge.tsx:19` | add |
| PriceChart | `packages/ui/src/components/finance-charts/PriceChart.tsx:50` | add |

## dashboard (`apps/dashboard`)

| element | source | add? |
|---|---|---|
| BriefDesk / BriefDeskView / BriefPaneFrame | `components/desk/panes/brief/BriefDesk.tsx:86,57,35` | add |
| DeskPaneChrome | `components/desk/atoms/DeskPaneChrome.tsx:11` | add |
| DeskPipelineFrame / DeskTearsheetFrame | `atoms/DeskPipelineFrame.tsx:20`, `DeskTearsheetFrame.tsx:21` | add |
| DeskState (loading/empty/error) | `atoms/DeskState.tsx:22` | add |
| DeskTable / DeskChart / DeskFeed | `atoms/DeskTable.tsx:63`, `DeskChart.tsx:32`, `DeskFeed.tsx:19` | add |
| time-frame toggle | `panes/brief/bodies.tsx:212` | add |
| DailySnapshotPanel + skeleton/error/empty | `components/overview/daily-snapshot-panel.tsx:88,138,165,211` | add |
| Narrative / Actionable / Risk lists | `daily-snapshot-panel.tsx:374,385,418` | add |
| TodayActionsPanel | `components/overview/today-actions-panel.tsx:108` | add |
| StatCard / Metric | `components/ui.tsx:29`, `tearsheet/DashboardTearsheetView.tsx:101` | add |
| PerformanceTearsheetView / holdings table / open holdings | `DashboardTearsheetView.tsx:173,51,129` | add |
| PortfolioContributionChart / ReturnValue | `PortfolioPerformanceCharts.tsx:18`, `DashboardTearsheetView.tsx:41` | add |
| pipeline trace ledger | `components/pipeline/PipelineTraceLedger.tsx:160` | add — trace design |
| globals chrome / print tearsheet | `app/globals.css:20,138,484` | add |

## digichat skin (`apps/digichat`, `packages/ui`)

| element | source | add? |
|---|---|---|
| composer (states, dropzone, centered empty) | `packages/ui/src/components/chat/skins/base/thread.tsx:504` | add |
| composer attachments | `chat/stock/attachment.aui.tsx:237` | add |
| model picker | `skins/base/thread.tsx:100` | add |
| `@` mention + `/` slash menu | `skins/base/thread.tsx:535,537-541` | add |
| thinking indicator | `skins/base/thread.tsx:620` | add |
| tool running status | `skins/base/thread.tsx:716-719` | add |
| done/error status | `chat/stock/message-error.aui.tsx:35`, `thread.tsx:774-779` | add |
| tool card / tool group | `chat/stock/tool-fallback.aui.tsx:836`, `tool-group.aui.tsx:225` | add |
| reasoning disclosure | `chat/stock/reasoning.aui.tsx:84` | add |
| assistant / user rows + action bars | `skins/base/thread.tsx:685,817,765,844` | add |
| welcome / suggestion chips | `skins/base/thread.tsx:239,205-211` | add |
| widget frame | `chat/ChatWidgetFrame.tsx:38` | add |
| thread header / model badge / keyboard hints | none | gap — do not invent |

## tracing / digitrace

| element | source | add? |
|---|---|---|
| trace waterfall emblem | `packages/ui/src/components/emblems.tsx:79` | add (icons) |
| chat tool/trace row | `packages/ui/src/components/chat/ChatToolCall.tsx:1` | add |
| status marks `… ✓ ✕` | `ChatToolCall.tsx:45` | add |
| trace spacing tokens | `chat/trace-spacing.ts:1` | add (foundations) |
| trace row rhythm | `styles/chat-aui.css:719` | add |
| pipeline trace ledger + run header + filters | `apps/dashboard/components/pipeline/PipelineTraceLedger.tsx:160,284,309` | add |
| span kind icons | `PipelineTraceLedger.tsx:131` | add |
| trace empty states | `PipelineTraceLedger.tsx:137` | add |
| latency badge / status badges | `PipelineTraceLedger.tsx:211,204` | add |
| call-trace table | `apps/digiquant-app/components/blocks-pipeline.tsx:132` | add |
| Langfuse trace UI | `apps/digitrace-langfuse` | skip — third-party screen |

## TUI clients

| element | source | add? |
|---|---|---|
| frame chrome (digiquant / digichat) | `clients/digiquant-tui/src/app.tsx:488`, `digichat-tui/src/app.tsx:469` | add |
| recorded frame type | `packages/tui-frame/src/record.ts:13` | add |
| status bar + key hints | `digichat-tui/src/app.tsx:543,548`, `digiquant-tui/src/app.tsx:618,471` | add |
| slash / command rows | `digichat-tui/src/palette.ts:174,363`, `digiquant-tui/src/command.ts:98` | add |
| transcript rows / skeleton / welcome | `digichat-tui/src/chrome.ts:61,51,126` | add |
| tables + braille charts | `digiquant-tui/src/pages/shape.ts:8`, `charts.ts:113,149,188,230,256` | add |
| chart ramps / glyph sets | `digiquant-tui/src/charts.ts:35`, `digichat-tui/src/theme.ts:17` | add (foundations) |
| rail / nav | `digiquant-tui/src/rail.ts:54,101`, `digichat-tui/src/app.tsx:471` | add |
| boot / loading | `digichat-tui/src/chrome.ts:153`, `packages/ui/.../ContainerBootLoader.tsx:58` | partial |
| hero banner half-block / ANSI | `packages/hero-banner/src/tui.ts:71,224` | add |

## Icons, glyphs, emblems

| family | items | source |
|---|---|---|
| vendor logos | GitHub, Google, LinkedIn, X | `packages/ui/src/components/icons.tsx:19,36,67,84` |
| module marks | DigiquantMark, Wordmark | `components/symbols/marks.tsx:30,102` |
| terminal marks | TerminalMark, TerminalWordmark, HairlineWordmark | `components/symbols/terminal-marks.tsx:103,139,204` |
| emblems (13) | digigraph, digiquant, digisearch, digichat, digikey, digitrace, digibot, digibase, digistore, digivault, digilink, research, portfolio, execution | `components/emblems.tsx:35-160` |
| TUI glyphs | digichat 10, digivoice 7 | `clients/digichat-tui/src/theme.ts:17`, `digivoice-tui/src/theme.ts:22` |
| favicons | dt/dq light+dark, dashboard | `apps/*/public/favicon*.svg` |
| integration marks | GloombergMark, IntegrationMark, RowMark | `apps/digiquant-web/components/integrations/marks.tsx:31,46,128` |
| status glyphs | `▲ ▼ ↕ ● ✕ ✓ ·` | finance/chat/search |
| generic | lucide check/chevron/x | `packages/ui/src/ui/*` |

58 distinct glyphs, 3 duplicated across apps. Add a `/icons` page grouped by
family; flag the duplicates rather than copying them again.

## Themes and palettes

| family | count | source |
|---|---:|---|
| platform palettes | 32 | `packages/design/palettes.css:1` |
| livery accents | 18 | `packages/design/tokens.css:8-25` |
| livery scope classes | 14 | `tokens.css:53-66` |
| dark/light | 2 | `tokens.css:68,124` |
| chat catalog skins | 11 | `docs/digichat/DESIGN-THEMES.md:41` |
| chat density | 3 | `packages/ui/src/styles/chat-aui.css:190` |
| table density | 3 | `packages/ui/src/ui/table.tsx:12` |
| ThemeProvider | 1 | `packages/ui/src/components/ThemeProvider.tsx:115` |

Add a `/themes` page: 32 palette swatches, 18 liveries, both modes, the kit
Table density, and the chat density switch in a live thread. Flag
`--accent-digivoice`, `-digillm`, `-digibook`, `-digidev` as tokens with no
scope class, and the vendored chat skins as not-for-restyle.

## Toolbars and menus

| element | source | add? |
|---|---|---|
| CommandPalette (⌘K) | `packages/ui/src/components/command-palette/CommandPalette.tsx:128` | add |
| NavShell dropdowns | `packages/ui/src/components/NavShell.tsx:487` | add |
| TerminalManifest | `packages/ui/src/components/TerminalManifest.tsx:71` | add |
| DropdownMenu / Select / Tabs | `packages/ui/src/ui/{dropdown-menu,select,tabs}.tsx` | add |
| DeskCommand / DeskShortcuts | `desk-command.tsx:12`, `desk-shortcuts.tsx:6` | add |
| EmbedComposerMenu (slash) | `apps/digichat/src/components/stock/embed-composer-menu.tsx:445` | add |
| DigichatComposerToolbar | `packages/ui/src/components/chat/skins/digichat-composer-toolbar.tsx:20` | add |
| PipelineCanvas toolbar / PanelView toolbar | `apps/dashboard/components/pipeline/PipelineCanvas.tsx:611`, `panel-view.tsx:96` | add |
| Mermaid zoom toolbar | `packages/ui/src/components/assistant-ui/elements/mermaid-diagram.tsx:208` | add |
| SkipLink | `packages/ui/src/components/chrome.tsx:65` | present (rtl already uses kit) |

## Kit coverage

104 kit parts: 67 live somewhere, 25 in digiweb, 45 live but unshown, 37 unused.

Highest-value additions, ranked by live use:

1. `components/chrome` — NavShell, Footer, ModuleCard, CtaLink, IconLink (24 files)
2. `components/finance-tearsheet` — print-grade tearsheets (22 files)
3. `components/document` — framed document grammar (15 files)
4. `components/data-layout` — bento, frames, feature cells (12 files)
5. `segmented-control` (10 files)
6. `components/contact` (9 files)
7. `components/repo-activity` (8 files)
8. `components/emblems` (8 files)
9. `components/conviction` (8 files)
10. `icon-button` (6 files)

Unused anywhere (37): the 11 primitives `avatar, breadcrumb, form, kbd, pager,
pagination, radio-group, search-bar, separator, tabs, tags-input`; and 26
composites including `Spinner`, `TerminalManifest`, the chat transcript family,
`graph`, `metrics/*`, `pricing/Pricing`, `stages/NumberedStages`,
`symbols/terminal-lockup`, `terminal/*` loaders, `typography/*` reveals,
`motion/scrolly`, `navigation/hashScroll`. Do not surface these as canon; some
are candidates for deletion.

## Motion

| element | trigger / timing | source |
|---|---|---|
| Reveal | scroll once, 0.6s ease, y16 | `packages/ui/src/motion/primitives.tsx:48` |
| Stagger / HeroEntrance | scroll / mount, 0.06s | `primitives.tsx:77,95` |
| ScrollyFeatures | scroll pinned, stepper fallback | `motion/scrolly.tsx:45` |
| HorizontalScrollTrack | scroll → x, derived runway | `effects-chrome/HorizontalScrollTrack.tsx:372` |
| TabStrip ink | click/resize/dir | `effects-chrome/TabStrip.tsx:98` |
| ToastStack | push, 0.26s | `effects-chrome/ToastStack.tsx:63` |
| RotatingPrompts | 3200ms interval | `effects-chrome/RotatingPrompts.tsx:45` |
| StackingPanels | scroll transform | `effects-chrome/StackingPanels.tsx:42` |
| WordReveal / MotionReveal / TypewriterReveal | scroll, 150vh pinned / unpinned | `components/typography/*` |
| Marquee | 34s loop, hover pin | `components/marquee/Marquee.tsx:119` |
| PixelField | rAF canvas, static under reduce | `apps/digithings-web/.../pixel-field-core.ts:80` |
| HeroBanner | build once/tab, settled under reduce | `packages/hero-banner/src/web.tsx:22` |
| CountUp | scroll, 1100ms | `apps/digiquant-web/.../count-up.tsx` |
| chat block caret | focus, 1.06s | `apps/digichat/src/styles/product-chrome.css:177` |

All 19 effects honour `prefers-reduced-motion`.

## Next digiweb additions, in order

1. `/surfaces` — one live proof per surface: digithings hero, digiquant band,
   desk pane, dashboard brief, chat thread. Use the real grammar from this doc.
2. `/chat` — composer, slash menu, status marks, tool card, reasoning, rows.
3. `/trace` — trace ledger, span kinds, latency/status badges, empty states.
4. `/icons` — the 58 glyphs grouped by family, duplicates flagged.
5. `/themes` — 32 palettes, 18 liveries, dark/light, density switches.
6. `/toolbars` — command palette, nav dropdowns, desk command, shortcuts.
7. `/tui` — recorded frames + braille charts + glyph ramps.
8. `/motion` — the 19 effects with reduced-motion toggles.

Do not treat this list as canon until each specimen is composed from the kit and
the live surface's own source. The baseline rules on `/` stay the gate.
