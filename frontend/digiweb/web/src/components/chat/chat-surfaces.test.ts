import { describe, expect, it } from "vitest";

import { DIGICHAT_GLYPHS, digichatSurfaces } from "./chat-surfaces";

describe("digichat surfaces", () => {
  it("locks glyphs and a zero-radius terminal dress", () => {
    expect(DIGICHAT_GLYPHS).toEqual({ user: ">", assistant: "▸", system: "·" });
    expect(digichatSurfaces.thread).toContain("digichat-thread");
    expect(digichatSurfaces.thread).toContain("bg-term-bg");
    expect(digichatSurfaces.send).toContain("rounded-none");
    expect(digichatSurfaces.chip).toContain("rounded-none");
    expect(JSON.stringify(digichatSurfaces)).not.toContain("rounded-full");
    expect(JSON.stringify(digichatSurfaces)).not.toContain("rounded-2xl");
  });
});
