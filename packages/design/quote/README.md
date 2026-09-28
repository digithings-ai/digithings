# Quote template

A one-page quote / statement of work, companion to [`../invoice/`](../invoice/) and
sharing its utilitarian house style (Geist Mono for claim, body, and chrome,
hairline rules, zero radius, no glass, tabular figures, no colour, no logo mark).
Self-contained single `index.html` — no build step.

Unlike the invoice, scope items here **do** carry prices: the client is deciding
what to buy, so they need to see what each piece costs. Items can be marked
optional with `class="opt"` on the `<tr>`, which renders an "optional" chip
beside the title and keeps the item out of the balance.

## The staged-engagement pattern

The specimen shows the pattern this template exists for. Work already delivered
under a flat-fee earlier phase is listed **at full fair value** alongside the work still
to come, and anything already paid is then credited back on its own line:

```
Delivered — phase one (01–09)              A
To complete — next phase (10–13)           B
Engagement at fair value                 A + B
Discount (n%)                             − D
Less phase one invoice, paid              − P
Balance due                    A + B − D − P
```

Line items carry **fair market value**, and every concession is its own line:
the relationship discount and any payment already made. That way the client
sees what the engagement is actually worth, the discount is explicit rather
than silent, and the flat earlier-phase fee never reads as the standing rate.
Price optional items so they stay round *after* the discount — pick the fair-value
figure such that `fair × (1 − n)` lands on a round net. Use `class="sec"` on a
`<tr><td colspan="3">` to start each phase section.

## Fill it in

Replace every `[bracketed]` placeholder, then edit the scope rows, prices,
timeline and terms for the engagement:

- **Header** — quote №, date, valid-until, phase.
- **Prepared for** — client entity and address.
- **Headline** — core scope figure, the with-options figure, and timeline.
- **Scope of work** — one row per deliverable, with a short plain-English
  description of what the client actually gets.
- **Terms** — payment schedule, timeline, validity.
- **Running costs & assumptions** — third-party services the client pays
  directly, plus what the quote assumes and excludes.

The specimen uses illustrative generic scope and figures. **Keep real client
names, amounts and project detail out of this repository** — fill them in on a
working copy.

## Convert to PDF

Same workflow as the invoice:

```bash
chromium --headless --no-pdf-header-footer \
  --print-to-pdf=quote.pdf index.html
```

Or open `index.html` in a browser → **Print** → **Save as PDF** (A4, default
margins). Page geometry lives in the `@page` / `@media print` rules at the
bottom of the `<style>` block (A4, 11 mm margins).

Keeping it to one page is deliberate — a quote that fits on a single sheet gets
read. If you add scope rows, trim descriptions to two lines and check the render
before sending.
