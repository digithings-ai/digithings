// @vitest-environment happy-dom
"use client";

/**
 * The credit must render by default but honour an explicit `attribution: false`
 * opt-out resolved by the host (embed tenant / deploy `chrome.attribution`).
 * Before this, every skin mount passed a bare `attribution`, so the opt-out was
 * ignored and a titled opted-out tenant rendered two credits (m2502 review, M2).
 */

import { afterEach, describe, expect, it } from "vitest";
import { cleanup, render, screen } from "@testing-library/react";
import { CreditFooter } from "./credit-footer";
import { SkinChromeProvider, DEFAULT_SKIN_CHROME } from "./skin-chrome";

// No globals auto-cleanup in this package (vitest environment is node) —
// unmount between tests so getBy* queries see one render.
afterEach(() => cleanup());

describe("CreditFooter", () => {
  it("renders by default when no provider and no prop", () => {
    render(<CreditFooter />);
    expect(screen.getByText(/powered by digichat/i)).toBeTruthy();
  });

  it("reads the resolved attribution from SkinChromeProvider", () => {
    render(
      <SkinChromeProvider value={{ ...DEFAULT_SKIN_CHROME, attribution: true }}>
        <CreditFooter />
      </SkinChromeProvider>,
    );
    expect(screen.getByText(/powered by digichat/i)).toBeTruthy();
  });

  it("honours an attribution:false context (the embed opt-out)", () => {
    const { container } = render(
      <SkinChromeProvider value={{ ...DEFAULT_SKIN_CHROME, attribution: false }}>
        <CreditFooter />
      </SkinChromeProvider>,
    );
    expect(container.querySelector('[data-slot="aui_credit"]')).toBeNull();
  });

  it("lets an explicit prop override the context", () => {
    const { container } = render(
      <SkinChromeProvider value={{ ...DEFAULT_SKIN_CHROME, attribution: true }}>
        <CreditFooter attribution={false} />
      </SkinChromeProvider>,
    );
    expect(container.querySelector('[data-slot="aui_credit"]')).toBeNull();
  });
});
