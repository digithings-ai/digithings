import { describe, expect, it } from "vitest";
import { applyScrollSpyVote, visibleGroupFromEntries } from "./devkit-editors";

describe("visibleGroupFromEntries", () => {
  it("returns null with no entries", () => {
    expect(visibleGroupFromEntries([])).toBe(null);
  });
  it("picks the foremost group", () => {
    expect(
      visibleGroupFromEntries([
        { id: "basics", top: -120 },
        { id: "appearance", top: 40 },
        { id: "advanced", top: 600 },
      ]),
    ).toBe("basics");
  });
});

describe("applyScrollSpyVote", () => {
  it("opens the visible group when nothing is suppressed", () => {
    expect(applyScrollSpyVote("basics", null, "appearance")).toEqual({
      open: "appearance",
      manualClosed: null,
    });
  });
  it("never collapses on a null vote", () => {
    expect(applyScrollSpyVote("basics", null, null)).toEqual({
      open: "basics",
      manualClosed: null,
    });
    expect(applyScrollSpyVote(null, "basics", null)).toEqual({
      open: null,
      manualClosed: "basics",
    });
  });
  it("suppresses a same-id reopen after a manual close", () => {
    expect(applyScrollSpyVote(null, "basics", "basics")).toEqual({
      open: null,
      manualClosed: "basics",
    });
  });
  it("releases the suppression when a different group becomes visible", () => {
    expect(applyScrollSpyVote(null, "basics", "appearance")).toEqual({
      open: "appearance",
      manualClosed: null,
    });
  });
  it("holds the nav-clicked group over a stale vote during settle", () => {
    // Nav click opened appearance; the smooth scroll has not settled yet and
    // the observer still elects basics from pre-scroll geometry. The stale
    // vote must not yank the clicked group away.
    expect(applyScrollSpyVote("appearance", null, "basics", "appearance")).toEqual({
      open: "appearance",
      manualClosed: null,
    });
  });
  it("holds the nav-clicked group on a null vote during settle", () => {
    expect(applyScrollSpyVote("appearance", null, null, "appearance")).toEqual({
      open: "appearance",
      manualClosed: null,
    });
  });
  it("releases the nav hold when the clicked group becomes foremost", () => {
    expect(applyScrollSpyVote("appearance", null, "appearance", "appearance")).toEqual({
      open: "appearance",
      manualClosed: null,
    });
  });
});
