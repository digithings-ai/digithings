"use client";

import { useEffect, useRef } from "react";
import { ChatWidgetFrame } from "@digithings/web";
import {
  AreaSeries,
  ColorType,
  createChart,
  CrosshairMode,
  type AreaData,
  type IChartApi,
  type Time,
} from "lightweight-charts";

function generate(n: number) {
  let seed = 41213;
  const rnd = () => {
    seed = (seed * 1103515245 + 12345) & 0x7fffffff;
    return seed / 0x7fffffff;
  };
  const data: AreaData[] = [];
  let v = 100;
  const start = new Date(Date.UTC(2025, 0, 1));
  for (let i = 0; i < n; i++) {
    const date = new Date(start);
    date.setUTCDate(start.getUTCDate() + i * 3);
    v = Math.max(60, v * (1 + (rnd() - 0.45) * 0.045));
    data.push({ time: date.toISOString().slice(0, 10) as unknown as Time, value: v });
  }
  return data;
}

const DATA = generate(90);

/** A chart the assistant can drop straight into a turn — same engine and token
 *  discipline as the Finance surfaces, just compact and bubble-framed. The
 *  frame is the shared <ChatWidgetFrame variant="embed"> (@digithings/web);
 *  the Lightweight-Charts internals stay specimen-side. */
export function ChatInlineChartReference() {
  const hostRef = useRef<HTMLDivElement | null>(null);

  useEffect(() => {
    const host = hostRef.current;
    if (!host) return;
    const cssVar = (name: string, fb: string) =>
      getComputedStyle(host).getPropertyValue(name).trim() || fb;
    const toRgba = (col: string, a: number) => {
      const m = col.match(/[\d.]+/g);
      if (col.startsWith("#") || !m || m.length < 3) return col;
      return `rgba(${m[0]},${m[1]},${m[2]},${a})`;
    };
    const palette = () => ({
      inkMute: cssVar("--ink-mute", "#8A9097"),
      hair: cssVar("--hair", "rgba(255,255,255,0.1)"),
      accent: cssVar("--accent", "#e2708a"),
      mono: cssVar("--font-mono", "monospace"),
    });
    let p = palette();

    const chart: IChartApi = createChart(host, {
      autoSize: true,
      layout: {
        background: { type: ColorType.Solid, color: "transparent" },
        textColor: p.inkMute,
        fontFamily: p.mono,
        fontSize: 10,
        attributionLogo: false,
      },
      grid: { vertLines: { visible: false }, horzLines: { color: p.hair } },
      rightPriceScale: { borderVisible: false },
      timeScale: { borderColor: p.hair, timeVisible: false },
      crosshair: {
        mode: CrosshairMode.Magnet,
        vertLine: { color: p.inkMute, labelBackgroundColor: p.accent },
        horzLine: { visible: false, labelVisible: false },
      },
    });

    const area = chart.addSeries(AreaSeries, {
      lineColor: p.accent,
      topColor: toRgba(p.accent, 0.24),
      bottomColor: toRgba(p.accent, 0.02),
      lineWidth: 2,
      priceLineVisible: false,
    });
    area.setData(DATA);
    chart.timeScale().fitContent();

    const retheme = () => {
      p = palette();
      chart.applyOptions({
        layout: { textColor: p.inkMute },
        grid: { horzLines: { color: p.hair } },
        timeScale: { borderColor: p.hair },
      });
      area.applyOptions({
        lineColor: p.accent,
        topColor: toRgba(p.accent, 0.24),
        bottomColor: toRgba(p.accent, 0.02),
      });
    };
    const themeObs = new MutationObserver(retheme);
    themeObs.observe(document.documentElement, { attributes: true, attributeFilter: ["data-theme"] });

    return () => {
      themeObs.disconnect();
      chart.remove();
    };
  }, []);

  return (
    <section className="section-block">
      <p className="kicker">{"// inline chart"}</p>
      <h2 className="title">A chart inside the answer.</h2>
      <p className="section-copy">
        When the answer is a shape, the assistant renders it: the same Lightweight Charts engine as
        the Finance page, embedded in the bubble. It fills the bubble, re-themes with the surface,
        and wears the digichat accent — identity, not a P&amp;L read.
      </p>

      <div className="chat-surface mt-[1.3rem] max-w-[760px] flex flex-col gap-[0.7rem] rounded-[12px] border border-term-hair bg-term-bg px-[1.15rem] pt-[1rem] pb-[1.2rem] font-mono">
        <div className="flex gap-[0.55rem] items-baseline justify-start">
          <div className="chat-bubble--user min-w-0 border-0 bg-transparent p-0 font-mono text-[0.84rem] leading-[1.6] text-term-ink">
            show me the equity curve
          </div>
        </div>
        <div className="flex gap-[0.55rem] items-baseline chat-turn--assistant">
          <span className="shrink-0 font-mono text-[0.86rem] leading-[1.5] text-accent" aria-hidden="true">
            ▸
          </span>
          <div className="min-w-0 border-0 rounded-none bg-transparent p-0 text-ink-soft text-[0.88rem] leading-[1.6]">
            <p className="m-0 mb-[0.55rem] text-ink-soft text-[0.85rem]">
              Cumulative equity, last 90 sessions:
            </p>
            <ChatWidgetFrame variant="embed">
              <div className="w-full h-[180px]" ref={hostRef} aria-hidden="true" />
            </ChatWidgetFrame>
          </div>
        </div>
      </div>
    </section>
  );
}
