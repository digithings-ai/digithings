// @vitest-environment happy-dom
import { afterEach, describe, expect, it, vi } from "vitest";
import { loadSwaggerAsset } from "./SwaggerExplorer";

const BUNDLE = "/swagger-ui/swagger-ui-bundle.js";

describe("loadSwaggerAsset", () => {
  afterEach(() => {
    document.querySelectorAll("[data-swagger-src]").forEach((node) => node.remove());
    vi.restoreAllMocks();
  });

  it("does not treat a failed script tag as already loaded", async () => {
    const failed = document.createElement("script");
    failed.setAttribute("data-swagger-src", BUNDLE);
    failed.setAttribute("data-swagger-status", "error");
    document.body.appendChild(failed);

    const created: Element[] = [];
    const orig = document.createElement.bind(document);
    vi.spyOn(document, "createElement").mockImplementation((tagName: string) => {
      const el = orig(tagName);
      if (tagName === "script") created.push(el);
      return el;
    });

    let resolved = false;
    // happy-dom rejects a new script immediately (JS file loading is off).
    // The old loader resolved as soon as any tag with this src existed.
    const pending = loadSwaggerAsset("script", BUNDLE).then(
      () => {
        resolved = true;
      },
      () => undefined,
    );
    await pending;

    expect(resolved).toBe(false);
    expect(document.body.contains(failed)).toBe(false);
    expect(created).toHaveLength(1);
    expect(created[0]?.getAttribute("data-swagger-src")).toBe(BUNDLE);
    expect(created[0]?.getAttribute("data-swagger-status")).not.toBe("ready");
  });

  it("reuses a tag that already finished loading", async () => {
    const ready = document.createElement("script");
    ready.setAttribute("data-swagger-src", BUNDLE);
    ready.setAttribute("data-swagger-status", "ready");
    document.body.appendChild(ready);

    await loadSwaggerAsset("script", BUNDLE);
    expect(document.querySelectorAll(`script[data-swagger-src="${BUNDLE}"]`)).toHaveLength(1);
  });
});
