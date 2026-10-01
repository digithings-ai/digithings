import { renderToStaticMarkup } from "react-dom/server"
import { describe, expect, it } from "vitest"

import { CompositionBar } from "./composition-bar"
import { Sparkline } from "./sparkline"
import { StatusDot, StatusStrip } from "./status-strip"

describe("Sparkline", () => {
  it("renders a labelled svg with a last dot", () => {
    const html = renderToStaticMarkup(<Sparkline values={[1, 2, 3, 2]} />)
    expect(html).toContain('data-slot="sparkline"')
    expect(html).toContain('role="img"')
    expect(html).toContain("<circle")
  })
  it("breaks the line at null gaps", () => {
    const html = renderToStaticMarkup(
      <Sparkline values={[1, 2, null, 3, 4]} lastDot={false} />
    )
    expect(html.match(/<path/g)?.length).toBe(2)
  })
  it("handles empty and flat data", () => {
    expect(renderToStaticMarkup(<Sparkline values={[]} />)).toContain("no data")
    expect(renderToStaticMarkup(<Sparkline values={[null, null]} />)).toContain(
      "data-empty"
    )
    expect(
      renderToStaticMarkup(<Sparkline values={[5, 5, 5]} area />)
    ).not.toContain("NaN")
  })
})

describe("StatusDot / StatusStrip", () => {
  it("dot is decorative without label", () => {
    expect(renderToStaticMarkup(<StatusDot tone="warn" />)).toContain(
      'aria-hidden="true"'
    )
    expect(renderToStaticMarkup(<StatusDot label="live" />)).toContain(
      'aria-label="live"'
    )
  })
  it("strip renders cells with tooltip labels and tones", () => {
    const html = renderToStaticMarkup(
      <StatusStrip
        cells={[
          { label: "run 1" },
          { label: "run 2", tone: "warn" },
          { label: "run 3", tone: "off" },
        ]}
      />
    )
    expect(html).toContain('title="run 2"')
    expect(html).toContain('data-tone="warn"')
    expect(html).toContain("1 ok, 1 warn, 1 off")
    expect(html).not.toContain("<button")
  })
  it("cells are buttons with onSelect; empty is safe", () => {
    expect(
      renderToStaticMarkup(
        <StatusStrip cells={[{ label: "a" }]} onSelect={() => {}} />
      )
    ).toContain("<button")
    expect(renderToStaticMarkup(<StatusStrip cells={[]} />)).toContain("no data")
  })
})

describe("CompositionBar", () => {
  const segs = [
    { label: "Equity", value: 60 },
    { label: "Bonds", value: 20 },
    { label: "Cash", value: 20, cash: true },
  ]
  it("normalises to shares and styles cash", () => {
    const html = renderToStaticMarkup(<CompositionBar segments={segs} legend />)
    expect(html).toContain("width:60%")
    expect(html).toContain('data-tone="cash"')
    expect(html).toContain("Equity 60%")
  })
  it("stacked mode keeps a partial bar partial", () => {
    const html = renderToStaticMarkup(
      <CompositionBar mode="stacked" total={200} segments={segs} />
    )
    expect(html).toContain("width:30%")
  })
  it("segments are buttons with onSelect; empty is safe", () => {
    expect(
      renderToStaticMarkup(<CompositionBar segments={segs} onSelect={() => {}} />)
    ).toContain("<button")
    expect(
      renderToStaticMarkup(<CompositionBar segments={[{ label: "x", value: 0 }]} />)
    ).toContain("no data")
  })
})
