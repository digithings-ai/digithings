## Goal

Implement the frontend design evolution plan in [`frontend/design/EVOLUTION.md`](https://github.com/digithings-ai/digithings/blob/develop/frontend/design/EVOLUTION.md): borrow advanced UI/UX patterns from Graphite (scroll/motion), Cursor (bento, literal CTAs), and x.ai (mono infrastructure, flat dashboards) across **digithings.ai**, **digiquant.io**, **DigiChat**, and **Olympus/twelve-x** — without copying any reference site literally.

**Blend:** Cursor page map · Graphite scroll craft · xAI mono on dashboards · our mesh/grain/module accents.

## Child issues

Full index: [`docs/agent-backlog/design-evolution/INDEX.md`](https://github.com/digithings-ai/digithings/blob/develop/docs/agent-backlog/design-evolution/INDEX.md)

### Phase A — Tokens & docs
- [ ] #1201 — Motion & layout tokens
- [ ] #1219 — Typography README (Geist, not Inter)

### Phase B — Shared primitives (`frontend/design/`)
- [ ] #1202 — ProductFrame
- [ ] #1203 — BentoGrid
- [ ] #1204 — TrustStrip + reveal-up
- [ ] #1205 — ScrollyFeatures
- [ ] #1206 — StatCounter
- [ ] #1207 — ChangelogBand
- [ ] #1208 — CapabilityCard
- [ ] #1209 — CodeSampleBand

### Phase C — Landing realignment
- [ ] #1210 — digithings.ai hero
- [ ] #1211 — digithings.ai bento modules
- [ ] #1212 — digithings.ai changelog band
- [ ] #1213 — digiquant.io hero
- [ ] #1214 — digiquant.io bento grid
- [ ] #1215 — digiquant.io Olympus progress rail

### Phase D — Dashboard & product surfaces
- [ ] #1216 — Olympus glass → surface
- [ ] #1217 — twelve-x utility polish
- [ ] #1218 — DigiChat product-as-hero (#240 prerequisite)
- [ ] #1220 — Olympus subpage chrome docs

### Phase E — Primitives, copy & landing polish
- [ ] #1221 — E1 HorizontalScrollBand
- [ ] #1222 — E2 ClosingCtaBand
- [ ] #1223 — E3 FaqAccordion + PricingMatrix
- [ ] #1224 — E4 HeroFeaturePicker
- [ ] #1225 — E5 AnnouncementBar (content-gated)
- [ ] #1226 — E6 digiquant.io pricing FAQ + matrix
- [ ] #1227 — E7 Both landings closing CTA wiring
- [ ] #1228 — E8 COPY_GUIDE.md
- [ ] #1229 — E9 TrustStrip integration logos
- [ ] #1230 — E10 CaseStudyCard (P3, content-gated)
- [ ] #1231 — E11 Olympus status dot → DigiSmith (P3)

**Deep spec:** [`docs/superpowers/specs/2026-06-30-frontend-design-evolution-layers-design.md`](https://github.com/digithings-ai/digithings/blob/develop/docs/superpowers/specs/2026-06-30-frontend-design-evolution-layers-design.md)

## Acceptance Criteria

- [x] All child issues filed and linked above
- [ ] `frontend/design/EVOLUTION.md` phase checkboxes updated as children complete
- [x] `docs/agent-backlog/INDEX.md` includes a "Design evolution" theme row

## Related

- Parent: #235 (shared design language epic)
- Also: #1195 (hoist landing primitives), #240 (DigiChat tokens)
- Strategy: [`frontend/design/EVOLUTION.md`](https://github.com/digithings-ai/digithings/blob/develop/frontend/design/EVOLUTION.md)
- Scans: [`frontend/design/references/scans/`](https://github.com/digithings-ai/digithings/blob/develop/frontend/design/references/scans/INDEX.md)

## Out of Scope

- Re-auditing reference sites (unless they ship major redesigns)
- Live-trading UI changes
- Auth/crypto changes

## Human Gate Required?

- [ ] No
