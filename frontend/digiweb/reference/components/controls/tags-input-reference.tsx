"use client";

import { useState } from "react";

import { TagsInput } from "@digithings/web";

/**
 * Tags / chips input — the multi-select filter. Type and Enter (or comma) to
 * add a chip, × or Backspace-on-empty to remove, click a suggestion to add it.
 * Chips wear a hairline pill; the field lights the accent on focus. Keyboard-
 * complete and dedup-guarded. Accent reads under the monochrome default.
 * Consumes the shared <TagsInput/> primitive from @digithings/web (the
 * suggestions row included — already-added values are filtered out).
 */
const SUGGESTIONS = ["momentum", "mean-reversion", "carry", "ETH-USD", "BTC-PERP", "PF>2", "live"];

export function TagsInputReference() {
  const [tags, setTags] = useState<string[]>(["momentum", "ETH-USD"]);

  return (
    <section className="section-block">
      <p className="kicker">{"// tags input"}</p>
      <h2 className="title">Filters, as chips.</h2>
      <p className="section-copy">
        A multi-select built from chips: type and Enter (or a comma) to add, × or Backspace to
        remove, or pull from the suggestions. Duplicates are dropped, the field lights the accent on
        focus, and every chip carries its own remove control.
      </p>

      <TagsInput
        className="mt-[1.2rem]"
        value={tags}
        onAdd={(tag) => setTags((prev) => [...prev, tag])}
        onRemove={(_, i) => setTags((prev) => prev.filter((_, idx) => idx !== i))}
        placeholder="filter strategies…"
        inputAriaLabel="Add a filter tag"
        suggestions={SUGGESTIONS}
      />
    </section>
  );
}
