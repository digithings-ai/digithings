"use client";

import { useState } from "react";

import {
  Button,
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuGroup,
  DropdownMenuItem,
  DropdownMenuLabel,
  DropdownMenuRadioGroup,
  DropdownMenuRadioItem,
  DropdownMenuSeparator,
  DropdownMenuShortcut,
  DropdownMenuTrigger,
  Input,
} from "@digithings/web/ui";

/**
 * Dropdown — the stock DropdownMenu from `@digithings/web/ui` with an inline
 * filter. The pane stays its own surface: a filter row, grouped options, rich
 * rows (livery dot, description, profit-factor metric), and a footer action.
 * The filter state is app-side; roving highlight, keyboard navigation and
 * focus-return-to-trigger are Base UI defaults.
 *
 * Wave 1 mapping from the deleted hand-built `.dd-*` pane:
 *   .dd-trigger/.dd-value/.dd-label/.dd-note/.dd-caret
 *     → DropdownMenuTrigger rendered as the kit Button
 *   .dd-search-row/.dd-search-glyph/.dd-search
 *     → call-site row wrapping the kit Input inside DropdownMenuContent
 *   .dd-scroll/.dd-group/.dd-group-label
 *     → DropdownMenuContent scrolls; DropdownMenuGroup + DropdownMenuLabel
 *   .dd-option (+ .dd-dot/.dd-opt-note/.dd-metric/.dd-check)
 *     → DropdownMenuRadioItem (+ DropdownMenuShortcut for the metric)
 *   .dd-empty → call-site paragraph (no stock empty part)
 *   .dd-footer/.dd-footer-action → DropdownMenuSeparator + DropdownMenuItem
 * Base UI menu items keep the menu open on click by default, so every pick
 * carries `closeOnClick` — the old pane closed on choice and on the footer
 * action.
 */
type Option = { id: string; group: string; label: string; note: string; pf: string; livery: string };

const OPTIONS: Option[] = [
  { id: "trend_xsec", group: "Momentum", label: "trend_xsec", note: "cross-sectional", pf: "2.31", livery: "digiquant" },
  { id: "breakout", group: "Momentum", label: "breakout", note: "volatility breakout", pf: "1.94", livery: "digiquant" },
  { id: "mean_rev", group: "Mean reversion", label: "mean_rev", note: "intraday", pf: "2.58", livery: "research" },
  { id: "pairs", group: "Mean reversion", label: "pairs", note: "cointegrated legs", pf: "1.71", livery: "research" },
  { id: "carry", group: "Carry", label: "carry", note: "funding-rate", pf: "3.02", livery: "portfolio" },
];

export function DropdownReference() {
  const [selected, setSelected] = useState(OPTIONS[0].id);
  const [query, setQuery] = useState("");

  const current = OPTIONS.find((o) => o.id === selected) ?? OPTIONS[0];
  const filtered = OPTIONS.filter(
    (o) =>
      o.label.toLowerCase().includes(query.toLowerCase()) ||
      o.note.toLowerCase().includes(query.toLowerCase()),
  );
  // Group order mirrors the source order, filtered set first.
  const groups = Array.from(new Set(filtered.map((o) => o.group)));

  return (
    <section className="section-block">
      <p className="kicker">{"// dropdown"}</p>
      <h2 className="title">A pane, not a list.</h2>
      <p className="section-copy">
        The stock menu with an in-pane filter: grouped options, rich rows (livery dot, description,
        a profit-factor metric), and a footer action. Type to filter, arrow-keys to move, Enter to
        choose, click-outside or Escape to close.
      </p>

      <div className="mt-[1.2rem] w-[min(100%,22rem)]">
        <DropdownMenu
          onOpenChange={(open) => {
            if (open) setQuery("");
          }}
        >
          <DropdownMenuTrigger
            render={<Button variant="outline" className="h-auto w-full justify-between py-2" />}
          >
            <span className="flex flex-col items-start">
              <span className="text-[0.86rem]">{current.label}</span>
              <span className="text-[0.62rem] text-muted-foreground">{current.note}</span>
            </span>
            <svg
              className="size-2 shrink-0 text-muted-foreground"
              viewBox="0 0 8 8"
              aria-hidden="true"
            >
              <path d="M1 2.5 4 5.5 7 2.5" fill="none" stroke="currentColor" strokeWidth="1.4" />
            </svg>
          </DropdownMenuTrigger>

          <DropdownMenuContent>
            <div className="border-b border-hair p-1">
              <Input
                value={query}
                onChange={(e) => setQuery(e.target.value)}
                placeholder="Filter strategies…"
                aria-label="Filter strategies"
              />
            </div>

            {filtered.length === 0 ? (
              <p className="p-[1rem] text-center font-mono text-[0.74rem] text-muted-foreground">
                No strategy matches “{query}”.
              </p>
            ) : (
              <DropdownMenuRadioGroup
                value={selected}
                onValueChange={(value) => setSelected(String(value))}
              >
                {groups.map((g) => (
                  <DropdownMenuGroup key={g}>
                    <DropdownMenuLabel>{g}</DropdownMenuLabel>
                    {filtered
                      .filter((o) => o.group === g)
                      .map((o) => (
                        <DropdownMenuRadioItem
                          key={o.id}
                          value={o.id}
                          closeOnClick
                          className={`accent-${o.livery}`}
                        >
                          <span className="size-[7px] rounded-full bg-accent" aria-hidden="true" />
                          <span className="text-[0.8rem]">{o.label}</span>
                          <span className="text-[0.62rem] text-muted-foreground">{o.note}</span>
                          <DropdownMenuShortcut>PF {o.pf}</DropdownMenuShortcut>
                        </DropdownMenuRadioItem>
                      ))}
                  </DropdownMenuGroup>
                ))}
              </DropdownMenuRadioGroup>
            )}

            <DropdownMenuSeparator />
            <DropdownMenuItem closeOnClick className="text-accent">
              <span aria-hidden="true">+</span> New strategy…
            </DropdownMenuItem>
          </DropdownMenuContent>
        </DropdownMenu>
      </div>
    </section>
  );
}
