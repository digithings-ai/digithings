/**
 * Small price table under the why band's step column (Refs #4429): their
 * stack against the digithings stack, per layer, for the current picks.
 */

"use client";

import { useEffect, useRef, useState } from "react";
import {
  Table,
  TableBody,
  TableCell,
  TableFooter,
  TableHead,
  TableHeader,
  TableRow,
  TableRowHeader,
} from "@digithings/ui/ui";

import type { RagWorkload } from "@/lib/ragCost";
import {
  DIGI_LAYERS,
  PROVIDER_LAYERS,
  pricePick,
  type LayerId,
  type PricedLine,
  type StackPick,
} from "@/lib/stackCatalog";

const LAYER_NAME: Record<LayerId, string> = {
  models: "models",
  embeddings: "embeddings",
  vector: "vector store",
  telemetry: "traces",
  hosting: "hosting",
};
const LAYER_ORDER: LayerId[] = ["models", "embeddings", "vector", "telemetry", "hosting"];

interface Cell {
  amount: number;
  estimate: boolean;
  unpriced: boolean;
}

function sumLayer(lines: PricedLine[], layer: LayerId, recurring: boolean): Cell | null {
  const hits = lines.filter((line) => line.layer === layer && line.recurring === recurring);
  if (hits.length === 0) return null;
  return {
    amount: hits.reduce((n, line) => n + line.amount, 0),
    estimate: hits.some((line) => line.estimate),
    unpriced: hits.every((line) => line.unpriced),
  };
}

function money({ amount, estimate, unpriced }: Cell): string {
  if (unpriced) return "—";
  const tilde = estimate ? "~" : "";
  if (amount === 0) return "$0";
  if (amount < 1) return `${tilde}<$1`;
  return `${tilde}$${Math.round(amount).toLocaleString("en-US")}`;
}

/* Accent as small text uses the kit recipe (MIGRATION.md): mixed toward ink so
   a light livery still clears contrast at 0.72rem. */
const ACCENT_TEXT = "text-[color:color-mix(in_srgb,var(--accent)_70%,var(--ink))]";
const CELL = "px-[0.7rem]";
const HEAD = `${CELL} text-[0.62rem] font-normal uppercase tracking-[0.08em] text-ink-mute`;

export function WhyPriceTable({
  provider,
  digi,
  workload,
  topology,
  replaced,
}: {
  provider: StackPick;
  digi: StackPick;
  workload: RagWorkload;
  topology: "rag" | "support" | "finance";
  /** Layers the walk has already handed to digithings. */
  replaced: LayerId[];
}) {
  const theirs = pricePick(PROVIDER_LAYERS, provider, workload, topology);
  const ours = pricePick(DIGI_LAYERS, digi, workload, topology);
  const rows = LAYER_ORDER.flatMap((layer) => {
    const a = sumLayer(theirs.lines, layer, true);
    const b = sumLayer(ours.lines, layer, true);
    return a || b ? [{ layer, a, b }] : [];
  });
  const setupEstimate = (lines: PricedLine[]) => lines.some((l) => !l.recurring && l.estimate);
  const showSetup = theirs.setup > 0 || ours.setup > 0;
  const est = (lines: PricedLine[]) => lines.some((l) => l.recurring && l.estimate);

  /* The table shares its column with the step list. When the per-layer rows
     would run into the walked step, fold to the total alone; when even that
     would, step aside entirely. Each part's last measured height is kept, so
     folding cannot flip the decision back. */
  const rootRef = useRef<HTMLDivElement>(null);
  const detailRef = useRef<HTMLTableSectionElement>(null);
  const detailH = useRef(0);
  const totalH = useRef(0);
  const [fold, setFold] = useState<"full" | "total" | "none">("full");
  const compact = fold !== "full";
  useEffect(() => {
    const root = rootRef.current;
    const side = root?.closest(".arch-tour__side");
    const rail = side?.querySelector(":scope > .arch-tour__rail");
    const frame = side?.querySelector(":scope > .arch-tour__frame");
    if (!root || !rail || !frame) return;
    const check = () => {
      const detail = detailRef.current;
      const shownDetail = detail?.offsetHeight ?? 0;
      if (shownDetail > 0) detailH.current = shownDetail;
      if (root.offsetHeight > 0) totalH.current = root.offsetHeight - shownDetail;
      const room = frame.getBoundingClientRect().bottom - rail.getBoundingClientRect().bottom - 12;
      setFold(
        totalH.current + detailH.current <= room
          ? "full"
          : totalH.current <= room
            ? "total"
            : "none",
      );
    };
    const ro = new ResizeObserver(check);
    ro.observe(rail);
    ro.observe(frame);
    ro.observe(root);
    return () => ro.disconnect();
  }, []);

  return (
    <div
      ref={rootRef}
      hidden={fold === "none"}
      className="border border-hair bg-surface font-mono text-ink-soft"
    >
      <Table density="dense" className="text-[0.72rem] leading-[1.4]">
        <TableHeader>
          <TableRow className="border-hair hover:bg-transparent">
            <TableHead className={`${HEAD} max-w-0 truncate`}>
              /mo · {workload.queriesPerDay.toLocaleString("en-US")} queries/day
            </TableHead>
            <TableHead numeric className={`${HEAD} w-[5.2rem]`}>
              theirs
            </TableHead>
            <TableHead numeric className={`${HEAD} w-[5.2rem]`}>
              digithings
            </TableHead>
          </TableRow>
        </TableHeader>
        <TableBody ref={detailRef} hidden={compact}>
          {rows.map(({ layer, a, b }) => {
            const on = replaced.includes(layer);
            return (
              <TableRow key={layer} className="border-0 hover:bg-transparent">
                <TableRowHeader className={`${CELL} font-normal ${on ? "text-ink" : "text-ink-soft"}`}>
                  {LAYER_NAME[layer]}
                </TableRowHeader>
                <TableCell numeric className={CELL}>
                  {a ? money(a) : "·"}
                </TableCell>
                <TableCell numeric className={`${CELL} ${on ? ACCENT_TEXT : ""}`}>
                  {b ? money(b) : "·"}
                </TableCell>
              </TableRow>
            );
          })}
          {showSetup ? (
            <TableRow className="border-0 hover:bg-transparent">
              <TableRowHeader className={`${CELL} font-normal text-ink-soft`}>one-time setup</TableRowHeader>
              <TableCell numeric className={CELL}>
                {money({ amount: theirs.setup, estimate: setupEstimate(theirs.lines), unpriced: false })}
              </TableCell>
              <TableCell numeric className={CELL}>
                {money({ amount: ours.setup, estimate: setupEstimate(ours.lines), unpriced: false })}
              </TableCell>
            </TableRow>
          ) : null}
        </TableBody>
        <TableFooter className="border-hair bg-transparent font-normal text-ink">
          <TableRow className="border-0 hover:bg-transparent">
            <TableRowHeader className={`${CELL} font-normal`}>total / mo</TableRowHeader>
            <TableCell numeric className={CELL}>
              {money({ amount: theirs.monthly, estimate: est(theirs.lines), unpriced: false })}
            </TableCell>
            <TableCell numeric className={`${CELL} ${ACCENT_TEXT}`}>
              {money({ amount: ours.monthly, estimate: est(ours.lines), unpriced: false })}
            </TableCell>
          </TableRow>
        </TableFooter>
      </Table>
      <p className="m-0 truncate border-t border-hair px-[0.7rem] py-[0.3rem] text-[0.62rem] text-ink-mute">
        list prices · ~ estimate · — no sourced rate · $0 on your hardware
      </p>
    </div>
  );
}
