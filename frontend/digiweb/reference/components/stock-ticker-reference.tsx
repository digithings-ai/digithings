/**
 * Stock ticker tape — the scrolling market strip, in our register. One mono
 * row of symbol · last · change loops seamlessly (content duplicated, track
 * translated exactly -50%) behind edge-fade masks, pause-on-hover. Unlike the
 * tech marquee, this one legitimately wears the money colors: a price change
 * is the up/down semantic. Pure CSS, so a plain server component; reduced
 * motion stops the drift. Consumes the shared <StockTicker/> primitive from
 * @digithings/web. Static display template.
 */
import { StockTicker, type TickerItem } from "@digithings/web";

const TICKS: TickerItem[] = [
  { symbol: "BTC-PERP", last: "63,410", change: "1.24%", up: true },
  { symbol: "ETH-PERP", last: "3,088", change: "0.62%", up: true },
  { symbol: "SOL-PERP", last: "142.60", change: "2.10%", up: false },
  { symbol: "SPY", last: "548.21", change: "0.31%", up: true },
  { symbol: "NVDA", last: "121.44", change: "3.44%", up: true },
  { symbol: "AAPL", last: "229.87", change: "0.18%", up: false },
  { symbol: "TSLA", last: "246.910", change: "1.77%", up: true },
  { symbol: "GOLD", last: "2,410.5", change: "0.22%", up: true },
  { symbol: "US10Y", last: "4.281%", change: "0.05%", up: false },
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

      <StockTicker items={TICKS} className="mt-[1.2rem]" />
    </section>
  );
}
