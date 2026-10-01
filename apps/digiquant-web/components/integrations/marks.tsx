import { siCoinbase } from "simple-icons";

/** Marks for the integrations band. Real vendor marks where a single-path monochrome
 *  asset exists in the monorepo's dependencies; a monogram chip where none does
 *  (LuxAlgo, NautilusTrader, digithings, Alpaca, Interactive Brokers have none here).
 *  Everything is drawn in currentColor so the marks sit in the page's ink. Product names and marks
 *  belong to their owners; showing one implies no affiliation. */

export type IntegrationId = "gloomberb" | "luxalgo" | "nautilus" | "digithings" | "coinbase" | "alpaca" | "ibkr";

/** Gloomberb candlestick mark: monochrome adaptation of the Gloomberb mark (source
 *  gloom-sh/gloomberb, MIT; Copyright (c) 2026 Gloomberb Contributors). Same drawing as
 *  apps/dashboard/components/gloomberb-mark.tsx. */
function GloomberbMark({ size }: { size: number }) {
  return (
    <svg width={size} height={size} viewBox="0 0 512 512" fill="currentColor" aria-hidden="true" focusable="false">
      <g transform="translate(256 248) scale(1.15) translate(-256 -248)">
        <rect x="168" y="130" width="14" height="236" rx="7" />
        <rect x="143.5" y="173" width="63" height="150" rx="8" />
        <rect x="249" y="106" width="14" height="284" rx="7" />
        <rect x="220.9" y="149" width="70.2" height="198" rx="8" />
        <rect x="330" y="130" width="14" height="236" rx="7" />
        <rect x="305.5" y="173" width="63" height="150" rx="8" />
      </g>
    </svg>
  );
}

const MONOGRAMS: Record<"luxalgo" | "nautilus" | "digithings" | "alpaca" | "ibkr", string> = {
  luxalgo: "LA",
  nautilus: "NT",
  digithings: "dt",
  alpaca: "Al",
  ibkr: "IB",
};

export function IntegrationMark({ id, size = 20 }: { id: IntegrationId; size?: number }) {
  if (id === "gloomberb") return <GloomberbMark size={size} />;
  if (id === "coinbase") {
    return (
      <svg width={size} height={size} viewBox="0 0 24 24" fill="currentColor" aria-hidden="true" focusable="false">
        <path d={siCoinbase.path} />
      </svg>
    );
  }
  return (
    <span
      aria-hidden="true"
      className="inline-grid shrink-0 place-items-center border border-current font-mono font-medium leading-none"
      style={{ width: size, height: size, fontSize: Math.round(size * 0.42) }}
    >
      {MONOGRAMS[id]}
    </span>
  );
}
