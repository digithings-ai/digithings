# Cross-site component catalog

Comparison of **Graphite**, **Cursor**, and **x.ai** component implementations.  
Use with [`../EVOLUTION.md`](../EVOLUTION.md) primitive mapping at the end.

**Legend:** ● strong pattern · ◐ partial · ○ absent

---

## Buttons

| Component | Graphite | Cursor | x.ai | Notes |
|-----------|----------|--------|------|-------|
| Primary | ● Orange fill `#ff8833`, ~10px radius, subtle shadow | ● Dark fill on light bg; "Get started" | ● **White filled pill** (one per view) | DigiThings: `--accent` primary, not orange |
| Secondary | ● Ghost "Request a demo" | ● Outlined / text | ● **Outline pill** 1px white | |
| Nav CTA | ● "Sign up" + arrows | ● "Sign in" text link | ● Sign up filled pill | Keep GitHub/theme always visible (our pattern) |
| Link CTA | ● "Learn more →" text + arrow | ● "Learn about X →" | ● "Explore →" | Adopt arrow suffix for docs links |
| Destructive | ○ | ○ | ○ | N/A on marketing |
| Icon button | ● Menu 28×28, close 32×32 | ● Open nav 32×32 | ◐ | Min 40×40 touch (our hamburger) |

### Primary button anatomy

```
Graphite:  [  Get started for free  ↗↗  ]  h~35px  r=10px  bg=#ff8833
Cursor:    [  Get started  →  ]              h~44px  r=~10px  bg=dark
x.ai:      [  GET API KEY  ]                 pill    bg=white  text=dark
```

---

## Navigation

| Pattern | Graphite | Cursor | x.ai |
|---------|----------|--------|------|
| Announcement bar | ● Product news, 48px | ○ | ◐ "New" pills |
| Desktop links | ● Opacity hover | ● Standard | ● Sparse |
| Mobile menu | ● Full dialog sheet | ● Overlay nav | ◐ (not verified) |
| Auth in header mobile | ● Log in + Sign up visible | ● Sign in visible | ◐ |
| Theme toggle | ○ | ● Footer segmented | ○ |
| Sticky header | ● Yes | ● Yes | ● Yes |
| Scroll hide | ○ | ○ | ○ |

---

## Hero

| Element | Graphite | Cursor | x.ai |
|---------|----------|--------|------|
| h1 style | Statement 2-line | Single ambitious sentence | Massive mono display |
| Subhead | 2-line value prop | ○ minimal on mobile | Supercluster tagline |
| Primary CTA | Get started for free | Get started | Get API Key |
| Friction text | ● 3-part trust | ○ | ○ |
| Product visual | ● Video + picker | ● Multi-UI demo | ● Interactive teasers |
| Logo strip in hero | ● Below CTAs | ● Below hero | ○ |

---

## Feature presentation

| Pattern | Graphite | Cursor | x.ai |
|---------|----------|--------|------|
| Scroll-pinned stack | ● Signature | ○ | ○ |
| Bento grid | ○ | ● Large linked cards | ○ |
| Capability cards | ◐ In pinned section | ◐ In bento | ● Explore → modality |
| Product frame | ● 800px CQ scale | ● rounded-xl shadow | ● Flat 8px cards |
| CLI / code row | ● In features page | ● curl + copy | ● Tabbed SDK block |
| Live UI mock | ● PR diff, chat | ● Agent tasks | ● Agent terminal |

---

## Social proof

| Component | Graphite | Cursor | x.ai |
|-----------|----------|--------|------|
| Logo strip | ● | ● | ○ |
| Testimonial | ◐ Case study cards | ● Quote carousel | ○ |
| Case study format | ● Partner × Graphite | ● Customer stories dated | ○ |
| Stat counters | ○ | ● Enterprise % | ● API scale metrics |
| Named executives | ○ | ● Jensen, Patrick, etc. | ○ |

---

## Content bands

| Component | Graphite | Cursor | x.ai |
|-----------|----------|--------|------|
| Changelog | ○ | ● Dated + version | ◐ News posts |
| Blog highlights | ● /blog | ● Research/Product tags | ● /news archive |
| FAQ accordion | ● Pricing | ● Pricing + Enterprise | ○ |
| Pricing table | ● Matrix + cards | ● 4 tiers + toggle | ● Per-token tables |
| Partner logos | ○ | ○ | ● Azure, OCI, GCP |

---

## Footer

| Element | Graphite | Cursor | x.ai |
|---------|----------|--------|------|
| Columns | 4 | 5 | ◐ minimal |
| Status indicator | ● operational | ○ | ○ |
| Theme/lang | ○ | ● System/Light/Dark + EN | ○ |
| Brand moment | ● Neon sign image | ○ | ◐ gradient bloom |
| SOC / trust | ○ | ● SOC 2 link | ○ |

---

## Typography roles (summary)

| Role | Graphite | Cursor | x.ai | DigiThings target |
|------|----------|--------|------|-------------------|
| Display | Matter 500 | Cursor Gothic | Geist Mono 300 | Fraunces / Instrument Serif (marketing) |
| Body | Matter 400 | Lato | Universal Sans | Geist Sans |
| Label | Matter 400 | Sans | Geist Mono UPPERCASE | Geist Mono `// kicker` |
| Code | DM Mono | Mono in demos | Geist Mono | Geist Mono |

---

## Motion (summary)

| Type | Graphite | Cursor | x.ai |
|------|----------|--------|------|
| Scroll-pin | ● | ○ | ○ |
| Glide easing | ● | ◐ subtle | ◐ |
| Hover lift | ◐ | ● cards | ○ |
| Counter | ○ | ○ | ● |
| Video | ● hero | ◐ demo | ○ |

---

## DigiThings primitive mapping

| Planned primitive | Primary reference | Secondary |
|-------------------|-------------------|-----------|
| `ProductFrame` | Graphite 800px CQ | Cursor rounded-xl frame |
| `BentoGrid` | Cursor linked cells | — |
| `ScrollyFeatures` | Graphite pinned stack | — |
| `TrustStrip` | Graphite + Cursor logos | — |
| `StatCounter` | x.ai + Cursor enterprise | — |
| `CapabilityCard` | x.ai Explore → | Graphite feature cells |
| `ChangelogBand` | Cursor | x.ai news |
| `CodeSampleBand` | x.ai API tabs | Cursor curl row |
| `PricingMatrix` | Graphite comparison | x.ai token table |
| `AnnouncementBar` | Graphite | x.ai New pill |
| `MobileNavSheet` | Graphite dialog | Our dqnav + scrim |
| `FrictionReducer` | Graphite hero | Cursor "No credit card" |
| `CaseStudyCard` | Graphite carousel | Cursor enterprise stories |

---

## Token extraction quick reference

| Token | Graphite | Cursor | x.ai | Ours (`tokens.css`) |
|-------|----------|--------|------|---------------------|
| Page bg | `#0a0a0a` | `#f7f8f3` | `#0a0a0a` | `--bg` |
| Accent | `#ff8833` | dark/neutral | white pill | `--accent` cyan |
| Radius md | 8–10px | ~12px | 8px / pill | 8–12px |
| Hairline | white 10% | `#e3e2dd` | `#212327` | `--hair` |
| Section y | ~64–80px | ~96px | ~64px | propose `--section-y` |
| Easing | glide linear() | ease default | minimal | propose `--ease-glide` |
