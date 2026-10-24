import { readFileSync } from "node:fs";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";
import { describe, expect, it } from "vitest";

/**
 * The keyboard has to retract on *every* path that starts a turn, not only on
 * the composer's submit.
 *
 * An example question, a redo, a retry and a resubmitted edit all begin a turn
 * without going through `handleSubmit`, and each one used to leave the phone
 * keyboard up over the streaming answer. Those paths meet in this hook, so the
 * dismissal belongs at the entry points asserted here. The helper is unit
 * tested next door in `@digithings/ui`; this file pins that it is actually
 * called.
 */
const here = dirname(fileURLToPath(import.meta.url));
const source = readFileSync(join(here, "use-embed-digi-chat.ts"), "utf8");

function bodyAfter(marker: string, length = 900): string {
  const at = source.indexOf(marker);
  expect(at, `${marker} should exist`).toBeGreaterThan(-1);
  return source.slice(at, at + length);
}

describe("keyboard dismissal on every send path", () => {
  it("dismisses in send, which an example question and a retry both reach", () => {
    expect(bodyAfter("const send = useCallback(")).toContain("dismissKeyboardIfCoarse()");
  });

  it("dismisses in doRegenerate, which the redo action reaches", () => {
    expect(bodyAfter("const doRegenerate = useCallback(")).toContain(
      "dismissKeyboardIfCoarse()",
    );
  });

  it("dismisses in editLastUser, which a resubmitted edit reaches", () => {
    expect(bodyAfter("const editLastUser = useCallback(")).toContain(
      "dismissKeyboardIfCoarse()",
    );
  });

  it("imports the dismissal from the shared kit rather than re-implementing it", () => {
    expect(source).toContain('from "@digithings/ui/chat/composer-keyboard"');
  });
});
