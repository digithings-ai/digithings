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
import { publicCatalogPages } from "@/components/desk/public-surface";
import { screenKind } from "./terminal-screen";
import {
  HOSTED_COPY,
  SELF_HOSTED_COPY,
  TOUR_CAPTION,
  deskShellLoaded,
  nextDeskAnchor,
  nextTerminalPath,
  nextWebPath,
  prevTerminalPath,
  surfaceFromSlider,
} from "./surface-tour";

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
  { label: "/strategies", href: "/app/strategies" },
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

describe("surface tour", () => {
  it("keeps the two stories free of a price", () => {
    const copy = `${SELF_HOSTED_COPY} ${HOSTED_COPY} ${TOUR_CAPTION}`;
    expect(copy).toContain("The terminal runs on your computer.");
    expect(copy).toContain("You run pipelines, models, and strategies yourself.");
    expect(copy).toContain("Paying makes the hosted services available.");
    expect(copy).toContain("The web app hosts pipelines and runs the strategies.");
    expect(copy).not.toMatch(/\$\d|\bFree\b|Coming soon|per month|99\.909|204\.04/);
  });

  it("slides the terminal in from the left and the web app in from the right", () => {
    expect(surfaceFromSlider(0)).toBe("terminal");
    expect(surfaceFromSlider(49)).toBe("terminal");
    expect(surfaceFromSlider(50)).toBe("web");
    expect(surfaceFromSlider(100)).toBe("web");
  });

  it("treats a page rail with no links as a loaded desk", () => {
    const doc = docWith([], { body: "Nothing is filed under this address. access unavailable" });
    expect(deskShellLoaded(doc)).toBe(true);
    expect(embedLooksDown(doc)).toBe(true);
    expect(nextDeskAnchor(doc)).toBeNull();
    expect(nextWebPath("/app/")).toBe("/portfolio");
  });

  it("tours every terminal page, including strategies, and wraps", () => {
    expect(nextTerminalPath("/brief")).toBe("/portfolio");
    expect(nextTerminalPath("/strategies")).toBe("/strategies/detail");
    expect(nextTerminalPath("/strategies/deploy")).toBe("/brief");
    expect(prevTerminalPath("/brief")).toBe("/strategies/deploy");
    expect(nextTerminalPath("/fx")).toBe("/brief");
    expect(nextTerminalPath("/fx/settings")).toBe("/brief");
    expect(nextWebPath("/app")).toBe("/portfolio");
    expect(nextWebPath("/app/brief/")).toBe("/portfolio");
    expect(nextWebPath("/app/strategies/")).toBe("/strategies/detail");
    const pages = publicCatalogPages();
    const seen = new Set<string>();
    let path = "/brief";
    for (let i = 0; i < pages.length; i += 1) {
      seen.add(path);
      path = nextTerminalPath(path);
    }
    expect(seen.size).toBe(pages.length);
    expect(path).toBe("/brief");
    expect(seen.has("/fx")).toBe(false);
  });

  it("draws a real screen for every public page and not for a web-only or invite path", () => {
    for (const page of publicCatalogPages()) expect(screenKind(page.path)).not.toBe("undrawn");
    expect(screenKind("/fx")).toBe("undrawn");
    expect(screenKind("/fx/ideas")).toBe("undrawn");
    expect(screenKind("/tools/charts")).toBe("undrawn");
    expect(screenKind("/tools/chat")).toBe("undrawn");
  });

  it("clicks the next /app page and skips the landing pipeline link", () => {
    const doc = docWith([
      ...shell,
      { label: "Strategies", href: "/app/strategies" },
      { label: "Pipeline", href: "/#pipeline" },
    ], { pathname: "/app/brief" });
    expect(nextDeskAnchor(doc)?.getAttribute("href")).toBe("/app/portfolio");
    const last = docWith(shell, { pathname: "/app/strategies" });
    expect(nextDeskAnchor(last)?.getAttribute("href")).toBe("/app/brief");
  });
});

describe("DashboardBand", () => {
  const html = renderToStaticMarkup(<DashboardBand />);

  it("loads the web desk and the terminal screens, with no invented book", () => {
    expect(html).toContain('src="/app"');
    expect(html).toContain('title="Hosted digiquant"');
    expect(html).toContain('aria-label="Terminal pages"');
    expect(html).toContain('data-slot="slider"');
    expect(html).toContain(SELF_HOSTED_COPY);
    expect(html).toContain(HOSTED_COPY);
    expect(html).toContain("Opening the web app.");
    expect(html).toContain("Brief · scoreboard");
    expect(html).toContain("Strategies");
    expect(html).toContain("screens the terminal draws");
    expect(html).not.toContain("01 / Book");
    expect(html).not.toContain("12×12");
    expect(html).not.toContain("Reading the official API.");
    expect(html).not.toContain("99.909");
    expect(html).not.toContain("204.04");
    expect(html).not.toContain("legacy_estimate");
    expect(html).not.toContain("sample run");
    expect(html).not.toContain("Take control");
    expect(html).not.toMatch(/fx hub|12x terminal/i);
    expect(html).not.toMatch(/\$\d|\bFree\b|Coming soon/);
  });
});

describe("terminal embed rewrite", () => {
  const source = readFileSync(new URL("../../next.config.mjs", import.meta.url), "utf8");

  it("keeps the static export and serves the terminal on this site", () => {
    expect(source).toContain('output: "export"');
    expect(source).toContain("legacyDashboardRedirects()");
    expect(source).toContain('source: "/official-api/:path*"');
    expect(source).toContain('const DEFAULT_OFFICIAL_API_ORIGIN = "http://127.0.0.1:8788"');
    expect(source).toContain("process.env.DIGIQUANT_WEB_OFFICIAL_API_ORIGIN");
    expect(source).toContain("officialApiRewriteOrigin()");
    expect(source).not.toContain("8789");
    expect(source).not.toContain("127.0.0.1:3930");
    expect(source).not.toContain("127.0.0.1:4014");
    expect(source).not.toContain('source: "/dashboard');
    expect(source).not.toContain('source: "/app');
  });

  it("rewrites /official-api to 8788 unless the origin env is set", async () => {
    const key = "DIGIQUANT_WEB_OFFICIAL_API_ORIGIN";
    const previous = process.env[key];
    const { default: config } = await import("../../next.config.mjs");
    try {
      delete process.env[key];
      await expect(config.rewrites()).resolves.toEqual([
        { source: "/official-api/:path*", destination: "http://127.0.0.1:8788/:path*" },
      ]);
      process.env[key] = "  ";
      await expect(config.rewrites()).resolves.toEqual([
        { source: "/official-api/:path*", destination: "http://127.0.0.1:8788/:path*" },
      ]);
      process.env[key] = "http://127.0.0.1:8791/";
      await expect(config.rewrites()).resolves.toEqual([
        { source: "/official-api/:path*", destination: "http://127.0.0.1:8791/:path*" },
      ]);
    } finally {
      if (previous === undefined) delete process.env[key];
      else process.env[key] = previous;
    }
  });
});
