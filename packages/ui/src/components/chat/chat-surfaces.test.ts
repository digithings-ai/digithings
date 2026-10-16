import { describe, expect, it } from "vitest";

import { DIGICHAT_GLYPHS, digichatSurfaces } from "./chat-surfaces";

describe("digichat surfaces", () => {
  it("locks glyphs and a zero-radius terminal dress", () => {
    expect(DIGICHAT_GLYPHS).toEqual({ user: ">", assistant: "▸", system: "·" });
    expect(digichatSurfaces.thread).toContain("aui-root");
    expect(digichatSurfaces.composer).toContain("aui-composer-root");
    expect(digichatSurfaces.composerInput).toContain("aui-composer-input");
    expect(digichatSurfaces.send).toContain("aui-composer-send");
    expect(digichatSurfaces.send).not.toContain("bg-ink");
    expect(digichatSurfaces.example).toContain("rounded-none");
    expect(digichatSurfaces.example).toContain("grid-cols-[1.25rem_minmax(0,1fr)]");
    expect(digichatSurfaces.footer).toContain("mt-auto");
    expect(JSON.stringify(digichatSurfaces)).not.toContain("rounded-full");
    expect(JSON.stringify(digichatSurfaces)).not.toContain("rounded-2xl");
  });
});
