# Invoice template

A clean, print-ready invoice in an elegant **monochrome** (black & white) style —
Geist / Geist Mono / Instrument Serif voices, hairline rules, generous
whitespace, and tabular figures for money. No colour and no logo mark, so it
reads as a plain professional document. Self-contained single `index.html` — no
build step, no external assets beyond web fonts.

The invoice itself is always **one A4 page**. Line items read like an
AI-services invoice: a deliverable name followed by a compact scope, one row
each.

An **optional second page** — the *delivery breakdown* — follows for clients who
want the fuller per-deliverable scope. It carries no charges (all amounts live
on the invoice). Delete the entire `<section class="sheet appendix">` block if
you only want the one-pager; the invoice page is unaffected.

## Fill it in

Every value the sender must supply is a `[bracketed]` placeholder in muted mono.
Replace them all before sending:

- **From** — business name, address, VAT/tax no. (contact is pre-filled).
- **Bill to** — client legal entity and address.
- **Amounts** — each deliverable's price, the subtotal, tax/VAT, and the total.
- **Meta** — invoice №, dates, terms, and the payment details.
- **Line items** — the specimen is populated with the 12X pilot deliverables;
  edit for the engagement you are billing.

## Convert to PDF

Headless Chromium (what CI/the design servers already have):

```bash
chromium --headless --no-pdf-header-footer \
  --print-to-pdf=invoice.pdf index.html
```

Or open `index.html` in a browser → **Print** → **Save as PDF** (A4, default
margins). Being monochrome, it prints correctly whether or not "background
graphics" is enabled.

Page geometry lives in the `@page` / `@media print` rules at the bottom of the
`<style>` block (A4, 12 mm margins). The screen view shows the sheet as a card;
print drops the card chrome and flows edge-to-edge within the page margins.
