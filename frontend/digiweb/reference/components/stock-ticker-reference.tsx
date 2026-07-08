/**
 * Stock ticker tape — the scrolling market strip, in our register. One mono
 * row of symbol · last · change loops seamlessly (content duplicated, track
 * translated exactly -50%) behind edge-fade masks, pause-on-hover. Unlike the
 * tech marquee, this one legitimately wears the money colors: a price change
 * is the up/down semantic. Pure CSS, so a plain server component; reduced
 * motion stops the drift.
 */
type Tick = { sym: string; px: string; chg: string; up: boolean };

const TICKS: Tick[] = [
  { sym: "BTC-PERP", px: "63,410", chg: "1.24%", up: true },
  { sym: "ETH-PERP", px: "3,088", chg: "0.62%", up: true },
  { sym: "SOL-PERP", px: "142.60", chg: "2.10%", up: false },
  { sym: "SPY", px: "548.21", chg: "0.31%", up: true },
  { sym: "NVDA", px: "121.44", chg: "3.44%", up: true },
  { sym: "AAPL", px: "229.87", chg: "0.18%", up: false },
  { sym: "TSLA", px: "246.910", chg: "1.77%", up: true },
  { sym: "GOLD", px: "2,410.5", chg: "0.22%", up: true },
  { sym: "US10Y", px: "4.281%", chg: "0.05%", up: false },
];

export function StockTickerReference() {
  return (
    <section className="section-block" id="ticker-tape">
      <p className="kicker">{"// ticker tape"}</p>
      <h2 className="title">The tape never sleeps.</h2>
      <p className="section-copy">
        The market strip: symbol, last, and change scrolling as one seamless loop behind edge-fade
        masks. Change wears the sanctioned <code>--up</code> / <code>--down</code> money colors —
        this is the one marquee where color carries meaning. Hover to pause; reduced motion holds
        it still.
      </p>

      {/* .tk (edge-fade mask), .tk-track (scroll animation), :hover pause, and
          reduced-motion stay in finance.css — they're mask/keyframe mechanics.
          The item + cell typography migrated to utilities; change wears the
          money colors (text-up / text-down). */}
      <div className="tk">
        <div className="tk-track">
          {[...TICKS, ...TICKS].map((t, i) => (
            <span
              className="inline-flex items-baseline gap-2 whitespace-nowrap border-r border-hair px-[1.3rem] py-[0.7rem] font-mono text-[0.82rem] [font-variant-numeric:tabular-nums]"
              key={`${t.sym}-${i}`}
              aria-hidden={i >= TICKS.length || undefined}
            >
              <span className="tracking-[0.02em] text-ink">{t.sym}</span>
              <span className="text-ink-soft">{t.px}</span>
              <span
                className={`inline-flex items-center gap-[0.28rem] text-[0.76rem] ${
                  t.up ? "text-up" : "text-down"
                }`}
              >
                <span aria-hidden="true">{t.up ? "▲" : "▼"}</span>
                {t.chg}
              </span>
            </span>
          ))}
        </div>
      </div>
    </section>
  );
}
