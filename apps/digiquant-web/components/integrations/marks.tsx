import Image from "next/image";
import { siCoinbase } from "simple-icons";

/** Marks for the integrations band. DigiThings, LuxAlgo and NautilusTrader use
 *  the vendors' own assets: the digithings favicon, the LuxAlgo app icon, and the
 *  nautilus shell cropped from the nautilus_trader logo (the wordmark would repeat
 *  the card title). Gloomberb is the monochrome adaptation already used in the
 *  dashboard. Coinbase is the simple-icons path. Alpaca and Interactive Brokers
 *  publish no single-path asset in this repo, so they stay a letter chip. Product
 *  names and marks belong to their owners; showing one implies no affiliation. */

export type IntegrationId = "gloomberb" | "luxalgo" | "nautilus" | "digithings" | "coinbase" | "alpaca" | "ibkr";

const HREF: Record<IntegrationId, string> = {
  gloomberb: "https://github.com/gloom-sh/gloomberb",
  luxalgo: "https://www.luxalgo.com/",
  nautilus: "https://nautilustrader.io/",
  digithings: "https://digithings.ai",
  coinbase: "https://www.coinbase.com/",
  alpaca: "https://alpaca.markets/",
  ibkr: "https://www.interactivebrokers.com/",
};

export function integrationHref(id: IntegrationId): string {
  return HREF[id];
}

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

export function IntegrationMark({ id, size = 20 }: { id: IntegrationId; size?: number }) {
  if (id === "gloomberb") return <GloomberbMark size={size} />;
  if (id === "digithings") {
    return (
      <Image src="/favicon-dg.svg" alt="" width={size} height={size} unoptimized className="shrink-0" />
    );
  }
  if (id === "luxalgo") {
    return (
      <Image src="/marks/luxalgo-mark.png" alt="" width={size} height={size} unoptimized className="shrink-0" />
    );
  }
  if (id === "nautilus") {
    return (
      <Image src="/marks/nautilus-mark.png" alt="" width={size} height={size} unoptimized className="shrink-0" />
    );
  }
  if (id === "coinbase") {
    return (
      <svg width={size} height={size} viewBox="0 0 24 24" fill="currentColor" aria-hidden="true" focusable="false">
        <path d={siCoinbase.path} />
      </svg>
    );
  }
  const letter = id === "alpaca" ? "Al" : "IB";
  return (
    <span
      aria-hidden="true"
      className="inline-grid shrink-0 place-items-center border border-current font-mono font-medium leading-none"
      style={{ width: size, height: size, fontSize: Math.round(size * 0.42) }}
    >
      {letter}
    </span>
  );
}
