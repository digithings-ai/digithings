# Why-band copy deck (Refs #4429)

Working file for the `#why` landing band. Iterate on the WORDING here first;
the UI migration (diagrams, tour, styles) is a secondary step. Nothing in this
file renders — `WhyStack.tsx` + `lib/whyStack.ts` are still the live copy until
we migrate.

Naming rules: product names always lowercase (digithings, digichat, digillm,
digisearch, digivault, digigraph, digikey, digismith, digiclaw, digibase,
digiquant). No vendor/brand names anywhere. No performance figures, no
live-trading promises, no new factual claims.

Framing (agreed): less you-vs-theirs, less owning-vs-renting. The themes are
custom builds, modularity (one layer or all), no lock-in, price optimization.
Owning is part of it, never the headline. digiquant stays OUT — it is a
product built on the infrastructure, not a layer of it.

---

## 1. Headline (two-tone: dim half / bright half)

Current live:

> Their AI stack,
> or the digithings stack.

Candidates:

- [ ] H1 (live): Their AI stack, / or the digithings stack.
- [ ] H2: One fixed AI stack, / or a digithings stack you compose.
- [ ] H3: Their stack, rented by the meter. / Your stack, composed by the layer.
- [ ] H4: _______________________________________________ (yours)

## 2. Subtext / lede (AI infrastructure lives HERE, not in the headline)

Current live:

> Off-the-shelf AI arrives as one fixed shape — models, index, data and
> machines behind a single interface, metered and versioned on somebody
> else's schedule. digithings is the same AI infrastructure as pieces you
> compose yourself: start with the layer that hurts, swap any piece without
> migrating, pay your provider's own rates. Owning the stack is part of
> it — never being locked in is the point.

Rewrite notes (open):

- Sentence 1 (their shape): is "metered and versioned" the sharpest critique,
  or should it be lock-in ("you can't swap a layer")?
- Sentence 2 (our shape): does "pieces you compose yourself" land, or do we
  want "custom build" language explicitly?
- Sentence 3 (owning, de-emphasized): keep as the closer, or cut entirely?

Draft v2 (edit freely):

> _______________________________________________
>
> _______________________________________________
>
> _______________________________________________

## 3. Left side — their stack (stays generic, no brands, no module names)

- Tag: `their stack`
- Diagram title: The fixed AI stack
- Boundary: one vendor's roadmap · one account · one bill you don't set
- Boxes: your product → their interface → their models / their index /
  their data store → their monitoring / their machines / their terms
- Edges: every request · per-token · per-query · per-gigabyte · per-span · metered
- Caption: Every edge metered — per-token · per-query · per-gigabyte

Walk (4 steps, rented-side critique — check against new framing):

1. You own one box. They own the rest.
2. One door in, and they hold the key.
3. Every layer below is rented by the meter.
4. One wall, and it does not open.

Open question: do steps 3–4 lean too hard on renting (the thing we're
de-emphasizing)? Possible tilt: fixed shape → locked door → metered edges →
no exit.

## 4. Right side — digithings stack (named modules = the parts list)

- Tag: `digithings stack`
- Diagram title: The digithings stack you compose
- Boundary: digithings · take one module or run them all
- Boxes (8): digichat · chat interface / digigraph · request router /
  digillm · model gateway / digisearch · vector index / digivault · notes
  vault / digiclaw · scheduler / digismith · run traces / digikey · your keys
- Caption: Every box a module — take one or run them all · digibase under
  all of them

Walk (5 steps — check each against the four themes):

1. One fixed shape, or pieces you compose. (custom build)
2. Your front door, your router. — digichat + digigraph (modularity)
3. Any model. Your keys, your rates. — digillm (price)
4. Your index, your vault. — digisearch + digivault (no lock-in)
5. Runs itself. Proves itself. — digiclaw + digikey + digismith (trust)

Open questions:

- Is step 5 doing too much (three boxes, scheduler + keys + traces)?
- Should price get its own step, or is it fine inside step 3?
- digibase/digistore/digilink live only in the caption + mosaic — enough?

## 5. Migration checklist (secondary step, NOT now)

- [ ] Freeze headline + lede here, then port to `WhyStack.tsx`
- [ ] Freeze box labels, then port to `DIGITHINGS_ARCH` in `lib/whyStack.ts`
- [ ] Freeze steps, then port to `OWNED_TOUR_STEPS` / `RENTED_TOUR_STEPS`
- [ ] Freeze tags + captions, then port side props + `diagrams.css` hooks
- [ ] Scroll the band on :3900 (desktop walk + static fallback), then commit
