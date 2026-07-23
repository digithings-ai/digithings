# Invoice template

A polished, print-ready invoice built on the digiweb design canon
([`design/tokens.css`](../tokens.css)): light/paper theme, Geist / Geist Mono /
Instrument Serif voices, the phosphor accent (`#0E8C7F` on paper), hairline
rules, and tabular figures for money. Self-contained single `index.html` — no
build step, no external assets beyond web fonts.

The invoice itself is always **one A4 page**. Line items read like an
AI-services invoice: a bold deliverable followed by a compact scope, with the
work's traceability (PR range) folded into the Notes rather than cluttering each
row.

An **optional second page** — the *delivery breakdown* — follows for clients who
want the fuller per-deliverable scope and PR references. It carries no charges
(all amounts live on the invoice). Delete the entire
`<section class="sheet appendix">` block if you only want the one-pager; the
invoice page is unaffected.

## Fill it in

Every value the sender must supply is either a `[bracketed]` field or carries a
`.ph` dotted-underline placeholder. Replace them all before sending:

- **From** — business name, address, VAT/tax no. (contact is pre-filled).
- **Bill to** — client legal entity and address.
- **Amounts** — each deliverable's price, the subtotal, tax/VAT, and the total.
- **Meta** — invoice №, dates, terms, and the payment details.
- **Line items** — the specimen is populated with the Twelve X FX-research work
  delivered in June 2026; edit for the engagement you are billing.

## Convert to PDF

Headless Chromium (what CI/the design servers already have):

```bash
chromium --headless --no-pdf-header-footer \
  --print-to-pdf=invoice.pdf index.html
```

Or open `index.html` in a browser → **Print** → **Save as PDF** (A4, margins:
default/none, background graphics **on** so the accent rule and amount-due card
render).

Page geometry lives in the `@page` / `@media print` rules at the bottom of the
`<style>` block (A4, 11 mm margins). The screen view shows the sheet as a card;
print drops the card chrome and flows edge-to-edge within the page margins.
