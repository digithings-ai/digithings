import { describe, expect, it } from "vitest";
import { VIEW_CODES, VIEW_LABELS } from "@digithings/digichat-ui";
import { normalizeViewPref } from "@digithings/ui/chat/stock";

import {
  DEFAULT_THINKING_MODE,
  DEFAULT_VIEW_MODE,
  LEGACY_VIEW_MODE_ALIASES,
  THINKING_MODES,
  VIEW_MODES,
  effectiveReasoningMode,
  effectiveToolCallsMode,
  isLegacyViewMode,
  isThinkingMode,
  isViewMode,
  normalizeViewMode,
} from "@/lib/view-modes";

describe("view-modes", () => {
  it("defaults to the balanced view with auto thinking", () => {
    expect(DEFAULT_VIEW_MODE).toBe("balanced");
    expect(DEFAULT_THINKING_MODE).toBe("auto");
    expect(VIEW_MODES).toEqual(["quiet", "balanced", "verbose"]);
    expect(THINKING_MODES).toEqual(["auto", "collapsed", "open"]);
  });

  it("keeps the id contract aligned with the shared palette", () => {
    // The app owns the ids, the shared package owns the wording. Both must
    // name the same levels: when they drift, a row can find no label and
    // render a blank description (DIG-4665).
    expect(VIEW_MODES).toEqual([...VIEW_CODES]);
    for (const mode of VIEW_MODES) {
      expect(VIEW_LABELS[mode].trim()).not.toBe("");
    }
  });

  it("keeps the prefs twin on the same levels", () => {
    // The third id twin: the prefs host in `@digithings/ui/chat/stock` types
    // `api.prefs.view` and normalises what it is given. It must name the
    // app's levels and fold the retired ids to the same targets, or a pref
    // the app cannot read lands on the default.
    for (const mode of VIEW_MODES) {
      expect(normalizeViewPref(mode)).toBe(mode);
    }
    for (const [retired, current] of Object.entries(LEGACY_VIEW_MODE_ALIASES)) {
      expect(normalizeViewPref(retired)).toBe(current);
    }
  });

  it("guards view and thinking mode values", () => {
    expect(isViewMode("quiet")).toBe(true);
    expect(isViewMode("balanced")).toBe(true);
    expect(isViewMode("hidden")).toBe(false);
    expect(isViewMode("expanded")).toBe(false);
    expect(isViewMode(undefined)).toBe(false);

    expect(isThinkingMode("auto")).toBe(true);
    expect(isThinkingMode("open")).toBe(true);
    expect(isThinkingMode("detailed")).toBe(false);
    expect(isThinkingMode(true)).toBe(false);
  });

  it("folds the retired view ids forward", () => {
    // `hidden` was the one-line level; the folded chain shows that same line
    // as its header now, so it means the titles only.
    expect(isLegacyViewMode("hidden")).toBe(true);
    expect(normalizeViewMode("hidden")).toBe("quiet");
    expect(normalizeViewMode("compact")).toBe("quiet");
    expect(normalizeViewMode("detailed")).toBe("verbose");
    expect(normalizeViewMode("verbose")).toBe("verbose");
    expect(normalizeViewMode("nonsense")).toBe("balanced");
    expect(normalizeViewMode(undefined)).toBe("balanced");
  });

  it("folds the view mode with the thinking override for reasoning", () => {
    expect(effectiveReasoningMode("quiet", "auto")).toBe("collapsed");
    expect(effectiveReasoningMode("quiet", "collapsed")).toBe("collapsed");
    expect(effectiveReasoningMode("quiet", "open")).toBe("expanded");

    expect(effectiveReasoningMode("balanced", "auto")).toBe("balanced");
    expect(effectiveReasoningMode("balanced", "collapsed")).toBe("collapsed");
    expect(effectiveReasoningMode("balanced", "open")).toBe("expanded");

    expect(effectiveReasoningMode("verbose", "auto")).toBe("expanded");
    expect(effectiveReasoningMode("verbose", "collapsed")).toBe("collapsed");
    expect(effectiveReasoningMode("verbose", "open")).toBe("expanded");
  });

  it("maps the view mode onto tool-call disclosure", () => {
    expect(effectiveToolCallsMode("quiet")).toBe("collapsed");
    expect(effectiveToolCallsMode("balanced")).toBe("balanced");
    expect(effectiveToolCallsMode("verbose")).toBe("expanded");
  });

  it("has no view that turns the trace off", () => {
    // The retired `hidden` level was the only one that did.
    for (const view of VIEW_MODES) {
      expect(effectiveToolCallsMode(view)).not.toBe("off");
      expect(effectiveReasoningMode(view, "auto")).not.toBe("off");
    }
  });
});
