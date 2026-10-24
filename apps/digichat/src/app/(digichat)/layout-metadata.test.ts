import { describe, expect, it } from "vitest";
import { readFile } from "node:fs/promises";

/**
 * Audit T7 (web-quality P1): the authenticated app route group was indexable.
 * The root layout is the single place that covers `/`, `/embed`, and every
 * product mode, so the directive lives there.
 */
describe("(digichat) layout metadata", () => {
  it("keeps the authenticated app out of search", async () => {
    const layout = await readFile("src/app/(digichat)/layout.tsx", "utf8");
    expect(layout).toMatch(
      /robots:\s*\{\s*index:\s*false,\s*follow:\s*false\s*\}/,
    );
  });
});
