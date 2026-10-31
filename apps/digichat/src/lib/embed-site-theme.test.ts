// @vitest-environment happy-dom
import { afterEach, describe, expect, it } from "vitest";
import {
  SITE_RAILS_SCRIPT,
  embedDocumentFollowsSiteTheme,
  embedPalettePinScript,
  themePinScript,
} from "./embed-site-theme";

function run(script: string): void {
  // The script is a constant, the same string the document inlines.
  new Function(script)();
}

afterEach(() => {
  document.documentElement.removeAttribute("data-theme");
  document.documentElement.removeAttribute("data-theme-pin");
  document.documentElement.removeAttribute("data-palette");
  document.documentElement.removeAttribute("data-site-theme");
  document.documentElement.removeAttribute("data-site-rails");
  document.documentElement.className = "";
  window.history.replaceState(null, "", "/");
});

describe("embed site theme pin", () => {
  it("follows the site on a top-level URL with no theme lock", () => {
    expect(embedDocumentFollowsSiteTheme(true, "?host=occ.digithings.ai")).toBe(true);
    expect(embedDocumentFollowsSiteTheme(true, "?theme=dark")).toBe(false);
    expect(embedDocumentFollowsSiteTheme(false, "")).toBe(false);
  });

  it("leaves the site paint in place on a top-level chat", () => {
    document.documentElement.setAttribute("data-theme", "dark");
    document.documentElement.setAttribute("data-palette", "nord");
    window.history.replaceState(null, "", "/chat/embed?host=occ.digithings.ai");
    run(themePinScript("light"));
    expect(document.documentElement.getAttribute("data-theme")).toBe("dark");
    expect(document.documentElement.getAttribute("data-palette")).toBe("nord");
    expect(document.documentElement.getAttribute("data-site-theme")).toBe("1");
    expect(document.documentElement.hasAttribute("data-theme-pin")).toBe(false);
  });

  it("pins an iframe-style lock when the URL names a theme", () => {
    document.documentElement.setAttribute("data-theme", "dark");
    document.documentElement.setAttribute("data-palette", "nord");
    window.history.replaceState(null, "", "/embed?theme=light&host=digithings.ai");
    run(themePinScript("light"));
    expect(document.documentElement.getAttribute("data-theme")).toBe("light");
    expect(document.documentElement.getAttribute("data-theme-pin")).toBe("1");
    expect(document.documentElement.hasAttribute("data-palette")).toBe(false);
    expect(document.documentElement.hasAttribute("data-site-theme")).toBe(false);
    expect(document.documentElement.classList.contains("light")).toBe(true);
  });

  it("adopts an allowlisted palette only while pinned", () => {
    window.history.replaceState(null, "", "/embed?theme=dark&palette=dracula");
    run(embedPalettePinScript());
    expect(document.documentElement.hasAttribute("data-palette")).toBe(false);

    document.documentElement.setAttribute("data-theme-pin", "1");
    run(embedPalettePinScript());
    expect(document.documentElement.getAttribute("data-palette")).toBe("dracula");

    window.history.replaceState(null, "", "/embed?theme=dark&palette=not-a-palette");
    document.documentElement.removeAttribute("data-palette");
    run(embedPalettePinScript());
    expect(document.documentElement.hasAttribute("data-palette")).toBe(false);
  });

  it("marks rails only for the top-level document", () => {
    run(SITE_RAILS_SCRIPT);
    expect(document.documentElement.getAttribute("data-site-rails")).toBe("1");
  });

  it("does not interpolate request data into the script source", () => {
    const light = themePinScript("light");
    const dark = themePinScript("dark");
    expect(light).toContain("data-site-theme");
    expect(light).not.toContain("occ.digithings.ai");
    expect(dark).toContain("window.top===window");
    expect(embedPalettePinScript()).toContain("dracula");
    expect(embedPalettePinScript()).not.toContain("${");
  });
});
