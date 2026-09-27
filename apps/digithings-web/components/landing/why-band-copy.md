# Why-band copy deck (Refs #4429)

Working file for the `#why` landing band. Pick a version, then we iterate on
it here. UI migration (diagrams, tour, styles) is a secondary step — nothing
in this file renders. `WhyStack.tsx` + `lib/whyStack.ts` stay live until a
version freezes.

Naming rules: product names always lowercase (digithings, digichat, digillm,
digisearch, digivault, digigraph, digikey, digismith, digiclaw, digibase,
digiquant). No vendor/brand names anywhere. No performance figures, no
live-trading promises, no new factual claims.

Agreed framing: less you-vs-theirs, less owning-vs-renting. Themes are custom
builds, modularity (one layer or all), no lock-in, price optimization. Owning
is part of it, never the headline. digiquant stays OUT — a product built on
the infrastructure, not a layer of it.

Shared inventory (same in all versions unless noted):

- Left tag: `their stack` · left title: The fixed AI stack · boundary: one
  vendor's roadmap · one account · one bill you don't set.
- Left boxes: your product → their interface → their models / their index /
  their data store → their monitoring / their machines / their terms.
- Left edges: every request · per-token · per-query · per-gigabyte · per-span
  · metered. Left caption: Every edge metered — per-token · per-query ·
  per-gigabyte.
- Right tag: `digithings stack` · right title: The digithings stack you
  compose · boundary: digithings · take one module or run them all.
- Right boxes (8): digichat · chat interface / digigraph · request router /
  digillm · model gateway / digisearch · vector index / digivault · notes
  vault / digiclaw · scheduler / digismith · run traces / digikey · your keys.
- Right caption: Every box a module — take one or run them all · digibase
  under all of them.

---

## Version A — "Compose it yourself" (evolution of the live band)

Best if: we want continuity with what's on :3900 now, sharpened.

Headline:

> Their AI stack,
> or the digithings stack you compose.

Lede:

> Off-the-shelf AI arrives as one fixed shape — models, index, data and
> machines behind a single interface, metered and versioned on somebody
> else's schedule. digithings is the same AI infrastructure as pieces you
> compose yourself: start with the layer that hurts, swap any piece without
> migrating, pay your provider's own rates. Owning the stack is part of
> it — never being locked in is the point.

Left walk (unchanged):

1. You own one box. They own the rest.
2. One door in, and they hold the key.
3. Every layer below is rented by the meter.
4. One wall, and it does not open.

Right walk:

1. One fixed shape, or pieces you compose.
2. Your front door, your router. — digichat + digigraph
3. Any model. Your keys, your rates. — digillm
4. Your index, your vault. — digisearch + digivault
5. Runs itself. Proves itself. — digiclaw + digikey + digismith

---

## Version B — "Never locked in" (freedom-first)

Best if: the sharpest pain we sell against is the roadmap trap, not the bill.

Headline:

> One vendor's roadmap,
> or your own stack, layer by layer.

Lede:

> Every off-the-shelf platform asks the same question: how much of your
> stack are you willing to rent back? digithings asks a different one:
> which layer do you want to take back first? Take the chat interface this
> quarter and the model gateway next — each piece runs on your hosts, your
> keys, your bill, and nothing you adopt locks the rest.

Left walk (tilted toward no-exit):

1. You own one box. They own the rest.
2. One door in, and they hold the key.
3. Every layer below is rented by the meter.
4. No exit, only upgrades — theirs.

Right walk:

1. Leave whenever — including piece by piece.
2. Your front door, your router. — digichat + digigraph
3. Any model, no migration. — digillm
4. Your index, your vault, your stores. — digisearch + digivault
5. Runs itself. Proves itself. — digiclaw + digikey + digismith

---

## Version C — "No middleman's meter" (price-first)

Best if: the bill is the wedge — infra buyers feel the margin first.

Headline:

> Metered by them,
> or priced by your own providers.

Lede:

> The managed AI bill is a margin on top of the same models, indexes and
> machines you could call directly. digithings removes the middleman's
> meter: your keys call the providers, your hosts run the rest, and every
> layer stays swappable when a cheaper option appears. Start with one
> module — each layer you take back is one less margin you pay.

Left walk (tilted toward the meter):

1. You own one box. They own the rest.
2. One door in, and they hold the key.
3. Every edge has a meter on it.
4. One bill, and you don't set it.

Right walk (price up front):

1. Same stack. No middleman.
2. Any model, your rates. — digillm
3. Your front door, your router. — digichat + digigraph
4. Your index, your vault. — digisearch + digivault
5. Runs itself. Proves itself. — digiclaw + digikey + digismith

---

## Scorecard (fill together after the pick)

- [ ] Pick: A / B / C / hybrid (note: ___________)
- [ ] Left walk step 4: keep, or soften the renting language further?
- [ ] Right walk step 5: three boxes in one step — split, or keep?
- [ ] Price: own step (C), inside the models step (A), or ambient (B)?
- [ ] digibase/digistore/digilink: caption + mosaic enough, or name them?

## Migration checklist (secondary step, NOT now)

- [ ] Freeze headline + lede here, then port to `WhyStack.tsx`
- [ ] Freeze box labels, then port to `DIGITHINGS_ARCH` in `lib/whyStack.ts`
- [ ] Freeze steps, then port to `OWNED_TOUR_STEPS` / `RENTED_TOUR_STEPS`
- [ ] Freeze tags + captions, then port side props + `diagrams.css` hooks
- [ ] Scroll the band on :3900 (desktop walk + static fallback), then commit
