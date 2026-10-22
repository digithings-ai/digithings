// @vitest-environment happy-dom
import { act, renderHook } from "@testing-library/react";
import { useState } from "react";
import { renderToString } from "react-dom/server";
import { afterEach, describe, expect, it, vi } from "vitest";
import {
  DEFAULT_EMBED_CHAT_PREFS,
  chromePrefsFromDeploy,
  useStoredDensityAfterMount,
  type EmbedChatPrefs,
} from "./embed-chat-prefs";

function stubStorage(values: Record<string, string>) {
  vi.stubGlobal("localStorage", {
    getItem: (k: string) => values[k] ?? null,
    setItem: () => {},
    removeItem: () => {},
  });
}

function usePrefs() {
  const [prefs, setPrefs] = useState<EmbedChatPrefs>(() => ({
    ...DEFAULT_EMBED_CHAT_PREFS,
    ...chromePrefsFromDeploy({ density: "compact" }, null),
  }));
  useStoredDensityAfterMount(setPrefs);
  return prefs;
}

function Probe() {
  return <div data-density={usePrefs().density} />;
}

describe("stored density and hydration", () => {
  afterEach(() => {
    vi.unstubAllGlobals();
  });

  it("renders the deployment density first, even with a stored choice", () => {
    stubStorage({ "dt-density": "airy" });
    expect(renderToString(<Probe />)).toContain('data-density="compact"');
  });

  it("applies the stored choice after mount", async () => {
    stubStorage({ "dt-density": "airy" });
    const { result } = renderHook(() => usePrefs());
    await act(async () => {});
    expect(result.current.density).toBe("airy");
  });

  it("keeps the deployment density when nothing is stored", async () => {
    stubStorage({});
    const { result } = renderHook(() => usePrefs());
    await act(async () => {});
    expect(result.current.density).toBe("compact");
  });
});
