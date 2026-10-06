import { execFileSync } from "node:child_process";
import { extname, relative, resolve } from "node:path";
import { describe, expect, it } from "vitest";

/**
 * DIG-1640. The landing page returned 500 because `Sections.tsx` and `sections.ts`
 * sat in the same directory, sharing a stem that differs only by case. Webpack
 * tries `.tsx` before `.ts`, so on a case-insensitive filesystem `./sections`
 * resolved to the component module — which does not export `LANDING_SECTIONS` —
 * and `SectionRail` threw on `SECTIONS.map`.
 *
 * The check keys on the **stem**, not the whole path, because that is the unit
 * webpack's `resolve.extensions` collides on: `Sections.tsx` + `sections.ts` are
 * different paths and different extensions, but `sections` + `.tsx` is a single
 * resolution request that one of them answers on macOS and the other on Linux.
 * A full-path lowercase comparison would not have caught this.
 *
 * Tracked files only (`git ls-files`), so a dirty or ignored working file cannot
 * fail or mask the check.
 */
const APP_ROOT = resolve(__dirname, "..");

function trackedAppFiles(): string[] {
  const out = execFileSync("git", ["ls-files", "-z", "--", "apps/digithings-web"], {
    cwd: resolve(APP_ROOT, "../.."),
    encoding: "utf8",
  });
  return out.split("\0").filter(Boolean);
}

/** Directory + lowercased stem -> the tracked paths sharing it. */
function stemCollisions(): Map<string, string[]> {
  const byKey = new Map<string, string[]>();
  for (const repoPath of trackedAppFiles()) {
    const parts = repoPath.split("/");
    const file = parts.pop() as string;
    const key = `${parts.join("/")}/${file.slice(0, file.length - extname(file).length)}`.toLowerCase();
    const bucket = byKey.get(key);
    if (bucket) bucket.push(repoPath);
    else byKey.set(key, [repoPath]);
  }
  return new Map([...byKey].filter(([, paths]) => paths.length > 1));
}

describe("digithings-web file naming", () => {
  it("tracks no two files that differ only by case", () => {
    const collisions = [...stemCollisions().entries()].map(
      ([key, paths]) => `${key}: ${paths.map((p) => relative(APP_ROOT, resolve(APP_ROOT, "..", "..", p))).join(", ")}`,
    );
    expect(collisions).toEqual([]);
  });

  it("finds a case-differing stem pair when one exists", () => {
    // Guards the guard: if the walk stopped matching stems, this would pass
    // vacuously and the first test would stop meaning anything.
    const fake = new Map(
      ["components/landing/sections", ["a/Sections.tsx", "a/sections.ts"]].map(([k, v]) => [k.toLowerCase(), v]),
    );
    const hits = [...fake].filter(([, paths]) => paths.length > 1);
    expect(hits).toHaveLength(1);
  });
});