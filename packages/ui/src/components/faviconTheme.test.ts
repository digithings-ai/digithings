import { describe, expect, it } from "vitest";

import { faviconThemeScript } from "./faviconTheme";

describe("faviconThemeScript", () => {
  it("follows data-theme and both icon pairs", () => {
    const script = faviconThemeScript({
      dark: "/icons/digi-app-dark.svg",
      light: "/icons/digi-app-light.svg",
      touchDark: "/icons/digi-app-touch-dark.png",
      touchLight: "/icons/digi-app-touch-light.png",
    });
    expect(script).toContain('getAttribute("data-theme")==="light"');
    expect(script).toContain("/icons/digi-app-dark.svg");
    expect(script).toContain("/icons/digi-app-light.svg");
    expect(script).toContain("/icons/digi-app-touch-dark.png");
    expect(script).toContain("/icons/digi-app-touch-light.png");
    expect(script).toContain("MutationObserver");
    expect(script).not.toContain("prefers-color-scheme");
  });
});
