import { describe, expect, it } from "vitest";

import {
  normalizeViewPref,
  resolveWorkDisclosure,
  workVisibilityForView,
} from "./skin-types";

describe("work visibility", () => {
  it("folds the quiet chain when the answer starts, not when the turn ends", () => {
    expect(resolveWorkDisclosure("quiet").foldOnAnswer).toBe(true);
    expect(resolveWorkDisclosure("balanced").foldOnAnswer).toBe(false);
    expect(resolveWorkDisclosure("verbose").foldOnAnswer).toBe(false);
  });

  it("keeps the verbose chain open for good and the balanced one folded at rest", () => {
    expect(resolveWorkDisclosure("verbose").openAtRest).toBe(true);
    expect(resolveWorkDisclosure("balanced").openAtRest).toBe(false);
    expect(resolveWorkDisclosure("quiet").openAtRest).toBe(false);
  });

  it("has no summary-only level any more", () => {
    // The chain always renders; the folded header is the status line, so the
    // retired one-line replacement is never used.
    expect(resolveWorkDisclosure("quiet").summaryOnly).toBe(false);
    expect(resolveWorkDisclosure("quiet").chainOpen).toBe(true);
    expect(resolveWorkDisclosure("balanced").summaryOnly).toBe(false);
    expect(resolveWorkDisclosure("verbose").summaryOnly).toBe(false);
    expect(resolveWorkDisclosure(undefined).summaryOnly).toBe(false);
  });

  it("maps the client's view level straight onto the work visibility", () => {
    expect(workVisibilityForView("quiet")).toBe("quiet");
    expect(workVisibilityForView("verbose")).toBe("verbose");
    expect(workVisibilityForView("balanced")).toBe("balanced");
    expect(workVisibilityForView(undefined)).toBe("balanced");
  });

  it("folds a stale hidden level onto the titles-only chain", () => {
    // A host bundle that predates the removal of `hidden` still sends it.
    expect(workVisibilityForView("hidden" as never)).toBe("quiet");
  });

  it("folds the retired view ids in saved prefs", () => {
    expect(normalizeViewPref("hidden")).toBe("quiet");
    expect(normalizeViewPref("compact")).toBe("quiet");
    expect(normalizeViewPref("detailed")).toBe("verbose");
    expect(normalizeViewPref("verbose")).toBe("verbose");
    expect(normalizeViewPref("nonsense")).toBe("balanced");
  });
});
