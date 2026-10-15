import Image from "next/image";
import { siCoinbase, siSupabase } from "simple-icons";

/** Marks for the integrations band. DigiThings, LuxAlgo and NautilusTrader use
 *  the vendors' own assets: the digithings favicon, the LuxAlgo app icon, and the
 *  nautilus shell cropped from the nautilus_trader logo (the wordmark would repeat
 *  the card title). Gloomberg is the monochrome adaptation already used in the
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

/** Gloomberg candlestick mark: monochrome adaptation of the Gloomberg mark (source
 *  gloom-sh/gloomberb, MIT; Copyright (c) 2026 Gloomberg Contributors). Same drawing as
 *  apps/dashboard/components/gloomberb-mark.tsx. */
function GloombergMark({ size }: { size: number }) {
  return (
    <svg width={size} height={size} viewBox="0 0 512 512" fill="currentColor" aria-hidden="true" focusable="false" className="shrink-0" style={{ width: size, height: size }}>
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
  if (id === "gloomberb") return <GloombergMark size={size} />;
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
      <svg width={size} height={size} viewBox="0 0 24 24" fill="currentColor" aria-hidden="true" focusable="false" className="shrink-0" style={{ width: size, height: size }}>
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

/** The providers the two connected-package rows can name. Narrower than it
 *  looks: the rows themselves are generated from this tree's real dependencies
 *  by scripts/build_providers_band.py, so a provider only belongs here while
 *  some manifest declares one of its packages and a non-test source file
 *  imports it. tests/scripts/test_providers_band_is_current.py fails CI when the
 *  generated JSON names an id this union does not cover. */
export type RowProviderId = "alpaca" | "supabase" | "yahoo";

interface SimpleIcon {
  hex: string;
  path: string;
}

/**
 * Marks for the connected-package rows, taken from Simple Icons — the CC0 source
 * of official brand paths this repo already uses. Each path renders with
 * fill="currentColor", so a mark is monochrome by construction and takes the
 * row's ink colour on any surface.
 *
 * A provider with NO entry here is a real gap, not a rendering failure to paper
 * over. Simple Icons 15.18.0 carries no official path for Alpaca or Yahoo
 * Finance; public/marks/ holds only the LuxAlgo and NautilusTrader assets; and
 * the vendor sites serve favicons (16–32px ICOs) or full-colour app icons rather
 * than an official monochrome SVG. Those rows keep the plain lozenge on purpose.
 * A recoloured favicon or a hand-drawn monogram is not the vendor's mark, and a
 * scraped one carries no provenance — so the gap is named rather than faked.
 *
 * scripts/build_providers_band.py reads this object to record a `logo` for each
 * generated row, so adding an entry here and regenerating is what closes a gap;
 * the generator cannot invent one this file does not register.
 */
const ROW_MARKS: Partial<Record<RowProviderId, SimpleIcon>> = {
  supabase: siSupabase,
};

/** The official monochrome path for a row provider, or null when none exists. */
export function rowMark(id: RowProviderId): SimpleIcon | null {
  return ROW_MARKS[id] ?? null;
}

/** The row glyph: an official monochrome path, or nothing at all. */
export function RowMark({ id, size = 14 }: { id: RowProviderId; size?: number }) {
  const mark = rowMark(id);
  if (!mark) return null;
  return (
    <svg
      viewBox="0 0 24 24"
      width={size}
      height={size}
      aria-hidden="true"
      focusable="false"
      className="shrink-0"
    >
      <path d={mark.path} fill="currentColor" />
    </svg>
  );
}

