import { describe, expect, it } from "vitest";
import {
  buildPopupEmbedSrc,
  originFromScriptSrc,
  parsePopupLauncherMode,
  readPopupWidgetConfigFromScript,
} from "@/lib/embed-popup-config";

describe("embed-popup-config", () => {
  it("parses launcher mode (default dot)", () => {
    expect(parsePopupLauncherMode(undefined)).toBe("dot");
    expect(parsePopupLauncherMode("bar")).toBe("bar");
    expect(parsePopupLauncherMode("DOT")).toBe("dot");
  });

  it("derives origin from absolute script src", () => {
    expect(originFromScriptSrc("https://chat.example/widget.js")).toBe("https://chat.example");
    expect(originFromScriptSrc("/widget.js")).toBe("");
  });

  it("reads data-* config from the script tag", () => {
    const attrs: Record<string, string> = {
      src: "https://digithings.ai/widget.js",
      "data-host": "digithings.ai",
      "data-mode": "bar",
      "data-theme": "light",
      "data-accent": "#112233",
      "data-page-context": "1",
      "data-page-context-max-chars": "1000",
      "data-token": "tenant-token",
    };
    const script = {
      src: attrs.src,
      getAttribute: (name: string) => attrs[name] ?? null,
    };
    const cfg = readPopupWidgetConfigFromScript(script);
    expect(cfg).toEqual({
      origin: "https://digithings.ai",
      host: "digithings.ai",
      token: "tenant-token",
      mode: "bar",
      theme: "light",
      accent: "#112233",
      pageContext: true,
      pageContextMaxChars: 1000,
    });
  });

  it("returns null without origin/host", () => {
    const script = {
      getAttribute: () => null,
    };
    expect(readPopupWidgetConfigFromScript(script)).toBeNull();
  });

  it("builds /embed URL with layout=embed (not wide)", () => {
    const src = buildPopupEmbedSrc({
      origin: "https://digithings.ai/",
      host: "occ.digithings.ai",
      mode: "dot",
      pageContext: false,
      pageContextMaxChars: 8000,
      theme: "dark",
      accent: "#abcdef",
      token: "t1",
    });
    const url = new URL(src);
    expect(url.origin).toBe("https://digithings.ai");
    expect(url.pathname).toBe("/embed");
    expect(url.searchParams.get("host")).toBe("occ.digithings.ai");
    expect(url.searchParams.get("layout")).toBe("embed");
    expect(url.searchParams.get("theme")).toBe("dark");
    expect(url.searchParams.get("accent")).toBe("#abcdef");
    expect(url.searchParams.get("token")).toBe("t1");
    expect(url.searchParams.get("wide")).toBeNull();
  });
});
