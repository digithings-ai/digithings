# Home page — what the reference templates actually do

**Date:** 2026-09-21 · **Context:** after V1–V8 were judged "basic, not polished". The owner
asked us to find real practitioner templates instead of inventing composition. This is what
they do, read from source rather than from screenshots.

## The finding in one line

Our V8 is **flat cards on a flat page**. Every good template below is the same two things:
**structural geometry that runs the full height of the viewport** (so the page reads as one
built object), and **layered depth on the hero artefact** (so the product shot sits *above*
the page rather than inside a box on it). We had neither. That is the whole gap.

## What we looked at

| Source | License | Why it matters |
|---|---|---|
| **launch-ui/launch-ui** (857★, 152 forks) | MIT | Explicitly "for Developer Tools, AI-Powered Applications, technical products" — our exact audience. Next.js 16, Tailwind v4, shadcn/ui, React 19. Same stack as us. |
| tailark | — | shadcn marketing blocks. Site is JS-rendered; not source-readable without a browser. |
| shadcnblocks (Plasma / Meridian / Mainline) | paid | 100+ components, 14–27 pages, Figma included. Plasma is the "developer SaaS" sibling we'd want if we paid. |
| shadcn.io / 21st.dev registries | mixed | Block catalogues; useful as a source of individual sections, not as architecture. |

Launch UI is the one to model on: **free, MIT, same stack, and built for our category.**

## The five techniques, from source

### 1. Persistent vertical layout lines

```tsx
// components/ui/layout-lines.tsx
<section className="pointer-events-none fixed inset-0 top-0">
  <div className="max-w-container line-y line-dashed mx-auto flex h-full flex-col" />
</section>
```

```css
@utility line-y { border-width: 0 var(--line-width, 0); }  /* left + right only */
@utility line-dashed { border-dashed; }
```

A **fixed, full-viewport-height pair of dashed vertical rules** at the container's edges, mounted
once at the top of the page and `pointer-events-none`. Every section then sits between them. This
is the single biggest thing our V8 lacks — it is what makes the page read as one continuous
document rather than a stack of bordered boxes. It costs ~6 lines. V2/V8's `DocumentFrame` was
*literal* side borders on a real element; this is a fixed overlay, so it survives scrolling and
never fights a section's own width.

### 2. The gradient-clipped headline

```tsx
<h1 className="from-foreground to-foreground dark:to-muted-foreground relative z-10
               inline-block bg-linear-to-r bg-clip-text text-4xl leading-tight font-semibold
               text-balance text-transparent drop-shadow-2xl sm:text-6xl md:text-8xl md:leading-tight">
```

Note `md:text-8xl` — a genuinely **big** hero headline, gradient-clipped from full ink to muted,
with `drop-shadow-2xl`. Our hero tops out at `--type-hero` = `clamp(2rem, 4.5vw, 2.75rem)`, i.e.
44px on a desktop. Theirs is 96px. We are not "smaller type, more utilitarian" — we are *timid*,
and the page reads as under-designed because the most important element on it is set at body scale.

### 3. Mockup + frame + glow (the hero artefact)

```tsx
<MockupFrame className="animate-appear opacity-0 delay-700" size="small">
  <Mockup type="responsive" className="bg-background/90 w-full rounded-xl border-0">
    {mockup}
  </MockupFrame>
  <Glow variant="top" className="animate-appear-zoom opacity-0 delay-1000" />
```

The product shot is a **three-layer artefact**: a mockup *frame* (browser chrome), the mockup
inside it, and a **`Glow` light source** behind/above it. Plus `fade-bottom` on the section so the
artefact bleeds into the page instead of stopping at a hard edge. We have `ProductFrame` (a crop)
and nothing else — no frame treatment, no glow, no bleed.

### 4. Staggered entrance choreography

```css
--animate-appear: appear 0.6s forwards ease-out;
@keyframes appear {
  0%   { opacity: 0; transform: translateY(1rem); filter: blur(0.5rem); }
  50%  { filter: blur(0); }
  100% { opacity: 1; transform: translateY(0); filter: blur(0); }
}
```

