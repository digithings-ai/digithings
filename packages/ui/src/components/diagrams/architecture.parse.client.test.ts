import { describe, expect, it } from "vitest";
import mermaid from "mermaid";

import { toMermaid, type ArchSpec } from "./ArchitectureDiagram";

/**
 * The grammar guard: everything `toMermaid` can emit has to survive mermaid's
 * own parser. A unit test on the emitted string only proves it looks like the
 * syntax we intended; this one proves mermaid agrees.
 *
 * mermaid sanitizes inside `parse`, and the DOMPurify build mermaid bundles
 * cannot register itself under vitest's DOM — so a run that reaches that error
 * has already passed the lexer and the parser, which is the thing under test.
 * Anything else is a real grammar failure and fails the test.
 */
async function mermaidAccepts(source: string): Promise<void> {
  await mermaid.parse(source);
}

const FEATURES: ArchSpec = {
  title: "Every feature the emitter can produce",
  description: "A spec that exercises titles, groups, labels, arrows, junctions and alignments.",
  groups: [
    { id: "nested", label: "inner boundary", parent: "outer" },
    { id: "outer", label: "outer boundary · with punctuation", icon: "cloud" },
  ],
  services: [
    { id: "entry", label: "an entry point", icon: "internet" },
    { id: "store", label: "a store", icon: "database", group: "nested" },
    { id: "worker", label: "a worker", group: "nested" },
  ],
  junctions: [{ id: "split", group: "nested" }],
  edges: [
    { from: "entry", to: "store", fromSide: "B", toSide: "T", label: "reads" },
    { from: "store", to: "worker", fromSide: "R", toSide: "L" },
    { from: "worker", to: "entry", fromSide: "T", toSide: "L", arrow: "none", label: "reports" },
    { from: "worker", to: "split", fromSide: "B", toSide: "T", arrow: "from" },
  ],
  aligns: [{ axis: "row", ids: ["store", "worker"] }],
};

describe("the emitted architecture source", () => {
  it("is accepted by mermaid's parser", async () => {
    try {
      await mermaidAccepts(toMermaid(FEATURES));
    } catch (error) {
      const message = String(error);
      // See the note above: reaching the sanitizer means the grammar passed.
      expect(message).toContain("DOMPurify");
    }
  });
});
