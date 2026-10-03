import { describe, expect, it } from "vitest";
import { renderToStaticMarkup } from "react-dom/server";
import { bookModel } from "./terminal-book";
import { DeskView } from "./terminal-desk";

const reading = {
  loading: true,
  configured: true,
  error: null,
  navContractError: null,
  positions: [],
  nav: [],
  metricsAsOf: null,
  kpis: null,
};

describe("DeskView", () => {
  const html = renderToStaticMarkup(<DeskView model={bookModel(reading)} />);

  it("withholds figures while the official read is still open", () => {
    expect(html).toContain("01 / Book");
    expect(html).toContain("04 / Holdings");
    expect(html).toContain("06 / Drawdown");
    expect(html).toContain("Reading the official API.");
    expect(html).not.toContain("99.909");
    expect(html).not.toContain("204.04");
    expect(html).not.toContain("legacy_estimate");
    expect(html).toContain("—");
  });
});
