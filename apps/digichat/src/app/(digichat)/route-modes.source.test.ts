import { readFileSync } from "node:fs";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";
import { describe, expect, it } from "vitest";

const here = dirname(fileURLToPath(import.meta.url));
const read = (rel: string) => readFileSync(join(here, rel), "utf8");

/**
 * Single route `/` with `?mode=` (single-route plan, Step 3 + menu root).
 * Bare `/` renders the menu (no chat); product/embed/catalog via `?mode=`.
 * Old routes stay alive until Step 6 (compat shims = Step 5).
 */
describe("single route / with ?mode=", () => {
  const page = read("page.tsx");

  it("is force-dynamic (embed per-tenant paint must never cache)", () => {
    expect(page).toMatch(/export const dynamic = "force-dynamic"/);
  });

  it("branches on ?mode=", () => {
    expect(page).toMatch(/params\.mode === "embed"/);
    expect(page).toMatch(/params\.mode === "catalog"/);
    expect(page).toMatch(/<EmbedRouteShell params=\{params\} \/>/);
    expect(page).toMatch(/<BaselineClient \/>/);
  });

  it("renders the menu at bare / and product only on ?mode=product", () => {
    expect(page).toMatch(/params\.mode === "product"/);
    expect(page).toMatch(/<RouteMenu \/>/);
    expect(page).toMatch(/from "\.\/route-menu"/);
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
    // /embed keeps serving directly: production splits / (Pages) from
    // /embed* (Container), so redirecting it would strand tenant iframes.
    expect(config).not.toMatch(/destination: "[^"]*mode=embed/);
  });
});
