/**
 * Secondary-pages card contracts (Coder C light upgrade).
 *
 * Guards the /services + /about + /team refresh: list content renders through
 * the shared SecondaryCard atom on the kit Card + Reveal (modest cards, subtle
 * motion only), page copy is unchanged in meaning, and no out-of-scope surface
 * (landing QuantSection, OpenSourceLive, DigiVoice) is touched.
 */
import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";
import { describe, expect, it } from "vitest";

function src(rel: string): string {
  return readFileSync(fileURLToPath(new URL(rel, import.meta.url)), "utf8");
}

describe("SecondaryCard atom", () => {
  const atom = src("./SecondaryCard.tsx");

  it("builds on the kit Card and the shared Reveal, with no new CSS or flashy motion", () => {
    expect(atom).toContain('"use client"');
    expect(atom).toContain('from "@digithings/ui/ui"');
    expect(atom).toContain("Card");
    expect(atom).toContain('from "@digithings/ui"');
    expect(atom).toContain("Reveal");
    // No flashy marketing animation vocabulary.
    expect(atom).not.toMatch(/\bscale\b|\brotate\b|\banimate=\{\{|whileHover|whileTap/);
    expect(atom).not.toContain("duration");
    // No app-local cursor utilities (pointer cursors are kit-level); the cards
    // are non-interactive, so no cursor class at all.
    expect(atom).not.toContain("cursor-");
  });

  it("caps the entrance stagger so grids stay calm", () => {
    expect(atom).toContain("secondaryDelay");
    expect(atom).toContain("0.2");
  });
});

describe("secondary pages use the shared atom", () => {
  const pages = ["../app/services/page.tsx", "../app/about/page.tsx", "../app/team/page.tsx"];

  it("renders list content through SecondaryCard/SecondaryGrid, not GlyphList", () => {
    for (const rel of pages) {
      const page = src(rel);
      expect(page).toContain("SecondaryCard");
      expect(page).toContain("@/components/SecondaryCard");
      expect(page).not.toContain("GlyphList");
      expect(page).not.toContain("GlyphRow");
      expect(page).not.toContain("cursor-");
    }
  });

  it("keeps DocumentFrame / PageTitle / Section structure", () => {
    for (const rel of pages) {
      const page = src(rel);
      expect(page).toContain("<DocumentFrame>");
      expect(page).toContain("<PageTitle");
      expect(page).toContain("<Section");
    }
  });

  it("keeps copy unchanged in meaning", () => {
    expect(src("../app/services/page.tsx")).toContain("Deploy the stack");
    expect(src("../app/services/page.tsx")).toContain("Hand over the work");
    expect(src("../app/about/page.tsx")).toContain("MIT, and public");
    expect(src("../app/about/page.tsx")).toContain("Bring your own keys");
    expect(src("../app/about/page.tsx")).toContain("NautilusTrader");
    expect(src("../app/team/page.tsx")).toContain("chrizefan");
    expect(src("../app/team/page.tsx")).toContain("In the open");
  });

  it("keeps the team avatar vendored locally, never hotlinked", () => {
    const team = src("../app/team/page.tsx");
    expect(team).toContain('"/team/chris.png"');
    expect(team).not.toMatch(/https:\/\/[^"]*\.png/);
  });

  it("leaves out-of-scope surfaces alone", () => {
    for (const rel of [
      "../components/landing/QuantSection.tsx",
      "../components/landing/OpenSourceLive.tsx",
    ]) {
      let page: string | null = null;
      try {
        page = src(rel);
      } catch {
        page = null;
      }
      if (page !== null) expect(page).not.toContain("SecondaryCard");
    }
  });
});
