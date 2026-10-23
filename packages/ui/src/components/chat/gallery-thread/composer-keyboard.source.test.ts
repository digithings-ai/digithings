import { readFileSync } from "node:fs";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";
import { describe, expect, it } from "vitest";

/**
 * The dismissal has to run from the submit path, not merely exist as a helper:
 * a unit-tested `dismissComposerKeyboard` that nothing calls would leave the
 * phone keyboard up exactly as before.
 *
 * It also has to survive assistant-ui's own focus behaviour. The input refocuses
 * on `thread.runStart` (and on scroll-to-bottom) by default, which focuses the
 * textarea again the moment the answer starts streaming — the blur would be
 * undone before the user saw anything. Both defaults are therefore switched off
 * on a coarse pointer, and the assertions below pin that as well as the call.
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

  it("only dismisses when the composer actually had text to send", () => {
    const start = thread.indexOf("const handleSubmit");
    const body = thread.slice(start, start + 900);

    // Read before the submit clears the textarea, and guard the dismissal with
    // it: Enter on an empty composer submits the form too, and that must not
    // take focus away.
    const captured = body.indexOf("const sent = composerHasText(composerRootRef.current)");
    const submitted = body.indexOf("onComposerSubmit?.(event)");
    expect(captured).toBeGreaterThan(-1);
    expect(captured).toBeLessThan(submitted);
    expect(body).toContain("if (sent) dismissComposerKeyboard");
  });

  it("dismisses on the edit-message path too", () => {
    // An edit is a send: the visitor submits corrected text and the answer
    // starts streaming. Leaving the keyboard up there hides the very thing
    // they just asked for, so this branch dismisses as well.
    const start = thread.indexOf("const handleSubmit");
    const body = thread.slice(start, start + 900);
    const editBranch = body.slice(0, body.indexOf("onComposerSubmit?.(event)"));

    expect(editBranch).toContain("edit.commit(");
    expect(editBranch).toContain("dismissKeyboardIfCoarse()");
  });

  it("turns off the runtime's refocus on a coarse pointer", () => {
    // Without these, assistant-ui focuses the textarea again on run start and
    // on scroll-to-bottom, reopening the keyboard over the streaming answer.
    expect(thread).toContain("unstable_focusOnRunStart={!coarsePointer}");
    expect(thread).toContain("unstable_focusOnScrollToBottom={!coarsePointer}");
    // The pointer check must be resolved after mount, not during render: the
    // server has no matchMedia, and a phone would otherwise hydrate a tree that
    // disagrees with the one it was sent.
    expect(thread).toContain("const [coarsePointer, setCoarsePointer] = useState(false)");
  });
});

/**
 * A tapped example never reaches the composer's submit or the app's `send`:
 * the static chip calls `aui.thread.append`, the runtime one goes through
 * `SuggestionPrimitive.Trigger send`, and a follow-up chip through
 * `ThreadPrimitive.Suggestion send`. On iOS a button takes no focus, so the
 * composer would keep the keyboard up over the answer unless each one
 * dismisses for itself.
 */
describe("suggestion taps retract the keyboard", () => {
  const followUps = readFileSync(join(here, "follow-up-suggestions.aui.tsx"), "utf8");

  it("dismisses from a static example question before appending", () => {
    const at = thread.indexOf("const StaticSuggestionItem");
    expect(at).toBeGreaterThan(-1);
    const body = thread.slice(at, at + 700);
    const dismissed = body.indexOf("dismissKeyboardIfCoarse()");
    const appended = body.indexOf("aui.thread.append(");

    expect(dismissed).toBeGreaterThan(-1);
    expect(appended).toBeGreaterThan(-1);
    expect(dismissed).toBeLessThan(appended);
  });

  it("dismisses from a runtime suggestion trigger", () => {
    const at = thread.indexOf("<SuggestionPrimitive.Trigger send asChild>");
    expect(at).toBeGreaterThan(-1);
    expect(thread.slice(at, at + 400)).toContain("onClick={() => dismissKeyboardIfCoarse()}");
  });

  it("dismisses from a follow-up suggestion chip", () => {
    expect(followUps).toContain("onClick={() => dismissKeyboardIfCoarse()}");
  });
});
