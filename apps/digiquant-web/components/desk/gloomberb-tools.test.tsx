import { describe, expect, it } from "vitest";
import { renderToStaticMarkup } from "react-dom/server";
import ToolsGloomberbPage from "../../app/app/tools/gloomberb/page";
import { GloomberbTools } from "./gloomberb-tools";

describe("Gloomberb tools", () => {
  it("brands the empty surface as Gloomberb", () => {
    const html = renderToStaticMarkup(<GloomberbTools />);
    expect(html).toContain("Gloomberb");
    expect(html).toContain("Gloomberb tools are not mounted on this desk yet.");
    expect(html.toLowerCase()).not.toContain("digiquant");
  });

  it("lists Gloomberb tools once they are mounted", () => {
    const html = renderToStaticMarkup(<GloomberbTools tools={["gloomberb_quote"]} />);
    expect(html).toContain("gloomberb_quote");
    expect(html).not.toContain("digifetch_");
    expect(html).not.toContain("not mounted");
  });

  it("mounts gloomberb registry names on the page", () => {
    const html = renderToStaticMarkup(ToolsGloomberbPage());
    expect(html).toContain("gloomberb_quote");
    expect(html).not.toContain("not mounted");
    expect(html).not.toContain("digifetch_");
    expect(html.toLowerCase()).not.toContain("digiquant");
  });
});
