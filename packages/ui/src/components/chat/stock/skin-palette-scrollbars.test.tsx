// @vitest-environment happy-dom
import { readFileSync } from "node:fs";
import { join } from "node:path";
import { act, cleanup, render } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

// The skin mounted without a slash palette: the bridge still carries the look.
vi.mock("./skin-slash-palette", async (orig) => ({
  ...(await orig<Record<string, unknown>>()),
  useSkinSlashPalette: () => ({ enabled: false }),
}));
import { SkinPaletteBridge } from "./skin-palette-bridge";
import {
  DEFAULT_EMBED_CHAT_PREFS,
  EmbedChatPrefsProvider,
  useEmbedChatPrefs,
  type EmbedChatPrefsApi,
} from "./embed-chat-prefs";

const css = readFileSync(join(__dirname, "../../../styles/chat-skin-palette.css"), "utf8");
const SURFACES =
  ':is([data-slot="aui_thread-viewport"], .overflow-y-scroll, .overflow-y-auto, .overflow-auto)';

let api: EmbedChatPrefsApi | null = null;
function Grab() {
  api = useEmbedChatPrefs();
  return <div data-slot="aui_thread-viewport" className="overflow-y-scroll" />;
}

function mount(scrollbars: "always" | "auto") {
  const value = {
    prefs: { ...DEFAULT_EMBED_CHAT_PREFS, scrollbars },
  } as unknown as EmbedChatPrefsApi;
  return render(
    <EmbedChatPrefsProvider value={value}>
      <SkinPaletteBridge slash={undefined as never}>
        <Grab />
      </SkinPaletteBridge>
    </EmbedChatPrefsProvider>,
  );
}

const mode = () =>
  document.querySelector("[data-skin-scrollbars]")?.getAttribute("data-skin-scrollbars");

describe("/scrollbar in skins that are not digichat", () => {
  afterEach(() => {
    cleanup();
    api = null;
  });

  it("the palette scope carries the committed mode", () => {
    mount("always");
    expect(mode()).toBe("always");
    cleanup();
    mount("auto");
    expect(mode()).toBe("auto");
  });

  it("follows a live preview and drops it again", () => {
    mount("always");
    act(() => api!.previewPrefs!({ scrollbars: "auto" }));
    expect(mode()).toBe("auto");
    act(() => api!.previewPrefs!(null));
    expect(mode()).toBe("always");
  });

  it("always shows a bar in a reserved gutter; auto hides it", () => {
    const rule = (sel: string) => {
      const at = css.indexOf(sel);
      expect(at, sel).toBeGreaterThan(-1);
      return css.slice(at, css.indexOf("}", at));
    };
    const always = rule(`[data-skin-scrollbars="always"]\n  ${SURFACES} {`);
    expect(always).toMatch(/scrollbar-gutter: stable/);
    expect(always).toMatch(/scrollbar-width: thin/);
    const auto = rule(`[data-skin-scrollbars="auto"]\n  ${SURFACES} {`);
    expect(auto).toMatch(/scrollbar-width: none/);
    expect(auto).toMatch(/scrollbar-gutter: auto/);
  });
});
