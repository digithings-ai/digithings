// @vitest-environment happy-dom
"use client";

import { describe, expect, it, vi } from "vitest";
import { render, screen } from "@testing-library/react";
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
  it("forwards an explicit composerLayout to the digichat skin", () => {
    render(<ThreadSkinView skin="digichat" composerLayout="compact" />);
    expect(
      screen.getByTestId("digichat-skin").getAttribute("data-composer-layout"),
    ).toBe("compact");
  });

  it("passes undefined through when no composerLayout is given", () => {
    render(<ThreadSkinView skin="digichat" />);
    expect(
      screen.getByTestId("digichat-skin").getAttribute("data-composer-layout"),
    ).toBe("");
  });
});
