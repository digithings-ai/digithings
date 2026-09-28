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
    // Grouped picker + collapsible inspector sidebar (chat-shell pattern).
    expect(client).toMatch(/<select/);
    expect(client).toMatch(/<optgroup/);
    expect(client).toMatch(/Hide inspector sidebar/);
    expect(client).toMatch(/Show inspector sidebar/);
    expect(client).toMatch(/keydown/);
    // Draft-driven preview: the shell validates drafts and passes the
    // last-valid deployment down; the preview keeps no draft knowledge.
    expect(client).toMatch(/\/api\/devkit\/validate/);
    expect(client).toMatch(/withValidation/);
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
    expect(client).toContain("read-only");
    expect(client).toMatch(/aria-label="Deployments"/);
  });

  it("editors cover every config area without touching the save API", () => {
    const editors = read("devkit/devkit-editors.tsx");
    for (const section of [
      "Identity",
      "Backend",
      "Appearance",
      "Features",
      "Models",
      "Tools",
      "MCP servers",
      "Gate",
    ]) {
      expect(editors).toContain(`title="${section}"`);
    }
    // Form edits go through the tested draft helpers, never raw string ops.
    expect(editors).toMatch(/setScalar|setBoolean|setStringList/);
    expect(editors).toMatch(/secretState/);
    expect(editors).not.toMatch(/\/api\/devkit\/save/);
  });
});
