"use client";

import { useEffect, useRef, useState } from "react";
import type { Vela } from "@luxalgo/vela";
import { Button } from "@digithings/ui/ui";
import type { HeroBar } from "@/lib/hero-build";
import { chartBars, coinbaseBars, lockPriceFrame, mountPriceStudies } from "./vela-scale";
import {
  VELA_FEED_MAX_MS,
  VELA_PRODUCTS,
  VELA_UNAVAILABLE,
  velaChartOptions,
  velaHostStyle,
  velaReadyCaption,
  type VelaProduct,
} from "./vela-options";

const UP = "#3DFF9A"; // canon-allow: Vela candle up
const DOWN = "#FF5C6C"; // canon-allow: Vela candle down

const THEME = {
  background: "#000000", // canon-allow: Vela theme background
  textColor: "#d7dde4", // canon-allow: Vela axis text
  gridColor: "#1a1f24", // canon-allow: Vela grid
  borderColor: "#2a3138", // canon-allow: Vela frame
  upColor: UP,
  downColor: DOWN,
  fontFamily: "ui-monospace, SFMono-Regular, Menlo, monospace",
};

type BarSource = {
  getBars?: (ticker: string, timeframe: string, range: { limit?: number }) => Promise<unknown>;
};

function VelaChart({ product }: { product: VelaProduct }) {
  const ref = useRef<HTMLDivElement>(null);
  const [caption, setCaption] = useState(`LuxAlgo Vela · ${product}`);
  const [reduced, setReduced] = useState(false);
  const [painted, setPainted] = useState(false);

  useEffect(() => {
    const host = ref.current;
    if (!host) return;
    const prefersReduced = window.matchMedia("(prefers-reduced-motion: reduce)").matches;
    setReduced(prefersReduced);
    let dead = false;
    let shown = false;
    let studies = false;
    let book: HeroBar[] = [];
    let chart: Vela | null = null;
    let destroy = () => {};

    const fail = () => {
      if (dead || shown) return;
      setCaption(VELA_UNAVAILABLE);
    };

    const show = (chart: Vela) => {
      if (dead || shown) return;
      const rows = chartBars(chart, book);
      if (rows.length < 2) return;
      if (!studies) {
        studies = true;
        mountPriceStudies(chart);
      }
      lockPriceFrame(chart, rows);
      chart.resize();
      const again = chartBars(chart, book);
      lockPriceFrame(chart, again.length >= 2 ? again : rows);
      shown = true;
      setCaption(velaReadyCaption(product));
      setPainted(true);
    };

    const mount = async () => {
      const [{ Vela: VelaChartCtor }, { CoinbaseProvider }] = await Promise.all([
        import("@luxalgo/vela"),
        import("@luxalgo/vela/providers/coinbase"),
      ]);
      if (dead) return;
      const live = new VelaChartCtor(host, {
        ...velaChartOptions(product, prefersReduced),
        theme: THEME,
        upColor: UP,
        downColor: DOWN,
      });
      chart = live;
      destroy = () => live.destroy();
      live.data.registerProvider("coinbase", new CoinbaseProvider());
      const source = live.data.providerInstance("coinbase") as BarSource | undefined;
      if (source?.getBars) {
        void source
          .getBars(product, "1", { limit: 300 })
          .then((rows) => {
            if (dead) return;
            book = coinbaseBars(rows);
            show(live);
          })
          .catch(() => undefined);
      }
      live.on("load:end", (ev) => {
        if (dead) return;
        if ((ev?.bars ?? 0) > 0) show(live);
        else fail();
      });
      await live.ready().catch(() => undefined);
      if (dead) return;
      if (live.replay.bounds) show(live);
      else if (prefersReduced) fail();
    };

    const timer = window.setTimeout(() => {
      if (chart) show(chart);
      if (!shown) fail();
    }, VELA_FEED_MAX_MS);
    void mount().catch(() => fail());
    return () => {
      dead = true;
      window.clearTimeout(timer);
      destroy();
    };
  }, [product]);

  return (
    <div className="flex min-h-0 flex-1 flex-col border border-hair bg-black">
      <div ref={ref} aria-label={caption} className="min-h-0 flex-1" style={velaHostStyle(reduced, painted)} />
      <p aria-live="polite" className="m-0 border-t border-hair px-2 py-1 text-[0.7rem] text-ink-mute">
        {caption}
      </p>
    </div>
  );
}

/** LuxAlgo charts. BTC, ETH, and SOL from Coinbase. A failed feed keeps this chrome. */
export function VelaPane() {
  const [product, setProduct] = useState<VelaProduct>(VELA_PRODUCTS[0]);
  return (
    <div className="flex min-h-0 flex-1 flex-col gap-1 p-1">
      <div className="flex shrink-0 gap-1" role="group" aria-label="Coinbase products">
        {VELA_PRODUCTS.map((item) => (
          <Button
            key={item}
            type="button"
            size="xs"
            variant={item === product ? "secondary" : "ghost"}
            aria-pressed={item === product}
            onClick={() => setProduct(item)}
          >
            {item}
          </Button>
        ))}
      </div>
      <VelaChart key={product} product={product} />
    </div>
  );
}
