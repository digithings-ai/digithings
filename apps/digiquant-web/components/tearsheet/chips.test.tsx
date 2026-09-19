import { describe, expect, it } from "vitest";
import { renderToStaticMarkup } from "react-dom/server";
import { BacktestOnlyChip, OosHonestyChip } from "./honesty";
import { SignalDelayChip } from "./signal-delay";
import { StrategyTypeChip } from "./strategy-type-chip";

describe("tearsheet chips on the vendored kit Badge (wave 2 T3)", () => {
  it("renders the strategy type chip as a kit Badge with the soft tone", () => {
    const html = renderToStaticMarkup(<StrategyTypeChip strategy="btc_slapper" kind="long_short" />);
    expect(html).toContain('data-slot="badge"');
    expect(html).toContain("text-ink-soft");
    expect(html).toContain(">L/S<");
    expect(html).not.toContain("ts-chip");
  });

  it("keeps a call-site className (ts-card-kind) on the type badge", () => {
    const html = renderToStaticMarkup(
      <StrategyTypeChip strategy="btc_sdca" className="ts-card-kind" />,
    );
    expect(html).toContain('data-slot="badge"');
    expect(html).toContain("ts-card-kind");
    expect(html).toContain(">SDCA<");
  });

  it("carries the signal-delay copy, tooltip and accent tone", () => {
    const html = renderToStaticMarkup(<SignalDelayChip days={3} detail="full" />);
    const tip = "Signals are delayed 3 days (backtest; not a live strategy)";
    expect(html).toContain('data-slot="badge"');
    expect(html).toContain(`title="${tip}"`);
    expect(html).toContain(`aria-label="${tip}"`);
    expect(html).toContain("Signals delayed 3 days");
    expect(html).toContain("border-accent-weak bg-accent-weak");
    expect(html).not.toContain("ts-chip");
  });

  it("renders the concise signal-delay copy for cards", () => {
    const html = renderToStaticMarkup(<SignalDelayChip days={1} />);
    expect(html).toContain("Signals +1d delayed");
    expect(html).toContain("1 day");
  });

  it("renders no chip for absent or zero delay", () => {
    expect(renderToStaticMarkup(<SignalDelayChip days={0} />)).toBe("");
    expect(renderToStaticMarkup(<SignalDelayChip days={null} />)).toBe("");
    expect(renderToStaticMarkup(<SignalDelayChip days={undefined} />)).toBe("");
  });

  it("keeps the honesty chips' labels, tooltips and soft tone", () => {
    const backtest = renderToStaticMarkup(<BacktestOnlyChip />);
    expect(backtest).toContain('data-slot="badge"');
    expect(backtest).toContain("Backtest only");
    expect(backtest).toContain(
      'title="Illustrative Nautilus backtest — not a live trading strategy"',
    );
    expect(backtest).toContain('aria-label="Backtest only"');
    expect(backtest).toContain("text-ink-soft");

    expect(renderToStaticMarkup(<OosHonestyChip beatsFlatDcaOos={true} />)).toBe("");
    expect(renderToStaticMarkup(<OosHonestyChip beatsFlatDcaOos={null} />)).toContain(
      "Not OOS vs flat DCA",
    );
    const oos = renderToStaticMarkup(<OosHonestyChip beatsFlatDcaOos={false} />);
    expect(oos).toContain('aria-label="Does not beat flat DCA out of sample"');
    expect(oos).not.toContain("ts-chip");
  });
});
