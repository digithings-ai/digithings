import { renderToStaticMarkup } from "react-dom/server";
import { describe, expect, it } from "vitest";

import { DigichatLauncher } from "./DigichatLauncher";

describe("DigichatLauncher", () => {
  it("renders a square compact-mark trigger in contained mode", () => {
    const html = renderToStaticMarkup(
      <DigichatLauncher portal={false}>
        <iframe title="digichat embed" />
      </DigichatLauncher>,
    );

    expect(html).toContain("digichat-launcher--contained");
    expect(html).toContain("digichat-launcher__trigger");
    expect(html).toContain('aria-label="Open digichat"');
    expect(html).toContain("digichat-launcher__mark");
    expect(html).toContain("digichat-launcher__cursor");
    expect(html).not.toContain("digichat-launcher__panel");
  });

  it("renders the panel, close control, and consumer content when open", () => {
    const html = renderToStaticMarkup(
      <DigichatLauncher portal={false} defaultOpen title="page assistant">
        <iframe title="digichat embed" />
      </DigichatLauncher>,
    );

    expect(html).toContain('role="dialog"');
    expect(html).toContain("page assistant");
    expect(html).toContain('aria-label="Close digichat"');
    expect(html).toContain('title="digichat embed"');
    expect(html).not.toContain("digichat-launcher__trigger");
  });
});
