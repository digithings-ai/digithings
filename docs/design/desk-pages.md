# Desk pages

Public desk pages, in rail order. One page at a time: draw it in the terminal, then the same blocks on the web desk.

The component set is the gloomberb pane body (stat, then table or chart, then an empty sentence) from [the function matrix](../superpowers/plans/2026-09-30-gloomberb-function-matrix.md). OpenTUI 0.5 draws `box`, `text`, and `input`. A chart is one row of block characters from a numeric series the payload already contains. There is no canvas. A missing series is not a flat line. An unreachable API, a stub envelope, or an empty block stays the sentence that read already returns.

Invite-only desks are not on this list. Do not invent rows, prices, or sessions.

- [x] `/brief` Brief — stat (NAV, day, since inception, invested, overlay) and a session table when `session_events` has rows. Live marks: stat, plus a symbol table when `universe` has names. Decision: the lead and body, or the empty sentence. Signals, risks, and movers: a table, or the empty sentence. Run health: a stat, or the empty sentence. No chart: none of these reads return a series.
- [x] `/portfolio` Portfolio — stat from the envelope (NAV tip, invested, cash). Sleeves: table. Movers: table. Book: table from allocation rows. NAV: chart from `points` when that array has two or more values, otherwise the empty sentence, plus the point table. Drawdown: stat (max, current) and a chart only when `series` has values.
- [x] `/portfolio/holdings` Holdings — table of the enriched book rows, or the empty sentence.
- [x] `/portfolio/attribution` Attribution — table of sleeves and names, or the empty sentence.
- [x] `/portfolio/ledger` Ledger — table of position events, and a cash table, or the empty sentence for a block with no rows.
- [x] `/portfolio/tearsheet` Tearsheet — performance stat. NAV table from the series, and a chart only when `points` has two or more values. Benchmarks table. Empty sentence per block when that read is empty.
- [x] `/portfolio/theses` Theses — stat of the counts when theses exist, then the thesis table. Signals table. Empty sentence when a list is empty.
- [x] `/pipeline` Pipeline — run-health stat. Narrative sentence. Artifact table. Graph as a node table (no canvas). Node document sentence. Call-trace table. Empty sentence per block when that read is empty.
- [x] `/strategies` Strategies — summary stat, catalog table, deployments table. An empty deployment store stays its empty sentence.
- [ ] `/strategies/detail` Detail — overview fields as a stat or table. Parameters table. Track record: stat from the card, table of points, and a chart only when `points` has two or more values. Runs table. Empty sentence when a store is empty.
- [ ] `/strategies/deploy` Deploy — targets table, plan steps table, draft fields. Empty sentence when a list is empty. The draft is not an order.
- [ ] `/tools/terminal` Terminal — not drawn in this terminal. Web keeps the existing link. No invented quotes.
- [ ] `/tools/charts` Charts — not drawn in this terminal. Web chart stays on bars the API returns. No invented prices.
- [x] `/tools/chat` digichat — threads in the desk rail. One sentence when digichat is not configured. No second sidebar and no read footer. No invented messages.
