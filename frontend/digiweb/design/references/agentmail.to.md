# Reference scan: agentmail.to

- **URL:** https://www.agentmail.to
- **Product:** Email inbox API for AI agents
- **Stack (observed):** Next.js; Inter + Geist Mono
- **Last audited:** 2026-08-30
- **Refero Styles:** not present — closest library matches: Resend, Linear, Default, Neon

---

## 1. First impression

AgentMail is **sparse dark API SaaS**. Black canvas, white primary CTA, left-aligned claim, right-side live proof (code tabs + live inbox). No ornamental radius theater — soft enough to feel product-grade, quiet enough to feel serious.

---

## 2. What to steal for digiweb

| Pattern | AgentMail does | Digiweb adopt / adapt / avoid |
|---------|----------------|-------------------------------|
| Split hero | Claim + CTAs left / live demo right | **Adopt** for digithings.ai / digikey API pages |
| White filled CTA on dark | One loud thing = paper fill, dark ink | **Adopt** as a primary CTA variant (alongside accent fill) |
| Bracket / corner docs button | Square-corner “DOCS” affordance | **Adapt** as a ghost docs control |
| Code tabs as product | Python / TS / cURL / CLI | **Adopt** — already close to CodeTabs |
| Live interactive proof | Real inbox created for the visitor | **Adapt** where we can (don’t fake live) |
| Inter as display | Clean geometric sans | **Avoid** as brand — prefer Geist; Inter is the SaaS default we reject |

---

## 3. Tokens (observed)

**Canvas:** near-black (`#0a0a0a` / `#0d0d0d` / `#111`)

**Type:** Inter (sans) · Geist Mono (code)

**Accent:** orange YC / feature callouts; white primary button; blue announcement bar (skip for digiweb)

**Density:** generous whitespace, two-column hero, logo strip

---

## 4. One-line lesson

> Sparse claim + one white CTA + a live code/inbox proof. No decoration required.
