/**
 * StockTicker — the scrolling market strip promoted from the design reference
 * (finance/ticker-tape): one mono row of symbol · last · change looping
 * seamlessly (content duplicated once, track translated exactly -50%) behind
 * edge-fade masks, pause-on-hover. This is the one marquee that legitimately
 * wears the money colors — a price change IS the up/down semantic — while the
 * module accent stays out of it entirely. Pure CSS animation
 * (styles/finance-composites.css), so a plain server component; the tape is
 * fully readable with no JS and prefers-reduced-motion holds it still.
 *
 * Wiring (in the consuming app):
 *   globals.css   @import "@digithings/web/styles/finance-composites.css";
 *                 @source "<path-to>/digiweb/web/src/components/finance-composites";
 */
export type TickerItem = {
  /** Instrument symbol — "BTC-PERP", "SPY", "US10Y" … */
  symbol: string;
  /** Preformatted last price — "63,410", "4.281%" … */
  last: string;
  /** Preformatted change magnitude — "1.24%" (direction carried by `up`). */
  change: string;
  /** Direction of the change: true wears --up, false wears --down. */
  up: boolean;
};

export type StockTickerProps = {
  /** The ticks on the tape — duplicated internally for the seamless loop. */
  items: TickerItem[];
  /** Extra classes on the tape shell (margins, widths — the call site's business). */
  className?: string;
};

export function StockTicker({ items, className }: StockTickerProps) {
  return (
    <div className={`tk${className ? ` ${className}` : ""}`}>
      <div className="tk-track">
        {[...items, ...items].map((t, i) => (
          <span
            className="inline-flex items-baseline gap-2 whitespace-nowrap border-r border-hair px-[1.3rem] py-[0.7rem] font-mono text-[0.82rem] [font-variant-numeric:tabular-nums]"
            key={`${t.symbol}-${i}`}
            aria-hidden={i >= items.length || undefined}
          >
            <span className="tracking-[0.02em] text-ink">{t.symbol}</span>
            <span className="text-ink-soft">{t.last}</span>
            <span
              className={`inline-flex items-center gap-[0.28rem] text-[0.76rem] ${
                t.up ? "text-up" : "text-down"
              }`}
            >
              <span aria-hidden="true">{t.up ? "▲" : "▼"}</span>
              {t.change}
            </span>
          </span>
        ))}
      </div>
    </div>
  );
}
