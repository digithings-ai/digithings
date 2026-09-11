// @vitest-environment happy-dom
/**
 * Isolated BASE_PATH regression for the OpenRouter models prefetch (#2383).
 *
 * Kept in its own file so vi.mock("@/lib/base-path") does not rewrite p() for
 * the rest of byok-cli-flow.test.tsx (which asserts un-prefixed /api/... URLs
 * under the default empty BASE_PATH).
 */
import { render, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

vi.mock("@/lib/base-path", () => ({
  BASE_PATH: "/chat",
  p: (path: string) => `/chat${path}`,
}));

import { ByokCliFlow } from "./byok-cli-flow";

describe("ByokCliFlow basePath (#2383)", () => {
  afterEach(() => {
    vi.restoreAllMocks();
    vi.unstubAllGlobals();
  });

  it("prefixes the OpenRouter models prefetch with BASE_PATH", async () => {
    const fetchSpy = vi.fn().mockImplementation(() =>
      Promise.resolve(
        new Response(
          JSON.stringify({ ok: true, free: [], opensource: [], flagship: [], all: [] }),
          { status: 200, headers: { "content-type": "application/json" } },
        ),
      ),
    );
    vi.stubGlobal("fetch", fetchSpy);

    render(<ByokCliFlow onClose={() => {}} onActivate={() => {}} />);

    await waitFor(() => expect(fetchSpy).toHaveBeenCalled());
    const [url] = fetchSpy.mock.calls[0] as [string];
    expect(url).toBe("/chat/api/byok/models?provider=openrouter");
  });
});
