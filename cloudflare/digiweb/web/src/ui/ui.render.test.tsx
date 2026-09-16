import { renderToStaticMarkup } from "react-dom/server";
import { describe, expect, it } from "vitest";
import { Button, Card, CardContent, Input } from "./index";

describe("vendored ui kit renders server-side", () => {
  it("Button keeps the shadcn data-slot contract", () => {
    const html = renderToStaticMarkup(<Button>Run</Button>);
    expect(html).toContain('data-slot="button"');
    expect(html).toContain("Run");
  });

  it("Card composes parts", () => {
    const html = renderToStaticMarkup(
      <Card>
        <CardContent>body</CardContent>
      </Card>,
    );
    expect(html).toContain('data-slot="card"');
    expect(html).toContain("body");
  });

  it("Input renders with the input slot", () => {
    const html = renderToStaticMarkup(<Input placeholder="ticker" />);
    expect(html).toContain('data-slot="input"');
  });
});
