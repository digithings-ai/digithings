import { readFileSync } from "node:fs";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";
import { describe, expect, it } from "vitest";

const here = dirname(fileURLToPath(import.meta.url));
const read = (name: string) => readFileSync(join(here, name), "utf8");

describe("kit primitives keep the ink/hair motion contract", () => {
  it("never transitions every property", () => {
    for (const file of ["button.tsx", "badge.tsx", "tabs.tsx", "switch.tsx"]) {
      expect(read(file), file).not.toContain("transition-all");
    }
  });

  it("keeps the empty-state note line at AA", () => {
    const emptyState = read("empty-state.tsx");
    expect(emptyState).not.toContain("text-ink-mute/60");
    expect(emptyState).toContain("text-ink-mute");
  });
});

describe("ChatThinking keeps a 40px target", () => {
  it("declares the dense-UI minimum height on the chip", () => {
    const here = dirname(fileURLToPath(import.meta.url));
    const thinking = readFileSync(
      join(here, "..", "components", "chat", "ChatThinking.tsx"),
      "utf8",
    );
    expect(thinking).toContain("min-h-10");
  });
});
