"use client";

/**
 * Select specimen — the stock kit form select (`@digithings/ui/ui`), live,
 * composed inside the shared Field (label + hint wiring included). The
 * dropdown specimen covers menu panes; this one is the form control:
 * type-ahead, arrow-key travel, flip-aware popup, check on the picked row.
 * Wave 4: the non-portal `SelectPopup` moved from the controls layer onto the
 * kit, so this specimen dropped the controls import; the kit `SelectItem`
 * renders its own check, so the explicit `<SelectItemIndicator/>` child is gone.
 */
import { useState } from "react";
import { Field } from "@digithings/ui";
import {
  Select,
  SelectItem,
  SelectPopup,
  SelectTrigger,
  SelectValue,
} from "@digithings/ui/ui";

const VENUES = ["coinbase", "kraken", "binance", "paper"] as const;

export function SelectReference() {
  const [venue, setVenue] = useState<string>("paper");
  return (
    <section className="section-block">
      <p className="kicker">{"// select"}</p>
      <h2 className="title">Pick one, honestly.</h2>
      <p className="section-copy">
        <code>Select</code> from <code>@digithings/ui/ui</code>, sitting in a shared{" "}
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
