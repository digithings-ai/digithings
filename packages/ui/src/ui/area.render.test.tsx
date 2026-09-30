import { renderToStaticMarkup } from "react-dom/server"
import { describe, expect, it } from "vitest"
import { StackedAreaChart } from "./stacked-area"
import { AllocationTreemap, squarify } from "./treemap"
import { WaterfallBridge, WaterfallTrace } from "./waterfall"

const data = [
  { date: "2026-01-01", eq: 60, bd: 30, cash: 10 },
  { date: "2026-02-01", eq: 50, bd: 30, cash: 20 },
  { date: "2026-03-01", eq: 55, bd: 35, cash: 10 },
]

describe("StackedAreaChart", () => {
  it("renders series paths, cash wash, legend, sr summary", () => {
    const html = renderToStaticMarkup(
      <StackedAreaChart
        data={data}
        keys={["eq", "bd"]}
        cashKey="cash"
        selectedX="2026-02-01"
        onSelect={() => {}}
      />,
    )
    expect(html).toContain('data-slot="stacked-area"')
    expect(html).toContain('role="img"')
    expect(html).toContain('data-series="cash"')
    expect(html).toContain("fill-ink-mute/25")
    expect(html).toContain("fill-accent/70")
    expect(html).toContain("stacked-area-selected")
    expect(html).toContain("sr-only")
    expect(html).not.toMatch(/#[0-9a-f]{6}/i)
  })
  it("handles empty, single-row and null data", () => {
    expect(renderToStaticMarkup(<StackedAreaChart data={[]} keys={["a"]} />)).toContain(
      "data-empty",
    )
    expect(
      renderToStaticMarkup(<StackedAreaChart data={[data[0]]} keys={["eq"]} />),
    ).toContain("<path")
    expect(
      renderToStaticMarkup(<StackedAreaChart data={[{ date: "x", a: null }]} keys={["a"]} />),
    ).not.toContain("NaN")
  })
})

describe("AllocationTreemap", () => {
  it("squarify conserves area", () => {
    const r = squarify([6, 6, 4, 3, 2, 2, 1], { x: 0, y: 0, w: 600, h: 400 })
    const area = r.reduce((s, q) => s + q.w * q.h, 0)
    expect(Math.round(area)).toBe(240000)
  })
  it("renders labelled cells with tone and selection, skips zero values", () => {
    const html = renderToStaticMarkup(
      <AllocationTreemap
        items={[
          { id: "a", label: "Equities", value: 60 },
          { id: "b", label: "Bonds", value: 30 },
          { id: "z", label: "Zero", value: 0 },
        ]}
        selectedId="a"
        onSelect={() => {}}
      />,
    )
    expect(html).toContain("Equities")
    expect(html).not.toContain(">Zero<")
    expect(html).toContain("stroke-accent")
    expect(html).toContain('role="button"')
    expect(html).toContain("fill-accent/")
  })
  it("empty", () => {
    expect(renderToStaticMarkup(<AllocationTreemap items={[]} />)).toContain("data-empty")
  })
})

describe("Waterfall", () => {
  it("bridge: signed steps use up/down by default, neutral opt-in", () => {
    const steps = [
      { label: "Start", value: 100, kind: "total" as const },
      { label: "Alpha", value: 12 },
      { label: "Fees", value: -5 },
      { label: "End", value: 107, kind: "total" as const },
    ]
    const pnl = renderToStaticMarkup(<WaterfallBridge steps={steps} />)
    expect(pnl).toContain("fill-up")
    expect(pnl).toContain("fill-down")
    const neutral = renderToStaticMarkup(<WaterfallBridge steps={steps} signTone="neutral" />)
    expect(neutral).not.toContain("fill-up")
    expect(neutral).toContain("fill-warn")
  })
  it("trace: health colours, never up/down", () => {
    const html = renderToStaticMarkup(
      <WaterfallTrace
        selectedId="b"
        onSelect={() => {}}
        rows={[
          { id: "a", label: "load", start: 0, duration: 40 },
          { id: "b", label: "score", start: 40, duration: 120, status: "warn", depth: 1 },
          { id: "c", label: "skip", start: 160, duration: 0, status: "mute" },
        ]}
      />,
    )
    expect(html).toContain("fill-accent")
    expect(html).toContain("fill-warn")
    expect(html).toContain("fill-ink-mute")
    expect(html).not.toMatch(/fill-(up|down)/)
    expect(html).not.toContain("NaN")
  })
  it("empty", () => {
    expect(renderToStaticMarkup(<WaterfallBridge steps={[]} />)).toContain("data-empty")
    expect(renderToStaticMarkup(<WaterfallTrace rows={[]} />)).toContain("data-empty")
  })
})
