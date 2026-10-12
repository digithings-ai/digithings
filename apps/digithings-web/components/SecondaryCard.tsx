"use client";

/**
 * Shared card atom for the company pages (/services, /about, /team).
 *
 * A thin wrapper on the kit `Card` (document-grammar dress: hairline border,
 * surface background, square corners) with one subtle entrance: the shared
 * kit `Reveal` (short fade/slide-in on enter, static under
 * prefers-reduced-motion). Delay is capped so long grids do not cascade.
 *
 * Copy passes straight through — this atom adds presentation only.
 */

import type { ReactNode } from "react";
import { Reveal } from "@digithings/ui";
import { Card, CardContent, CardHeader, CardTitle } from "@digithings/ui/ui";

/** Stagger step for card entrances. Capped at 0.2s so grids stay calm. */
export function secondaryDelay(index: number): number {
  const safe = Number.isFinite(index) ? Math.max(index, 0) : 0;
  return Math.min(safe * 0.05, 0.2);
}

export interface SecondaryCardProps {
  /** Bold lead-in — the item name, same role as the GlyphRow label. */
  label: ReactNode;
  children: ReactNode;
  /** Position in the grid; sets the entrance stagger only. */
  index?: number;
  size?: "default" | "sm";
}

export function SecondaryCard({ label, children, index = 0, size = "default" }: SecondaryCardProps) {
  return (
    <li className="min-w-0">
      <Reveal delay={secondaryDelay(index)} className="h-full">
        <Card size={size} className="h-full border border-hair bg-surface ring-0">
          <CardHeader>
            <CardTitle className="text-[length:var(--type-body)] font-medium text-ink">
              {label}
            </CardTitle>
          </CardHeader>
          <CardContent className="text-[length:var(--type-body)] leading-[var(--leading-prose)] text-ink-soft">
            {children}
          </CardContent>
        </Card>
      </Reveal>
    </li>
  );
}

export interface SecondaryGridProps {
  children: ReactNode;
  /** Grid width: one column, two columns from sm, or two→three at lg. */
  cols?: "one" | "two" | "three";
}

const COLS: Record<NonNullable<SecondaryGridProps["cols"]>, string> = {
  one: "",
  two: "sm:grid-cols-2",
  three: "sm:grid-cols-2 lg:grid-cols-3",
};

export function SecondaryGrid({ children, cols = "two" }: SecondaryGridProps) {
  return (
    <ul className={["m-0 grid list-none gap-[1rem] p-0", COLS[cols]].filter(Boolean).join(" ")}>
      {children}
    </ul>
  );
}
