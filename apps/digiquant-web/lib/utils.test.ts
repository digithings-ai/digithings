import { readFileSync } from "node:fs";
import { describe, expect, it } from "vitest";
import { cn } from "@/lib/utils";

const REEXPORTS = [
  new URL("./utils.ts", import.meta.url),
  new URL("../../digichat/src/lib/utils.ts", import.meta.url),
  new URL("../../reference/lib/utils.ts", import.meta.url),
  new URL("../../../packages/ui/src/components/chat/gallery-thread/cn.ts", import.meta.url),
] as const;

describe("shared cn", () => {
  it("merges conflicting tailwind utilities through @digithings/ui/cn", () => {
    expect(cn("p-2", "p-4")).toBe("p-4");
  });

  it("keeps one implementation and re-exports it", () => {
    const canonical = readFileSync(
      new URL("../../../packages/ui/src/lib/utils.ts", import.meta.url),
      "utf8",
    );
    expect(canonical).toContain("export function cn");
    for (const url of REEXPORTS) {
      const src = readFileSync(url, "utf8");
      expect(src, url.pathname).not.toContain("twMerge");
      expect(src, url.pathname).toMatch(/export \{ cn \} from /);
    }
  });
});
