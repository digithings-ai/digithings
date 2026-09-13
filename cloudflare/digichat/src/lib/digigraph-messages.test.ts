import { describe, expect, it } from "vitest";
import {
  coerceMessageContentToString,
  coreMessagesToDigigraphOpenAi,
} from "./digigraph-messages";
import type { ModelMessage } from "ai";

describe("coreMessagesToDigigraphOpenAi", () => {
  it("strips providerOptions and keeps text from part lists", () => {
    const core = [
      {
        role: "system",
        content: "sys",
        providerOptions: { x: 1 },
      },
      {
        role: "user",
        content: [
          { type: "text", text: "hi", providerOptions: { z: 2 } },
          { type: "reasoning", text: "think" },
        ],
      },
    ] as unknown as ModelMessage[];
    expect(coreMessagesToDigigraphOpenAi(core)).toEqual([
      { role: "system", content: "sys" },
      { role: "user", content: "hithink" },
    ]);
  });

  it("coerces content via String fallback", () => {
    expect(coerceMessageContentToString(42)).toBe("42");
  });
});
