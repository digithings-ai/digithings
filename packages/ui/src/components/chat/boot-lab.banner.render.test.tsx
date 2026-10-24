import { renderToStaticMarkup } from "react-dom/server";
import { describe, expect, it } from "vitest";
import * as React from "react";

import { BootLabOverlay } from "./boot-lab";

// Test-env only: packages/hero-banner ships no tsconfig, so vitest compiles
// its web.tsx with classic JSX while production (Next.js) uses automatic.
// The free `React` name resolves here at render time.
(globalThis as unknown as Record<string, unknown>).React ??= React;

/**
 * The site shell (ChatEmbedShell) has always shown the digichat hero banner
 * while the chat boots. The banner variant is that same cover, so every
 * digichat deployment gets it without the site shell around it: the wrapper
 * that gives the canvas a width, the DIGICHAT definition, and the sr-only
 * label — no copy and no spinner.
 */
function markup() {
  return renderToStaticMarkup(
    <BootLabOverlay variant="banner" ready={false} onSettled={() => {}} />,
  );
}

describe("BootLabOverlay — banner", () => {
  it("renders the digichat hero banner inside the sized cover", () => {
    const html = markup();
    expect(html).toContain('data-variant="banner"');
    // The canvas comes from @digithings/hero-banner, not a reimplementation.
    expect(html).toContain('aria-label="digichat"');
    expect(html).toContain("min(560px, 72vw)");
  });

  it("keeps the cover's screen-reader label", () => {
    expect(markup()).toContain("Loading chat…");
  });

  it("draws no boot rows or spinner beside the banner", () => {
    const html = markup();
    expect(html).not.toContain("dboot-lab-line");
    expect(html).not.toContain("dboot-lab-tools");
  });
});
