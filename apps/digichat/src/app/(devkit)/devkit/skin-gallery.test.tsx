// @vitest-environment happy-dom
import { describe, expect, it, vi } from "vitest";
import { render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { useState } from "react";
import { THREAD_SKINS } from "@digithings/ui/chat/skins";
import { PALETTES } from "@digithings/ui/theme";
import type { DigichatDeployment } from "@/lib/deploy-config/schema";
import { contrast } from "./devkit-contrast";
import { DevkitEditors } from "./devkit-editors";
import { createDraft, type EntryDraft, withText } from "./draft";
import {
  pairContrast,
  SkinGallery,
  skinMode,
  skinTokenPair,
} from "./skin-gallery";

describe("SkinGallery", () => {
  it("renders one button per registered skin", () => {
    render(<SkinGallery value="digichat" onCommit={() => true} />);
    const grid = screen.getByRole("group", { name: /skin — pick one/i });
    const cards = within(grid).getAllByRole("button");
    // Count first: THREAD_SKINS must be non-empty for the sweep below to prove
    // anything (a zero-length registry would pass a bare forEach).
    expect(THREAD_SKINS.length).toBeGreaterThan(0);
    expect(cards).toHaveLength(THREAD_SKINS.length);
    for (const skin of THREAD_SKINS) {
      expect(
        screen.getByRole("button", { name: new RegExp(`^skin ${skin} `) }),
      ).toBeTruthy();
    }
  });

  it("marks only the draft skin pressed and derives its mode from the registry", () => {
    render(<SkinGallery value="claude" onCommit={() => true} />);
    const selected = screen.getByRole("button", { name: /^skin claude / });
    expect(selected.getAttribute("aria-pressed")).toBe("true");
    expect(selected.textContent).toContain("clone");
    expect(
      screen.getByRole("button", { name: /^skin digichat / }).getAttribute("aria-pressed"),
    ).toBe("false");
    expect(skinMode("webpage-assistant")).toBe("layout");
    expect(skinMode("digichat")).toBe("first-party");
    expect(skinMode("base")).toBe("catalog");
  });

  it("commits the picked skin (selection is a draft edit, not a save)", async () => {
    const user = userEvent.setup();
    const onCommit = vi.fn().mockReturnValue(true);
    render(<SkinGallery value="digichat" onCommit={onCommit} />);
    await user.click(screen.getByRole("button", { name: /^skin claude / }));
    expect(onCommit).toHaveBeenCalledTimes(1);
    expect(onCommit).toHaveBeenCalledWith("claude");
  });

  it("shows a contrast readout for both the light and dark pair", () => {
    const { rerender } = render(<SkinGallery value="claude" onCommit={() => true} />);
    const light = screen.getByTestId("skin-pair-light");
    const dark = screen.getByTestId("skin-pair-dark");
    const lightRatio = pairContrast(skinTokenPair(undefined, "light"));
    const darkRatio = pairContrast(skinTokenPair(undefined, "dark"));
    expect(lightRatio).toBeGreaterThan(1);
    expect(darkRatio).toBeGreaterThan(1);
    expect(light.textContent).toContain(`${lightRatio.toFixed(2)}:1`);
    expect(dark.textContent).toContain(`${darkRatio.toFixed(2)}:1`);
    expect(light.textContent).toContain("claude");
    expect(dark.textContent).toContain("claude");

    // A pinned deployment palette is what the pair is computed from.
    rerender(<SkinGallery value="claude" palette="nord" onCommit={() => true} />);
    const nord = PALETTES.nord.light;
    expect(pairContrast(skinTokenPair("nord", "light"))).toBe(
      contrast(nord.accent, nord.onAccent),
    );
    expect(screen.getByTestId("skin-pair-light").textContent).toContain(
      `${contrast(nord.accent, nord.onAccent).toFixed(2)}:1`,
    );
  });

  it("selects with the keyboard (arrows, Home, End)", async () => {
    const user = userEvent.setup();
    const onCommit = vi.fn().mockReturnValue(true);
    render(<SkinGallery value="base" onCommit={onCommit} />);
    const first = screen.getByRole("button", { name: /^skin base / });
    first.focus();
    await user.keyboard("{ArrowRight}");
    expect(onCommit).toHaveBeenLastCalledWith(THREAD_SKINS[1]);
    await user.keyboard("{End}");
    expect(onCommit).toHaveBeenLastCalledWith(THREAD_SKINS[THREAD_SKINS.length - 1]);
    await user.keyboard("{Home}");
    expect(onCommit).toHaveBeenLastCalledWith(THREAD_SKINS[0]);
  });
});

const DRAFT_TEXT = [
  "version: 1",
  "deployment:",
  "  slug: probe",
  "  chrome:",
  "    skin: digichat",
  "    theme: dark",
  "  backend:",
  "    type: digigraph",
  "",
].join("\n");

const DEPLOYMENT = {
  slug: "probe",
  chrome: { skin: "digichat", theme: "dark" },
  backend: { type: "digigraph" },
  models: {},
  features: {},
  gate: {},
} as unknown as DigichatDeployment;

function Harness({ initial }: { initial: EntryDraft }) {
  const [draft, setDraft] = useState<EntryDraft>(initial);
  return (
    <>
      <DevkitEditors
        draft={draft}
        commit={(edit) => {
          if (!edit.applied) return false;
          setDraft((d) => withText(d, edit.text));
          return true;
        }}
      />
      <output data-testid="draft-text">{draft.text}</output>
      <output data-testid="saved-text">{draft.savedText}</output>
    </>
  );
}

describe("Appearance skin selection", () => {
  it("rewrites the draft skin and never calls the save endpoint", async () => {
    const user = userEvent.setup();
    const fetchSpy = vi.fn();
    vi.stubGlobal("fetch", fetchSpy);
    try {
      const draft = createDraft({
        entryId: "file:probe.yaml",
        scope: ["deployment"],
        savedText: DRAFT_TEXT,
        parsed: DEPLOYMENT,
      });
      render(<Harness initial={draft} />);

      await user.click(screen.getByRole("button", { name: "Appearance" }));
      await user.click(screen.getByRole("button", { name: /^skin gemini / }));

      expect(screen.getByTestId("draft-text").textContent).toContain("skin: gemini");
      // The saved text is untouched, so the change is a draft edit only.
      expect(screen.getByTestId("saved-text").textContent).toContain("skin: digichat");
      for (const call of fetchSpy.mock.calls) {
        expect(String(call[0])).not.toContain("/api/devkit/save");
      }
    } finally {
      vi.unstubAllGlobals();
    }
  });
});
