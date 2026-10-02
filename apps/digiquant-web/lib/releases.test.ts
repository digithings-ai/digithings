import { describe, expect, it } from "vitest";
import { readFileSync } from "node:fs";
import { resolve } from "node:path";
import { TAGGED_RELEASES } from "./releases";

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
});
