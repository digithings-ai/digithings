# Reference scan: langfuse.com

- **URL:** https://langfuse.com
- **Product:** Open-source LLM engineering platform (observability, evals, prompt management)
- **Last audited:** 2026-10-01 (light pass; qualitative — no pixel-level token extraction)
- **Status:** reference for the **next polish pass** on the digithings.ai home and
  digiquant-web marketing. Not a copy target, not a visual north-star rewrite, and
  **not implemented in this PR** (docs only).
- **Capture tone (Chris lock, 2026-10-01):** **lightness** + **product marketing clarity**.

---

## 1. First impression

Light, airy marketing surface: mostly white/near-white ground, generous whitespace,
thin hairlines, restrained chrome. The home page tells one product story in plain
language, then proves it with product screenshots in quiet frames. We study the
*marketing craft* only — not the observability product features.

---

## 2. What to steal for digiweb

| Pattern | Langfuse does | Digiweb adopt / adapt / avoid |
|---------|---------------|-------------------------------|
| Light surfaces, sparse chrome | White ground, hairline borders, little decoration | **Adapt** — a light-ground treatment for digithings.ai home / digiquant-web sections, within our existing `[data-theme]` contract |
| Plain-language product story | Headline states what the product is; sections follow one narrative | **Adopt** — tighten hero + section copy per `COPY_GUIDE.md` |
| Product-in-quiet-frame | Screenshots in soft, low-contrast frames | **Adapt** — digiquant-web product proof with calmer framing; no invented metrics |
| Literal CTAs | Short verbs (get started, docs) | **Adopt** — consistent with Cursor/AgentMail scans |
| Modest nav | Few top-level items, docs one click away | **Adopt** for marketing nav density |
| Dense feature grids / dashboard-style marketing | Many capability tiles on home | **Avoid** — keep one story per section |
| Brand color flourishes, heavy illustration | Occasional accent use | **Avoid** as a second brand hue; keep our single accent |
| Observability product concepts (traces, evals) | Core of their story | **Avoid** — out of scope; do not borrow product claims |

---

## 3. Tokens (observed, qualitative)

- **Ground:** white / near-white; light-first marketing
- **Ink:** near-black body text, grey secondary
- **Lines:** hairline neutral borders instead of shadows
- **Type:** clean sans for display and body; mono only for code snippets
- **Rhythm:** wide section spacing, narrow readable text column

Exact values intentionally not recorded; re-scan before any implementation.

---

## 4. One-line lesson

> Say what it is in one plain sentence, keep the surface light, and let a quiet product frame do the proving.
