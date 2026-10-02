import { readFileSync } from "node:fs";
import { describe, expect, it, vi } from "vitest";
import { renderToStaticMarkup } from "react-dom/server";
import { DashboardBand } from "@/app/_bands/dashboard";
import {
  CLICK_FALLBACK_MS,
  DESK_EMPTY_COPY,
  activateNavLink,
  activeStop,
  bindYieldListeners,
  dashboardReady,
  deskStatus,
  embedLooksDown,
  navAnchor,
  nextWalkAnchor,
  nextWalkStop,
  probeEmbed,
  shouldYieldToUser,
  stopFromPath,
} from "./desk-walk";

function docWith(
  links: { label: string; href: string; current?: boolean }[],
  extra: { title?: string; body?: string; pathname?: string } = {},
): Document {
  const anchors = links.map((link) => ({
    textContent: ` ${link.label} `,
    isConnected: true,
    getAttribute: (name: string) => {
      if (name === "href") return link.href;
      if (name === "aria-current") return link.current ? "page" : null;
      return null;
    },
  }));
  return {
    title: extra.title ?? "digiquant",
    body: { textContent: extra.body ?? "" },
    location: {
      href: `http://127.0.0.1:3910${extra.pathname ?? "/app/brief"}`,
      pathname: extra.pathname ?? "/app/brief",
    },
    querySelector: (sel: string) => {
      if (sel === 'nav[aria-label="Pages"]') {
        return { querySelectorAll: () => anchors };
      }
      return null;
    },
  } as unknown as Document;
}

const shell = [
  { label: "/brief", href: "/app/brief" },
  { label: "/portfolio", href: "/app/portfolio" },
  { label: "/pipeline", href: "/app/pipeline" },
  { label: "/fx", href: "/app/fx" },
];

