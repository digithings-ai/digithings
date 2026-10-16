import { describe, it, expect, vi } from "vitest";
import { applyEmbedSeed } from "./embed-seed-apply";

describe("applyEmbedSeed", () => {
  it("seeds transcript and auto-sends pending", () => {
    const seed = vi.fn();
    const send = vi.fn();
    applyEmbedSeed(
      {
        messages: [
          { role: "user", content: "a" },
          { role: "assistant", content: "b" },
        ],
        pending: "c",
      },
      { seed, send },
    );
    expect(seed).toHaveBeenCalledWith([
      { role: "user", content: "a" },
      { role: "assistant", content: "b" },
    ]);
    expect(send).toHaveBeenCalledWith("c");
  });

  it("seeds without send when pending empty", () => {
    const seed = vi.fn();
    const send = vi.fn();
    applyEmbedSeed({ messages: [], pending: "  " }, { seed, send });
    expect(seed).toHaveBeenCalledWith([]);
    expect(send).not.toHaveBeenCalled();
  });
});
