import { readFileSync } from "node:fs";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";
import { describe, expect, it } from "vitest";
import { resolveRouteMode } from "./route-mode";

const here = dirname(fileURLToPath(import.meta.url));
const read = (rel: string) => readFileSync(join(here, rel), "utf8");

/**
 * Single route `/` with `?mode=` (single-route plan, Step 3).
 * Bare `/` renders the product chat; the dev menu is opt-in via `?mode=menu`
 * (DIG-5395: the DIG-5121 cutover put this root on the public digithings.ai/chat).
 * Old routes stay alive until Step 6 (compat shims = Step 5).
 */
describe("single route / with ?mode=", () => {
  const page = read("page.tsx");

  it("is force-dynamic (embed per-tenant paint must never cache)", () => {
    expect(page).toMatch(/export const dynamic = "force-dynamic"/);
  });

  it("branches on ?mode=", () => {
    const resolver = read("route-mode.ts");
    expect(resolver).toMatch(/mode === "embed"/);
    expect(resolver).toMatch(/mode === "catalog"/);
    expect(resolver).toMatch(/mode === "menu"/);
    expect(page).toMatch(/<EmbedRouteShell params=\{params\} \/>/);
    expect(page).toMatch(/<BaselineClient \/>/);
  });

  it("defaults bare / to the product chat", () => {
    expect(resolveRouteMode(undefined)).toBe("product");
    expect(resolveRouteMode("product")).toBe("product");
    expect(resolveRouteMode("")).toBe("product");
  });

  it("never falls through to the menu on an unknown ?mode=", () => {
    expect(resolveRouteMode("nope")).toBe("product");
    expect(resolveRouteMode(["menu", "product"])).toBe("product");
  });

  it("keeps the dev menu behind ?mode=menu", () => {
    expect(resolveRouteMode("menu")).toBe("menu");
    expect(page).toMatch(/<RouteMenu \/>/);
    expect(page).toMatch(/from "\.\/route-menu"/);
    expect(page).toMatch(/resolveRouteMode\(params\.mode\)/);
  });

  it("still resolves the explicit embed and catalog surfaces", () => {
    expect(resolveRouteMode("embed")).toBe("embed");
    expect(resolveRouteMode("catalog")).toBe("catalog");
  });

  it("falls back to product for repeated, empty and oddly-cased values", () => {
    expect(resolveRouteMode(["embed", "x"])).toBe("product");
    expect(resolveRouteMode(["menu", "menu"])).toBe("product");
    expect(resolveRouteMode([])).toBe("product");
    expect(resolveRouteMode("PRODUCT")).toBe("product");
    expect(resolveRouteMode(" menu ")).toBe("product");
  });

  it("guards catalog in production and de-indexes non-product modes", () => {
    expect(page).toMatch(/NODE_ENV.*production/);
    expect(page).toMatch(/notFound\(\)/);
    expect(page).toMatch(/robots/);
    expect(page).toMatch(/index: false/);
  });

  it("marks catalog mode for scoped CSS", () => {
    expect(page).toMatch(/data-route-mode="catalog"/);
  });

  const shell = read("embed-route-shell.tsx");

  it("embed shell verifies tenant + seeds paint server-side", () => {
    expect(shell).toMatch(/resolveEmbedClientConfigForPaint/);
    expect(shell).toMatch(/resolveEmbedSeededTenant/);
    expect(shell).toMatch(/themePinScript\(paintTheme\)/);
    expect(shell).toMatch(/<EmbedClient/);
  });

  const embedPage = read("embed/page.tsx");

  it("old /embed route renders the shared shell (byte-identical)", () => {
    expect(embedPage).toMatch(
      /<EmbedRouteShell params=\{await searchParams\} \/>/,
    );
    expect(embedPage).not.toMatch(/resolveEmbedClientConfigForPaint/);
  });

  it("shims /baseline to /?mode=catalog and keeps /embed direct", () => {
    const config = readFileSync(
      join(here, "..", "..", "..", "next.config.ts"),
      "utf8",
    );
    expect(config).toMatch(/source: "\/baseline"/);
    expect(config).toMatch(/destination: "\/\?mode=catalog"/);
    // /embed keeps serving directly (never a redirect): production splits /
    // (Pages) from /embed* (Container), so redirecting it would strand
    // tenant iframes. The rewrite below is internal, not a redirect — it
    // carries no `permanent` flag.
    expect(config).not.toMatch(/source: "\/embed[^"]*", destination[^}]*permanent/);
  });

  it("aliases /embed into the single route internally (rewrite, no redirect)", () => {
    const config = readFileSync(
      join(here, "..", "..", "..", "next.config.ts"),
      "utf8",
    );
    expect(config).toMatch(
      /\{ source: "\/embed", destination: "\/\?mode=embed" \}/,
    );
    expect(config).toMatch(
      /\{ source: "\/embed\/", destination: "\/\?mode=embed" \}/,
    );
  });
});
