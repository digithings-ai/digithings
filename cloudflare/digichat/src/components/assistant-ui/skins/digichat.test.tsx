// @vitest-environment happy-dom
"use client";

import { describe, expect, it, vi } from "vitest";
import { render, screen } from "@testing-library/react";
import { SkinChromeProvider } from "@/components/stock/skin-chrome";
import { DEFAULT_SKIN_CHROME } from "@/components/stock/skin-chrome";
import { DigichatSkin } from "./digichat";

vi.mock("@assistant-ui/react", async () => {
  const actual = await vi.importActual<typeof import("@assistant-ui/react")>(
    "@assistant-ui/react",
  );
  const aui = {
    composer: {
      getState: () => ({ text: "" }),
      setText: vi.fn(),
      clearAttachments: vi.fn(),
      send: vi.fn(),
    },
    thread: () => ({ getState: () => ({ messages: [] as unknown[] }) }),
    threads: { switchToNewThread: vi.fn() },
  };
  return {
    ...actual,
    useAui: () => aui,
    unstable_useSlashCommandAdapter: () => ({ adapter: {}, action: {} }),
    unstable_useMentionAdapter: () => ({ adapter: {}, directive: {} }),
  };
});

vi.mock("@digithings/web/chat/thread", () => ({
  DigichatThread: ({ composerLayout }: { composerLayout?: string }) => (
    <div
      data-testid="digichat-thread"
      data-composer-layout={composerLayout ?? ""}
    />
  ),
}));

vi.mock("@digithings/digichat-ui", () => ({
  copyMarkdownWithFallback: vi.fn(),
  downloadMarkdown: vi.fn(),
  serializeAssistantMarkdown: () => "",
  serializeThreadMarkdown: () => "",
}));

vi.mock("@/lib/product-slash-commands", () => ({
  buildProductSlashCommands: () => [],
  extraSlashDefs: () => [],
  executeSlashDef: vi.fn(),
  executeSlashFromComposer: vi.fn(),
  prefixSlashAdapter: (a: unknown) => a,
  shouldInsertToolDraft: () => false,
  slashSubmitAction: () => ({ kind: "none" }),
}));

function renderSkin(
  mode: "app" | "embed",
  composerLayout?: "expanded" | "compact",
) {
  render(
    <SkinChromeProvider value={{ ...DEFAULT_SKIN_CHROME, mode }}>
      <DigichatSkin composerLayout={composerLayout} />
    </SkinChromeProvider>,
  );
  return screen.getByTestId("digichat-thread").getAttribute(
    "data-composer-layout",
  );
}

describe("DigichatSkin composerLayout", () => {
  it("derives expanded from app mode by default", () => {
    expect(renderSkin("app")).toBe("expanded");
  });

  it("an explicit compact prop wins over app mode", () => {
    expect(renderSkin("app", "compact")).toBe("compact");
  });

  it("derives compact from embed mode by default", () => {
    expect(renderSkin("embed")).toBe("compact");
  });
});
