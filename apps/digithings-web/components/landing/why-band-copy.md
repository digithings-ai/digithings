# Why-band copy deck (Refs #4429)

Working file for the `#why` landing band. Review the live variants at
`/variants/why-copy`, pick a direction, iterate HERE first. UI migration
(diagrams, tour, styles) is a secondary step — nothing in this file renders.

Naming rules: product names always lowercase (digithings, digichat, digillm,
digisearch, digivault, digigraph, digikey, digismith, digiclaw, digibase,
digiquant). No vendor/brand names anywhere. No performance figures, no
live-trading promises, no new factual claims.

Agreed framing: less you-vs-theirs, less owning-vs-renting. Themes are custom
builds, modularity (one layer or all), no lock-in, price optimization. Owning
is part of it, never the headline. digiquant stays OUT — a product built on
the infrastructure, not a layer of it.

Diagrams must read like real infrastructure to a developer/architect:
protocol-labeled wires (HTTPS/SSE/OpenAI API/MCP/OTLP/your key), accurate
topologies, module names on the digithings side, generic categories on the
fixed side. No new glyphs (the mermaid doc-export grammar knows five plates).

---

## Version A — "One wall, or eight seams" (lock-in, guided walk)

- Headline: One wall around everything, / or seams everywhere you need them.
- Lede: fixed-shape critique → same infra cut along its seams → the
  difference is whether anything in the drawing can move.
- Left: 3-box monolith (your product → their interface → 8 layers · 0 seams,
  wired HTTPS / metered · opaque), boundary "one bill · one roadmap · no
  seams". 3 walk steps (door / wall / bill).
- Right: open-hub module map with a "swap any box" hot-path group and
  protocol wires. 5 walk steps (compose / front door / models / knowledge /
  runs-proves).
- Open: does the monolith's single "8 layers" box underplay the fixed shape,
  or is the condensation the point?

## Version B — "Start with the layer that hurts" (modularity, 4 stages)

- Headline: Start with the layer that hurts, / end with a stack that's yours.
- Lede: nobody rips out eight layers at once; pain-arrival adoption order.
- Four cumulative static diagrams, chat+index → +router/gateway →
  +vault/keys → +scheduler/traces, wires in protocol language
  (HTTPS/SSE/your key/HTTP/MCP/your rates/OTLP/interval). No scroll-walk.
- Open: stage 2 jumps two modules at once (router + gateway) — split it?

## Version C — "The invoice duel" (price, graphs + ledger)

- Headline: Metered by them, / or priced by your own providers.
- Lede: managed bill as margin; your keys, your hosts; one less margin per
  layer taken back.
- Graphs: metered fixed stack with a vendor-invoice box collecting every
  meter vs two-lane direct build (your hosts | your providers, billed to
  you). Ledger below, meters only, no figures.
- Open: ledger + two graphs — too much for one version, or belt and braces?

## Scorecard (fill together after the pick)

- [ ] Pick: A / B / C / hybrid (note: ___________)
- [ ] Price: own version (C), inside the models step, or ambient?
- [ ] digibase/digistore/digilink: caption + mosaic enough, or name them?

## Migration checklist (secondary step, NOT now)

- [ ] Freeze headline + lede + walks here, then port to `WhyStack.tsx` /
  `lib/whyStack.ts`
- [ ] Freeze specs (`whyDiagrams.ts` / `whyCopyVariants.ts` carry them
  review-side), then port the winner's pair
- [ ] Scroll the band on :3900 (desktop walk + static fallback), then commit
