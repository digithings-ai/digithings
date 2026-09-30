import { renderToStaticMarkup } from "react-dom/server"
import { describe, expect, it } from "vitest"

import { Donut } from "./donut"

const MIX = [
  { label: "Equity", value: 60 },
  { label: "Credit", value: 20 },
  { label: "Cash", value: 20, cash: true },
]

describe("Donut", () => {
  it("draws one arc and one legend row per positive segment", () => {
    const html = renderToStaticMarkup(
      <Donut segments={[...MIX, { label: "Zero", value: 0 }, { label: "Bad", value: NaN }]} />
    )
    expect(html.match(/data-slot="donut-arc"/g)).toHaveLength(3)
    expect(html.match(/data-slot="donut-legend-row"/g)).toHaveLength(3)
    expect(html).toContain("Equity 60%")
  })
  it("sizes arcs by share of the whole", () => {
    const html = renderToStaticMarkup(<Donut segments={MIX} size={100} thickness={20} />)
    const c = 2 * Math.PI * 40
    // 60% arc, minus the 1.5px gap between segments.
    expect(html).toContain(`stroke-dasharray="${0.6 * c - 1.5} ${c - (0.6 * c - 1.5)}"`)
  })
  it("draws cash in hair and never in up/down", () => {
    const html = renderToStaticMarkup(<Donut segments={MIX} />)
    expect(html).toContain("stroke-hair")
    expect(html).not.toMatch(/stroke-(up|down)\b/)
  })
  it("dims repeated palette tones and renders centre content", () => {
    const many = Array.from({ length: 7 }, (_, i) => ({ label: `S${i}`, value: 10 }))
    const html = renderToStaticMarkup(<Donut segments={many}>82%</Donut>)
    expect(html).toContain("opacity-60")
    expect(html).toContain("82%")
  })
  it("renders an empty ring without legend when there is no data", () => {
    const html = renderToStaticMarkup(<Donut segments={[]} />)
    expect(html).toContain('aria-label="No data"')
    expect(html).not.toContain("donut-legend")
  })
})
