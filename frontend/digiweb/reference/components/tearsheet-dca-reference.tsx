"use client";
/**
 * DCA overlay charts — valuation rails (spot + low/median/high) and the
 * composite-risk band strip. Print-first SVG, same ViewWindow contract as
 * the rest of the finance-tearsheet family (#3172).
 */
import { useMemo } from "react";
import {
  ChartLegend,
  MultiTimeSeries,
  RISK_BANDS,
  RiskBandStrip,
  TEARSHEET_DEMO,
} from "@digithings/web";

const D = TEARSHEET_DEMO;

export function TearsheetDcaReference() {
  const spot = useMemo(() => D.bars.map((b) => ({ t: b.t, v: b.c })), []);
  const rails = useMemo(
    () =>
      D.bars.map((b) => ({
        t: b.t,
        low: b.c * 0.72,
        median: b.c * 0.98,
        high: b.c * 1.35,
      })),
    [],
  );
  const risk = useMemo(
    () =>
      D.bars.map((b, i) => ({
        t: b.t,
        v: Math.max(0, Math.min(100, 42 + 38 * Math.sin(i / 28))),
      })),
    [],
  );

  return (
    <div className="ts-print-root">
      <section className="ts-panel">
        <div className="ts-panel-head">
          <span className="ts-panel-label">Valuation rails</span>
          <ChartLegend
            items={[
              { kind: "line", label: "Spot" },
              { kind: "line-dashed", label: "Low / high" },
              { kind: "line-mute", label: "Median" },
            ]}
          />
        </div>
        <div className="ts-chart" style={{ height: 280 }}>
          <MultiTimeSeries
            series={[
              { id: "spot", label: "Spot", points: spot, tone: "accent", fill: true },
              {
                id: "low",
                label: "Low",
                points: rails.map((r) => ({ t: r.t, v: r.low })),
                tone: "mute",
                dashed: true,
              },
              {
                id: "median",
                label: "Median",
                points: rails.map((r) => ({ t: r.t, v: r.median })),
                tone: "mute",
              },
              {
                id: "high",
                label: "High",
                points: rails.map((r) => ({ t: r.t, v: r.high })),
                tone: "mute",
                dashed: true,
              },
            ]}
            height={280}
            scale="log"
            ariaLabel="Demo log price with valuation rails"
          />
        </div>
      </section>
      <section className="ts-panel">
        <div className="ts-panel-head">
          <span className="ts-panel-label">Risk band</span>
          <span className="ts-panel-hint">
            {RISK_BANDS.map((b) => `${b.lo}–${b.hi} ${b.label}`).join(" · ")}
          </span>
        </div>
        <div className="ts-chart" style={{ height: 220 }}>
          <RiskBandStrip points={risk} height={220} ariaLabel="Demo composite risk 0 to 100" />
        </div>
      </section>
    </div>
  );
}