Every element in the hero carries `animate-appear opacity-0 delay-100`, `delay-300`, `delay-700`,
`delay-1000` — a **staged reveal**: badge → headline → buttons → mockup → glow. Note `forwards`
with `opacity-0` as the resting state, so nothing flashes. This is ~20 lines of CSS and is most of
what "polished" subjectively feels like on first load.

### 5. The @utility token vocabulary

```css
@utility glass-1 { @apply border-border from-card/80 to-card/40 border bg-linear-to-b; }
@utility fade-bottom { mask-image: linear-gradient(to top, transparent 0%, black 35%); }
@utility line-dashed { @apply border-dashed; }
```

A small set of **named, composable utilities** — `glass-1…5`, `fade-{x,y,top,bottom,left,right}`
(and `-lg` variants), `line-{x,y,t,b}`, `line-dashed` — wired into their token layer. Sections
compose these instead of inventing one-off classes. This is exactly the discipline our own canon
enforces, and it is how they get consistency across 100+ blocks.

## Smaller things worth stealing

- **Stats set as a gradient number + suffix + label + description**, four across, `md:text-6xl`
  numerals. We render `OdometerStrip` cells that are much quieter.
- **`grid-cols-2 sm:grid-cols-3 lg:grid-cols-4` with `auto-rows-fr`** for feature items, and
  `gap-0` on mobile / `gap-4` on desktop — tight, deliberate rhythm rather than uniform gaps.
- **`text-balance`** on headlines and `text-pretty` on descriptions, throughout.
- **`max-w-container` (1280) / `max-w-container-lg` (1536)** as the only two width registers.
- Their nav has **static and floating variants**; the floating one is what our V5 wanted.

## What is wrong with V1–V8, stated plainly

1. **No structural geometry.** Nothing spans the viewport; the page is boxes inside a column.
2. **The hero is too small.** `--type-hero` (44px) where a dev-tools page wants 72–96px.
3. **No depth anywhere.** Flat cards on a flat ground; no frame/glow/bleed on any artefact.
4. **No entrance choreography.** Everything is just *there* on load.
5. **Inconsistent internal rhythm.** Padding and gaps were chosen per section by hand — the "ad
   hoc" the owner named.
6. **The stack showcase was the one original idea**, and it is fighting a container that gives it
   no room (5 columns beside a card, cells 7rem tall).

## Recommended direction

Rebuild the home page on **Launch UI's architecture**, not on our own invention:

1. Add `LayoutLines` (fixed dashed container rules) and mount it once.
2. Promote a real **hero scale** into the type ladder, and set the headline with the gradient clip.
3. Build a **`MockupFrame` + `Glow` + `fade-bottom`** treatment and give the hero a genuine
   artefact — we have real files to show, so this does not need invented screenshots.
4. Add the **staggered `appear` choreography** as canon utilities.
5. Add the **`glass-*` / `fade-*` / `line-*` utility set** to the design layer so sections compose
   rather than hand-roll.
6. Keep the **stack showcase** (it is the one thing that is ours) but give it the width it needs,
   and drive its focus from the same scroll idiom.
7. Port **Launch UI's section set** as the page skeleton — navbar, hero, logos, items, stats,
   pricing, faq, cta, footer — swapping invented content for our real content, and dropping
   pricing/testimonials (no honest material exists for either).

**Licensing:** Launch UI is MIT, so the technique and code are both usable. If we copy code
verbatim we must carry the MIT notice; the safer and more consistent route is to **port the
techniques into `packages/ui`** in our own token vocabulary, which is what the canon requires
anyway. Tailark and the shadcnblocks templates are visual references only.

## Explicitly not doing

- No invented pricing tiers, customer logos, or testimonials — the honesty rule holds.
- No Tailwind-theme transplant: our tokens stay; we take geometry and choreography, not colour.
- Not adopting their component library as a dependency — these are copy-in registries, and our
  canon already refuses app-local UI built outside `packages/ui`.
