import { describe, expect, it } from "vitest";
import { readFileSync } from "node:fs";
import { resolve } from "node:path";
import { TAGGED_RELEASES } from "./releases";

const CHANGELOG_BY_PRODUCT: Record<string, string> = {
  digichat: "apps/digichat/CHANGELOG.md",
  digiskills: "digiskills/CHANGELOG.md",
};

describe("tagged releases", () => {
  it("matches the version headings in the repository changelogs", () => {
    const root = resolve(__dirname, "../../..");
    const digichat = readFileSync(resolve(root, "apps/digichat/CHANGELOG.md"), "utf8");
    const digiskills = readFileSync(resolve(root, "digiskills/CHANGELOG.md"), "utf8");
    const chat = TAGGED_RELEASES.find((r) => r.product === "digichat");
    const skills = TAGGED_RELEASES.find((r) => r.product === "digiskills");
    expect(digichat).toContain(`## [${chat?.version}]`);
    expect(digichat).toContain(chat?.date ?? "");
    expect(digiskills).toContain(`## [${skills?.version}]`);
    expect(digiskills).toContain(skills?.date ?? "");
  });

  it("lists each product release once", () => {
    const keys = TAGGED_RELEASES.map((release) => `${release.product}-${release.version}`);
    expect(new Set(keys).size).toBe(keys.length);
  });

  it("links each release to the range its own changelog entry names", () => {
    const root = resolve(__dirname, "../../..");
    for (const release of TAGGED_RELEASES) {
      const changelog = readFileSync(resolve(root, CHANGELOG_BY_PRODUCT[release.product]), "utf8");
      const heading = changelog
        .split("\n")
        .find((line) => line.startsWith(`## [${release.version}]`));
      expect(heading).toBeDefined();
      expect(release.href).toBe(heading?.match(/\]\(([^)]+)\)/)?.[1]);
    }
  });
});
