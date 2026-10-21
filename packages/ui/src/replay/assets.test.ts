import { join } from "node:path";
import { pathToFileURL } from "node:url";
import { describe, expect, it } from "vitest";
import { findReplayPackagesDir, loadReplayStyles, replayPackageCandidates } from "./assets";

describe("replay assets", () => {
  it("falls back to the working directory when the module is bundled", () => {
    const candidates = replayPackageCandidates(null, "/srv/app/apps/digichat");
    expect(candidates).toEqual(["/srv/app/packages", "/srv/app/apps/digichat/packages"]);
    const found = findReplayPackagesDir(candidates, (path) =>
      path.startsWith("/srv/app/packages/"),
    );
    expect(found).toBe("/srv/app/packages");
  });

  it("prefers the source tree next to the module", () => {
    const url = pathToFileURL("/repo/packages/ui/src/replay/assets.ts").href;
    expect(replayPackageCandidates(url, "/elsewhere")[0]).toBe(join("/repo/packages"));
  });

  it("throws when the sheets are missing, so routes can answer 503", () => {
    expect(() => findReplayPackagesDir(["/nope"], () => false)).toThrow(/not found/);
  });

  it("loads the sheets and fonts from source", () => {
    const css = loadReplayStyles();
    expect(css).toContain(".aui-user-message-content");
    expect(css).toContain("data:font/woff2;base64,");
  });
});
