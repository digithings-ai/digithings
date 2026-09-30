import { renderToStaticMarkup } from "react-dom/server"
import { describe, expect, it } from "vitest"

import { DivergingBars, ScoreBar } from "./diverging-bars"
import { CalendarHeatmap, HeatGrid } from "./heat-grid"
import { envelopeRange, RangeTrack, rangeFraction } from "./range-track"

describe("DivergingBars", () => {
  it("renders labelled signed bars with a summary label", () => {
    const html = renderToStaticMarkup(
      <DivergingBars
        label="Consensus"
        items={[
          { label: "USD", value: 1.5 },
          { label: "JPY", value: -0.5 },
          { label: "CHF", value: null },
        ]}
      />
    )
    expect(html).toContain('data-slot="diverging-bars"')
    expect(html).toContain('role="img"')
    expect(html).toContain("Consensus: USD +1.50, JPY -0.50, CHF")
    expect(html).toContain("fill-up")
    expect(html).toContain("fill-down")
    expect(html).not.toMatch(/#[0-9a-f]{3,6}\b/i)
  })

  it("ranks by value and handles empty", () => {
    const html = renderToStaticMarkup(
      <DivergingBars sort="desc" items={[{ label: "a", value: 1 }, { label: "b", value: 3 }]} />
    )
    expect(html.indexOf(">b<")).toBeLessThan(html.indexOf(">a<"))
    expect(renderToStaticMarkup(<DivergingBars items={[]} />)).toContain("data-empty")
  })
})

describe("ScoreBar", () => {
  it("draws fill, ticks and target; drops null ticks", () => {
    const html = renderToStaticMarkup(
      <ScoreBar
        value={0.5}
        ticks={[
          { value: 0.2, label: "prior" },
          { value: null, label: "ago" },
        ]}
        target={{ value: 0.8, label: "target" }}
      />
    )
    expect(html).toContain('data-slot="score-bar-fill"')
    expect(html.match(/data-slot="score-bar-tick"/g)).toHaveLength(1)
    expect(html).toContain('data-slot="score-bar-target"')
    expect(html).toContain("prior +0.20")
  })

  it("renders an empty track for null", () => {
    const html = renderToStaticMarkup(<ScoreBar value={null} />)
    expect(html).toContain("data-empty")
    expect(html).not.toContain("score-bar-fill")
    expect(html).toContain("no data")
  })
})

describe("RangeTrack", () => {
  it("places markers and pins out-of-range readings", () => {
    const { low, high } = envelopeRange(-5, 10)
    expect([low, high]).toEqual([-5, 10])
    expect(rangeFraction(0, low, high)).toBeCloseTo(1 / 3)
    const html = renderToStaticMarkup(
      <RangeTrack
        low={low}
        high={high}
        envelope
        markers={[
          { kind: "entry", value: 0 },
          { kind: "current", value: 12, label: "Now" },
        ]}
      />
    )
    expect(html).toContain('data-kind="entry"')
    expect(html).toContain('data-pinned="high"')
    expect(html).toContain("beyond the high end")
  })

  it("draws nothing for a zero-width or missing range", () => {
    for (const html of [
      renderToStaticMarkup(<RangeTrack low={0} high={0} markers={[{ value: 0 }]} />),
      renderToStaticMarkup(<RangeTrack low={null} high={3} />),
    ]) {
      expect(html).toContain("data-empty")
      expect(html).not.toContain("range-track-marker")
    }
  })
})

describe("HeatGrid", () => {
  it("renders sequential cells with levels and empty cells", () => {
    const html = renderToStaticMarkup(
      <HeatGrid rows={["a", "b"]} cols={["x", "y"]} values={[[1, 4], [null, 2]]} />
    )
    expect(html).toContain('data-slot="heat-grid"')
    expect(html.match(/data-slot="heat-grid-cell"/g)).toHaveLength(4)
    expect(html).toContain('data-level="4"')
    expect(html).toContain("data-empty")
    expect(html).toContain("color-mix")
  })

  it("diverging uses warn for negatives by default and down for pnl", () => {
    const v = [[-2, 2]]
    const health = renderToStaticMarkup(
      <HeatGrid rows={["r"]} cols={["a", "b"]} values={v} scale="diverging" />
    )
    expect(health).toContain("var(--warn)")
    expect(health).not.toContain("var(--down)")
    const pnl = renderToStaticMarkup(
      <HeatGrid rows={["r"]} cols={["a", "b"]} values={v} scale="diverging" palette="pnl" />
    )
    expect(pnl).toContain("var(--down)")
  })

  it("handles empty data", () => {
    expect(renderToStaticMarkup(<HeatGrid rows={[]} cols={[]} values={[]} />)).toContain(
      "data-empty"
    )
  })
})

describe("CalendarHeatmap", () => {
  it("renders day cells with the unit in tooltips and summary", () => {
    const html = renderToStaticMarkup(
      <CalendarHeatmap
        unit={{ singular: "doc", plural: "docs" }}
        days={[
          { date: "2026-08-02", count: 0 },
          { date: "2026-08-03", count: 1 },
          { date: "2026-08-04", count: 5 },
        ]}
      />
    )
    expect(html).toContain('data-slot="calendar-heatmap-cell"')
    expect(html).toContain("2026-08-03: 1 doc<")
    expect(html).toContain("2026-08-04: 5 docs")
    expect(html).toContain("6 docs from 2026-08-02 to 2026-08-04")
  })

  it("handles empty", () => {
    expect(renderToStaticMarkup(<CalendarHeatmap days={[]} />)).toContain("data-empty")
  })
})