describe("desk walk", () => {
  it("keeps the empty and cross-origin lines free of invented figures", () => {
    expect(deskStatus("empty")).toBe("The terminal did not load.");
    expect(deskStatus("live")).toContain("not same-origin");
    expect(DESK_EMPTY_COPY).not.toMatch(/99\.909|204\.04|legacy_estimate/);
  });

  it("cycles Brief, Portfolio, and Pipeline", () => {
    expect(nextWalkStop(null)).toBe("Portfolio");
    expect(nextWalkStop("Brief")).toBe("Portfolio");
    expect(nextWalkStop("Portfolio")).toBe("Pipeline");
    expect(nextWalkStop("Pipeline")).toBe("Brief");
    const home = docWith(shell, { pathname: "/app/brief" });
    expect(nextWalkAnchor(home)?.getAttribute("href")).toBe("/app/portfolio");
  });

  it("reads the frame path when the sidebar has no current page", () => {
    expect(stopFromPath("/app")).toBe("Brief");
    expect(stopFromPath("/app/brief")).toBe("Brief");
    expect(stopFromPath("/app/portfolio/")).toBe("Portfolio");
    expect(stopFromPath("/app/pipeline/runs")).toBe("Pipeline");
    expect(stopFromPath("/dashboard/")).toBeNull();
    expect(stopFromPath("/#pipeline")).toBeNull();
    const doc = docWith(shell, { pathname: "/app/portfolio/" });
    expect(activeStop(doc)).toBe("Portfolio");
  });

  it("clicks only the terminal sidebar anchors", () => {
    const doc = docWith([
      ...shell,
      { label: "Pipeline", href: "/#pipeline" },
    ]);
    expect(dashboardReady(doc)).toBe(true);
    expect(navAnchor(doc, "Pipeline")?.getAttribute("href")).toBe("/app/pipeline");
    const landing = docWith([
      { label: "Dashboard", href: "/#dashboard" },
      { label: "Pipeline", href: "/#pipeline" },
    ]);
    expect(dashboardReady(landing)).toBe(false);
    expect(navAnchor(landing, "Pipeline")).toBeNull();
  });

  it("yields on a trusted pointer, wheel, or key, and ignores the scripted click", () => {
    expect(shouldYieldToUser({ isTrusted: true, type: "pointerdown" })).toBe(true);
    expect(shouldYieldToUser({ isTrusted: true, type: "wheel" })).toBe(true);
    expect(shouldYieldToUser({ isTrusted: true, type: "keydown" })).toBe(true);
    expect(shouldYieldToUser({ isTrusted: false, type: "pointerdown" })).toBe(false);
    expect(shouldYieldToUser({ isTrusted: false, type: "click" })).toBe(false);
    expect(shouldYieldToUser({ isTrusted: true, type: "pointermove" })).toBe(false);

    const target = new EventTarget();
    let yielded = 0;
    const off = bindYieldListeners(target, () => {
      yielded += 1;
    });
    target.dispatchEvent(new Event("pointerdown"));
    expect(yielded).toBe(0);
    off();
    target.dispatchEvent(new Event("wheel"));
    expect(yielded).toBe(0);
  });

  it("follows the anchor href when the click does not navigate", () => {
    vi.useFakeTimers();
    const assign = vi.fn();
    const link = {
      href: "http://127.0.0.1:3910/app/portfolio",
      isConnected: true,
      click: vi.fn(),
      ownerDocument: {
        location: { href: "http://127.0.0.1:3910/app/brief", assign },
      },
    } as unknown as HTMLAnchorElement;
    const cancel = activateNavLink(link);
    expect(link.click).toHaveBeenCalledOnce();
    vi.advanceTimersByTime(CLICK_FALLBACK_MS);
    expect(assign).toHaveBeenCalledWith(link.href);
    cancel();
    vi.useRealTimers();
  });

  it("does not assign when the click already moved the frame", () => {
    vi.useFakeTimers();
    let href = "http://127.0.0.1:3910/app/brief";
    const assign = vi.fn();
    const link = {
      href: "http://127.0.0.1:3910/app/pipeline",
      isConnected: true,
      click: () => {
        href = "http://127.0.0.1:3910/app/pipeline";
      },
      ownerDocument: {
        location: {
          get href() {
            return href;
          },
          assign,
        },
      },
    } as unknown as HTMLAnchorElement;
    activateNavLink(link);
    vi.advanceTimersByTime(CLICK_FALLBACK_MS);
    expect(assign).not.toHaveBeenCalled();
    vi.useRealTimers();
  });

  it("treats a same-origin miss as down and an opaque frame as not scriptable", () => {
    const down = docWith([{ label: "Pipeline", href: "/#pipeline" }], {
      title: "No such page — digiquant",
      body: "Nothing is filed under this address.",
    });
    expect(embedLooksDown(down)).toBe(true);
    expect(embedLooksDown(docWith(shell, { body: "Nothing is filed under this address." }))).toBe(false);
    expect(probeEmbed({ contentDocument: null })).toEqual({ kind: "cross-origin" });
    expect(
      probeEmbed({
        get contentDocument(): Document | null {
          throw new Error("blocked");
        },
      }),
    ).toEqual({ kind: "cross-origin" });
    expect(
      probeEmbed({
        contentDocument: { location: { href: "about:blank" } } as Document,
      }).kind,
    ).toBe("closed");
  });
});

describe("DashboardBand", () => {
  const html = renderToStaticMarkup(<DashboardBand />);

  it("embeds the terminal and does not paint the placeholder book", () => {
    expect(html).toContain('src="/app"');
    expect(html).toContain('title="digiquant terminal"');
    expect(html).toContain("Opening the terminal.");
    expect(html).toContain("Take control");
    expect(html).toContain("Brief, Portfolio, and Pipeline");
    expect(html).not.toContain("01 / Book");
    expect(html).not.toContain("12×12");
    expect(html).not.toContain("Reading the official API.");
    expect(html).not.toContain("99.909");
    expect(html).not.toContain("204.04");
    expect(html).not.toContain("legacy_estimate");
    expect(html).not.toContain("sample run");
    expect(html).not.toContain(DESK_EMPTY_COPY);
  });
});

describe("terminal embed rewrite", () => {
  const source = readFileSync(new URL("../../next.config.mjs", import.meta.url), "utf8");

  it("keeps the static export and serves the terminal on this site", () => {
    expect(source).toContain('output: "export"');
    expect(source).toContain('source: "/official-api/:path*"');
    expect(source).toContain('destination: "http://127.0.0.1:8788/:path*"');
    expect(source).not.toContain("127.0.0.1:3930");
    expect(source).not.toContain("127.0.0.1:4014");
    expect(source).not.toContain('source: "/dashboard');
    expect(source).not.toContain('source: "/app');
  });
});
