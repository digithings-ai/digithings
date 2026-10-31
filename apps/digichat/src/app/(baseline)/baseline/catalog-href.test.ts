import { afterEach, describe, expect, it, vi } from "vitest";

async function load(basePath: string | undefined) {
  vi.resetModules();
  if (basePath === undefined) vi.stubEnv("NEXT_PUBLIC_DIGICHAT_BASE_PATH", "");
  else vi.stubEnv("NEXT_PUBLIC_DIGICHAT_BASE_PATH", basePath);
  return (await import("./catalog-href")).catalogHref;
}

afterEach(() => {
  vi.unstubAllEnvs();
  vi.resetModules();
});

describe("catalog skin and light/dark links", () => {
  it("carry the /chat base path, so the theme toggle does not 404", async () => {
    const catalogHref = await load("/chat");
    expect(catalogHref("base", "dark")).toBe("/chat/baseline?theme=dark");
    expect(catalogHref("base", "light")).toBe("/chat/baseline");
    expect(catalogHref("chatgpt", "dark")).toBe("/chat/baseline?skin=chatgpt&theme=dark");
    expect(catalogHref("chatgpt", "light")).toBe("/chat/baseline?skin=chatgpt");
  });

  it("stay root-relative when the app is served at the root", async () => {
    const catalogHref = await load(undefined);
    expect(catalogHref("base", "dark")).toBe("/baseline?theme=dark");
    expect(catalogHref("claude", "light")).toBe("/baseline?skin=claude");
  });

  it("never double the slash when the base path has a trailing one", async () => {
    const catalogHref = await load("/chat/");
    expect(catalogHref("base", "dark")).toBe("/chat/baseline?theme=dark");
  });
});
