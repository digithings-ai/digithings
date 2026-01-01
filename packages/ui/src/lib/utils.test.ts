import { readFileSync } from "node:fs";
import path from "node:path";
import { describe, expect, it } from "vitest";
import { cn } from "./utils";

const UI_FILES = ["button.tsx", "card.tsx", "dialog.tsx", "input.tsx"] as const;

describe("cn", () => {
  it("merges conflicting tailwind utilities (last wins)", () => {
    expect(cn("p-2", "p-4")).toBe("p-4");
  });

  it("keeps non-conflicting classes", () => {
    expect(cn("text-ink", "rounded-none")).toBe("text-ink rounded-none");
  });

  it("keeps the vendored ui kit on the package-relative cn import", () => {
    for (const file of UI_FILES) {
      const src = readFileSync(path.resolve(__dirname, "../ui", file), "utf8");
      expect(src).toContain('from "../lib/utils"');
      expect(src).not.toContain('from "@/lib/utils"');
    }
  });
});
