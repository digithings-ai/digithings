import { renderToStaticMarkup } from "react-dom/server"
import { describe, expect, it } from "vitest"

import { PipelineSelect } from "./pipeline-select"
import { PlanLadder } from "./plan-ladder"
import { Stat } from "./stat"
import { StepMeter } from "./step-meter"

describe("StepMeter", () => {
  it("fills proportionally with meter semantics", () => {
    const html = renderToStaticMarkup(<StepMeter label="Runs" value={3} limit={10} />)
    expect(html).toContain('role="meter"')
    expect(html).toContain('aria-valuenow="3"')
    expect(html.match(/data-filled="true"/g)).toHaveLength(3)
    expect(html.match(/data-slot="step-meter-cell"/g)).toHaveLength(10)
    expect(html).not.toContain("bg-warn")
  })
  it("warns near the limit", () => {
    const html = renderToStaticMarkup(<StepMeter label="Runs" value={9} limit={10} />)
    expect(html).toContain('data-state="warn"')
    expect(html).toContain("bg-warn")
  })
  it("handles null data", () => {
    const html = renderToStaticMarkup(<StepMeter value={null} limit={null} />)
    expect(html).toContain("—")
    expect(html).not.toContain('data-filled="true"')
  })
})

describe("PlanLadder", () => {
  const rungs = [
    { id: "a", name: "Alpha" },
    { id: "b", name: "Beta", meta: "x" },
    { id: "c", name: "Gamma", locked: true },
  ]
  it("marks current, available and locked rungs", () => {
    const html = renderToStaticMarkup(<PlanLadder rungs={rungs} current="b" />)
    expect(html).toContain('aria-current="step"')
    expect(html).toContain('data-state="current"')
    expect(html).toContain('data-state="locked"')
    expect(html).toContain('data-state="available"')
    expect(html).not.toMatch(/\$\d/)
  })
  it("renders the empty state", () => {
    expect(renderToStaticMarkup(<PlanLadder rungs={null} />)).toContain("No plans")
  })
})

describe("Stat", () => {
  it("renders label, value, delta and spark slot", () => {
    const html = renderToStaticMarkup(
      <Stat label="NAV" value="1.2m" delta="+1%" spark={<svg data-x="s" />} />
    )
    expect(html).toContain("NAV")
    expect(html).toContain("1.2m")
    expect(html).toContain("+1%")
    expect(html).toContain('data-x="s"')
  })
  it("shows a dash for missing value", () => {
    expect(renderToStaticMarkup(<Stat label="NAV" value={null} />)).toContain("—")
  })
})

describe("PipelineSelect", () => {
  const two = [
    { id: "base", label: "Baseline", kind: "baseline" },
    { id: "u1", label: "Mine", kind: "user" },
  ]
  it("shows the selected label with a linked label", () => {
    const html = renderToStaticMarkup(<PipelineSelect options={two} value="u1" />)
    expect(html).toContain("Mine")
    expect(html).toContain("<label")
    expect(html).not.toMatch(/\sdisabled(=|\s|>)/)
  })
  it("single option renders disabled showing that option", () => {
    const html = renderToStaticMarkup(<PipelineSelect options={[two[0]]} value="base" />)
    expect(html).toContain("Baseline")
    expect(html).toMatch(/\sdisabled(=|\s|>)/)
  })
  it("empty options do not throw", () => {
    expect(renderToStaticMarkup(<PipelineSelect options={null} value={null} />)).toContain(
      "No pipelines"
    )
  })
})
