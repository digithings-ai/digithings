import { readFileSync } from "node:fs";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";
import { describe, expect, it } from "vitest";

/**
 * The dismissal has to run from the submit path, not merely exist as a helper:
 * a unit-tested `dismissComposerKeyboard` that nothing calls would leave the
 * phone keyboard up exactly as before.
 */
const here = dirname(fileURLToPath(import.meta.url));
const thread = readFileSync(join(here, "thread.aui.tsx"), "utf8");

describe("composer keyboard dismissal wiring", () => {
  it("dismisses the keyboard after a send is handed to the runtime", () => {
    const start = thread.indexOf("const handleSubmit");
    expect(start).toBeGreaterThan(-1);
    const body = thread.slice(start, start + 900);

    const submitted = body.indexOf("onComposerSubmit?.(event)");
    const dismissed = body.indexOf("dismissComposerKeyboard(composerRootRef.current)");

    expect(submitted).toBeGreaterThan(-1);
    expect(dismissed).toBeGreaterThan(-1);
    // After the submit, so the runtime has already read the draft.
    expect(dismissed).toBeGreaterThan(submitted);
  });

  it("does not run the dismissal on the edit-message path", () => {
    const start = thread.indexOf("const handleSubmit");
    const body = thread.slice(start, start + 900);
    const editBranch = body.slice(0, body.indexOf("onComposerSubmit?.(event)"));

    expect(editBranch).toContain("edit.commit(");
    expect(editBranch).not.toContain("dismissComposerKeyboard");
  });
});
