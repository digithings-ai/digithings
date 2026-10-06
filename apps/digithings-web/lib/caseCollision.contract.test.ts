import { execFileSync } from "node:child_process";
import { extname, relative, resolve } from "node:path";
import { describe, expect, it } from "vitest";

/**
 * DIG-1640. The landing page returned 500 because `Sections.tsx` and `sections.ts`
 * sat in the same directory, sharing a stem that differs only by case. Next's
 * webpack config tries `.tsx` before `.ts`, so on a case-insensitive filesystem
 * `./sections` resolved to the component module — which does not export
 * `LANDING_SECTIONS` — and `SectionRail` threw on `SECTIONS.map`.
 *
 * The check keys on the **stem**, not the whole path, because that is the unit
 * `resolve.extensions` collides on: `Sections.tsx` + `sections.ts` are different
 * paths with different extensions, so they can coexist on disk, but `sections` +
 * `.tsx` is a single resolution request that one of them answers on macOS and the
 * other on Linux. A full-path lowercase comparison would not have caught this.
 *
 * Tracked files only (`git ls-files`), so the result matches what CI checks out
 * and a dirty or ignored working file cannot mask the check.
 */
const APP_ROOT = resolve(__dirname, "..");
const REPO_ROOT = resolve(APP_ROOT, "../..");

function trackedAppFiles(): string[] {
  const out = execFileSync("git", ["ls-files", "-z", "--", "apps/digithings-web"], {
    cwd: REPO_ROOT,
    encoding: "utf8",
  });
  const files = out.split("\0").filter(Boolean);
  // A pathspec that matches nothing exits 0 with empty output, which would turn
  // this guard green while it inspects zero files. Fail loudly instead, so
  // moving or renaming the app cannot silently disable the check.
  if (files.length === 0) {
    throw new Error("git ls-files matched no files under apps/digithings-web — guard would pass vacuously");
  }
  return files;
}

/** Directory + lowercased stem -> the paths sharing it. Pure, so it is testable. */
function stemCollisionsFor(files: string[]): Map<string, string[]> {
  const byKey = new Map<string, string[]>();
  for (const repoPath of files) {
    const parts = repoPath.split("/");
    const file = parts.pop() as string;
    const key = `${parts.join("/")}/${file.slice(0, file.length - extname(file).length)}`.toLowerCase();
    const bucket = byKey.get(key);
    if (bucket) bucket.push(repoPath);
    else byKey.set(key, [repoPath]);
  }
  return new Map([...byKey].filter(([, paths]) => paths.length > 1));
}

function stemCollisions(): Map<string, string[]> {
  return stemCollisionsFor(trackedAppFiles());
}

describe("digithings-web file naming", () => {
  it("tracks no two files that differ only by case", () => {
    const collisions = [...stemCollisions().entries()].map(
      ([key, paths]) =>
        `${key}: ${paths.map((p) => relative(APP_ROOT, resolve(REPO_ROOT, p))).join(", ")}`,
    );
    expect(collisions).toEqual([]);
  });

  // Guards the guard. It calls the real bucketing function on synthetic input,
  // so sabotaging the stem logic — or replacing it with a naive full-path
  // lowercase compare — turns this red instead of leaving test 1 unfalsifiable.
  it("finds a case-differing stem pair when one exists", () => {
    expect([...stemCollisionsFor(["a/Sections.tsx", "a/sections.ts"]).values()]).toEqual([
      ["a/Sections.tsx", "a/sections.ts"],
    ]);
    // The real bug's shape: different paths AND different extensions, one stem.
    expect([...stemCollisionsFor(["d/Sections.tsx", "d/sections.ts"]).keys()]).toEqual(["d/sections"]);
    // A case-only rename of the same extension is the other shape that bites.
    expect([...stemCollisionsFor(["d/index.ts", "d/Index.ts"]).keys()]).toEqual(["d/index"]);
    // Distinct stems are not a collision, however similar they look.
    expect(stemCollisionsFor(["a/Section.tsx", "a/Sections.ts"])).toEqual(new Map());
    expect(stemCollisionsFor(["a/Foo.tsx", "a/Bar.tsx"])).toEqual(new Map());
    // Different directories never collide, however similar.
    expect(stemCollisionsFor(["x/Sections.tsx", "y/sections.ts"])).toEqual(new Map());
    // A lone file cannot collide with itself.
    expect(stemCollisionsFor(["a/sections.ts"])).toEqual(new Map());
  });
});
