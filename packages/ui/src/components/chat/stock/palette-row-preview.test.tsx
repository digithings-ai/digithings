// @vitest-environment happy-dom
import { afterEach, describe, expect, it, vi } from "vitest";
import { act, cleanup, render } from "@testing-library/react";

const scope = vi.hoisted(() => ({
  value: { open: true, items: [{ id: "scrollbar" }, { id: "models" }], highlightedIndex: 0 } as {
    open: boolean;
    items: { id: string }[];
    highlightedIndex: number;
  } | null,
}));

vi.mock("@assistant-ui/react", () => ({
  unstable_useTriggerPopoverScopeContextOptional: () => scope.value,
}));

import { PaletteRowPreview } from "./palette-row-preview";
import {
  DEFAULT_EMBED_CHAT_PREFS,
  EmbedChatPrefsProvider,
  useEmbedChatPrefs,
  type EmbedChatPrefsApi,
} from "./embed-chat-prefs";

function Page() {
  return <output data-testid="page">{useEmbedChatPrefs().prefs.scrollbars}</output>;
}

function tree() {
  const value = {
    prefs: { ...DEFAULT_EMBED_CHAT_PREFS, scrollbars: "auto" },
  } as unknown as EmbedChatPrefsApi;
  return (
    <EmbedChatPrefsProvider value={value}>
      <Page />
      <PaletteRowPreview />
    </EmbedChatPrefsProvider>
  );
}

describe("PaletteRowPreview", () => {
  afterEach(() => {
    cleanup();
    scope.value = { open: true, items: [{ id: "scrollbar" }, { id: "models" }], highlightedIndex: 0 };
  });

  it("previews /scrollbar while it is highlighted and drops it when the cursor moves", () => {
    const view = render(tree());
    const page = () => view.getByTestId("page").textContent;
    expect(page()).toBe("always");
    scope.value = { ...scope.value!, highlightedIndex: 1 };
    view.rerender(tree());
    expect(page()).toBe("auto");
  });

  it("drops the preview when the popover closes", () => {
    const view = render(tree());
    expect(view.getByTestId("page").textContent).toBe("always");
    scope.value = { ...scope.value!, open: false };
    act(() => view.rerender(tree()));
    expect(view.getByTestId("page").textContent).toBe("auto");
  });

  it("does nothing outside a popover", () => {
    scope.value = null;
    const view = render(tree());
    expect(view.getByTestId("page").textContent).toBe("auto");
  });
});
