// @vitest-environment happy-dom
/**
 * The product `/` palette is a chat-shell feature, not a digichat-skin one:
 * every registered skin renders it with the same command list, keyboard
 * navigation and selection. Mocks only: a local runtime, no model calls.
 */
import {
  AssistantRuntimeProvider,
  type ChatModelAdapter,
  useAui,
  useLocalRuntime,
} from "@assistant-ui/react";
import { act, useEffect } from "react";
import { createRoot } from "react-dom/client";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { THREAD_SKINS, ThreadSkinView, type ThreadSkin } from "@digithings/ui/chat/skins";
import { StockChatPrefsHost, useStockChatPrefs } from "@digithings/ui/chat/stock";
import { DIGICHAT_SKIN_OPTIONS } from "@/lib/digichat-skin-options";
import {
  resolveRouteClientConfig,
  toStockChatPrefsConfig,
} from "@/lib/route-client-config";

(globalThis as { IS_REACT_ACT_ENVIRONMENT?: boolean }).IS_REACT_ACT_ENVIRONMENT = true;

const run = vi.fn(async () => ({ content: [{ type: "text" as const, text: "ok" }] }));
const adapter: ChatModelAdapter = { run };

const noop = () => {};
const PREFS_DEPS = {
  defaultLanguageCode: "en",
  detectLanguage: () => "en",
  resolveLanguage: () => null,
  mcpOps: {
    replace: () => [],
    connected: () => [],
    headerValue: () => null,
  },
  renderMenuPanes: () => null,
};

let composerApi: ReturnType<typeof useAui> | null = null;
function ComposerProbe() {
  const aui = useAui();
  useEffect(() => {
    composerApi = aui;
  }, [aui]);
  return null;
}

function Harness({ skin }: { skin: ThreadSkin }) {
  const runtime = useLocalRuntime(adapter);
  const { prefsApi, panes } = useStockChatPrefs({
    config: toStockChatPrefsConfig(resolveRouteClientConfig({ mode: "catalog" })),
    deps: PREFS_DEPS as never,
    sessionKey: "palette-test",
    hasSessions: false,
    newThread: noop,
    redo: noop,
  });
  return (
    <AssistantRuntimeProvider runtime={runtime}>
      <StockChatPrefsHost value={prefsApi} panes={panes}>
        <ComposerProbe />
        <ThreadSkinView skin={skin} digichat={DIGICHAT_SKIN_OPTIONS} />
      </StockChatPrefsHost>
    </AssistantRuntimeProvider>
  );
}

const ACT_WAIT = 60;

async function settle(ms = ACT_WAIT) {
  await act(async () => {
    await new Promise((resolve) => setTimeout(resolve, ms));
  });
}

/** Layout skins that open the thread from a launcher get it opened first. */
async function openLauncher(host: HTMLElement) {
  const trigger = host.querySelector<HTMLButtonElement>(".aui-modal-anchor button");
  if (!trigger || document.querySelector("form textarea, form [contenteditable='true']")) return;
  await act(async () => {
    trigger.click();
  });
}

async function mount(skin: ThreadSkin) {
  const host = document.createElement("div");
  document.body.append(host);
  const root = createRoot(host);
  await act(async () => {
    root.render(<Harness skin={skin} />);
  });
  await vi.waitFor(
    async () => {
      await openLauncher(host);
      if (!document.querySelector("form textarea, form [contenteditable='true']")) {
        throw new Error("composer not mounted");
      }
      if (skin !== "digichat" && !document.querySelector("form[data-skin-palette-composer]")) {
        throw new Error("palette anchor not marked");
      }
    },
    { timeout: 5000, interval: 20 },
  );
  return { unmount: () => act(() => root.unmount()) };
}

function composerForm(skin: ThreadSkin): HTMLFormElement {
  const form = document.querySelector<HTMLFormElement>(
    skin === "digichat" ? "form" : "form[data-skin-palette-composer]",
  );
  if (!form) throw new Error("composer form not found");
  return form;
}

function composerInput(skin: ThreadSkin): HTMLElement {
  const input = composerForm(skin).querySelector<HTMLElement>(
    "textarea, [contenteditable='true']",
  );
  if (!input) throw new Error("composer input not found");
  return input;
}

