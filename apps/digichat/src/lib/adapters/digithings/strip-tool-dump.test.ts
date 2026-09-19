import { describe, expect, it } from "vitest";
import { stripToolDumpFromAnswerDelta } from "./strip-tool-dump";

describe("stripToolDumpFromAnswerDelta", () => {
  it("removes Open WebUI details tool blocks", () => {
    const raw =
      "<details><summary>Tool</summary>dump</details>\n\nClean answer with citation.";
    expect(stripToolDumpFromAnswerDelta(raw)).toBe("Clean answer with citation.");
  });

  it("removes thinking blocks", () => {
    const raw = "<thinking>reasoning</thinking>\n\nFinal prose.";
    expect(stripToolDumpFromAnswerDelta(raw)).toBe("Final prose.");
  });

  it("removes neutral formatter tool dumps", () => {
    const raw = "Tool: digisearch\n```json\n{\"query\":\"auth\"}\n```\n\nAnswer text.";
    expect(stripToolDumpFromAnswerDelta(raw)).toBe("Answer text.");
  });
});
