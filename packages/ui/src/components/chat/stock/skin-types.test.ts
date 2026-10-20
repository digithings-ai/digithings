import { describe, expect, it } from "vitest";

import { resolveWorkDisclosure, workVisibilityForView } from "./skin-types";

describe("work visibility", () => {
  it("folds the quiet chain when the answer starts, not when the turn ends", () => {
    expect(resolveWorkDisclosure("quiet").foldOnAnswer).toBe(true);
    expect(resolveWorkDisclosure("balanced").foldOnAnswer).toBe(false);
    expect(resolveWorkDisclosure("verbose").foldOnAnswer).toBe(false);
    expect(resolveWorkDisclosure("hidden").foldOnAnswer).toBe(false);
  });

  it("keeps the verbose chain open for good and the balanced one folded at rest", () => {
    expect(resolveWorkDisclosure("verbose").openAtRest).toBe(true);
    expect(resolveWorkDisclosure("balanced").openAtRest).toBe(false);
    expect(resolveWorkDisclosure("quiet").openAtRest).toBe(false);
  });

  it("folds the whole trace away for the hidden level only", () => {
    expect(resolveWorkDisclosure("hidden").summaryOnly).toBe(true);
    expect(resolveWorkDisclosure("quiet").summaryOnly).toBe(false);
    expect(resolveWorkDisclosure("quiet").chainOpen).toBe(true);
  });

  it("maps the client's view level straight onto the work visibility", () => {
    expect(workVisibilityForView("quiet")).toBe("quiet");
    expect(workVisibilityForView("verbose")).toBe("verbose");
    expect(workVisibilityForView("balanced")).toBe("balanced");
    // `hidden` is a level of its own now: it renders the summary line.
    expect(workVisibilityForView("hidden")).toBe("hidden");
  });
});