/** Types into the composer the way each input kind receives text. */
async function type(skin: ThreadSkin, text: string) {
  const input = composerInput(skin);
  if (input instanceof HTMLTextAreaElement) {
    await act(async () => {
      input.focus();
      Object.getOwnPropertyDescriptor(HTMLTextAreaElement.prototype, "value")?.set?.call(
        input,
        text,
      );
      input.setSelectionRange(text.length, text.length);
      input.dispatchEvent(new Event("input", { bubbles: true }));
    });
  } else {
    // Rich-text (Lexical) composers mirror the composer state; happy-dom
    // has no editing engine, so the text arrives through the runtime.
    await act(async () => {
      input.focus();
      composerApi?.composer.setText(text);
    });
  }
  await settle();
  return input;
}

async function press(skin: ThreadSkin, key: string) {
  const input = composerInput(skin);
  await act(async () => {
    input.dispatchEvent(new KeyboardEvent("keydown", { key, bubbles: true, cancelable: true }));
  });
  await settle();
}

function palette() {
  return document.querySelector('[data-slot="composer-trigger-popover"]');
}

function rows(): string[] {
  return Array.from(
    document.querySelectorAll('[data-slot="composer-trigger-popover"] [role="option"]'),
  ).map((row) => row.textContent ?? "");
}

function highlighted(): string | null {
  return (
    document.querySelector('[data-slot="composer-trigger-popover"] [data-highlighted]')
      ?.textContent ?? null
  );
}

function composerText(): string {
  return composerApi?.composer.getState().text ?? "";
}

let digichatRows: string[] = [];

/** The digichat skin's list: the behaviour every other skin must match. */
async function referenceRows(): Promise<string[]> {
  if (digichatRows.length) return digichatRows;
  const { unmount } = await mount("digichat");
  await type("digichat", "/");
  digichatRows = rows();
  await type("digichat", "");
  await unmount();
  document.body.replaceChildren();
  return digichatRows;
}

beforeEach(() => {
  run.mockClear();
});

afterEach(() => {
  document.body.replaceChildren();
  composerApi = null;
});

describe("slash palette in every registered skin", () => {
  it("lists the product commands in the digichat skin (reference list)", async () => {
    const reference = await referenceRows();
    expect(reference.length).toBeGreaterThan(5);
    expect(reference.some((row) => row.startsWith("/language"))).toBe(true);
  });

  it.each(THREAD_SKINS)("%s: typing / opens the same command list", async (skin) => {
    const reference = await referenceRows();
    const { unmount } = await mount(skin);
    expect(palette()).toBeNull();
    await type(skin, "/");
    expect(palette()).not.toBeNull();
    expect(rows()).toEqual(reference);
    // The palette sits in the thread composer, not somewhere else on the page.
    expect(composerForm(skin).contains(palette())).toBe(true);
    await unmount();
  });

  it.each(THREAD_SKINS)("%s: arrow keys move the highlighted command", async (skin) => {
    const { unmount } = await mount(skin);
    await type(skin, "/");
    const [first, second] = rows();
    expect(highlighted()).toBe(first);
    await press(skin, "ArrowDown");
    expect(highlighted()).toBe(second);
    await press(skin, "ArrowUp");
    expect(highlighted()).toBe(first);
    await press(skin, "Escape");
    expect(palette()).toBeNull();
    await unmount();
  });

  it.each(THREAD_SKINS)("%s: Enter selects the highlighted command", async (skin) => {
    const { unmount } = await mount(skin);
    await type(skin, "/langu");
    expect(highlighted()?.startsWith("/language")).toBe(true);
    await press(skin, "Enter");
    // /language opens its pane: the palette writes the pane draft and the
    // command palette closes, exactly as in the digichat skin.
    expect(composerText()).toBe("/language ");
    expect(rows()).toEqual([]);
    expect(run).not.toHaveBeenCalled();
    await unmount();
  });

  it.each(THREAD_SKINS)("%s: a slash submit never reaches the model; plain text does", async (skin) => {
    const { unmount } = await mount(skin);
    await type(skin, "/language ");
    await act(async () => {
      composerForm(skin).requestSubmit();
    });
    await settle();
    expect(run).not.toHaveBeenCalled();
    expect(composerText()).toBe("/language ");

    await type(skin, "hello");
    await act(async () => {
      composerForm(skin).requestSubmit();
    });
    await settle(150);
    expect(run).toHaveBeenCalledTimes(1);
    await unmount();
  });
});
