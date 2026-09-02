import { execFileSync } from "node:child_process";
import { existsSync, readFileSync } from "node:fs";
import { resolve } from "node:path";
import { describe, expect, it } from "vitest";
import {
  AVATARS,
  BRAND_DOMAIN,
  BRAND_TAGLINE,
  BRAND_WORD,
  EMAIL_FILES,
  HEADERS,
  OG_CARDS,
  SIGNOFF_TEXT,
} from "./brandKit";

const publicDir = resolve(__dirname, "../public");
const pagePath = resolve(__dirname, "../app/brand/page.tsx");
const navPath = resolve(__dirname, "../app/_nav.tsx");

const FORBIDDEN = [
  "12X",
  "Twelve X",
  "TwelveX",
  "Prime Terminal",
  "DigiThings",
  "DigiChat",
  "Digiquant",
  "live-trading",
  "live trading",
];

function publicPath(href: string): string {
  return resolve(publicDir, href.replace(/^\//, ""));
}

describe("brand kit page", () => {
  it("uses the OG tagline and lowercase wordmark", () => {
    expect(BRAND_WORD).toBe("digithings");
    expect(BRAND_TAGLINE).toBe("AI infrastructure in a glass box you own.");
    expect(BRAND_DOMAIN).toBe("digithings.ai");
    expect(SIGNOFF_TEXT).toContain(BRAND_WORD);
    expect(SIGNOFF_TEXT).toContain(BRAND_TAGLINE);
    expect(SIGNOFF_TEXT).toContain(`https://${BRAND_DOMAIN}`);
  });

  it("ships a downloadable file for every catalogue href", () => {
    for (const file of [...AVATARS, ...HEADERS, ...OG_CARDS, ...EMAIL_FILES]) {
      expect(existsSync(publicPath(file.href)), file.href).toBe(true);
    }
  });

  it("does not invent a tagline or name private clients", () => {
    const page = readFileSync(pagePath, "utf8");
    const kit = readFileSync(resolve(__dirname, "./brandKit.ts"), "utf8");
    const signoff = readFileSync(publicPath("/brand/email/signoff.txt"), "utf8");
    const html = readFileSync(publicPath("/brand/email/signoff.html"), "utf8");
    for (const blob of [page, kit, signoff, html]) {
      for (const needle of FORBIDDEN) {
        expect(blob).not.toContain(needle);
      }
    }
    expect(page).toContain("{BRAND_TAGLINE}");
    expect(kit).toContain(BRAND_TAGLINE);
    expect(signoff).toContain(BRAND_TAGLINE);
    expect(html).toContain(BRAND_TAGLINE);
  });

  it("is linked from company nav and footer", () => {
    const nav = readFileSync(navPath, "utf8");
    expect(nav).toContain('href: "/brand"');
    expect(nav.match(/href: "\/brand"/g)?.length).toBeGreaterThanOrEqual(2);
  });

  it("includes X 1500×500 and LinkedIn 1584×396 headers", () => {
    const hrefs = HEADERS.map((h) => h.href).join("\n");
    expect(hrefs).toContain("digithings-x-1500x500");
    expect(hrefs).toContain("digithings-linkedin-personal-1584x396");
    expect(hrefs).toContain("digithings-linkedin-company-1128x191");
  });

  it("build-header.py --check is clean", () => {
    const repo = resolve(__dirname, "../../..");
    try {
      execFileSync("python3", ["-c", "import fontTools"], { stdio: "ignore" });
    } catch {
      execFileSync(
        "python3",
        ["-m", "pip", "install", "--user", "fonttools==4.63.0"],
        { cwd: repo },
      );
    }
    const out = execFileSync(
      "python3",
      ["frontend/digiweb/brand/build-header.py", "--check"],
      { cwd: repo, encoding: "utf8" },
    );
    expect(out).toContain("in sync");
  }, 30_000);
});
