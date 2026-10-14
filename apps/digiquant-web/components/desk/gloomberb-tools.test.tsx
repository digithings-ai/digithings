import { describe, expect, it } from "vitest";
import { renderToStaticMarkup } from "react-dom/server";
import { GloomberbTools } from "./gloomberb-tools";

describe("Gloomberb tools", () => {
  it("brands the empty surface as Gloomberb", () => {
    const html = renderToStaticMarkup(<GloomberbTools />);
    expect(html).toContain("Gloomberb");
    expect(html).toContain("Gloomberb tools are not mounted on this desk yet.");
    expect(html.toLowerCase()).not.toContain("digiquant");
  });

  it("lists Gloomberb tools once they are mounted", () => {
    const html = renderToStaticMarkup(<GloomberbTools tools={["digifetch_quote"]} />);
    expect(html).toContain("digifetch_quote");
    expect(html).not.toContain("not mounted");
  });
});
