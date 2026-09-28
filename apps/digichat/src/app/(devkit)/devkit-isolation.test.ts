import { readFileSync } from "node:fs";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";
import { describe, expect, it } from "vitest";

const here = dirname(fileURLToPath(import.meta.url));

function read(rel: string): string {
  return readFileSync(join(here, rel), "utf8");
}

describe("devkit route isolation", () => {
  it("stays out of the digichat app shell", () => {
    const layout = read("layout.tsx");
    expect(layout).not.toMatch(/import ["'].*globals\.css["']/);
    expect(layout).not.toMatch(/themeInitScript/);
    expect(layout).not.toMatch(/accent-digichat/);
    expect(layout).not.toMatch(/data-theme/);
    expect(layout).not.toMatch(/<Providers/);
    // Shares the baseline assistant-ui template sheet, never app chrome.
    expect(layout).toMatch(/\(baseline\)\/baseline\.css/);
    expect(layout).toMatch(/variable:\s*"--font-geist-mono"/);
    // Kit-native rebuild: layout pulls the devkit-scoped controls sheet,
    // which imports the token bridge + kit sheets (order pinned there).
    expect(layout).toMatch(/devkit-controls\.css/);
    const css = read("devkit-controls.css");
    expect(css).toMatch(/@digithings\/design\/tokens\.css/);
    expect(css).toMatch(/styles\/web-theme\.css/);
    expect(css).toMatch(/styles\/controls-core\.css/);
    expect(css).toMatch(/styles\/controls-overlay\.css/);
    // No selector may leak outside devkit scope: every rule opens .devkit-,
    // @import, or @source.
    for (const line of css.split("\n")) {
      const t = line.trim();
      if (t === "" || t.startsWith("@") || t.startsWith("/*") || t.startsWith("*") || t === "}") continue;
      if (t.startsWith(".devkit-") || t.startsWith(".")) {
        expect(t.startsWith(".devkit-")).toBe(true);
      }
    }
  });

  it("is dev-only at the page boundary", () => {
    const page = read("devkit/page.tsx");
    expect(page).toMatch(/NODE_ENV.*production/);
    expect(page).toMatch(/notFound\(\)/);
    expect(page).toMatch(/force-dynamic/);
  });

  it("menu reads from the devkit configs API and saves through the save API", () => {
    const client = read("devkit/devkit-client.tsx");
    expect(client).toMatch(/\/api\/devkit\/configs/);
    // Collapsible inspector sidebar (chat-shell pattern).
    expect(client).toMatch(/Hide inspector sidebar/);
    expect(client).toMatch(/Show inspector sidebar/);
    expect(client).toMatch(/keydown/);
    // Draft-driven preview: the shell validates drafts and passes the
    // last-valid deployment down; the preview keeps no draft knowledge.
    expect(client).toMatch(/\/api\/devkit\/validate/);
    expect(client).toMatch(/withValidation/);
    // Grouped kit deployment picker (select-reference pattern): kit Select
    // with grouped popup, never a native dropdown.
    expect(client).toMatch(/DevkitDeploymentSelect|SelectValue/);
    expect(client).toMatch(/SelectGroup/);
    expect(client).toMatch(/SelectLabel/);
    expect(client).toMatch(/SelectSeparator/);
    expect(client).toMatch(/Select a deployment/);
    expect(client).toMatch(/onValueChange/);
    expect(client).not.toMatch(/<select/);
    expect(client).not.toMatch(/<optgroup/);
    // Sidebar scroll container ref feeds the editors scroll-spy observer.
    expect(client).toMatch(/scrollRoot/);
    // Canon tokens resolve inside the devkit subtree only (never layout).
    expect(client).toMatch(/data-theme="light"/);
    // Step-4 accordion editors are wired; Step 5 adds the save path.
    expect(client).toMatch(/DevkitEditors/);
    // Step 5: raw YAML is an editable textarea, the save button posts the
    // draft (dirty-gated, invalid-blocked), and "+ new" starts a blank draft
    // whose save id derives from its slug.
    expect(client).toMatch(/<textarea/);
    expect(client).toMatch(/\/api\/devkit\/save/);
    expect(client).toMatch(/aria-label="Save draft"/);
    expect(client).toMatch(/aria-label="New deployment"/);
    expect(client).toMatch(/createNewFileDraft/);
    expect(client).toMatch(/slugFromDraftText/);
    // P2 export pane builds deploy artifacts from the live draft,
    // client-side only — no export API exists.
    expect(client).toMatch(/DevkitExportPane/);
    expect(client).toMatch(/setExportOpen/);
    expect(client).not.toMatch(/\/api\/devkit\/export/);
    const pane = read("devkit/devkit-export-pane.tsx");
    expect(pane).toMatch(/aria-label="Export deployment"/);
    expect(pane).toMatch(/role="tab"/);
    expect(pane).toMatch(/buildComposeBundle/);
    expect(pane).toMatch(/buildEmbedBundle/);
    expect(pane).not.toMatch(/\/api\//);
    expect(client).toContain("read-only");
    expect(client).toMatch(/aria-label="Deployments"/);
  });

  it("editors cover every config area without touching the save API", () => {
    const editors = read("devkit/devkit-editors.tsx");
    const sections = [
      "Identity",
      "Backend",
      "Appearance",
      "Features",
      "Models",
      "Tools",
      "MCP servers",
      "Gate",
    ];
    for (const section of sections) {
      expect(editors).toContain(section);
    }
    // Spec §2 regrouping map: all 8 titles each under exactly one group
    // (Basics: Identity/Features/Models; Appearance: Appearance;
    // Advanced: Backend/Tools/MCP servers/Gate).
    const groupsAt = editors.indexOf("const GROUPS");
    expect(groupsAt).toBeGreaterThan(-1);
    const groupsEnd = editors.indexOf("] as const", groupsAt);
    expect(groupsEnd).toBeGreaterThan(groupsAt);
    const groupsBlock = editors.slice(groupsAt, groupsEnd);
    // Each title lives in exactly one group's sections array (the
    // "Appearance" group label shares its name with its section, so scope
    // the count to sections arrays, not the whole GROUPS literal).
    const sectionsArrays = [...groupsBlock.matchAll(/sections: \[([^\]]*)\]/g)].map(
      (m) => m[1],
    );
    expect(sectionsArrays).toHaveLength(3);
    for (const section of sections) {
      const hits = sectionsArrays.filter((body) => body.includes(`"${section}"`)).length;
      expect(hits).toBe(1);
    }
    // Single-open kit disclosure shell with scroll-spy (spec §1): kit
    // Collapsible per group, one openGroup, one IntersectionObserver over
    // the group anchors that opens but never closes. No native dropdowns
    // and no native selects anywhere in the editors or picker rows.
    expect(editors).toMatch(/Collapsible/);
    expect(editors).toMatch(/openGroup/);
    expect(editors).toMatch(/IntersectionObserver/);
    expect(editors).toMatch(/visibleGroupFromEntries/);
    expect(editors).toMatch(/-20% 0px -65% 0px/);
    expect(editors).toMatch(/scrollRoot/);
    expect(editors).not.toMatch(/<details/);
    expect(editors).not.toMatch(/<summary/);
    expect(editors).not.toMatch(/<select/);
    expect(editors).not.toMatch(/<optgroup/);
    // Form edits go through the tested draft helpers, never raw string ops.
    expect(editors).toMatch(/setScalar|setBoolean|setStringList/);
    expect(editors).toMatch(/secretState/);
    expect(editors).not.toMatch(/\/api\/devkit\/save/);
  });
});
