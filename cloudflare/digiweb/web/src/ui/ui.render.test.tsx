import { renderToStaticMarkup } from "react-dom/server";
import { describe, expect, it } from "vitest";
import {
  Alert,
  AlertDescription,
  AlertTitle,
  Badge,
  Button,
  Card,
  CardContent,
  Input,
  Label,
  Separator,
  Textarea,
} from "./index";

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

  it("Textarea renders with the textarea slot", () => {
    const html = renderToStaticMarkup(<Textarea placeholder="notes" />);
    expect(html).toContain('data-slot="textarea"');
  });

  it("Label renders with the label slot", () => {
    const html = renderToStaticMarkup(<Label htmlFor="ticker">Ticker</Label>);
    expect(html).toContain('data-slot="label"');
    expect(html).toContain('for="ticker"');
  });

  it("Separator renders with the separator slot", () => {
    const html = renderToStaticMarkup(<Separator />);
    expect(html).toContain('data-slot="separator"');
  });

  it("Badge renders with the badge slot", () => {
    const html = renderToStaticMarkup(<Badge>live</Badge>);
    expect(html).toContain('data-slot="badge"');
    expect(html).toContain("live");
  });

  it("Alert composes parts", () => {
    const html = renderToStaticMarkup(
      <Alert>
        <AlertTitle>Heads up</AlertTitle>
        <AlertDescription>body</AlertDescription>
      </Alert>,
    );
    expect(html).toContain('data-slot="alert"');
    expect(html).toContain('data-slot="alert-title"');
    expect(html).toContain('data-slot="alert-description"');
  });
});
