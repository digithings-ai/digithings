import { describe, expect, it } from "vitest";

import {
  DEFAULT_THINKING_MODE,
  DEFAULT_VIEW_MODE,
  THINKING_MODES,
  VIEW_MODES,
  effectiveReasoningMode,
  effectiveToolCallsMode,
  isThinkingMode,
  isViewMode,
  viewIsVisible,
} from "@/lib/view-modes";

describe("view-modes", () => {
  it("defaults to the balanced view with auto thinking", () => {
    expect(DEFAULT_VIEW_MODE).toBe("balanced");
    expect(DEFAULT_THINKING_MODE).toBe("auto");
    expect(VIEW_MODES).toEqual(["hidden", "quiet", "balanced", "verbose"]);
    expect(THINKING_MODES).toEqual(["auto", "collapsed", "open"]);
  });

  it("guards view and thinking mode values", () => {
    expect(isViewMode("hidden")).toBe(true);
    expect(isViewMode("balanced")).toBe(true);
    expect(isViewMode("expanded")).toBe(false);
    expect(isViewMode(undefined)).toBe(false);

    expect(isThinkingMode("auto")).toBe(true);
    expect(isThinkingMode("open")).toBe(true);
    expect(isThinkingMode("detailed")).toBe(false);
    expect(isThinkingMode(true)).toBe(false);
  });

  it("hides both groups only in the hidden view", () => {
    expect(viewIsVisible("hidden")).toBe(false);
    expect(viewIsVisible("quiet")).toBe(true);
    expect(viewIsVisible("balanced")).toBe(true);
    expect(viewIsVisible("verbose")).toBe(true);
  });

  it("folds the view mode with the thinking override for reasoning", () => {
    expect(effectiveReasoningMode("hidden", "auto")).toBe("off");
    expect(effectiveReasoningMode("hidden", "open")).toBe("off");

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
    expect(effectiveToolCallsMode("hidden")).toBe("off");
    expect(effectiveToolCallsMode("quiet")).toBe("collapsed");
    expect(effectiveToolCallsMode("balanced")).toBe("balanced");
    expect(effectiveToolCallsMode("verbose")).toBe("expanded");
  });
});
