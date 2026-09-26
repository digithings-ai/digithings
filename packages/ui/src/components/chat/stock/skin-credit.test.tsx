// @vitest-environment happy-dom
import { cleanup, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it } from "vitest";

import { SkinCredit, SKIN_CREDIT_TEXT } from "./skin-credit";
import { DEFAULT_SKIN_CHROME, SkinChromeProvider } from "./skin-chrome";

afterEach(() => {
  cleanup();
});

describe("SkinCredit", () => {
  it("renders the branding line by default (no provider)", () => {
    render(<SkinCredit />);
    const el = screen.getByTestId("skin-credit");
    expect(el.textContent).toBe(SKIN_CREDIT_TEXT);
    // Boot carve-out hook: product-chrome lifts this above the overlay.
    expect(el.getAttribute("data-slot")).toBe("aui_credit");
    expect(SKIN_CREDIT_TEXT).toBe(
      "powered by digichat — a digithings product.",
    );
  });

  it("returns null when the host opted out of attribution", () => {
    render(
      <SkinChromeProvider
        value={{ ...DEFAULT_SKIN_CHROME, attribution: false }}
      >
        <SkinCredit />
      </SkinChromeProvider>,
    );
    expect(screen.queryByTestId("skin-credit")).toBeNull();
  });

  it("links digithings to the website in a distinct color", () => {
    render(<SkinCredit />);
    const link = screen.getByRole("link", { name: "digithings" });
    expect(link.getAttribute("href")).toBe("https://digithings.ai");
    expect(link.getAttribute("target")).toBe("_blank");
    expect(link.className).toMatch(/text-primary/);
  });

  it("merges an override class onto the disclaimer styling", () => {
    render(<SkinCredit className="font-mono" />);
    const el = screen.getByTestId("skin-credit");
    expect(el.className).toMatch(/font-mono/);
    expect(el.className).toMatch(/text-xs/);
  });
});
