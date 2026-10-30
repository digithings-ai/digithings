import { readFileSync } from "node:fs";
import { join } from "node:path";
import { describe, expect, it } from "vitest";

const bridge = readFileSync(join(__dirname, "skin-palette-bridge.tsx"), "utf8");
const css = readFileSync(join(__dirname, "../../../styles/chat-skin-palette.css"), "utf8");

describe("/density in skins that are not digichat", () => {
  it("the palette scope carries the density pref", () => {
    expect(bridge).toMatch(/data-skin-density=\{density\}/);
    expect(bridge).toMatch(/useEmbedChatPrefsOptional\(\)\?\.prefs\.density/);
  });

  it("compact and airy respace the messages; default adds no rule", () => {
    for (const d of ["compact", "airy"]) {
      expect(css).toContain(`[data-skin-density="${d}"] [data-message-id]`);
      expect(css).toContain(`[data-skin-density="${d}"] [data-slot="aui_message-group"]`);
    }
    expect(css).not.toContain('[data-skin-density="default"]');
  });
});
