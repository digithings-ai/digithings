import { readdir, readFile } from "node:fs/promises";
import { fileURLToPath } from "node:url";

const artifactRoots = [
  fileURLToPath(new URL("../out/", import.meta.url)),
  fileURLToPath(new URL("../.next/server/app/", import.meta.url)),
];
// Next emitted this proxy body when a server component imported the constant
// from a `use client` module. Route artifacts must contain the literal class.
const marker = "Attempted to call SUBPAGE_MAX";
const matches = [];

async function scan(directory) {
  let entries;
  try {
    entries = await readdir(directory, { withFileTypes: true });
  } catch (error) {
    if (error.code === "ENOENT") return 0;
    throw error;
  }

  const counts = await Promise.all(
    entries.map(async (entry) => {
      const path = `${directory}/${entry.name}`;
      if (entry.isDirectory()) return scan(path);
      const isRouteArtifact = [".html", ".txt", ".rsc"].some((suffix) =>
        entry.name.endsWith(suffix),
      );
      if (!isRouteArtifact) return 0;
      if ((await readFile(path, "utf8")).includes(marker)) matches.push(path);
      return 1;
    }),
  );
  return counts.reduce((total, count) => total + count, 0);
}

const artifactCounts = await Promise.all(artifactRoots.map(scan));
const artifactCount = artifactCounts.reduce((total, count) => total + count, 0);

if (artifactCount === 0) {
  console.error("No Olympus route artifacts found. Run the production build first.");
  process.exitCode = 1;
} else if (matches.length > 0) {
  console.error(`Static export contains the SUBPAGE_MAX client proxy:\n${matches.join("\n")}`);
  process.exitCode = 1;
} else {
  console.log(`Static export boundary check passed (${artifactCount} route artifacts).`);
}