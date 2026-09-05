"use client";

/**
 * Select specimen — the shared form select from @digithings/web, live,
 * composed inside the shared Field (label + hint wiring included). The
 * dropdown specimen covers menu panes; this one is the form control:
 * type-ahead, arrow-key travel, flip-aware popup, accent check on the
 * picked row. Dress is `.ctl-select*` in the package core sheet.
 */
import { useState } from "react";
import {
  Field,
  Select,
  SelectItem,
  SelectItemIndicator,
  SelectPopup,
  SelectTrigger,
  SelectValue,
} from "@digithings/web";

const VENUES = ["coinbase", "kraken", "binance", "paper"] as const;

export function SelectReference() {
  const [venue, setVenue] = useState<string>("paper");
  return (
    <section className="section-block">
      <p className="kicker">{"// select"}</p>
      <h2 className="title">Pick one, honestly.</h2>
      <p className="section-copy">
        <code>Select</code> from <code>@digithings/web</code>, sitting in a shared{" "}
        <code>Field</code> — label, hint, and ids meshed by the wrapper. Open it with the
        keyboard and type to jump.
      </p>

      <div className="mt-[1.2rem] max-w-[22rem]">
        <Field label="Execution venue" hint="Paper until the book is committed.">
          <Select value={venue} onValueChange={(v) => v != null && setVenue(v)}>
            <SelectTrigger>
              <SelectValue placeholder="Choose a venue" />
            </SelectTrigger>
            <SelectPopup>
              {VENUES.map((v) => (
                <SelectItem key={v} value={v}>
                  {v}
                  <SelectItemIndicator />
                </SelectItem>
              ))}
            </SelectPopup>
          </Select>
        </Field>
        <p className="mt-[0.7rem] font-mono text-[0.72rem] text-ink-mute">
          venue = {venue}
        </p>
      </div>
    </section>
  );
}
