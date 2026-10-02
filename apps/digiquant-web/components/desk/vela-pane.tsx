"use client";

import { useEffect, useRef, useState } from "react";
import { Button } from "@digithings/ui/ui";
import {
  VELA_FEED_MAX_MS,
  VELA_PRODUCTS,
  VELA_UNAVAILABLE,
  velaChartOptions,
  velaHostStyle,
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
    let destroy = () => {};

    const fail = () => {
      if (dead || shown) return;
      setCaption(VELA_UNAVAILABLE);
    };

    const mount = async () => {
      const [{ Vela: VelaChartCtor }, { CoinbaseProvider }] = await Promise.all([
        import("@luxalgo/vela"),
        import("@luxalgo/vela/providers/coinbase"),
      ]);
      if (dead) return;
      const chart = new VelaChartCtor(host, {
        ...velaChartOptions(product, prefersReduced),
        theme: THEME,
        upColor: UP,
        downColor: DOWN,
      });
      destroy = () => chart.destroy();
      const lockScale = () => {
        try {
          chart.renderer.set({ animAutoscale: 0, autoScale: false });
        } catch {
          /* renderer without a scale lock */
        }
      };
      const fadeIn = () => {
        if (dead || shown) return;
        shown = true;
        lockScale();
        chart.resize();
        lockScale();
        setPainted(true);
      };
      chart.data.registerProvider("coinbase", new CoinbaseProvider());
      const source = chart.data.providerInstance("coinbase") as BarSource | undefined;
      if (source?.getBars) {
        void source.getBars(product, "1", { limit: 300 }).catch(() => undefined);
      }
      chart.on("load:end", (ev) => {
        if (dead) return;
        if ((ev?.bars ?? 0) > 0) fadeIn();
        else fail();
      });
      await chart.ready().catch(() => undefined);
      if (dead) return;
      if (chart.replay.bounds) fadeIn();
      else if (prefersReduced) fail();
    };

    const timer = window.setTimeout(() => {
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
