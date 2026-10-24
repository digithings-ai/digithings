/**
 * Test driver for the projects path guard (DIG-1302).
 *
 * Reads one JSON job on stdin, evaluates it against the real plugin module, and
 * prints one JSON result on stdout. pytest owns the assertions so the suite runs
 * under `pytest -m unit` with no npm install and no vitest dependency; this file
 * exists only to exercise the shipped JavaScript rather than a Python re-write
 * of it.
 *
 * Job:  { repoRoot, cwd, env: {...}, mapping: {...}|null, tool, args }
 * Result: { decision, reason, deniedPaths: [...], engagement, mappingError }
 */

import * as path from "node:path"
import * as fs from "node:fs"
import * as os from "node:os"

const { createGuard } = await import(
  new URL("../../.opencode/plugins/projects-path-guard.js", import.meta.url).href
)

const chunks = []
for await (const chunk of process.stdin) chunks.push(chunk)
const job = JSON.parse(Buffer.concat(chunks).toString("utf8"))

// `mapping: null` means "there is no mapping file at all" — the fail-closed
// case. Otherwise the object is written to a temp file and its path handed to
// the guard, so the real file-reading path is exercised.
let mappingPath = null
if (job.mapping !== null && job.mapping !== undefined) {
  mappingPath = path.join(fs.mkdtempSync(path.join(os.tmpdir(), "guard-map-")), "engagements.json")
  fs.writeFileSync(mappingPath, typeof job.mapping === "string" ? job.mapping : JSON.stringify(job.mapping))
}

const guard = createGuard({
  env: job.env ?? {},
  cwd: job.cwd ?? job.repoRoot,
  repoRoot: job.repoRoot,
  mappingPath,
})

const verdict = guard.evaluate(job.tool, job.args ?? {})

process.stdout.write(
  JSON.stringify({
    decision: verdict.decision,
    reason: verdict.reason,
    deniedPaths: verdict.candidates.map((entry) => entry.path),
    engagement: verdict.engagement,
    mappingError: verdict.mappingError,
  }),
)