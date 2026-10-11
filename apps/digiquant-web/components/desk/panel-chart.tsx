"use client";

import { useEffect, useRef, useState } from "react";
import type { ChartType, PanelPoint, PanelShape, PanelUnit } from "../../../../clients/digiquant-tui/src/pages/panel-shape";
import { chartEngine, inkFrom, echartsOption, velaConfig, velaOptions, type ChartInk } from "./panel-chart-options";

/** Caption when a chart fails to mount. The table toggle still has the numbers. */
export const CHART_UNAVAILABLE = "Chart unavailable · the table has the numbers";

type Input = { shape: PanelShape; type: ChartType; points: PanelPoint[]; unit: PanelUnit };

function readInk(host: HTMLElement): ChartInk {
  const style = getComputedStyle(host);
  return inkFrom((token) => style.getPropertyValue(token), style.fontFamily);
}

type Mounted = { resize: () => void; destroy: () => void };

/** Mounts the chart into `host`; resolves to its teardown, or null when the effect died while
 *  the library loaded. Both libraries load on first use. */
async function mount(host: HTMLDivElement, input: Input, ink: ChartInk, reduced: boolean, alive: () => boolean): Promise<Mounted | null> {
  const { shape, type, points, unit } = input;
  if (chartEngine(unit, type, points) === "vela" && (type === "line" || type === "area")) {
    const { Vela } = await import("@luxalgo/vela");
    if (!alive()) return null;
    const chart = new Vela(host, velaOptions(type, points, ink, reduced));
    chart.renderer.applyConfig(velaConfig(ink));
    return { resize: () => chart.resize(), destroy: () => chart.destroy() };
  }
  const [core, charts, components, renderers] = await Promise.all([
    import("echarts/core"),
    import("echarts/charts"),
    import("echarts/components"),
    import("echarts/renderers"),
  ]);
  if (!alive()) return null;
  core.use([
    charts.LineChart,
    charts.BarChart,
    charts.PieChart,
    charts.TreemapChart,
    charts.HeatmapChart,
    components.GridComponent,
    components.TooltipComponent,
    components.LegendComponent,
    components.VisualMapComponent,
    renderers.CanvasRenderer,
  ]);
  const chart = core.init(host, undefined, { renderer: "canvas" });
  chart.setOption(echartsOption(shape, type, points, unit, ink, reduced));
  return { resize: () => chart.resize(), destroy: () => chart.dispose() };
}

/** Draws one panel's points: Vela for an index level over dates, ECharts for everything else.
 *  Hairline axes, no gridlines, mono labels, a hover tooltip. */
export function PanelChart({ shape, type, points, unit, label }: Input & { label: string }) {
  const ref = useRef<HTMLDivElement>(null);
  const engine = chartEngine(unit, type, points);
  const key = JSON.stringify({ shape, type, points, unit });
  const [failedKey, setFailedKey] = useState<string | null>(null);

  useEffect(() => {
    const host = ref.current;
    if (!host) return;
    const input = JSON.parse(key) as Input;
    const reduced = window.matchMedia?.("(prefers-reduced-motion: reduce)").matches ?? false;
    let dead = false;
    let chart: Mounted | null = null;
    const observer = typeof ResizeObserver === "undefined" ? null : new ResizeObserver(() => chart?.resize());

    mount(host, input, readInk(host), reduced, () => !dead)
      .then((mounted) => {
        if (!mounted) return;
        chart = mounted;
        observer?.observe(host);
      })
      .catch(() => {
        if (!dead) setFailedKey(key);
      });

    return () => {
      dead = true;
      observer?.disconnect();
      chart?.destroy();
      chart = null;
    };
  }, [key]);

  return (
    <div role="img" aria-label={label} data-chart={type} data-engine={engine} className="relative block h-full min-h-[10rem] w-full font-mono">
      <div ref={ref} className="absolute inset-0" />
      {failedKey === key ? (
        <p aria-live="polite" className="absolute inset-x-0 bottom-0 m-0 font-mono text-[0.6875rem] tracking-[0.04em] text-ink-mute">
          {CHART_UNAVAILABLE}
        </p>
      ) : null}
    </div>
  );
}
