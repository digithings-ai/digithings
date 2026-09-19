import { describe, expect, it } from "vitest";
import { readFileSync } from "node:fs";
import { resolve } from "node:path";

/**
 * Product / Next surfaces must never pull Ink or the digichat CLI package
 * into the browser bundle.
 */
describe("web isolation from digichat CLI / react-ink", () => {
  const roots = [
    resolve(__dirname, "../../app"),
    resolve(__dirname, "../../components/stock"),
    resolve(__dirname, "../../lib/deploy-config"),
  ];

  it("stock + deploy-config sources do not import ink / react-ink / digichat-cli", () => {
    const forbidden =
      /@assistant-ui\/react-ink|from ["']ink["']|@digithings\/digichat-cli|digichat\/cli/;
    const hits: string[] = [];
    for (const root of roots) {
      // Lightweight: scan known entry files rather than a full walk.
      const samples = [
        resolve(root, "../components/stock/product-shell.tsx"),
        resolve(root, "../components/stock/deploy-ui-context.tsx"),
        resolve(root, "../lib/deploy-config/index.ts"),
        resolve(root, "../lib/deploy-config/client-projection.ts"),
        resolve(root, "../app/(digichat)/embed/embed-client.tsx"),
      ];
      for (const file of samples) {
        try {
          const src = readFileSync(file, "utf8");
          if (forbidden.test(src)) hits.push(file);
        } catch {
          /* optional path */
        }
      }
    }
    expect(hits).toEqual([]);
  });
});
