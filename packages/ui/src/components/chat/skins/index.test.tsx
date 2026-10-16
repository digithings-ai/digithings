// @vitest-environment happy-dom
"use client";

import { afterEach, describe, expect, it, vi } from "vitest";
import { cleanup, render, screen } from "@testing-library/react";

afterEach(() => {
  cleanup();
});
import { ThreadSkinView } from "./index";

vi.mock("./chatgpt", () => ({ ChatGPT: () => null }));
vi.mock("./claude", () => ({ Claude: () => null }));
vi.mock("./grok", () => ({ Grok: () => null }));
vi.mock("./gemini", () => ({ Gemini: () => null }));
vi.mock("./perplexity", () => ({ Perplexity: () => null }));
vi.mock("./react-ink", () => ({ ReactInkWeb: () => null }));
vi.mock("./expo-react-native", () => ({ ExpoReactNative: () => null }));
vi.mock("./base-assistant-ui", () => ({ ConfigurableBase: () => null }));
vi.mock("./webpage-assistant", () => ({ WebpageAssistant: () => null }));
vi.mock("./product-page-assistant", () => ({ ProductPageAssistant: () => null }));
vi.mock("./digichat", () => ({
  DigichatSkin: ({ composerLayout }: { composerLayout?: string }) => (
    <div
      data-testid="digichat-skin"
      data-composer-layout={composerLayout ?? ""}
    />
  ),
}));

describe("ThreadSkinView composerLayout", () => {
  it("forwards an explicit composerLayout to the digichat skin", async () => {
    render(<ThreadSkinView skin="digichat" composerLayout="compact" />);
    expect(
      (await screen.findByTestId("digichat-skin")).getAttribute(
        "data-composer-layout",
      ),
    ).toBe("compact");
  });

  it("passes undefined through when no composerLayout is given", async () => {
    render(<ThreadSkinView skin="digichat" />);
    expect(
      (await screen.findByTestId("digichat-skin")).getAttribute(
        "data-composer-layout",
      ),
    ).toBe("");
  });
});
